from datetime import date
import unittest

from ranking import (
    RESEARCHER,
    FusionService,
    GraphBudget,
    QueryPlan,
)
from support import build_mock_scenario


class RetrievalPortAndGraphTests(unittest.TestCase):
    def test_bm25_test_port_supports_fixed_schema_style_filters(self) -> None:
        scenario = build_mock_scenario()
        plan = QueryPlan(
            "electric vehicle emissions",
            as_of=date(2026, 9, 8),
            filters={"institution": "Monash University"},
        )

        channels = scenario.retrieval.retrieve(plan)

        self.assertIn("lexical", channels)
        self.assertTrue(channels["lexical"])
        self.assertEqual(channels["lexical"][0].entity.label, "Life-cycle Emissions of Electric Vehicles")

    def test_dense_channel_is_separate_from_bm25(self) -> None:
        scenario = build_mock_scenario()
        channels = scenario.retrieval.retrieve(
            QueryPlan("aged care robotics", as_of=date(2026, 9, 8))
        )

        self.assertEqual(set(channels), {"lexical", "dense"})
        self.assertTrue(all(hit.channel == "lexical" for hit in channels["lexical"]))
        self.assertTrue(all(hit.channel == "dense" for hit in channels["dense"]))

    def test_coauthorship_is_derived_by_two_authored_hops(self) -> None:
        scenario = build_mock_scenario()
        alice = next(entity for entity in scenario.entities if entity.label == "Dr Alice Chen")
        bob = next(entity for entity in scenario.entities if entity.label == "Dr Bob Nguyen")
        plan = QueryPlan(
            "Alice Chen",
            as_of=date(2026, 9, 8),
            target_kinds=(RESEARCHER,),
            seed_limit=1,
        )
        channels = scenario.retrieval.retrieve(plan)
        fused = FusionService().fuse({"lexical": channels["lexical"]})

        expansion = scenario.graph.expand(plan, fused)

        self.assertEqual(fused[0].entity.entity_id, alice.entity_id)
        self.assertIn(bob.entity_id, expansion.paths)
        self.assertEqual(expansion.paths[bob.entity_id].hops, 2)

    def test_graph_expansion_reports_hard_budget_truncation(self) -> None:
        scenario = build_mock_scenario(
            budget=GraphBudget(
                max_hops=2,
                max_entities=2,
                max_relationships=2,
                max_neighbors_per_node=1,
            )
        )
        plan = QueryPlan("Alice Chen", as_of=date(2026, 9, 8), seed_limit=1)
        fused = FusionService().fuse(scenario.retrieval.retrieve(plan))

        expansion = scenario.graph.expand(plan, fused)

        self.assertLessEqual(len(expansion.entities), 2)
        self.assertTrue(expansion.truncated)
        self.assertTrue(all(path.hops <= 2 for path in expansion.paths.values()))


if __name__ == "__main__":
    unittest.main()
