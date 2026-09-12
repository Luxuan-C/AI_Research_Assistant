"""Top-level answer orchestration over the deterministic ranking pipeline.

This boundary receives validated evidence from an external evidence layer. It
does not retrieve evidence from Supabase or fabricate excerpts, and it leaves
retrieval, graph expansion, and ranking to ``RetrievalRankingPipeline``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .paper_ranking import (
    EvidenceItem,
    EvidencePack,
    EvidencePackBuilder,
    GenerationPort,
    QueryPlan,
    RetrievalRankingPipeline,
    RetrievalRankingResult,
)


@dataclass(frozen=True, slots=True)
class Answer:
    """A generated answer with the exact evidence pack supplied to generation."""

    answer: object
    retrieval_ranking: RetrievalRankingResult
    evidence: EvidencePack


@dataclass(frozen=True, slots=True)
class InsufficientInformation:
    """Deterministic abstention when no validated evidence pack is available."""

    retrieval_ranking: RetrievalRankingResult
    evidence: EvidencePack
    status: str = "insufficient_information"


class AnswerOrchestrator:
    """Complete the production boundary after deterministic retrieval/ranking."""

    def __init__(
        self,
        *,
        retrieval_ranking: RetrievalRankingPipeline,
        evidence_builder: EvidencePackBuilder,
        generation: GenerationPort,
        evidence_limit: int = 8,
    ) -> None:
        if evidence_limit <= 0:
            raise ValueError("evidence_limit must be positive")
        self.retrieval_ranking = retrieval_ranking
        self.evidence_builder = evidence_builder
        self.generation = generation
        self.evidence_limit = evidence_limit

    def answer(
        self,
        plan: QueryPlan,
        validated_evidence_by_id: Mapping[str, EvidenceItem],
    ) -> Answer | InsufficientInformation:
        """Rank, build a bounded validated pack, then generate only when ready."""

        retrieval_ranking = self.retrieval_ranking.retrieve_and_rank(plan)
        evidence = self.evidence_builder.build(
            retrieval_ranking.ranked,
            validated_evidence_by_id,
            limit=self.evidence_limit,
        )
        if evidence.status != "ready" or not evidence.items:
            return InsufficientInformation(retrieval_ranking, evidence)
        return Answer(
            self.generation.synthesize(plan.text, evidence),
            retrieval_ranking,
            evidence,
        )
