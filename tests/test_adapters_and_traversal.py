import unittest

from academic_graphrag.in_memory import BM25KeywordRetriever
from academic_graphrag.mock_data import build_mock_backend
from academic_graphrag.models import RetrievalQuery
from academic_graphrag.traversal import BoundedGraphExpander, TraversalConfig


class InMemoryAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.backend = build_mock_backend()

    def test_bm25_retrieval_and_open_metadata_filters(self) -> None:
        retriever = BM25KeywordRetriever(self.backend.repository)
        query = RetrievalQuery(
            "aged care robotics",
            filters={"institution": "The University of Sydney"},
        )

        results = retriever.search(query, limit=5)
        entities = {item.id: item for item in self.backend.repository.get_entities([r.entity_id for r in results])}

        self.assertTrue(results)
        self.assertEqual(
            entities[results[0].entity_id].label,
            "Assistive Robotics in Residential Aged Care",
        )
        self.assertTrue(
            all(entity.metadata["institution"] == "The University of Sydney" for entity in entities.values())
        )

    def test_coauthorship_is_derived_by_two_authored_hops(self) -> None:
        alice = next(
            entity
            for entity in self.backend.repository.list_entities(entity_types=("Researcher",))
            if entity.label == "Dr Alice Chen"
        )
        bob = next(
            entity
            for entity in self.backend.repository.list_entities(entity_types=("Researcher",))
            if entity.label == "Dr Bob Nguyen"
        )
        expansion = BoundedGraphExpander().expand(
            self.backend.repository,
            (alice.id,),
            TraversalConfig(
                max_hops=2,
                max_entities=20,
                max_relationships=20,
                allowed_relation_types=("AUTHORED",),
            ),
        )

        self.assertIn(bob.id, expansion.paths)
        path = expansion.paths[bob.id]
        self.assertEqual(path.hops, 2)
        edge_by_id = {edge.id: edge for edge in expansion.relationships}
        self.assertEqual(
            [edge_by_id[edge_id].relation_type for edge_id in path.relationship_ids],
            ["AUTHORED", "AUTHORED"],
        )

    def test_source_record_supports_evidence_explicitly(self) -> None:
        alice = next(
            entity
            for entity in self.backend.repository.list_entities(entity_types=("Researcher",))
            if entity.label == "Dr Alice Chen"
        )
        evidence = self.backend.repository.get_evidence((alice.id,))[0]
        support_edges = self.backend.repository.get_relationships(
            (evidence.source_record_id,),
            relation_types=("SUPPORTS",),
        )

        self.assertTrue(any(edge.target_id == evidence.id for edge in support_edges))

    def test_traversal_reports_hard_budget_truncation(self) -> None:
        seed = self.backend.repository.list_entities(entity_types=("Researcher",))[0]
        expansion = BoundedGraphExpander().expand(
            self.backend.repository,
            (seed.id,),
            TraversalConfig(max_hops=2, max_entities=2, max_relationships=2, max_neighbors_per_node=1),
        )

        self.assertLessEqual(len(expansion.entities), 2)
        self.assertLessEqual(len(expansion.relationships), 2)
        self.assertTrue(expansion.truncated)


if __name__ == "__main__":
    unittest.main()
