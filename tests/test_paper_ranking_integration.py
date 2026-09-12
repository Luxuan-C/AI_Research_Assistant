from datetime import date
import unittest

from ranking import (
    PUBLICATION,
    RESEARCHER,
    EntityRecord,
    FusionService,
    GraphBudget,
    GraphEdge,
    QueryPlan,
    RankingCandidate,
    RankingService,
    RetrievalHit,
    SchemaRelationshipGraph,
    edges_from_fixed_schema_rows,
)


class RetrievalRankingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.plan = QueryPlan("robotics in aged care", as_of=date(2026, 9, 8))

    @staticmethod
    def publication(entity_id: str, **overrides: object) -> EntityRecord:
        values: dict[str, object] = {
            "entity_id": entity_id,
            "kind": PUBLICATION,
            "label": f"Paper {entity_id}",
            "publication_date": date(2025, 1, 1),
        }
        values.update(overrides)
        return EntityRecord(**values)

    def test_fusion_preserves_independent_lexical_and_dense_ranks(self) -> None:
        shared = self.publication("shared")
        lexical_only = self.publication("lexical")
        dense_only = self.publication("dense")

        fused = FusionService().fuse(
            {
                "lexical": (
                    RetrievalHit(shared, "lexical", 1, 12.0),
                    RetrievalHit(lexical_only, "lexical", 2, 9.0),
                ),
                "dense": (
                    RetrievalHit(dense_only, "dense", 1, 0.91),
                    RetrievalHit(shared, "dense", 2, 0.85),
                ),
            }
        )

        by_id = {item.entity.entity_id: item for item in fused}
        self.assertEqual(by_id["shared"].channel_ranks, {"dense": 2, "lexical": 1})
        self.assertEqual(by_id["shared"].channel_raw_scores, {"dense": 0.85, "lexical": 12.0})
        self.assertGreater(by_id["shared"].rrf_score, by_id["lexical"].rrf_score)
        self.assertGreater(by_id["shared"].rrf_score, by_id["dense"].rrf_score)

    def test_schema_arrays_project_to_read_only_graph_edges(self) -> None:
        edges = edges_from_fixed_schema_rows(
            academics=(
                {
                    "id": "researcher-1",
                    "research_paper_ids": ["paper-1"],
                    "university_ids": ["university-1"],
                    "discipline_ids": ["discipline-1"],
                    "field_ids": ["field-1"],
                },
            ),
            research_papers=(
                {
                    "id": "paper-1",
                    "academic_ids": ["researcher-1"],
                    "outgoing_citations": ["paper-2"],
                    "university_ids": ["university-1"],
                    "faculty_ids": ["faculty-1"],
                    "journal_id": "journal-1",
                },
            ),
        )

        self.assertEqual(
            {edge.relation_type for edge in edges},
            {
                "AUTHORED",
                "AFFILIATED_WITH",
                "ACADEMIC_IN_DISCIPLINE",
                "EXPERTISE_IN_FIELD",
                "CITES",
                "PAPER_AT_UNIVERSITY",
                "PAPER_IN_FACULTY",
                "PUBLISHED_IN",
            },
        )

    def test_graph_expansion_respects_entity_and_hop_budgets(self) -> None:
        seed = self.publication("paper-1")
        researcher = EntityRecord("researcher-1", RESEARCHER, "Researcher One")
        related = self.publication("paper-2")
        graph = SchemaRelationshipGraph(
            (seed, researcher, related),
            (
                GraphEdge("e1", "researcher-1", "paper-1", "AUTHORED"),
                GraphEdge("e2", "researcher-1", "paper-2", "AUTHORED"),
            ),
            budget=GraphBudget(max_hops=2, max_entities=2, max_relationships=2, max_neighbors_per_node=2),
        )
        fused = FusionService().fuse({"lexical": (RetrievalHit(seed, "lexical", 1, 1.0),)})

        expansion = graph.expand(self.plan, fused)

        self.assertLessEqual(len(expansion.paths), 2)
        self.assertTrue(expansion.truncated)
        self.assertTrue(all(path.hops <= 2 for path in expansion.paths.values()))

    def test_graph_expansion_counts_seeds_against_the_entity_budget(self) -> None:
        first = self.publication("paper-1")
        second = self.publication("paper-2")
        graph = SchemaRelationshipGraph(
            (first, second),
            (),
            budget=GraphBudget(max_entities=1),
        )
        fused = FusionService().fuse(
            {
                "lexical": (
                    RetrievalHit(first, "lexical", 1, 1.0),
                    RetrievalHit(second, "lexical", 2, 0.9),
                )
            }
        )

        expansion = graph.expand(self.plan, fused)

        self.assertEqual(len(expansion.paths), 1)
        self.assertTrue(expansion.truncated)

    def test_ranking_is_deterministic_for_reordered_input(self) -> None:
        first = self.publication("a")
        second = self.publication("b")
        candidates = (RankingCandidate(second, 0.8), RankingCandidate(first, 0.8))
        service = RankingService()

        one = service.rank(self.plan, candidates)
        two = service.rank(self.plan, tuple(reversed(candidates)))

        self.assertEqual([item.entity.entity_id for item in one], ["a", "b"])
        self.assertEqual(one, two)

    def test_researchers_rank_without_academic_authority(self) -> None:
        researcher = EntityRecord(
            "researcher-1",
            RESEARCHER,
            "Researcher One",
            academic_authority_score=1.0,
            academic_authority_provenance="undefined",
        )

        result = RankingService().rank(self.plan, (RankingCandidate(researcher, 0.8, 0.4),))[0]

        self.assertTrue(result.eligible)
        self.assertEqual(result.score_breakdown, {"retrieval": 0.8, "graph": 0.4})
        self.assertIn("academic_authority_score", result.ignored_signals)

    def test_missing_score_metadata_is_safe(self) -> None:
        baseline = self.publication("baseline")
        comparison = self.publication("comparison")
        service = RankingService()

        ranked = service.rank(
            self.plan,
            (RankingCandidate(baseline, 0.7), RankingCandidate(comparison, 0.7)),
        )
        by_id = {item.entity.entity_id: item for item in ranked}

        self.assertEqual(by_id["baseline"].final_score, by_id["comparison"].final_score)
        self.assertEqual(by_id["baseline"].score_breakdown["citation"], 0.0)
        self.assertEqual(by_id["baseline"].score_breakdown["paper_authority"], 0.0)

    def test_unreproducible_authority_is_not_used_and_journal_is_a_gate(self) -> None:
        candidate = self.publication(
            "paper-1",
            paper_authority_score=1.0,
            paper_authority_reproducible=False,
            journal_authenticity_score=0.2,
            journal_authenticity_reproducible=True,
        )

        result = RankingService().rank(self.plan, (RankingCandidate(candidate, 0.9),))[0]

        self.assertFalse(result.eligible)
        self.assertEqual(result.final_score, 0.0)
        self.assertEqual(result.score_breakdown["paper_authority"], 0.0)
        self.assertEqual(result.gate_reasons, ("journal_authenticity_gate",))


if __name__ == "__main__":
    unittest.main()
