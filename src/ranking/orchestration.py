"""Top-level answer orchestration over the deterministic ranking pipeline.

This boundary receives validated evidence from an external evidence layer and
may pass bounded ranked-paper metadata to a generation port that explicitly
supports external grounding. It does not retrieve evidence from Supabase or
fabricate excerpts, and it leaves retrieval, graph expansion, and ranking to
``RetrievalRankingPipeline``.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
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


@dataclass(frozen=True, slots=True)
class GenerationFailure:
    """Non-sensitive provider failure after ranking completed successfully."""

    retrieval_ranking: RetrievalRankingResult
    evidence: EvidencePack
    status: str = "provider_error"


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
        """Rank once, build the bounded evidence pack, then consider generation."""

        retrieval_ranking = self.retrieval_ranking.retrieve_and_rank(plan)
        return self.answer_ranked(
            plan,
            retrieval_ranking,
            validated_evidence_by_id,
        )

    def answer_ranked(
        self,
        plan: QueryPlan,
        retrieval_ranking: RetrievalRankingResult,
        validated_evidence_by_id: Mapping[str, EvidenceItem],
        *,
        ranked_papers: tuple[Mapping[str, object], ...] = (),
    ) -> Answer | InsufficientInformation | GenerationFailure:
        """Generate from an already-computed result without ranking a second time."""

        evidence = self.evidence_builder.build(
            retrieval_ranking.ranked,
            validated_evidence_by_id,
            limit=self.evidence_limit,
        )
        if ranked_papers:
            evidence = replace(evidence, ranked_papers=ranked_papers)
        has_internal_evidence = evidence.status == "ready" and bool(evidence.items)
        may_use_external_grounding = bool(
            getattr(self.generation, "supports_external_grounding", False)
            and evidence.ranked_papers
        )
        if not has_internal_evidence and not may_use_external_grounding:
            return InsufficientInformation(retrieval_ranking, evidence)
        try:
            generated = self.generation.synthesize(plan.text, evidence)
        except Exception:
            # Provider details may contain request data or credentials. The
            # application reports only this status and retains the ranked result.
            return GenerationFailure(retrieval_ranking, evidence)
        return Answer(generated, retrieval_ranking, evidence)
