import unittest

from academic_graphrag import PipelineConfig, RetrievalQuery, RetrievalStatus
from academic_graphrag.in_memory import PassthroughReranker
from academic_graphrag.mock_data import build_mock_backend


class GraphRAGPipelineTests(unittest.TestCase):
    def test_reranker_is_replaceable_and_invoked(self) -> None:
        class RecordingReranker(PassthroughReranker):
            called = False

            def rerank(self, query, candidates, entities):
                self.called = True
                return super().rerank(query, candidates, entities)

        backend = build_mock_backend()
        reranker = RecordingReranker()
        backend.engine.reranker = reranker

        backend.engine.retrieve(RetrievalQuery("aged care robotics"))

        self.assertTrue(reranker.called)

    def test_returns_ranked_explainable_sourced_results(self) -> None:
        response = build_mock_backend().engine.retrieve(
            RetrievalQuery("How can artificial intelligence improve aged care?", limit=5)
        )

        self.assertEqual(response.status, RetrievalStatus.OK)
        self.assertGreaterEqual(len(response.results), 2)
        self.assertEqual(response.results[0].rank, 1)
        self.assertIn(response.results[0].entity.entity_type, {"Researcher", "Publication"})
        self.assertTrue(response.relationships_used)
        self.assertTrue(response.generation_context.passages)

        expected_components = {
            "rrf",
            "semantic_relevance",
            "citation_influence",
            "recency",
            "venue_quality",
            "topic_coverage",
            "evidence_confidence",
            "graph_hops",
        }
        for result in response.results:
            self.assertEqual(set(result.score.components), expected_components)
            self.assertTrue(result.evidence)
            self.assertTrue(result.provenance_ids)
            self.assertIn(result.evidence[0].evidence.id, result.context)

    def test_unrelated_query_fails_closed(self) -> None:
        response = build_mock_backend().engine.retrieve(
            RetrievalQuery("quantum entanglement in marine geology")
        )

        self.assertEqual(response.status, RetrievalStatus.INSUFFICIENT_INFORMATION)
        self.assertEqual(response.results, ())
        self.assertIn("Insufficient Information", response.message or "")
        self.assertEqual(response.generation_context.passages, ())

    def test_evidence_confidence_threshold_is_configurable(self) -> None:
        backend = build_mock_backend(
            PipelineConfig(evidence_confidence_threshold=0.99)
        )
        response = backend.engine.retrieve(RetrievalQuery("aged care artificial intelligence"))

        self.assertEqual(response.status, RetrievalStatus.INSUFFICIENT_INFORMATION)

    def test_academic_filters_are_passed_to_retrieval_adapters(self) -> None:
        response = build_mock_backend().engine.retrieve(
            RetrievalQuery(
                "environmental impact of electric vehicles",
                filters={"institution": "Monash University"},
            )
        )

        self.assertEqual(response.status, RetrievalStatus.OK)
        self.assertTrue(response.results)
        self.assertTrue(
            all(result.entity.metadata["institution"] == "Monash University" for result in response.results)
        )

    def test_llm_is_not_required_for_retrieval_context(self) -> None:
        response = build_mock_backend().engine.retrieve(
            RetrievalQuery("assistive robotics for aged care", limit=3)
        )

        self.assertEqual(response.status, RetrievalStatus.OK)
        self.assertTrue(response.generation_context.provenance_ids)
        self.assertTrue(
            all(passage.evidence_ids for passage in response.generation_context.passages)
        )


if __name__ == "__main__":
    unittest.main()
