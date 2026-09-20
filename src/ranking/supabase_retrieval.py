"""Read-only Supabase adapters for the deterministic retrieval pipeline.

The fixed database schema is treated as an external contract. This module uses
ordinary table reads only: it does not issue SQL, invoke RPCs, or assume vector
support. All retrieval channels returned here are genuinely independent; the
current production adapter exposes only ``lexical``.
"""

from __future__ import annotations

from collections import Counter, OrderedDict
from dataclasses import dataclass, replace
from datetime import date
from math import log, log1p
import os
import re
from threading import Event, RLock
from time import monotonic
from typing import Any, Callable, Mapping, Sequence

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
    "score": (
        "id",
        "paper_authority_score",
        "academic_authority_score",
        "journal_authenticity_score",
        "research_paper_id",
        "academic_ids",
        "journal_id",
    ),
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

RELATIONSHIP_FILTER_TABLES: Mapping[str, str] = {
    "university": "university",
    "university_id": "university",
    "institution": "university",
    "faculty": "faculty",
    "faculty_id": "faculty",
    "discipline": "discipline",
    "discipline_id": "discipline",
    "field": "field",
    "field_id": "field",
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
    """Thread-safe TTL cache for bounded, keyset-paginated Supabase reads.

    Cache coordination never holds the state lock during a network request.
    Equivalent full-table and ID misses share in-flight loads, while reads for
    unrelated tables remain independent.
    """

    def __init__(
        self,
        client: Any,
        *,
        row_limit: int = 1000,
        cache_ttl_seconds: float = 60.0,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if row_limit <= 0:
            raise ValueError("row_limit must be positive")
        if cache_ttl_seconds <= 0:
            raise ValueError("cache_ttl_seconds must be positive")
        self.client = client
        self.row_limit = row_limit
        self.cache_ttl_seconds = float(cache_ttl_seconds)
        self._clock = clock
        self._scans: dict[str, tuple[Mapping[str, Any], ...]] = {}
        self._rows_by_id: dict[str, dict[str, Mapping[str, Any]]] = {}
        self._queried_ids: dict[str, set[str]] = {}
        self._fully_scanned: set[str] = set()
        self._possibly_truncated: set[str] = set()
        self._fetched_at: dict[str, float] = {}
        self._table_revisions: dict[str, int] = {}
        self._scan_inflight: dict[str, Event] = {}
        self._id_inflight: dict[str, dict[str, Event]] = {}
        self._lock = RLock()

    def rows(self, table: str) -> tuple[Mapping[str, Any], ...]:
        if table not in TABLE_COLUMNS:
            raise ValueError(f"No read projection is defined for table {table!r}")
        while True:
            with self._lock:
                self._expire_if_needed_locked(table)
                cached = self._scans.get(table)
                if cached is not None:
                    return cached
                inflight = self._scan_inflight.get(table)
                if inflight is None:
                    inflight = Event()
                    self._scan_inflight[table] = inflight
                    owns_load = True
                else:
                    owns_load = False

            if not owns_load:
                inflight.wait()
                continue

            try:
                loaded = self._read_all_pages(table, limit=self.row_limit)
            except BaseException:
                with self._lock:
                    self._scan_inflight.pop(table, None)
                    inflight.set()
                raise

            with self._lock:
                self._clear_table_locked(table)
                if len(loaded) >= self.row_limit:
                    self._possibly_truncated.add(table)
                else:
                    self._fully_scanned.add(table)
                self._remember_locked(table, loaded)
                self._scans[table] = loaded
                self._record_fetch_locked(table)
                self._scan_inflight.pop(table, None)
                inflight.set()
                return loaded

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
        while True:
            with self._lock:
                self._expire_if_needed_locked(table)
                cache = self._rows_by_id.setdefault(table, {})
                queried = self._queried_ids.setdefault(table, set())
                if table in self._fully_scanned:
                    return tuple(cache[value] for value in requested if value in cache)

                scan_inflight = self._scan_inflight.get(table)
                if scan_inflight is not None:
                    owned_ids: tuple[str, ...] = ()
                    wait_events = (scan_inflight,)
                else:
                    missing = tuple(
                        value
                        for value in requested
                        if value not in cache and value not in queried
                    )
                    inflight_by_id = self._id_inflight.setdefault(table, {})
                    wait_events = tuple(
                        dict.fromkeys(
                            inflight_by_id[value]
                            for value in missing
                            if value in inflight_by_id
                        )
                    )
                    unclaimed = tuple(
                        value for value in missing if value not in inflight_by_id
                    )
                    available = max(
                        0,
                        self.row_limit - len(cache) - len(inflight_by_id),
                    )
                    owned_ids = unclaimed[:available]
                    if len(owned_ids) < len(unclaimed):
                        self._possibly_truncated.add(table)
                    for value in owned_ids:
                        inflight_by_id[value] = Event()

                if not owned_ids and not wait_events:
                    return tuple(cache[value] for value in requested if value in cache)

            if owned_ids:
                try:
                    loaded: list[Mapping[str, Any]] = []
                    for start in range(0, len(owned_ids), batch_size):
                        batch = owned_ids[start : start + batch_size]
                        loaded.extend(
                            self._read_all_pages(table, limit=len(batch), ids=batch)
                        )
                except BaseException:
                    self._finish_id_load(table, owned_ids)
                    raise

                with self._lock:
                    self._expire_if_needed_locked(table)
                    self._remember_locked(table, loaded)
                    self._queried_ids.setdefault(table, set()).update(owned_ids)
                    self._record_fetch_locked(table)
                self._finish_id_load(table, owned_ids)

            for event in wait_events:
                event.wait()

    def rows_matching_array_values(
        self,
        table: str,
        column: str,
        values: Sequence[str],
        *,
        limit: int | None = None,
    ) -> tuple[Mapping[str, Any], ...]:
        """Read rows whose PostgreSQL array column overlaps supplied values."""

        if table not in TABLE_COLUMNS:
            raise ValueError(f"No read projection is defined for table {table!r}")
        if column not in TABLE_COLUMNS[table]:
            raise ValueError(f"Column {column!r} is not readable on table {table!r}")
        identifiers = tuple(dict.fromkeys(str(value) for value in values if value))
        if not identifiers:
            return ()
        read_limit = self.row_limit if limit is None else min(limit, self.row_limit)
        if read_limit <= 0:
            return ()
        try:
            return self._read_all_pages(
                table,
                limit=read_limit,
                array_column=column,
                array_values=identifiers,
            )
        except SupabaseReadError:
            raise

    def rows_limited(
        self,
        table: str,
        limit: int,
    ) -> tuple[Mapping[str, Any], ...]:
        """Read the first bounded page without building a full-table cache."""

        if table not in TABLE_COLUMNS:
            raise ValueError(f"No read projection is defined for table {table!r}")
        if limit <= 0:
            return ()
        try:
            response = (
                self.client.table(table)
                .select(",".join(TABLE_COLUMNS[table]))
                .order("id")
                .limit(min(limit, self.row_limit))
                .execute()
            )
        except Exception as error:
            raise SupabaseReadError(table, safe_error_detail(error)) from error
        data = getattr(response, "data", None) or ()
        return tuple(row for row in data if isinstance(row, Mapping))

    def _read_all_pages(
        self,
        table: str,
        *,
        limit: int,
        ids: Sequence[str] | None = None,
        array_column: str | None = None,
        array_values: Sequence[str] = (),
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
                if array_column is not None:
                    query = query.overlaps(array_column, array_values)
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

    def _remember_locked(
        self,
        table: str,
        rows: Sequence[Mapping[str, Any]],
    ) -> None:
        cache = self._rows_by_id.setdefault(table, {})
        for row in rows:
            if row.get("id") is not None:
                cache[str(row["id"])] = row

    def possibly_truncated(self, tables: Sequence[str]) -> bool:
        with self._lock:
            for table in tables:
                self._expire_if_needed_locked(table)
            return any(table in self._possibly_truncated for table in tables)

    def revisions_for(self, tables: Sequence[str]) -> tuple[int, ...]:
        """Return cache revisions suitable for derived-index invalidation."""

        with self._lock:
            for table in tables:
                self._expire_if_needed_locked(table)
            return tuple(self._table_revisions.get(table, 0) for table in tables)

    def invalidate(self, table: str | None = None) -> None:
        """Explicitly invalidate one table or every cached projection."""

        with self._lock:
            tables = (table,) if table is not None else tuple(TABLE_COLUMNS)
            for current in tables:
                if current not in TABLE_COLUMNS:
                    raise ValueError(
                        f"No read projection is defined for table {current!r}"
                    )
                self._clear_table_locked(current)
                self._table_revisions[current] = (
                    self._table_revisions.get(current, 0) + 1
                )

    def _expire_if_needed_locked(self, table: str) -> None:
        fetched_at = self._fetched_at.get(table)
        if fetched_at is None:
            return
        if self._clock() - fetched_at < self.cache_ttl_seconds:
            return
        self._clear_table_locked(table)
        self._table_revisions[table] = self._table_revisions.get(table, 0) + 1

    def _clear_table_locked(self, table: str) -> None:
        self._scans.pop(table, None)
        self._rows_by_id.pop(table, None)
        self._queried_ids.pop(table, None)
        self._fully_scanned.discard(table)
        self._possibly_truncated.discard(table)
        self._fetched_at.pop(table, None)

    def _record_fetch_locked(self, table: str) -> None:
        self._fetched_at[table] = self._clock()
        self._table_revisions[table] = self._table_revisions.get(table, 0) + 1

    def _finish_id_load(self, table: str, identifiers: Sequence[str]) -> None:
        with self._lock:
            inflight_by_id = self._id_inflight.get(table, {})
            for value in identifiers:
                event = inflight_by_id.pop(value, None)
                if event is not None:
                    event.set()
            if not inflight_by_id:
                self._id_inflight.pop(table, None)


@dataclass(frozen=True, slots=True)
class _CorpusDocument:
    entity: EntityRecord
    row: Mapping[str, Any]
    text: str
    tokens: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _LexicalCorpus:
    documents: tuple[_CorpusDocument, ...]
    document_frequency: Mapping[str, int]
    average_length: float


class SupabaseRetrievalPort:
    """Production metadata/lexical retrieval over fixed Supabase tables.

    With no database-owned FTS or vector contract in this repository, this
    adapter performs deterministic BM25 over bounded, batched metadata reads.
    It intentionally returns no ``dense`` channel.
    """

    def __init__(
        self,
        repository: SupabaseReadRepository,
        *,
        corpus_cache_size: int = 4,
    ) -> None:
        if corpus_cache_size <= 0:
            raise ValueError("corpus_cache_size must be positive")
        self.repository = repository
        self.corpus_cache_size = corpus_cache_size
        self._corpora: OrderedDict[
            tuple[tuple[str, ...], tuple[int, ...]], _LexicalCorpus
        ] = OrderedDict()
        self._corpus_inflight: dict[
            tuple[tuple[str, ...], tuple[int, ...]], Event
        ] = {}
        self._corpus_lock = RLock()
        self.corpus_build_count = 0

    def retrieve(self, plan: QueryPlan) -> Mapping[str, Sequence[RetrievalHit]]:
        corpus = self._corpus(plan.target_kinds)
        relationship_filter_ids = self._resolve_relationship_filter_ids(plan.filters)
        filtered = tuple(
            document
            for document in corpus.documents
            if self._matches_filters(
                document.entity,
                document.row,
                plan.filters,
                relationship_filter_ids,
            )
        )
        if plan.text.strip() == "*":
            scored = tuple(
                (document.entity, 1.0)
                for document in sorted(
                    filtered,
                    key=lambda item: item.entity.entity_id,
                )
            )
        else:
            scored = _bm25_scores_from_documents(
                plan.text,
                filtered,
                document_frequency=(
                    corpus.document_frequency if not plan.filters else None
                ),
                average_length=(corpus.average_length if not plan.filters else None),
            )
            scored_ids = {entity.entity_id for entity, _score in scored}
            normalized_query = plan.text.casefold().strip()
            if normalized_query:
                scored = (
                    *scored,
                    *(
                        (document.entity, 1.0)
                        for document in filtered
                        if document.entity.entity_id not in scored_ids
                        and normalized_query in document.text.casefold()
                    ),
                )
        ordered = sorted(scored, key=lambda item: (-item[1], item[0].entity_id))
        hits = tuple(
            RetrievalHit(entity, "lexical", rank, score)
            for rank, (entity, score) in enumerate(
                ordered[: plan.seed_limit], start=1
            )
        )
        return {"lexical": hits}

    def _corpus(self, target_kinds: Sequence[str]) -> _LexicalCorpus:
        normalized_kinds = tuple(dict.fromkeys(target_kinds))
        tables: list[str] = []
        rows_by_table: dict[str, tuple[Mapping[str, Any], ...]] = {}
        if PUBLICATION in normalized_kinds:
            tables.append("research_paper")
            rows_by_table["research_paper"] = self.repository.rows(
                "research_paper"
            )
        if RESEARCHER in normalized_kinds:
            tables.append("academic")
            rows_by_table["academic"] = self.repository.rows("academic")
        score_rows = self.repository.rows("score") if PUBLICATION in normalized_kinds else ()
        paper_scores_by_id = _score_by_paper(score_rows)
        academic_authority_by_id = _score_by_academic(score_rows)

        cache_key = (
            normalized_kinds,
            self.repository.revisions_for(tables + ["score"]),
        )
        while True:
            with self._corpus_lock:
                cached = self._corpora.get(cache_key)
                if cached is not None:
                    self._corpora.move_to_end(cache_key)
                    return cached
                inflight = self._corpus_inflight.get(cache_key)
                if inflight is None:
                    inflight = Event()
                    self._corpus_inflight[cache_key] = inflight
                    owns_build = True
                else:
                    owns_build = False

            if owns_build:
                break
            inflight.wait()

        try:
            documents: list[_CorpusDocument] = []
            for row in rows_by_table.get("research_paper", ()):
                if row.get("id") is None:
                    continue
                text = _paper_text(row)
                row_id = str(row["id"])
                documents.append(
                    _CorpusDocument(
                        _paper_entity(row, paper_scores_by_id.get(row_id)),
                        row,
                        text,
                        _tokens(text),
                    )
                )
            for row in rows_by_table.get("academic", ()):
                if row.get("id") is None:
                    continue
                text = _academic_text(row)
                row_id = str(row["id"])
                documents.append(
                    _CorpusDocument(
                        _academic_entity(row, academic_authority_by_id.get(row_id)),
                        row,
                        text,
                        _tokens(text),
                    )
                )
            frozen_documents = tuple(documents)
            document_frequency = Counter(
                term for document in frozen_documents for term in set(document.tokens)
            )
            average_length = (
                sum(len(document.tokens) for document in frozen_documents)
                / len(frozen_documents)
                if frozen_documents
                else 1.0
            ) or 1.0
            corpus = _LexicalCorpus(
                frozen_documents,
                dict(document_frequency),
                average_length,
            )
        except BaseException:
            with self._corpus_lock:
                self._corpus_inflight.pop(cache_key, None)
                inflight.set()
            raise

        with self._corpus_lock:
            self._corpora[cache_key] = corpus
            self.corpus_build_count += 1
            while len(self._corpora) > self.corpus_cache_size:
                self._corpora.popitem(last=False)
            self._corpus_inflight.pop(cache_key, None)
            inflight.set()
            return corpus

    def _matches_filters(
        self,
        entity: EntityRecord,
        row: Mapping[str, Any],
        filters: Mapping[str, object],
        relationship_filter_ids: Mapping[str, frozenset[str]],
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
                if not _matches_relationship_ids(
                    row.get("university_ids"),
                    relationship_filter_ids[normalized],
                ):
                    return False
            elif normalized in {"faculty", "faculty_id"}:
                if not _matches_relationship_ids(
                    row.get("faculty_ids"),
                    relationship_filter_ids[normalized],
                ):
                    return False
            elif normalized in {"discipline", "discipline_id"}:
                if not _matches_relationship_ids(
                    row.get("discipline_ids"),
                    relationship_filter_ids[normalized],
                ):
                    return False
            elif normalized in {"field", "field_id"}:
                if not _matches_relationship_ids(
                    row.get("field_ids"),
                    relationship_filter_ids[normalized],
                ):
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

    def _resolve_relationship_filter_ids(
        self,
        filters: Mapping[str, object],
    ) -> Mapping[str, frozenset[str]]:
        resolved: dict[str, frozenset[str]] = {}
        for key, expected in sorted(filters.items()):
            normalized = key.lower()
            table = RELATIONSHIP_FILTER_TABLES.get(normalized)
            if table is None:
                continue
            expected_text = str(expected)
            matching_ids = {
                expected_text,
                *(
                    str(row["id"])
                    for row in self.repository.rows(table)
                    if row.get("id") is not None
                    and str(row.get("name") or "").casefold()
                    == expected_text.casefold()
                ),
            }
            resolved[normalized] = frozenset(matching_ids)
        return resolved


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
        scheduled: set[tuple[str, str]] = set()
        for seed in seeds[: min(plan.seed_limit, self.budget.max_entities)]:
            table, raw_id = _split_entity_id(seed.entity.entity_id)
            if table in {"academic", "research_paper"}:
                frontier[table].add(raw_id)
                scheduled.add((table, raw_id))

        prefetch_truncated = False
        prefetched_relationships = 0
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
                            target = (target_table, target_id)
                            if target in scheduled:
                                continue
                            if prefetched_relationships >= self.budget.max_relationships:
                                prefetch_truncated = True
                                continue
                            if len(scheduled) >= self.budget.max_entities:
                                prefetch_truncated = True
                                continue
                            scheduled.add(target)
                            next_frontier[target_table].add(target_id)
                            prefetched_relationships += 1
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


def _matches_relationship_ids(
    values: object,
    accepted_ids: frozenset[str],
) -> bool:
    return any(str(value) in accepted_ids for value in _array(values))


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
    documents = tuple(
        _CorpusDocument(entity, {}, text, _tokens(text))
        for entity, text in records
    )
    return _bm25_scores_from_documents(query, documents)


def _bm25_scores_from_documents(
    query: str,
    documents: Sequence[_CorpusDocument],
    *,
    document_frequency: Mapping[str, int] | None = None,
    average_length: float | None = None,
) -> tuple[tuple[EntityRecord, float], ...]:
    query_terms = _tokens(query)
    if not query_terms or not documents:
        return ()

    resolved_frequency = document_frequency or Counter(
        term for document in documents for term in set(document.tokens)
    )
    resolved_average_length = average_length
    if resolved_average_length is None:
        resolved_average_length = sum(
            len(document.tokens) for document in documents
        ) / len(documents)
    resolved_average_length = resolved_average_length or 1.0
    k1, b = 1.2, 0.75
    output: list[tuple[EntityRecord, float]] = []
    for document in documents:
        frequencies = Counter(document.tokens)
        score = 0.0
        for term in query_terms:
            frequency = frequencies.get(term, 0)
            if not frequency:
                continue
            frequency_in_documents = resolved_frequency[term]
            inverse_document_frequency = log(
                1.0 + (len(documents) - frequency_in_documents + 0.5) / (frequency_in_documents + 0.5)
            )
            denominator = frequency + k1 * (
                1.0
                - b
                + b * len(document.tokens) / resolved_average_length
            )
            score += inverse_document_frequency * frequency * (k1 + 1.0) / denominator
        if score > 0.0:
            output.append((document.entity, score))
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


def _score_value(row: Mapping[str, Any] | None, field: str) -> float | None:
    if row is None:
        return None
    value = row.get(field)
    if value in (None, "", "null"):
        return None
    try:
        score = float(value)
    except (TypeError, ValueError):
        return None
    if not 0.0 <= score <= 1.0:
        score = max(0.0, min(1.0, score))
    return score


def _normalize_citation_score(value: object) -> float:
    if value in (None, ""):
        return 0.0
    try:
        raw = float(value)
    except (TypeError, ValueError):
        return 0.0
    if raw <= 0.0:
        return 0.0
    truncated = max(1.0, min(1_000_000.0, raw))
    return min(1.0, log1p(raw) / log1p(truncated))


def _aggregate_score(values: Sequence[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _score_by_paper(
    rows: Sequence[Mapping[str, Any]],
) -> Mapping[str, Mapping[str, float]]:
    totals: dict[str, dict[str, list[float]]] = {}
    for row in rows:
        paper_id = row.get("research_paper_id")
        if paper_id is None:
            continue
        fields = totals.setdefault(str(paper_id), {})
        for field in (
            "paper_authority_score",
            "academic_authority_score",
            "journal_authenticity_score",
        ):
            score = _score_value(row, field)
            if score is not None:
                fields.setdefault(field, []).append(score)
    return {
        paper_id: {
            field: aggregate
            for field, values in fields.items()
            if (aggregate := _aggregate_score(values)) is not None
        }
        for paper_id, fields in totals.items()
    }


def _score_by_academic(rows: Sequence[Mapping[str, Any]]) -> Mapping[str, float]:
    totals: dict[str, list[float]] = {}
    for row in rows:
        authority = _score_value(row, "academic_authority_score")
        if authority is None:
            continue
        for academic_id in _array(row.get("academic_ids")):
            totals.setdefault(str(academic_id), []).append(authority)
    return {academic_id: sum(scores) / len(scores) for academic_id, scores in totals.items()}


def _source_urls(*values: object) -> tuple[str, ...]:
    return tuple(dict.fromkeys(str(value) for value in values if isinstance(value, str) and value.strip()))


def _paper_entity(
    row: Mapping[str, Any],
    score_row: Mapping[str, Any] | None = None,
) -> EntityRecord:
    doi = row.get("doi")
    doi_url = f"https://doi.org/{doi}" if isinstance(doi, str) and doi.strip() else None
    paper_authority_score = _score_value(score_row, "paper_authority_score")
    journal_authenticity_score = _score_value(score_row, "journal_authenticity_score")
    return EntityRecord(
        entity_id=_entity_id("research_paper", row["id"]),
        kind=PUBLICATION,
        label=str(row.get("name") or row["id"]),
        publication_date=_parse_date(row.get("publication_date")),
        citation_score=_normalize_citation_score(row.get("incoming_citation_count")),
        paper_authority_score=paper_authority_score,
        paper_authority_reproducible=paper_authority_score is not None,
        journal_authenticity_score=journal_authenticity_score,
        journal_authenticity_reproducible=journal_authenticity_score is not None,
        academic_authority_score=_score_value(score_row, "academic_authority_score"),
        academic_authority_provenance="score_table" if score_row is not None else None,
        source_urls=_source_urls(row.get("primary_url"), row.get("open_access_url"), doi_url),
    )


def _academic_entity(
    row: Mapping[str, Any],
    authority_score: float | None = None,
) -> EntityRecord:
    return EntityRecord(
        entity_id=_entity_id("academic", row["id"]),
        kind=RESEARCHER,
        label=str(row.get("name") or row["id"]),
        academic_authority_score=authority_score,
        academic_authority_provenance="score_table" if authority_score is not None else None,
        source_urls=_source_urls(row.get("profile_url"), row.get("orcid_url")),
    )


def academic_entity_from_row(row: Mapping[str, Any]) -> EntityRecord:
    """Project one fixed-schema academic row through the production adapter."""

    return _academic_entity(row)


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
