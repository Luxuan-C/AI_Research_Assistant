"""Read-only Supabase adapters for the deterministic retrieval pipeline.

The fixed database schema is treated as an external contract. This module uses
ordinary table reads only: it does not issue SQL, invoke RPCs, or assume vector
support. All retrieval channels returned here are genuinely independent; the
current production adapter exposes only ``lexical``.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import replace
from datetime import date
from math import log
import os
import re
from typing import Any, Mapping, Sequence

from .paper_ranking import (
    PUBLICATION,
    RESEARCHER,
    EntityRecord,
    ExpansionResult,
    FusedCandidate,
    GraphBudget,
    QueryPlan,
    RetrievalHit,
    SchemaRelationshipGraph,
    edges_from_fixed_schema_rows,
)


READABLE_TABLES = (
    "university",
    "faculty",
    "discipline",
    "field",
    "journal",
    "academic",
    "research_paper",
    "score",
)

TABLE_COLUMNS: Mapping[str, tuple[str, ...]] = {
    "university": ("id", "name", "country_code", "ror_url", "type"),
    "faculty": ("id", "name"),
    "discipline": ("id", "name", "faculty_id"),
    "field": ("id", "name", "discipline_id"),
    "journal": ("id", "name", "type", "issn"),
    "academic": (
        "id",
        "name",
        "academic_position",
        "profile_url",
        "orcid_url",
        "research_paper_ids",
        "university_ids",
        "discipline_ids",
        "field_ids",
    ),
    "research_paper": (
        "id",
        "name",
        "publication_date",
        "doi",
        "is_open_access",
        "open_access_url",
        "primary_url",
        "publication_type",
        "incoming_citation_count",
        "keywords",
        "outgoing_citations",
        "journal_id",
        "university_ids",
        "faculty_ids",
        "academic_ids",
    ),
}

_TOKEN = re.compile(r"[a-z0-9]+")
SUPABASE_PAGE_SIZE = 1000

# Academic faculty membership is deliberately unsupported: the live academic
# schema has no ``faculty_ids`` field. These scopes prevent a filter from
# probing a field that does not exist for the current entity kind.
FILTER_TARGET_KINDS: Mapping[str, frozenset[str]] = {
    "university": frozenset((PUBLICATION, RESEARCHER)),
    "university_id": frozenset((PUBLICATION, RESEARCHER)),
    "institution": frozenset((PUBLICATION, RESEARCHER)),
    "faculty": frozenset((PUBLICATION,)),
    "faculty_id": frozenset((PUBLICATION,)),
    "discipline": frozenset((RESEARCHER,)),
    "discipline_id": frozenset((RESEARCHER,)),
    "field": frozenset((RESEARCHER,)),
    "field_id": frozenset((RESEARCHER,)),
    "is_open_access": frozenset((PUBLICATION,)),
    "publication_type": frozenset((PUBLICATION,)),
}


class SupabaseReadError(RuntimeError):
    """A read failed against one named table."""

    def __init__(self, table: str, detail: str) -> None:
        self.table = table
        self.detail = detail
        super().__init__(f"Read failed for table {table!r}: {detail}")


def safe_error_detail(error: BaseException) -> str:
    """Retain the server error while redacting configured credentials."""

    detail = str(error).strip() or type(error).__name__
    for variable in ("SUPABASE_URL", "SUPABASE_KEY"):
        value = os.getenv(variable, "")
        if value:
            detail = detail.replace(value, "<redacted>")
    detail = re.sub(
        r"(?i)(authorization|apikey)(\s*[:=]\s*)([^\s,;}]+)",
        r"\1\2<redacted>",
        detail,
    )
    return detail


def smoke_test_read_access(client: Any) -> tuple[str, ...]:
    """Verify minimal read access to every table in the external contract."""

    readable: list[str] = []
    for table in READABLE_TABLES:
        try:
            client.table(table).select("id").limit(1).execute()
        except Exception as error:  # SDK error types vary by version.
            raise SupabaseReadError(table, safe_error_detail(error)) from error
        readable.append(table)
    return tuple(readable)


class SupabaseReadRepository:
    """Read-through cache for bounded, keyset-paginated Supabase reads."""

    def __init__(self, client: Any, *, row_limit: int = 1000) -> None:
        if row_limit <= 0:
            raise ValueError("row_limit must be positive")
        self.client = client
        self.row_limit = row_limit
        self._scans: dict[str, tuple[Mapping[str, Any], ...]] = {}
        self._rows_by_id: dict[str, dict[str, Mapping[str, Any]]] = {}
        self._queried_ids: dict[str, set[str]] = {}
        self._fully_scanned: set[str] = set()
        self._possibly_truncated: set[str] = set()

    def rows(self, table: str) -> tuple[Mapping[str, Any], ...]:
        if table not in TABLE_COLUMNS:
            raise ValueError(f"No read projection is defined for table {table!r}")
        if table in self._scans:
            return self._scans[table]

        rows = self._read_all_pages(table, limit=self.row_limit)
        if len(rows) >= self.row_limit:
            self._possibly_truncated.add(table)
        else:
            self._fully_scanned.add(table)
        self._remember(table, rows)
        self._scans[table] = rows
        return rows

    def rows_by_ids(
        self,
        table: str,
        ids: Sequence[str],
        *,
        batch_size: int = 100,
    ) -> tuple[Mapping[str, Any], ...]:
        """Fetch missing IDs in deterministic batches, reusing prior scans."""

        if table not in TABLE_COLUMNS:
            raise ValueError(f"No read projection is defined for table {table!r}")
        if batch_size <= 0:
            raise ValueError("batch_size must be positive")
        requested = tuple(sorted({str(value) for value in ids if value}))
        cache = self._rows_by_id.setdefault(table, {})
        queried = self._queried_ids.setdefault(table, set())
        if table not in self._fully_scanned:
            missing = [value for value in requested if value not in cache and value not in queried]
            available = max(0, self.row_limit - len(cache))
            bounded_missing = missing[:available]
            if len(bounded_missing) < len(missing):
                self._possibly_truncated.add(table)
            for start in range(0, len(bounded_missing), batch_size):
                batch = bounded_missing[start : start + batch_size]
                rows = self._read_all_pages(table, limit=len(batch), ids=batch)
                self._remember(table, rows)
                queried.update(batch)
        return tuple(cache[value] for value in requested if value in cache)

    def _read_all_pages(
        self,
        table: str,
        *,
        limit: int,
        ids: Sequence[str] | None = None,
    ) -> tuple[Mapping[str, Any], ...]:
        """Read at most ``limit`` rows through stable, non-overlapping ID pages."""

        rows: list[Mapping[str, Any]] = []
        seen_ids: set[str] = set()
        last_id: str | None = None
        while len(rows) < limit:
            page_limit = min(SUPABASE_PAGE_SIZE, limit - len(rows))
            try:
                query = (
                    self.client.table(table)
                    .select(",".join(TABLE_COLUMNS[table]))
                    .order("id")
                    .limit(page_limit)
                )
                if ids is not None:
                    query = query.in_("id", ids)
                if last_id is not None:
                    query = query.gt("id", last_id)
                response = query.execute()
            except Exception as error:
                raise SupabaseReadError(table, safe_error_detail(error)) from error

            data = getattr(response, "data", None)
            if data is None:
                data = ()
            if not isinstance(data, (list, tuple)):
                raise SupabaseReadError(table, "Supabase response data was not a row sequence")
            page = tuple(row for row in data if isinstance(row, Mapping))
            if not page:
                break

            page_last_id = str(page[-1].get("id") or "")
            if not page_last_id or (last_id is not None and page_last_id <= last_id):
                raise SupabaseReadError(table, "Supabase page was not strictly ordered by id")
            for row in page:
                row_id = str(row.get("id") or "")
                if row_id and row_id not in seen_ids:
                    seen_ids.add(row_id)
                    rows.append(row)
            last_id = page_last_id
        return tuple(rows)

    def _remember(self, table: str, rows: Sequence[Mapping[str, Any]]) -> None:
        cache = self._rows_by_id.setdefault(table, {})
        for row in rows:
            if row.get("id") is not None:
                cache[str(row["id"])] = row

    def possibly_truncated(self, tables: Sequence[str]) -> bool:
        return any(table in self._possibly_truncated for table in tables)


class SupabaseRetrievalPort:
    """Production metadata/lexical retrieval over fixed Supabase tables.

    With no database-owned FTS or vector contract in this repository, this
    adapter performs deterministic BM25 over bounded, batched metadata reads.
    It intentionally returns no ``dense`` channel.
    """

    def __init__(self, repository: SupabaseReadRepository) -> None:
        self.repository = repository

    def retrieve(self, plan: QueryPlan) -> Mapping[str, Sequence[RetrievalHit]]:
        records: list[tuple[EntityRecord, Mapping[str, Any], str]] = []
        if PUBLICATION in plan.target_kinds:
            records.extend(
                (_paper_entity(row), row, _paper_text(row))
                for row in self.repository.rows("research_paper")
                if row.get("id") is not None
            )
        if RESEARCHER in plan.target_kinds:
            records.extend(
                (_academic_entity(row), row, _academic_text(row))
                for row in self.repository.rows("academic")
                if row.get("id") is not None
            )

        filtered = [
            (entity, text)
            for entity, row, text in records
            if self._matches_filters(entity, row, plan.filters)
        ]
        scored = _bm25_scores(plan.text, filtered)
        ordered = sorted(scored, key=lambda item: (-item[1], item[0].entity_id))
        hits = tuple(
            RetrievalHit(entity, "lexical", rank, score)
            for rank, (entity, score) in enumerate(ordered[: plan.seed_limit], start=1)
        )
        return {"lexical": hits}

    def _matches_filters(
        self,
        entity: EntityRecord,
        row: Mapping[str, Any],
        filters: Mapping[str, object],
    ) -> bool:
        for key, expected in sorted(filters.items()):
            normalized = key.lower()
            if normalized in {"kind", "entity_type"}:
                if entity.kind != str(expected):
                    return False
            elif entity.kind not in FILTER_TARGET_KINDS.get(
                normalized,
                frozenset((PUBLICATION, RESEARCHER)),
            ):
                return False
            elif normalized in {"university", "university_id", "institution"}:
                if not self._matches_relationship("university", row.get("university_ids"), expected):
                    return False
            elif normalized in {"faculty", "faculty_id"}:
                if not self._matches_relationship("faculty", row.get("faculty_ids"), expected):
                    return False
            elif normalized in {"discipline", "discipline_id"}:
                if not self._matches_relationship("discipline", row.get("discipline_ids"), expected):
                    return False
            elif normalized in {"field", "field_id"}:
                if not self._matches_relationship("field", row.get("field_ids"), expected):
                    return False
            elif normalized == "is_open_access":
                if bool(row.get("is_open_access")) is not bool(expected):
                    return False
            elif normalized == "publication_type":
                if str(row.get("publication_type") or "").casefold() != str(expected).casefold():
                    return False
            elif row.get(key) != expected:
                return False
        return True

    def _matches_relationship(self, table: str, ids: object, expected: object) -> bool:
        relationship_ids = {str(value) for value in _array(ids)}
        expected_text = str(expected)
        if expected_text in relationship_ids:
            return True
        matching_ids = {
            str(row["id"])
            for row in self.repository.rows(table)
            if row.get("id") is not None
            and str(row.get("name") or "").casefold() == expected_text.casefold()
        }
        return bool(relationship_ids & matching_ids)


class SupabaseSchemaRelationshipGraph:
    """Build and execute a seed-driven, bounded typed relationship graph."""

    GRAPH_TABLES = (
        "university",
        "faculty",
        "discipline",
        "field",
        "journal",
        "academic",
        "research_paper",
    )

    def __init__(
        self,
        repository: SupabaseReadRepository,
        *,
        budget: GraphBudget | None = None,
    ) -> None:
        self.repository = repository
        self.budget = budget or GraphBudget()

    def expand(
        self,
        plan: QueryPlan,
        seeds: Sequence[FusedCandidate],
    ) -> ExpansionResult:
        loaded: dict[str, dict[str, Mapping[str, Any]]] = {
            table: {} for table in self.GRAPH_TABLES
        }
        projected: dict[tuple[str, str], Mapping[str, Any]] = {}
        frontier: dict[str, set[str]] = {table: set() for table in self.GRAPH_TABLES}
        for seed in seeds[: plan.seed_limit]:
            table, raw_id = _split_entity_id(seed.entity.entity_id)
            if table in {"academic", "research_paper"}:
                frontier[table].add(raw_id)

        prefetch_truncated = False
        for depth in range(self.budget.max_hops + 1):
            next_frontier: dict[str, set[str]] = {
                table: set() for table in self.GRAPH_TABLES
            }
            for table in self.GRAPH_TABLES:
                identifiers = sorted(frontier[table])
                if not identifiers:
                    continue
                for row in self.repository.rows_by_ids(table, identifiers):
                    raw_id = str(row["id"])
                    loaded[table][raw_id] = row
                    bounded_row, references, was_truncated = _bounded_relationships(
                        table,
                        row,
                        self.budget.max_neighbors_per_node,
                    )
                    projected[(table, raw_id)] = bounded_row
                    prefetch_truncated = prefetch_truncated or was_truncated
                    if depth < self.budget.max_hops:
                        for target_table, target_id in references:
                            if target_id not in loaded[target_table]:
                                next_frontier[target_table].add(target_id)
            frontier = next_frontier

        entities: list[EntityRecord] = []
        entities.extend(_academic_entity(row) for row in loaded["academic"].values())
        entities.extend(_paper_entity(row) for row in loaded["research_paper"].values())
        for table in ("university", "faculty", "discipline", "field", "journal"):
            entities.extend(
                _metadata_entity(table, row)
                for row in loaded[table].values()
                if row.get("name")
            )

        academic_rows = tuple(
            _namespace_academic_row(row)
            for (table, _raw_id), row in sorted(projected.items())
            if table == "academic"
        )
        paper_rows = tuple(
            _namespace_paper_row(row)
            for (table, _raw_id), row in sorted(projected.items())
            if table == "research_paper"
        )
        graph = SchemaRelationshipGraph(
            entities,
            edges_from_fixed_schema_rows(
                academics=academic_rows,
                research_papers=paper_rows,
            ),
            budget=self.budget,
        )
        result = graph.expand(plan, seeds)
        if prefetch_truncated or self.repository.possibly_truncated(("academic", "research_paper")):
            return replace(result, truncated=True)
        return result


def _tokens(value: object) -> tuple[str, ...]:
    return tuple(_TOKEN.findall(str(value or "").casefold()))


def _array(value: object) -> tuple[object, ...]:
    if isinstance(value, (list, tuple, set, frozenset)):
        return tuple(item for item in value if item is not None)
    return ()


def _flatten_text(*values: object) -> str:
    parts: list[str] = []
    for value in values:
        if isinstance(value, (list, tuple, set, frozenset)):
            parts.extend(str(item) for item in value if item is not None)
        elif value is not None:
            parts.append(str(value))
    return " ".join(parts)


def _paper_text(row: Mapping[str, Any]) -> str:
    return _flatten_text(
        row.get("name"),
        row.get("keywords"),
        row.get("doi"),
        row.get("publication_type"),
    )


def _academic_text(row: Mapping[str, Any]) -> str:
    return _flatten_text(
        row.get("name"),
        row.get("academic_position"),
    )


def _bm25_scores(
    query: str,
    records: Sequence[tuple[EntityRecord, str]],
) -> tuple[tuple[EntityRecord, float], ...]:
    query_terms = _tokens(query)
    documents = tuple((_tokens(text), entity) for entity, text in records)
    if not query_terms or not documents:
        return ()

    document_frequency = Counter(
        term for terms, _entity in documents for term in set(terms)
    )
    average_length = sum(len(terms) for terms, _entity in documents) / len(documents)
    average_length = average_length or 1.0
    k1, b = 1.2, 0.75
    output: list[tuple[EntityRecord, float]] = []
    for terms, entity in documents:
        frequencies = Counter(terms)
        score = 0.0
        for term in query_terms:
            frequency = frequencies.get(term, 0)
            if not frequency:
                continue
            frequency_in_documents = document_frequency[term]
            inverse_document_frequency = log(
                1.0 + (len(documents) - frequency_in_documents + 0.5) / (frequency_in_documents + 0.5)
            )
            denominator = frequency + k1 * (1.0 - b + b * len(terms) / average_length)
            score += inverse_document_frequency * frequency * (k1 + 1.0) / denominator
        if score > 0.0:
            output.append((entity, score))
    return tuple(output)


def _entity_id(table: str, value: object) -> str:
    return f"{table}:{value}"


def _split_entity_id(entity_id: str) -> tuple[str, str]:
    table, separator, raw_id = entity_id.partition(":")
    return (table, raw_id) if separator else ("", entity_id)


def _bounded_relationships(
    table: str,
    row: Mapping[str, Any],
    maximum: int,
) -> tuple[Mapping[str, Any], tuple[tuple[str, str], ...], bool]:
    """Prune one row's outgoing relationship projection before fetching."""

    if table not in {"academic", "research_paper"}:
        return row, (), False

    raw_id = str(row["id"])
    entries: list[tuple[str, str, str, str]] = []

    def add(relation: str, field: str, target_table: str, values: object) -> None:
        for value in _array(values):
            target_id = str(value)
            if table == "research_paper" and relation == "AUTHORED":
                source = _entity_id("academic", target_id)
                target = _entity_id("research_paper", raw_id)
            else:
                source = _entity_id(table, raw_id)
                target = _entity_id(target_table, target_id)
            entries.append((f"{relation}:{source}:{target}", field, target_table, target_id))

    if table == "academic":
        add("AUTHORED", "research_paper_ids", "research_paper", row.get("research_paper_ids"))
        add("AFFILIATED_WITH", "university_ids", "university", row.get("university_ids"))
        add(
            "ACADEMIC_IN_DISCIPLINE",
            "discipline_ids",
            "discipline",
            row.get("discipline_ids"),
        )
        add("EXPERTISE_IN_FIELD", "field_ids", "field", row.get("field_ids"))
        fields = ("research_paper_ids", "university_ids", "discipline_ids", "field_ids")
    else:
        add("AUTHORED", "academic_ids", "academic", row.get("academic_ids"))
        add("CITES", "outgoing_citations", "research_paper", row.get("outgoing_citations"))
        add("PAPER_AT_UNIVERSITY", "university_ids", "university", row.get("university_ids"))
        add("PAPER_IN_FACULTY", "faculty_ids", "faculty", row.get("faculty_ids"))
        journal_id = row.get("journal_id")
        if journal_id is not None:
            add("PUBLISHED_IN", "journal_id", "journal", (journal_id,))
        fields = ("academic_ids", "outgoing_citations", "university_ids", "faculty_ids")

    unique = sorted({entry for entry in entries})
    selected = unique[:maximum]
    bounded = dict(row)
    for field in fields:
        bounded[field] = []
    if table == "research_paper":
        bounded["journal_id"] = None
    references: list[tuple[str, str]] = []
    for _edge_id, field, target_table, target_id in selected:
        if field == "journal_id":
            bounded[field] = target_id
        else:
            bounded[field].append(target_id)
        references.append((target_table, target_id))
    return bounded, tuple(references), len(unique) > len(selected)


def _parse_date(value: object) -> date | None:
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value:
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def _source_urls(*values: object) -> tuple[str, ...]:
    return tuple(dict.fromkeys(str(value) for value in values if isinstance(value, str) and value.strip()))


def _paper_entity(row: Mapping[str, Any]) -> EntityRecord:
    doi = row.get("doi")
    doi_url = f"https://doi.org/{doi}" if isinstance(doi, str) and doi.strip() else None
    return EntityRecord(
        entity_id=_entity_id("research_paper", row["id"]),
        kind=PUBLICATION,
        label=str(row.get("name") or row["id"]),
        publication_date=_parse_date(row.get("publication_date")),
        source_urls=_source_urls(row.get("primary_url"), row.get("open_access_url"), doi_url),
    )


def _academic_entity(row: Mapping[str, Any]) -> EntityRecord:
    return EntityRecord(
        entity_id=_entity_id("academic", row["id"]),
        kind=RESEARCHER,
        label=str(row.get("name") or row["id"]),
        source_urls=_source_urls(row.get("profile_url"), row.get("orcid_url")),
    )


def _metadata_entity(table: str, row: Mapping[str, Any]) -> EntityRecord:
    urls = _source_urls(row.get("ror_url")) if table == "university" else ()
    return EntityRecord(
        entity_id=_entity_id(table, row["id"]),
        kind=table,
        label=str(row["name"]),
        source_urls=urls,
    )


def _namespace_values(table: str, value: object) -> tuple[str, ...]:
    return tuple(_entity_id(table, item) for item in _array(value))


def _namespace_academic_row(row: Mapping[str, Any]) -> Mapping[str, object]:
    return {
        "id": _entity_id("academic", row["id"]),
        "research_paper_ids": _namespace_values("research_paper", row.get("research_paper_ids")),
        "university_ids": _namespace_values("university", row.get("university_ids")),
        "discipline_ids": _namespace_values("discipline", row.get("discipline_ids")),
        "field_ids": _namespace_values("field", row.get("field_ids")),
    }


def _namespace_paper_row(row: Mapping[str, Any]) -> Mapping[str, object]:
    journal_id = row.get("journal_id")
    return {
        "id": _entity_id("research_paper", row["id"]),
        "academic_ids": _namespace_values("academic", row.get("academic_ids")),
        "outgoing_citations": _namespace_values("research_paper", row.get("outgoing_citations")),
        "university_ids": _namespace_values("university", row.get("university_ids")),
        "faculty_ids": _namespace_values("faculty", row.get("faculty_ids")),
        "journal_id": _entity_id("journal", journal_id) if journal_id is not None else None,
    }
