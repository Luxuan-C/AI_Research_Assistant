"""Application-level adapters over the public ranking and profile contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Iterable, Mapping, Sequence

from academic_profiles import (
    AcademicProfile,
    AcademicProfileService,
    AcademicProfileSnapshot,
    ProfileCitation,
)
from ranking import (
    PUBLICATION,
    RESEARCHER,
    EntityRecord,
    EvidencePackBuilder,
    FusedCandidate,
    FusionService,
    QueryPlan,
    QueryPlanner,
    RankedEntity,
    RankingService,
    RetrievalRankingPipeline,
)
from ranking.supabase_retrieval import (
    SupabaseReadRepository,
    SupabaseRetrievalPort,
    SupabaseSchemaRelationshipGraph,
    academic_entity_from_row,
)


DEFAULT_API_ROW_LIMIT = 4_000
DEFAULT_CACHE_TTL_SECONDS = 60.0
FRONTEND_RESULT_LIMIT = 25
PIPELINE_RESULT_LIMIT = 50


def search_papers(
    pipeline: RetrievalRankingPipeline,
    plan: QueryPlan,
) -> list[dict[str, Any]]:
    """Retrieve and deterministically rank publication results once."""

    result = pipeline.retrieve_and_rank(plan)
    return [
        {
            "rank": ranked.rank,
            "paper_id": ranked.entity.entity_id,
            "title": ranked.entity.label,
            "eligible": ranked.eligible,
            "score": ranked.final_score,
            "score_breakdown": dict(ranked.score_breakdown),
            "evidence_ids": ranked.evidence_ids,
            "source_urls": ranked.entity.source_urls,
        }
        for ranked in result.ranked
        if ranked.entity.kind == PUBLICATION
    ]


def search_academic_profiles_with_ranking(
    pipeline: RetrievalRankingPipeline,
    plan: QueryPlan,
    snapshots: Sequence[AcademicProfileSnapshot],
) -> list[AcademicProfile]:
    """Render profiles for researchers returned by the ranking pipeline.

    Snapshots are caller-provided, bounded projections. This keeps profile
    rendering independent of storage while preserving ranked researcher order.
    """

    snapshots_by_id = {snapshot.academic.entity_id: snapshot for snapshot in snapshots}
    profile_service = AcademicProfileService()
    profiles: list[AcademicProfile] = []
    seen_ids: set[str] = set()
    for ranked in pipeline.retrieve_and_rank(plan).ranked:
        academic_id = ranked.entity.entity_id
        if ranked.entity.kind != RESEARCHER or academic_id in seen_ids:
            continue
        snapshot = snapshots_by_id.get(academic_id)
        if snapshot is None:
            continue
        profiles.append(profile_service.get_profile(snapshot))
        seen_ids.add(academic_id)
    return profiles


def search_academic_profiles(
    snapshots: Sequence[AcademicProfileSnapshot],
    search_text: str,
) -> list[AcademicProfile]:
    """Find researcher profiles by user-facing name from bounded snapshots."""

    normalized_query = search_text.strip().casefold()
    if not normalized_query:
        return []

    profiles = AcademicProfileService()
    return [
        profiles.get_profile(snapshot)
        for snapshot in sorted(snapshots, key=lambda item: item.academic.entity_id)
        if any(
            normalized_query in value.casefold()
            for value in (snapshot.academic.label, *snapshot.searchable_text)
        )
    ]


@dataclass(frozen=True, slots=True)
class ResearcherResult:
    rank: int
    raw_id: str
    name: str
    position: str | None
    institution: str | None
    discipline: str | None
    research_interests: tuple[str, ...]
    source_urls: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ResearcherSearchResult:
    researchers: tuple[ResearcherResult, ...]
    truncated: bool


@dataclass(frozen=True, slots=True)
class PublicationResult:
    rank: int
    raw_id: str
    title: str
    publication_date: date | None
    doi: str | None
    source_url: str | None
    score: float
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PublicationSearchResult:
    publications: tuple[PublicationResult, ...]
    truncated: bool
    evidence_status: str


@dataclass(frozen=True, slots=True)
class HydratedAcademicProfile:
    raw_id: str
    name: str
    institution: str | None
    discipline: str | None
    position: str | None
    research_interests: tuple[str, ...]
    publications: tuple[PublicationResult, ...]
    official_profile_url: str | None
    summary_status: str
    summary_text: str
    citations: tuple[ProfileCitation, ...]
    truncated: bool


@dataclass(frozen=True, slots=True)
class DirectoryOptions:
    universities: tuple[str, ...]
    disciplines: tuple[str, ...]
    truncated: bool


class ResearchApplication:
    """Application boundary over one shared live retrieval/ranking stack."""

    def __init__(
        self,
        *,
        repository: SupabaseReadRepository,
        retrieval: SupabaseRetrievalPort,
        graph: SupabaseSchemaRelationshipGraph,
        pipeline: RetrievalRankingPipeline,
        planner: QueryPlanner | None = None,
    ) -> None:
        self.repository = repository
        self.retrieval = retrieval
        self.graph = graph
        self.pipeline = pipeline
        self.planner = planner or QueryPlanner()

    @classmethod
    def from_supabase_client(
        cls,
        client: Any,
        *,
        row_limit: int = DEFAULT_API_ROW_LIMIT,
        cache_ttl_seconds: float = DEFAULT_CACHE_TTL_SECONDS,
    ) -> "ResearchApplication":
        repository = SupabaseReadRepository(
            client,
            row_limit=row_limit,
            cache_ttl_seconds=cache_ttl_seconds,
        )
        retrieval = SupabaseRetrievalPort(repository)
        graph = SupabaseSchemaRelationshipGraph(repository)
        pipeline = RetrievalRankingPipeline(
            retrieval=retrieval,
            fusion=FusionService(),
            expansion=graph,
            ranking=RankingService(),
        )
        return cls(
            repository=repository,
            retrieval=retrieval,
            graph=graph,
            pipeline=pipeline,
        )

    def search_researchers(
        self,
        query: str,
        *,
        university: str = "",
        discipline: str = "",
    ) -> ResearcherSearchResult:
        filters: dict[str, object] = {}
        if university:
            filters["university"] = university
        if discipline:
            filters["discipline"] = discipline
        plan = self.planner.plan(
            query.strip() or "*",
            as_of=date.today(),
            filters=filters,
            target_kinds=(RESEARCHER,),
            limit=PIPELINE_RESULT_LIMIT,
            seed_limit=PIPELINE_RESULT_LIMIT,
        )
        normalized_query = query.strip().casefold()
        query_terms = tuple(normalized_query.split())
        field_rows = self.repository.rows("field")
        fields = {
            str(row["id"]): str(row["name"])
            for row in field_rows
            if row.get("id") is not None and row.get("name")
        }
        matching_field_ids = tuple(
            field_id
            for field_id, name in fields.items()
            if not query_terms or any(term in name.casefold() for term in query_terms)
        )
        academic_rows = self.repository.rows("academic")
        if matching_field_ids:
            matching_ids = set(matching_field_ids)
            candidate_rows = tuple(
                row
                for row in academic_rows
                if matching_ids.intersection(
                    str(field_id) for field_id in _array(row.get("field_ids"))
                )
            )
            all_ranked_researchers = tuple(
                sorted(
                    (
                        academic_entity_from_row(row)
                        for row in candidate_rows
                        if self._matches_directory_filters(row, filters)
                    ),
                    key=lambda entity: (entity.label.casefold(), entity.entity_id),
                )
            )
        else:
            candidate_rows = academic_rows
            scored_researchers = []
            for row in candidate_rows:
                if not self._matches_directory_filters(row, filters):
                    continue
                searchable_text = " ".join(
                    str(row.get(value) or "").casefold()
                    for value in ("name", "academic_position")
                )
                matched_terms = sum(term in searchable_text for term in query_terms)
                if query_terms and matched_terms == 0:
                    continue
                exact_query = bool(normalized_query and normalized_query in searchable_text)
                scored_researchers.append(
                    (
                        matched_terms + (len(query_terms) if exact_query else 0),
                        academic_entity_from_row(row),
                    )
                )
            all_ranked_researchers = tuple(
                entity
                for _score, entity in sorted(
                    scored_researchers,
                    key=lambda item: (-item[0], item[1].label.casefold(), item[1].entity_id),
                )
            )
        ranked_researchers = all_ranked_researchers[:FRONTEND_RESULT_LIMIT]
        rows = {
            str(row["id"]): row
            for row in candidate_rows
            if row.get("id") is not None
        }
        universities = self._related_names(rows.values(), "university_ids", "university")
        disciplines = self._related_names(rows.values(), "discipline_ids", "discipline")

        researchers: list[ResearcherResult] = []
        for display_rank, entity in enumerate(ranked_researchers, start=1):
            raw_id = _raw_entity_id(entity.entity_id, "academic")
            row = rows.get(raw_id, {})
            researchers.append(
                ResearcherResult(
                    rank=display_rank,
                    raw_id=raw_id,
                    name=entity.label,
                    position=_optional_text(row.get("academic_position")),
                    institution=_first_related_name(
                        row.get("university_ids"), universities
                    ),
                    discipline=_first_related_name(
                        row.get("discipline_ids"), disciplines
                    ),
                    research_interests=tuple(
                        fields[str(field_id)]
                        for field_id in _array(row.get("field_ids"))
                        if str(field_id) in fields
                    ),
                    source_urls=entity.source_urls,
                )
            )
        return ResearcherSearchResult(
            tuple(researchers),
            len(all_ranked_researchers) >= plan.seed_limit
            or len(all_ranked_researchers) > len(ranked_researchers)
            or self.repository.possibly_truncated(("academic",)),
        )

    def _matches_directory_filters(
        self,
        row: Mapping[str, Any],
        filters: Mapping[str, object],
    ) -> bool:
        if filters.get("university"):
            university_names = self._related_names((row,), "university_ids", "university")
            if not any(
                university_names.get(str(identifier)) == filters["university"]
                for identifier in _array(row.get("university_ids"))
            ):
                return False
        if filters.get("discipline"):
            discipline_names = self._related_names((row,), "discipline_ids", "discipline")
            if not any(
                discipline_names.get(str(identifier)) == filters["discipline"]
                for identifier in _array(row.get("discipline_ids"))
            ):
                return False
        return True

    def search_publications(self, question: str) -> PublicationSearchResult:
        plan = self.planner.plan(
            question,
            as_of=date.today(),
            target_kinds=(PUBLICATION,),
            limit=10,
            seed_limit=20,
        )
        result = self.pipeline.retrieve_and_rank(plan)
        ranked_publications = tuple(
            item for item in result.ranked if item.entity.kind == PUBLICATION
        )
        rows = self._rows_for_entities("research_paper", ranked_publications)
        publications = tuple(
            _publication_result(
                ranked,
                rows.get(
                    _raw_entity_id(
                        ranked.entity.entity_id,
                        "research_paper",
                    ),
                    {},
                ),
            )
            for ranked in ranked_publications
        )
        evidence = EvidencePackBuilder().build(result.ranked, {})
        return PublicationSearchResult(
            publications,
            result.expansion.truncated
            or len(result.fused) >= plan.seed_limit
            or len(result.fused) > len(ranked_publications)
            or self.repository.possibly_truncated(("research_paper",)),
            evidence.status,
        )

    def get_academic_profile(
        self,
        academic_id: str,
    ) -> HydratedAcademicProfile | None:
        raw_id = _raw_entity_id(academic_id, "academic")
        rows = self.repository.rows_by_ids("academic", (raw_id,))
        if not rows:
            return None
        row = rows[0]
        academic = academic_entity_from_row(row)
        plan = self.planner.plan(
            academic.label,
            as_of=date.today(),
            target_kinds=(PUBLICATION, RESEARCHER),
            limit=PIPELINE_RESULT_LIMIT,
            seed_limit=1,
        )
        seed = FusedCandidate(
            academic,
            rrf_score=1.0,
            raw_rrf_score=1.0,
            channel_ranks={"profile_lookup": 1},
            channel_raw_scores={"profile_lookup": 1.0},
        )
        expansion = self.graph.expand(plan, (seed,))
        snapshot = AcademicProfileSnapshot(
            academic=academic,
            entities=expansion.entities,
            relationships=expansion.relationships,
            validated_evidence_by_id={},
            searchable_text=(academic.label,),
        )
        profile = AcademicProfileService().get_profile(snapshot)
        publication_ids = tuple(
            _raw_entity_id(entity.entity_id, "research_paper")
            for entity in profile.publications
        )
        publication_rows = {
            str(item["id"]): item
            for item in self.repository.rows_by_ids(
                "research_paper", publication_ids
            )
            if item.get("id") is not None
        }
        publications = tuple(
            _publication_from_entity(
                index,
                entity,
                publication_rows.get(
                    _raw_entity_id(entity.entity_id, "research_paper"), {}
                ),
            )
            for index, entity in enumerate(profile.publications, start=1)
        )
        university_names = self._related_names((row,), "university_ids", "university")
        discipline_names = self._related_names((row,), "discipline_ids", "discipline")
        return HydratedAcademicProfile(
            raw_id=raw_id,
            name=academic.label,
            institution=_first_related_name(row.get("university_ids"), university_names),
            discipline=_first_related_name(row.get("discipline_ids"), discipline_names),
            position=_optional_text(row.get("academic_position")),
            research_interests=(),
            publications=publications,
            official_profile_url=_first_source_url(
                row.get("profile_url"), row.get("orcid_url")
            ),
            summary_status=profile.summary.status,
            summary_text=profile.summary.text,
            citations=profile.summary.citations,
            truncated=expansion.truncated,
        )

    def directory_options(self) -> DirectoryOptions:
        universities = tuple(
            sorted(
                {
                    str(row["name"])
                    for row in self.repository.rows("university")
                    if row.get("name")
                },
                key=str.casefold,
            )
        )
        disciplines = tuple(
            sorted(
                {
                    str(row["name"])
                    for row in self.repository.rows("discipline")
                    if row.get("name")
                },
                key=str.casefold,
            )
        )
        return DirectoryOptions(
            universities,
            disciplines,
            self.repository.possibly_truncated(("university", "discipline")),
        )

    def _rows_for_entities(
        self,
        table: str,
        ranked: Sequence[RankedEntity],
    ) -> dict[str, Mapping[str, Any]]:
        identifiers = tuple(
            _raw_entity_id(item.entity.entity_id, table) for item in ranked
        )
        return {
            str(row["id"]): row
            for row in self.repository.rows_by_ids(table, identifiers)
            if row.get("id") is not None
        }

    def _related_names(
        self,
        rows: Iterable[Mapping[str, Any]],
        field: str,
        table: str,
    ) -> Mapping[str, str]:
        identifiers = tuple(
            str(value)
            for row in rows
            for value in _array(row.get(field))
        )
        return {
            str(row["id"]): str(row["name"])
            for row in self.repository.rows_by_ids(table, identifiers)
            if row.get("id") is not None and row.get("name")
        }


def _raw_entity_id(entity_id: str, table: str) -> str:
    prefix = f"{table}:"
    return entity_id[len(prefix) :] if entity_id.startswith(prefix) else entity_id


def _array(value: object) -> tuple[object, ...]:
    if isinstance(value, (list, tuple, set, frozenset)):
        return tuple(item for item in value if item is not None)
    return ()


def _first_related_name(value: object, names: Mapping[str, str]) -> str | None:
    return next((names[str(item)] for item in _array(value) if str(item) in names), None)


def _optional_text(value: object) -> str | None:
    return str(value) if value is not None and str(value).strip() else None


def _first_source_url(*values: object) -> str | None:
    return next(
        (str(value) for value in values if isinstance(value, str) and value.strip()),
        None,
    )


def _publication_source_url(row: Mapping[str, Any], entity: EntityRecord) -> str | None:
    doi = _optional_text(row.get("doi"))
    return _first_source_url(
        row.get("open_access_url"),
        row.get("primary_url"),
        f"https://doi.org/{doi}" if doi else None,
        *entity.source_urls,
    )


def _publication_result(
    ranked: RankedEntity,
    row: Mapping[str, Any],
) -> PublicationResult:
    return _publication_from_entity(
        ranked.rank,
        ranked.entity,
        row,
        score=ranked.final_score,
        evidence_ids=ranked.evidence_ids,
    )


def _publication_from_entity(
    rank: int,
    entity: EntityRecord,
    row: Mapping[str, Any],
    *,
    score: float = 0.0,
    evidence_ids: tuple[str, ...] = (),
) -> PublicationResult:
    raw_id = _raw_entity_id(entity.entity_id, "research_paper")
    return PublicationResult(
        rank=rank,
        raw_id=raw_id,
        title=entity.label,
        publication_date=entity.publication_date,
        doi=_optional_text(row.get("doi")),
        source_url=_publication_source_url(row, entity),
        score=score,
        evidence_ids=evidence_ids,
    )
