from datetime import date
import inspect
import unittest

from ranking import (
    Answer,
    AnswerOrchestrator,
    EvidencePackBuilder,
    FusionService,
    InsufficientInformation,
    QueryPlanner,
    RankingService,
    RetrievalRankingPipeline,
)
from support import build_mock_scenario


class RetrievalRankingPipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.scenario = build_mock_scenario()
        self.pipeline = RetrievalRankingPipeline(
            retrieval=self.scenario.retrieval,
            fusion=FusionService(),
            expansion=self.scenario.graph,
            ranking=RankingService(),
        )

    def test_pipeline_returns_ranked_publications_and_researchers(self) -> None:
        plan = QueryPlanner().plan("aged care robotics", as_of=date(2026, 9, 8))

        result = self.pipeline.retrieve_and_rank(plan)

        self.assertTrue(result.fused)
        self.assertTrue(result.expansion.paths)
        self.assertTrue(result.ranked)
        self.assertEqual(
            [item.rank for item in result.ranked],
            list(range(1, len(result.ranked) + 1)),
        )
        self.assertEqual(
            {item.entity.kind for item in result.ranked},
            {"publication", "researcher"},
        )

    def test_pipeline_stops_before_generation_and_builds_bounded_evidence(self) -> None:
        plan = QueryPlanner().plan(
            "aged care robotics",
            as_of=date(2026, 9, 8),
            require_evidence=True,
        )
        result = self.pipeline.retrieve_and_rank(plan)

        pack = EvidencePackBuilder().build(result.ranked, self.scenario.evidence, limit=3)

        self.assertEqual(pack.status, "ready")
        self.assertLessEqual(len(pack.items), 3)
        self.assertTrue(all(item.source_url.startswith("https://") for item in pack.items))

    def test_pipeline_is_stable_across_repeated_runs(self) -> None:
        plan = QueryPlanner().plan("aged care robotics", as_of=date(2026, 9, 8))

        first = self.pipeline.retrieve_and_rank(plan)
        second = self.pipeline.retrieve_and_rank(plan)

        self.assertEqual(first, second)

    def test_evidence_builder_fails_closed_without_evidence(self) -> None:
        plan = QueryPlanner().plan("aged care robotics", as_of=date(2026, 9, 8))
        result = self.pipeline.retrieve_and_rank(plan)

        pack = EvidencePackBuilder().build(result.ranked, {})

        self.assertEqual(pack.status, "insufficient_evidence")
        self.assertEqual(pack.items, ())

    def test_answer_orchestrator_builds_evidence_after_ranking_and_generates_once(self) -> None:
        calls: list[str] = []

        class RecordingRankingService(RankingService):
            def rank(self, plan, candidates):
                calls.append("ranking")
                return super().rank(plan, candidates)

        class RecordingEvidenceBuilder(EvidencePackBuilder):
            def build(self, ranked, evidence_by_id, *, limit=8):
                calls.append("evidence")
                return super().build(ranked, evidence_by_id, limit=limit)

        class RecordingGenerationPort:
            def synthesize(self, question, evidence):
                calls.append("generation")
                return {"question": question, "evidence_ids": [item.evidence_id for item in evidence.items]}

        pipeline = RetrievalRankingPipeline(
            retrieval=self.scenario.retrieval,
            fusion=FusionService(),
            expansion=self.scenario.graph,
            ranking=RecordingRankingService(),
        )
        orchestrator = AnswerOrchestrator(
            retrieval_ranking=pipeline,
            evidence_builder=RecordingEvidenceBuilder(),
            generation=RecordingGenerationPort(),
            evidence_limit=3,
        )
        plan = QueryPlanner().plan("aged care robotics", as_of=date(2026, 9, 8), require_evidence=True)

        result = orchestrator.answer(plan, self.scenario.evidence)

        self.assertIsInstance(result, Answer)
        self.assertEqual(calls, ["ranking", "evidence", "generation"])
        self.assertEqual(result.answer["question"], plan.text)
        self.assertLessEqual(len(result.evidence.items), 3)

    def test_answer_orchestrator_abstains_deterministically_without_evidence(self) -> None:
        calls: list[str] = []

        class RecordingGenerationPort:
            def synthesize(self, question, evidence):
                calls.append("generation")
                return "must not run"

        orchestrator = AnswerOrchestrator(
            retrieval_ranking=self.pipeline,
            evidence_builder=EvidencePackBuilder(),
            generation=RecordingGenerationPort(),
        )
        plan = QueryPlanner().plan("aged care robotics", as_of=date(2026, 9, 8), require_evidence=True)

        first = orchestrator.answer(plan, {})
        second = orchestrator.answer(plan, {})

        self.assertIsInstance(first, InsufficientInformation)
        self.assertEqual(first, second)
        self.assertEqual(first.status, "insufficient_information")
        self.assertEqual(first.evidence.status, "insufficient_evidence")
        self.assertEqual(calls, [])

    def test_ranking_service_has_no_supabase_or_generation_dependency(self) -> None:
        source = inspect.getsource(RankingService)

        self.assertNotIn("Supabase", source)
        self.assertNotIn(".table(", source)
        self.assertNotIn("synthesize(", source)


if __name__ == "__main__":
    unittest.main()
