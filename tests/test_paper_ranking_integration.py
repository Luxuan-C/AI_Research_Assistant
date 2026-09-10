import unittest

from academic_graphrag import RetrievalQuery
from ranking.application import search_papers
from academic_graphrag.mock_data import build_mock_backend
from ranking.paper_ranking import (
    candidates_from_retrieval_response,
    rank_retrieval_response,
)


class PaperRankingIntegrationTests(unittest.TestCase):
    def test_retrieval_response_becomes_publication_candidates(self) -> None:
        response = build_mock_backend().engine.retrieve(
            RetrievalQuery(
                "artificial intelligence aged care",
                limit=5,
                ranking_profile="GENERAL",
            )
        )

        candidates = candidates_from_retrieval_response(response)

        self.assertTrue(candidates)
        self.assertTrue(all(candidate.paper_id for candidate in candidates))
        self.assertTrue(all(candidate.publication_date.endswith("-01-01") for candidate in candidates))
        self.assertTrue(all(candidate.evidence for candidate in candidates))

    def test_retrieval_response_can_be_ranked_directly(self) -> None:
        response = build_mock_backend().engine.retrieve(
            RetrievalQuery(
                "artificial intelligence aged care",
                limit=5,
                ranking_profile="RECENT",
            )
        )

        results = rank_retrieval_response(response)

        self.assertTrue(results)
        self.assertEqual([result["rank"] for result in results], list(range(1, len(results) + 1)))
        self.assertTrue(all("explanation" in result for result in results))

    def test_application_service_connects_rag_to_ranking(self) -> None:
        backend = build_mock_backend()
        query = RetrievalQuery(
            "electric vehicle emissions",
            ranking_profile="RECENT",
        )

        results = search_papers(backend.engine, query)

        self.assertEqual(len(results), 1)
        self.assertEqual(
            results[0]["title"],
            "Life-cycle Emissions of Electric Vehicles in Australia",
        )


if __name__ == "__main__":
    unittest.main()