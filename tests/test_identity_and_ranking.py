import unittest

from ranking import FusionService, RetrievalHit
from support import build_mock_scenario, stable_id, stable_relationship_id


class StableIdentityTests(unittest.TestCase):
    def test_entity_identity_is_deterministic_and_authority_scoped(self) -> None:
        first = stable_id("researcher", "orcid", "0000-0001")
        second = stable_id("researcher", "orcid", "0000-0001")
        other_authority = stable_id("researcher", "openalex", "0000-0001")

        self.assertEqual(first, second)
        self.assertNotEqual(first, other_authority)

    def test_relationship_identity_ignores_mutable_evidence(self) -> None:
        source = stable_id("researcher", "orcid", "a")
        target = stable_id("publication", "doi", "b")

        authored = stable_relationship_id("AUTHORED", source, target)
        self.assertEqual(authored, stable_relationship_id("AUTHORED", source, target))
        self.assertNotEqual(authored, stable_relationship_id("CITES", source, target))


class FusionServiceTests(unittest.TestCase):
    def test_overlap_across_independent_channels_is_rewarded(self) -> None:
        scenario = build_mock_scenario()
        shared, lexical_only, dense_only = scenario.entities[:3]
        fused = FusionService().fuse(
            {
                "lexical": (
                    RetrievalHit(shared, "lexical", 1, 4.0),
                    RetrievalHit(lexical_only, "lexical", 2, 3.0),
                ),
                "dense": (
                    RetrievalHit(dense_only, "dense", 1, 0.9),
                    RetrievalHit(shared, "dense", 2, 0.8),
                ),
            }
        )
        by_id = {item.entity.entity_id: item for item in fused}

        self.assertGreater(by_id[shared.entity_id].rrf_score, by_id[lexical_only.entity_id].rrf_score)
        self.assertGreater(by_id[shared.entity_id].rrf_score, by_id[dense_only.entity_id].rrf_score)
        self.assertEqual(by_id[shared.entity_id].channel_ranks, {"dense": 2, "lexical": 1})

    def test_rrf_rejects_non_positive_k(self) -> None:
        with self.assertRaises(ValueError):
            FusionService(rrf_k=0)


if __name__ == "__main__":
    unittest.main()
