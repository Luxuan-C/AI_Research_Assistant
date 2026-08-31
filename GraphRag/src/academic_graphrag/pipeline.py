"""Standalone GraphRAG retrieval pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Mapping, Sequence

from .interfaces import (
    AcademicGraphRepository,
    AcademicSignalProvider,
    DenseRetriever,
    KeywordRetriever,
    Reranker,
)
from .models import (
    Candidate,
    ContextPassage,
    Entity,
    EvidenceWithSource,
    GenerationContext,
    GraphPath,
    RankedResult,
    Relationship,
    RetrievalQuery,
    RetrievalResponse,
    RetrievalStatus,
)
from .ranking import (
    RankingWeights,
    build_score_breakdown,
    max_channel_relevance,
    normalise_scores,
    reciprocal_rank_fusion,
)
from .traversal import BoundedGraphExpander, ExpansionResult, TraversalConfig


@dataclass(frozen=True, slots=True)
class PipelineConfig:
    keyword_limit: int = 20
    dense_limit: int = 20
    expansion_seed_limit: int = 10
    candidate_limit: int = 50
    evidence_per_result: int = 5
    context_relationships_per_result: int = 4
    rrf_k: int = 60
    graph_decay: float = 0.80
    relevance_threshold: float = 0.40
    evidence_confidence_threshold: float = 0.60
    weights: RankingWeights = field(default_factory=RankingWeights)
    traversal: TraversalConfig = field(default_factory=TraversalConfig)

    def __post_init__(self) -> None:
        for name in (
            "keyword_limit",
            "dense_limit",
            "expansion_seed_limit",
            "candidate_limit",
            "evidence_per_result",
            "context_relationships_per_result",
            "rrf_k",
        ):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive")
        for name in ("graph_decay", "relevance_threshold", "evidence_confidence_threshold"):
            if not 0.0 <= getattr(self, name) <= 1.0:
                raise ValueError(f"{name} must be between 0 and 1")


class GraphRAGEngine:
    """Public provider-neutral retrieval API."""

    def __init__(
        self,
        *,
        repository: AcademicGraphRepository,
        keyword_retriever: KeywordRetriever,
        dense_retriever: DenseRetriever,
        reranker: Reranker,
        signal_provider: AcademicSignalProvider,
        config: PipelineConfig | None = None,
        expander: BoundedGraphExpander | None = None,
    ) -> None:
        self.repository = repository
        self.keyword_retriever = keyword_retriever
        self.dense_retriever = dense_retriever
        self.reranker = reranker
        self.signal_provider = signal_provider
        self.config = config or PipelineConfig()
        self.expander = expander or BoundedGraphExpander()

    def retrieve(self, query: RetrievalQuery) -> RetrievalResponse:
        if not query.text.strip():
            raise ValueError("Query text cannot be empty")
        if query.limit <= 0:
            raise ValueError("Query limit must be positive")

        keyword = tuple(self.keyword_retriever.search(query, limit=self.config.keyword_limit))
        dense = tuple(self.dense_retriever.search(query, limit=self.config.dense_limit))
        channel_rankings = {"keyword": keyword, "dense": dense}
        fused_raw = reciprocal_rank_fusion(channel_rankings, k=self.config.rrf_k)
        fused = normalise_scores(fused_raw)
        absolute_relevance = max_channel_relevance(channel_rankings.values())

        ranked_seed_ids = sorted(
            fused,
            key=lambda entity_id: (-fused[entity_id], -absolute_relevance.get(entity_id, 0.0), entity_id),
        )[: self.config.expansion_seed_limit]
        if not ranked_seed_ids:
            return self._insufficient(query, truncated=False)

        expansion = self.expander.expand(
            self.repository,
            ranked_seed_ids,
            self.config.traversal,
        )
        entity_by_id = {entity.id: entity for entity in expansion.entities}
        eligible_ids = {
            entity.id
            for entity in self.repository.list_entities(
                entity_ids=tuple(entity_by_id),
                entity_types=query.entity_types,
                filters=query.filters,
            )
        }
        relationship_by_id = {edge.id: edge for edge in expansion.relationships}
        candidates = self._candidate_pool(
            ranked_seed_ids=ranked_seed_ids,
            expansion=expansion,
            fused=fused,
            absolute_relevance=absolute_relevance,
        )
        reranked = tuple(self.reranker.rerank(query, candidates, entity_by_id))
        results = self._build_results(
            query=query,
            reranked=reranked,
            entity_by_id=entity_by_id,
            relationship_by_id=relationship_by_id,
            paths=expansion.paths,
            fused=fused,
            eligible_ids=eligible_ids,
        )
        accepted = tuple(results[: min(query.limit, self.config.candidate_limit)])
        if not accepted:
            return self._insufficient(query, truncated=expansion.truncated)

        all_relationships = _unique_relationships(
            relationship
            for result in accepted
            for relationship in result.relationships_used
        )
        passages = tuple(
            ContextPassage(
                entity_id=result.entity.id,
                text=result.context,
                evidence_ids=tuple(item.evidence.id for item in result.evidence),
                provenance_ids=result.provenance_ids,
            )
            for result in accepted
        )
        provenance_ids = tuple(dict.fromkeys(value for result in accepted for value in result.provenance_ids))
        return RetrievalResponse(
            status=RetrievalStatus.OK,
            query=query,
            results=accepted,
            relationships_used=all_relationships,
            generation_context=GenerationContext(
                query=query.text,
                passages=passages,
                relationships=all_relationships,
                provenance_ids=provenance_ids,
            ),
            truncated=expansion.truncated,
        )

    def _candidate_pool(
        self,
        *,
        ranked_seed_ids: Sequence[str],
        expansion: ExpansionResult,
        fused: Mapping[str, float],
        absolute_relevance: Mapping[str, float],
    ) -> tuple[Candidate, ...]:
        relevance: dict[str, float] = {}
        for entity_id in ranked_seed_ids:
            relevance[entity_id] = absolute_relevance.get(entity_id, 0.0)
        for entity in expansion.entities:
            path = expansion.paths[entity.id]
            seed_relevance = absolute_relevance.get(path.seed_id, 0.0)
            graph_relevance = seed_relevance * (self.config.graph_decay ** path.hops)
            relevance[entity.id] = max(relevance.get(entity.id, 0.0), graph_relevance)

        ordered = sorted(
            relevance,
            key=lambda entity_id: (-relevance[entity_id], -fused.get(entity_id, 0.0), entity_id),
        )[: self.config.candidate_limit]
        return tuple(
            Candidate(
                entity_id=entity_id,
                score=fused.get(entity_id, 0.0),
                channel="graph" if entity_id not in fused else "rrf",
                rank=rank,
                metadata={
                    "retrieval_relevance": relevance[entity_id],
                    "rrf": fused.get(entity_id, 0.0),
                    "graph_hops": expansion.paths[entity_id].hops,
                },
            )
            for rank, entity_id in enumerate(ordered, start=1)
        )

    def _build_results(
        self,
        *,
        query: RetrievalQuery,
        reranked: Sequence[Candidate],
        entity_by_id: Mapping[str, Entity],
        relationship_by_id: Mapping[str, Relationship],
        paths: Mapping[str, GraphPath],
        fused: Mapping[str, float],
        eligible_ids: set[str],
    ) -> list[RankedResult]:
        provisional: list[RankedResult] = []
        for candidate in reranked:
            entity = entity_by_id.get(candidate.entity_id)
            if entity is None or entity.id not in eligible_ids:
                continue
            path = paths[entity.id]
            path_relationships = tuple(
                relationship_by_id[edge_id]
                for edge_id in path.relationship_ids
                if edge_id in relationship_by_id
            )
            if path_relationships:
                relationships = path_relationships
            else:
                relationships = tuple(
                    edge
                    for edge in sorted(relationship_by_id.values(), key=lambda item: item.id)
                    if edge.source_id == entity.id or edge.target_id == entity.id
                )[: self.config.context_relationships_per_result]
            evidence = self._select_evidence(entity.id, relationships)
            evidence_confidence = (
                sum(item.evidence.confidence for item in evidence) / len(evidence)
                if evidence
                else 0.0
            )
            signals = self.signal_provider.score(entity, query)
            breakdown = build_score_breakdown(
                semantic_relevance=candidate.score,
                rrf_score=fused.get(entity.id, 0.0),
                graph_hops=path.hops,
                evidence_confidence=evidence_confidence,
                signals=signals,
                weights=self.config.weights,
            )
            if breakdown.final_score < self.config.relevance_threshold:
                continue
            if evidence_confidence < self.config.evidence_confidence_threshold:
                continue
            provenance_ids = tuple(dict.fromkeys(item.source.id for item in evidence))
            provisional.append(
                RankedResult(
                    rank=0,
                    entity=entity,
                    relationships_used=relationships,
                    score=breakdown,
                    evidence=evidence,
                    provenance_ids=provenance_ids,
                    context=_render_context(entity, relationships, evidence, entity_by_id),
                )
            )
        provisional.sort(key=lambda item: (-item.score.final_score, item.entity.id))
        return [
            RankedResult(
                rank=rank,
                entity=item.entity,
                relationships_used=item.relationships_used,
                score=item.score,
                evidence=item.evidence,
                provenance_ids=item.provenance_ids,
                context=item.context,
            )
            for rank, item in enumerate(provisional, start=1)
        ]

    def _select_evidence(
        self,
        entity_id: str,
        relationships: Sequence[Relationship],
    ) -> tuple[EvidenceWithSource, ...]:
        supported_ids = (entity_id, *(edge.id for edge in relationships))
        evidence_items = sorted(
            self.repository.get_evidence(supported_ids),
            key=lambda item: (-item.confidence, item.id),
        )[: self.config.evidence_per_result]
        sources = {
            source.id: source
            for source in self.repository.get_sources(tuple(item.source_record_id for item in evidence_items))
        }
        return tuple(
            EvidenceWithSource(evidence=item, source=sources[item.source_record_id])
            for item in evidence_items
            if item.source_record_id in sources
        )

    @staticmethod
    def _insufficient(query: RetrievalQuery, *, truncated: bool) -> RetrievalResponse:
        context = GenerationContext(query=query.text, passages=(), relationships=(), provenance_ids=())
        return RetrievalResponse(
            status=RetrievalStatus.INSUFFICIENT_INFORMATION,
            query=query,
            results=(),
            relationships_used=(),
            generation_context=context,
            truncated=truncated,
            message="Insufficient Information: retrieved evidence did not meet the configured thresholds.",
        )


def _render_context(
    entity: Entity,
    relationships: Sequence[Relationship],
    evidence: Sequence[EvidenceWithSource],
    entity_by_id: Mapping[str, Entity],
) -> str:
    def label(entity_id: str) -> str:
        related = entity_by_id.get(entity_id)
        return related.label if related else entity_id

    relationship_text = "; ".join(
        f"{label(edge.source_id)} -{edge.relation_type}-> {label(edge.target_id)}"
        for edge in relationships
    )
    evidence_text = " ".join(
        f"[{item.evidence.id}] {item.evidence.excerpt}"
        for item in evidence
    )
    parts = [f"{entity.entity_type}: {entity.label}.", entity.text]
    if relationship_text:
        parts.append(f"Graph path: {relationship_text}.")
    if evidence_text:
        parts.append(f"Evidence: {evidence_text}")
    return " ".join(part for part in parts if part).strip()


def _unique_relationships(values: Iterable[Relationship]) -> tuple[Relationship, ...]:
    output: dict[str, Relationship] = {}
    for value in values:
        output[value.id] = value
    return tuple(output.values())
