"""Deterministic retrieval, graph-routing, and ranking contracts.

This module deliberately has no Supabase client, SQL, or LLM dependency. The
database schema is owned elsewhere, so adapters supply read-only rows through
the ports below. Lexical and optional dense results remain independent until
``FusionService`` applies RRF exactly once.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from math import isclose
from typing import Mapping, Protocol, Sequence


PUBLICATION = "publication"
RESEARCHER = "researcher"


def _unit(value: float, name: str) -> float:
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be in [0, 1], got {value}")
    return float(value)


@dataclass(frozen=True, slots=True)
class QueryPlan:
    """A deterministic, LLM-free interpretation of one user request."""

    text: str
    as_of: date
    target_kinds: tuple[str, ...] = (PUBLICATION, RESEARCHER)
    filters: Mapping[str, object] = field(default_factory=dict)
    profile: str = "GENERAL"
    limit: int = 10
    seed_limit: int = 10
    require_evidence: bool = False

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("Query text cannot be empty")
        if not self.target_kinds:
            raise ValueError("At least one target kind is required")
        if self.limit <= 0 or self.seed_limit <= 0:
            raise ValueError("limit and seed_limit must be positive")


class QueryPlanner:
    """Small deterministic planner; it never calls an LLM."""

    def plan(
        self,
        text: str,
        *,
        as_of: date,
        filters: Mapping[str, object] | None = None,
        target_kinds: tuple[str, ...] = (PUBLICATION, RESEARCHER),
        limit: int = 10,
        seed_limit: int = 10,
        require_evidence: bool = False,
    ) -> QueryPlan:
        lowered = text.lower()
        if any(word in lowered for word in ("latest", "recent", "newest", "current")):
            profile = "RECENT"
        elif any(word in lowered for word in ("foundational", "seminal", "classic")):
            profile = "FOUNDATIONAL"
        else:
            profile = "GENERAL"
        return QueryPlan(
            text=text,
            as_of=as_of,
            target_kinds=target_kinds,
            filters=filters or {},
            profile=profile,
            limit=limit,
            seed_limit=seed_limit,
            require_evidence=require_evidence,
        )


@dataclass(frozen=True, slots=True)
class EntityRecord:
    """Read-only projection of fields an adapter obtained from the fixed schema.

    ``citation_score`` must already be an offline, field/year/type-normalised
    feature. Raw ``incoming_citation_count`` is intentionally not ranked here.
    Academic authority fields are retained only to make their exclusion rules
    explicit.
    """

    entity_id: str
    kind: str
    label: str
    publication_date: date | None = None
    citation_score: float | None = None
    paper_authority_score: float | None = None
    paper_authority_reproducible: bool = False
    journal_authenticity_score: float | None = None
    journal_authenticity_reproducible: bool = False
    academic_authority_score: float | None = None
    academic_authority_provenance: str | None = None
    evidence_ids: tuple[str, ...] = ()
    source_urls: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.entity_id or not self.label:
            raise ValueError("Entity records need a stable ID and label")
        for name in (
            "citation_score",
            "paper_authority_score",
            "journal_authenticity_score",
            "academic_authority_score",
        ):
            value = getattr(self, name)
            if value is not None:
                _unit(value, name)


@dataclass(frozen=True, slots=True)
class RetrievalHit:
    """One item from exactly one upstream retrieval channel."""

    entity: EntityRecord
    channel: str
    rank: int
    raw_score: float

    def __post_init__(self) -> None:
        if not self.channel:
            raise ValueError("Retrieval channel cannot be empty")
        if self.rank < 1:
            raise ValueError("Retrieval rank must be positive")


class RetrievalPort(Protocol):
    """May expose lexical alone, or lexical and dense channels when available."""

    def retrieve(self, plan: QueryPlan) -> Mapping[str, Sequence[RetrievalHit]]: ...


@dataclass(frozen=True, slots=True)
class FusedCandidate:
    entity: EntityRecord
    rrf_score: float
    raw_rrf_score: float
    channel_ranks: Mapping[str, int]
    channel_raw_scores: Mapping[str, float]


class FusionService:
    """Fuse independent ranked lists once with reciprocal-rank fusion."""

    def __init__(self, *, rrf_k: int = 60) -> None:
        if rrf_k <= 0:
            raise ValueError("rrf_k must be positive")
        self.rrf_k = rrf_k

    def fuse(self, rankings: Mapping[str, Sequence[RetrievalHit]]) -> tuple[FusedCandidate, ...]:
        raw_scores: dict[str, float] = {}
        entities: dict[str, EntityRecord] = {}
        ranks: dict[str, dict[str, int]] = {}
        channel_scores: dict[str, dict[str, float]] = {}

        for channel, hits in rankings.items():
            if not channel:
                raise ValueError("Ranking map contains an empty channel name")
            seen: set[str] = set()
            for fallback_rank, hit in enumerate(hits, start=1):
                if hit.channel != channel:
                    raise ValueError(f"Hit channel {hit.channel!r} does not match {channel!r}")
                entity_id = hit.entity.entity_id
                if entity_id in seen:
                    continue
                seen.add(entity_id)
                rank = hit.rank if hit.rank > 0 else fallback_rank
                existing = entities.get(entity_id)
                if existing is not None and existing.kind != hit.entity.kind:
                    raise ValueError(f"Conflicting entity kind for {entity_id}")
                entities[entity_id] = hit.entity
                raw_scores[entity_id] = raw_scores.get(entity_id, 0.0) + 1.0 / (self.rrf_k + rank)
                ranks.setdefault(entity_id, {})[channel] = rank
                channel_scores.setdefault(entity_id, {})[channel] = hit.raw_score

        maximum = max(raw_scores.values(), default=0.0)
        output = tuple(
            FusedCandidate(
                entity=entities[entity_id],
                raw_rrf_score=raw_score,
                rrf_score=raw_score / maximum if maximum else 0.0,
                channel_ranks=dict(sorted(ranks[entity_id].items())),
                channel_raw_scores=dict(sorted(channel_scores[entity_id].items())),
            )
            for entity_id, raw_score in raw_scores.items()
        )
        return tuple(
            sorted(
                output,
                key=lambda item: (-item.rrf_score, -len(item.channel_ranks), item.entity.entity_id),
            )
        )


@dataclass(frozen=True, slots=True)
class GraphEdge:
    """A read-only relationship projected from the externally owned schema."""

    edge_id: str
    source_id: str
    target_id: str
    relation_type: str
    confidence: float = 1.0
    evidence_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.edge_id or not self.source_id or not self.target_id or not self.relation_type:
            raise ValueError("Graph edges need IDs and a relation type")
        _unit(self.confidence, "edge confidence")


@dataclass(frozen=True, slots=True)
class GraphBudget:
    max_hops: int = 2
    max_entities: int = 50
    max_relationships: int = 100
    max_neighbors_per_node: int = 20
    hop_decay: float = 0.80
    minimum_edge_confidence: float = 0.50
    allowed_relation_types: tuple[str, ...] = (
        "AUTHORED",
        "CITES",
        "AFFILIATED_WITH",
        "ACADEMIC_IN_DISCIPLINE",
        "EXPERTISE_IN_FIELD",
        "PAPER_AT_UNIVERSITY",
        "PAPER_IN_FACULTY",
        "PUBLISHED_IN",
    )

    def __post_init__(self) -> None:
        if self.max_hops < 0:
            raise ValueError("max_hops cannot be negative")
        if min(self.max_entities, self.max_relationships, self.max_neighbors_per_node) <= 0:
            raise ValueError("Graph budgets must be positive")
        _unit(self.hop_decay, "hop_decay")
        _unit(self.minimum_edge_confidence, "minimum_edge_confidence")


@dataclass(frozen=True, slots=True)
class GraphPath:
    seed_id: str
    target_id: str
    edge_ids: tuple[str, ...]
    relevance: float
    evidence_ids: tuple[str, ...] = ()

    @property
    def hops(self) -> int:
        return len(self.edge_ids)


@dataclass(frozen=True, slots=True)
class ExpansionResult:
    entities: Mapping[str, EntityRecord]
    paths: Mapping[str, GraphPath]
    truncated: bool
    relationships: tuple[GraphEdge, ...] = ()


class GraphExpansionPort(Protocol):
    def expand(
        self,
        plan: QueryPlan,
        seeds: Sequence[FusedCandidate],
    ) -> ExpansionResult: ...


class SchemaRelationshipGraph:
    """Bounded GraphRAG over read-only relationships from the fixed schema.

    A Supabase adapter fetches the needed rows and creates this projection. It
    does not require a graph table or a migration.
    """

    def __init__(
        self,
        entities: Sequence[EntityRecord],
        edges: Sequence[GraphEdge],
        *,
        budget: GraphBudget | None = None,
    ) -> None:
        self.entities = {entity.entity_id: entity for entity in entities}
        self.edges = {edge.edge_id: edge for edge in edges}
        self.budget = budget or GraphBudget()
        self._adjacency: dict[str, list[GraphEdge]] = {}
        for edge in self.edges.values():
            self._adjacency.setdefault(edge.source_id, []).append(edge)
            self._adjacency.setdefault(edge.target_id, []).append(edge)
        for values in self._adjacency.values():
            values.sort(key=lambda edge: edge.edge_id)

    def expand(self, plan: QueryPlan, seeds: Sequence[FusedCandidate]) -> ExpansionResult:
        selected = tuple(seeds[: min(plan.seed_limit, self.budget.max_entities)])
        truncated = len(seeds) > len(selected)
        entities = dict(self.entities)
        paths: dict[str, GraphPath] = {}
        selected_edge_ids: set[str] = set()
        frontier: list[GraphPath] = []

        for seed in selected:
            entity_id = seed.entity.entity_id
            entities[entity_id] = seed.entity
            path = GraphPath(entity_id, entity_id, (), seed.rrf_score, seed.entity.evidence_ids)
            paths[entity_id] = path
            frontier.append(path)

        while frontier:
            frontier.sort(key=lambda path: (-path.relevance, path.seed_id, path.target_id, path.edge_ids))
            current = frontier.pop(0)
            if current.hops >= self.budget.max_hops:
                continue
            neighbors = self._adjacency.get(current.target_id, ())
            accepted_neighbors = 0
            for edge in neighbors:
                if edge.relation_type not in self.budget.allowed_relation_types:
                    continue
                if edge.confidence < self.budget.minimum_edge_confidence:
                    continue
                accepted_neighbors += 1
                if accepted_neighbors > self.budget.max_neighbors_per_node:
                    truncated = True
                    break
                if edge.edge_id not in selected_edge_ids and len(selected_edge_ids) >= self.budget.max_relationships:
                    truncated = True
                    continue
                other_id = edge.target_id if edge.source_id == current.target_id else edge.source_id
                if other_id not in entities:
                    continue
                relevance = current.relevance * edge.confidence * self.budget.hop_decay
                candidate = GraphPath(
                    seed_id=current.seed_id,
                    target_id=other_id,
                    edge_ids=(*current.edge_ids, edge.edge_id),
                    relevance=relevance,
                    evidence_ids=tuple(dict.fromkeys((*current.evidence_ids, *edge.evidence_ids))),
                )
                previous = paths.get(other_id)
                if previous is None and len(paths) >= self.budget.max_entities:
                    truncated = True
                    continue
                if previous is not None and not _prefer_path(candidate, previous):
                    continue
                paths[other_id] = candidate
                selected_edge_ids.add(edge.edge_id)
                frontier.append(candidate)

        return ExpansionResult(
            entities={entity_id: entities[entity_id] for entity_id in paths},
            paths=paths,
            truncated=truncated,
            relationships=tuple(
                self.edges[edge_id] for edge_id in sorted(selected_edge_ids)
            ),
        )


def _prefer_path(candidate: GraphPath, previous: GraphPath) -> bool:
    return candidate.relevance > previous.relevance or (
        isclose(candidate.relevance, previous.relevance) and candidate.edge_ids < previous.edge_ids
    )


def edges_from_fixed_schema_rows(
    *,
    academics: Sequence[Mapping[str, object]] = (),
    research_papers: Sequence[Mapping[str, object]] = (),
) -> tuple[GraphEdge, ...]:
    """Project documented read-only array/FK relationships into graph edges.

    It uses only existing relationships: authorship, citations, affiliation,
    expertise, paper-university/faculty membership, and paper-journal links.
    """

    edges: dict[str, GraphEdge] = {}

    def add(relation: str, source: object, target: object) -> None:
        source_id, target_id = str(source), str(target)
        edge_id = f"{relation}:{source_id}:{target_id}"
        edges[edge_id] = GraphEdge(edge_id, source_id, target_id, relation)

    for academic in academics:
        academic_id = academic.get("id")
        if academic_id is None:
            continue
        for paper_id in _id_array(academic.get("research_paper_ids")):
            add("AUTHORED", academic_id, paper_id)
        for university_id in _id_array(academic.get("university_ids")):
            add("AFFILIATED_WITH", academic_id, university_id)
        for discipline_id in _id_array(academic.get("discipline_ids")):
            add("ACADEMIC_IN_DISCIPLINE", academic_id, discipline_id)
        for field_id in _id_array(academic.get("field_ids")):
            add("EXPERTISE_IN_FIELD", academic_id, field_id)

    for paper in research_papers:
        paper_id = paper.get("id")
        if paper_id is None:
            continue
        for academic_id in _id_array(paper.get("academic_ids")):
            add("AUTHORED", academic_id, paper_id)
        for cited_paper_id in _id_array(paper.get("outgoing_citations")):
            add("CITES", paper_id, cited_paper_id)
        for university_id in _id_array(paper.get("university_ids")):
            add("PAPER_AT_UNIVERSITY", paper_id, university_id)
        for faculty_id in _id_array(paper.get("faculty_ids")):
            add("PAPER_IN_FACULTY", paper_id, faculty_id)
        journal_id = paper.get("journal_id")
        if journal_id is not None:
            add("PUBLISHED_IN", paper_id, journal_id)

    return tuple(edges[key] for key in sorted(edges))


def _id_array(value: object) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple, set, frozenset)):
        return ()
    return tuple(str(item) for item in value if item is not None)


@dataclass(frozen=True, slots=True)
class RankingCandidate:
    entity: EntityRecord
    retrieval_score: float
    graph_score: float = 0.0
    graph_path: GraphPath | None = None
    evidence_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _unit(self.retrieval_score, "retrieval_score")
        _unit(self.graph_score, "graph_score")


def candidates_from_fusion_and_expansion(
    plan: QueryPlan,
    fused: Sequence[FusedCandidate],
    expansion: ExpansionResult,
) -> tuple[RankingCandidate, ...]:
    """Combine retrieval and graph output without fusing channels a second time."""

    by_id: dict[str, tuple[EntityRecord, float, GraphPath | None]] = {
        item.entity.entity_id: (item.entity, item.rrf_score, None) for item in fused
    }
    for entity_id, path in expansion.paths.items():
        entity = expansion.entities[entity_id]
        existing = by_id.get(entity_id)
        retrieval_score = existing[1] if existing is not None else 0.0
        by_id[entity_id] = (entity, retrieval_score, path)

    candidates: list[RankingCandidate] = []
    for entity_id, (entity, retrieval_score, path) in by_id.items():
        if entity.kind not in plan.target_kinds:
            continue
        graph_score = 0.0 if path is None or path.hops == 0 else path.relevance
        path_evidence = path.evidence_ids if path else ()
        evidence_ids = tuple(dict.fromkeys((*entity.evidence_ids, *path_evidence)))
        candidates.append(RankingCandidate(entity, retrieval_score, graph_score, path, evidence_ids))
    return tuple(sorted(candidates, key=lambda item: item.entity.entity_id))


@dataclass(frozen=True, slots=True)
class RankingProfile:
    name: str
    publication_retrieval_weight: float
    publication_graph_weight: float
    citation_weight: float
    recency_weight: float
    paper_authority_weight: float
    researcher_retrieval_weight: float
    researcher_graph_weight: float
    publication_half_life_years: float
    minimum_journal_authenticity: float | None = 0.50

    def __post_init__(self) -> None:
        publication_total = (
            self.publication_retrieval_weight
            + self.publication_graph_weight
            + self.citation_weight
            + self.recency_weight
            + self.paper_authority_weight
        )
        researcher_total = self.researcher_retrieval_weight + self.researcher_graph_weight
        if not isclose(publication_total, 1.0) or not isclose(researcher_total, 1.0):
            raise ValueError("Ranking profile weights must each sum to one")
        if self.publication_half_life_years <= 0:
            raise ValueError("publication_half_life_years must be positive")
        if self.minimum_journal_authenticity is not None:
            _unit(self.minimum_journal_authenticity, "minimum_journal_authenticity")


DEFAULT_PROFILES = {
    "GENERAL": RankingProfile("GENERAL", 0.65, 0.20, 0.07, 0.03, 0.05, 0.75, 0.25, 8.0),
    "RECENT": RankingProfile("RECENT", 0.60, 0.18, 0.04, 0.18, 0.00, 0.75, 0.25, 2.0),
    "FOUNDATIONAL": RankingProfile("FOUNDATIONAL", 0.65, 0.20, 0.12, 0.00, 0.03, 0.75, 0.25, 25.0),
}


@dataclass(frozen=True, slots=True)
class RankedEntity:
    rank: int
    entity: EntityRecord
    eligible: bool
    final_score: float
    score_breakdown: Mapping[str, float]
    gate_reasons: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    graph_path: GraphPath | None
    ignored_signals: tuple[str, ...]


class RankingService:
    """Pure deterministic ranking: no database calls, LLM calls, or I/O."""

    def __init__(self, profiles: Mapping[str, RankingProfile] | None = None) -> None:
        self.profiles = dict(profiles or DEFAULT_PROFILES)

    def rank(self, plan: QueryPlan, candidates: Sequence[RankingCandidate]) -> tuple[RankedEntity, ...]:
        profile = self.profiles.get(plan.profile)
        if profile is None:
            raise ValueError(f"Unknown ranking profile: {plan.profile}")
        provisional = [self._rank_one(plan, profile, candidate) for candidate in candidates]
        provisional.sort(key=lambda item: (not item["eligible"], -item["final_score"], item["entity"].entity_id))
        return tuple(
            RankedEntity(rank=index, **item)
            for index, item in enumerate(provisional[: plan.limit], start=1)
        )

    def _rank_one(
        self,
        plan: QueryPlan,
        profile: RankingProfile,
        candidate: RankingCandidate,
    ) -> dict[str, object]:
        entity = candidate.entity
        reasons: list[str] = []
        if plan.require_evidence and not candidate.evidence_ids:
            reasons.append("missing_evidence")
        if (
            entity.kind == PUBLICATION
            and entity.journal_authenticity_reproducible
            and entity.journal_authenticity_score is not None
            and profile.minimum_journal_authenticity is not None
            and entity.journal_authenticity_score < profile.minimum_journal_authenticity
        ):
            reasons.append("journal_authenticity_gate")

        ignored: list[str] = []
        if entity.academic_authority_score is not None:
            ignored.append("academic_authority_score")

        if entity.kind == PUBLICATION:
            citation = entity.citation_score if entity.citation_score is not None else 0.0
            authority = (
                entity.paper_authority_score
                if entity.paper_authority_reproducible and entity.paper_authority_score is not None
                else 0.0
            )
            recency = _recency(entity.publication_date, plan.as_of, profile.publication_half_life_years)
            components = {
                "retrieval": candidate.retrieval_score,
                "graph": candidate.graph_score,
                "citation": citation,
                "recency": recency,
                "paper_authority": authority,
            }
            score = (
                profile.publication_retrieval_weight * components["retrieval"]
                + profile.publication_graph_weight * components["graph"]
                + profile.citation_weight * components["citation"]
                + profile.recency_weight * components["recency"]
                + profile.paper_authority_weight * components["paper_authority"]
            )
        elif entity.kind == RESEARCHER:
            components = {"retrieval": candidate.retrieval_score, "graph": candidate.graph_score}
            score = (
                profile.researcher_retrieval_weight * components["retrieval"]
                + profile.researcher_graph_weight * components["graph"]
            )
        else:
            reasons.append(f"unsupported_ranking_kind={entity.kind}")
            components = {"retrieval": candidate.retrieval_score, "graph": candidate.graph_score}
            score = 0.0

        eligible = not reasons
        return {
            "entity": entity,
            "eligible": eligible,
            "final_score": round(score if eligible else 0.0, 12),
            "score_breakdown": {key: round(value, 12) for key, value in components.items()},
            "gate_reasons": tuple(reasons),
            "evidence_ids": candidate.evidence_ids,
            "graph_path": candidate.graph_path,
            "ignored_signals": tuple(ignored),
        }


def _recency(publication_date: date | None, as_of: date, half_life_years: float) -> float:
    if publication_date is None:
        return 0.0
    age = max(0.0, (as_of - publication_date).days / 365.25)
    return 0.5 ** (age / half_life_years)


@dataclass(frozen=True, slots=True)
class EvidenceItem:
    evidence_id: str
    entity_id: str
    source_url: str
    excerpt: str
    confidence: float = 1.0

    def __post_init__(self) -> None:
        if not self.evidence_id or not self.entity_id or not self.source_url:
            raise ValueError("Evidence needs an ID, subject entity, and source URL")
        _unit(self.confidence, "evidence confidence")


@dataclass(frozen=True, slots=True)
class EvidencePack:
    status: str
    items: tuple[EvidenceItem, ...]
    ranked_entity_ids: tuple[str, ...]


class EvidencePackBuilder:
    """Select bounded, server-supplied evidence. It never fabricates evidence."""

    def build(
        self,
        ranked: Sequence[RankedEntity],
        evidence_by_id: Mapping[str, EvidenceItem],
        *,
        limit: int = 8,
    ) -> EvidencePack:
        if limit <= 0:
            raise ValueError("Evidence limit must be positive")
        items: list[EvidenceItem] = []
        entity_ids: list[str] = []
        seen: set[str] = set()
        for result in ranked:
            if not result.eligible:
                continue
            entity_ids.append(result.entity.entity_id)
            for evidence_id in result.evidence_ids:
                item = evidence_by_id.get(evidence_id)
                if item is None or item.entity_id != result.entity.entity_id or item.evidence_id in seen:
                    continue
                seen.add(item.evidence_id)
                items.append(item)
                if len(items) == limit:
                    return EvidencePack("ready", tuple(items), tuple(entity_ids))
        return EvidencePack("ready" if items else "insufficient_evidence", tuple(items), tuple(entity_ids))


class GenerationPort(Protocol):
    """One downstream synthesis call receives an EvidencePack, never database access."""

    def synthesize(self, question: str, evidence: EvidencePack) -> object: ...


@dataclass(frozen=True, slots=True)
class RetrievalRankingResult:
    fused: tuple[FusedCandidate, ...]
    expansion: ExpansionResult
    ranked: tuple[RankedEntity, ...]


class RetrievalRankingPipeline:
    """Orchestrates retrieval through ranking; it intentionally stops before generation."""

    def __init__(
        self,
        *,
        retrieval: RetrievalPort,
        fusion: FusionService,
        expansion: GraphExpansionPort,
        ranking: RankingService,
    ) -> None:
        self.retrieval = retrieval
        self.fusion = fusion
        self.expansion = expansion
        self.ranking = ranking

    def retrieve_and_rank(self, plan: QueryPlan) -> RetrievalRankingResult:
        fused = self.fusion.fuse(self.retrieval.retrieve(plan))
        expansion = self.expansion.expand(plan, fused)
        candidates = candidates_from_fusion_and_expansion(plan, fused, expansion)
        return RetrievalRankingResult(fused, expansion, self.ranking.rank(plan, candidates))
