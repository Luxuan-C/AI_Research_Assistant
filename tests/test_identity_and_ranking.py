import unittest

from academic_graphrag.identity import stable_id, stable_relationship_id
from academic_graphrag.models import Candidate
from academic_graphrag.ranking import normalise_scores, reciprocal_rank_fusion


class StableIdentityTests(unittest.TestCase):
    def test_entity_identity_is_deterministic_and_authority_scoped(self) -> None:
        first = stable_id("Researcher", "orcid", "0000-0001")
        second = stable_id("Researcher", "orcid", "0000-0001")
        other_authority = stable_id("Researcher", "openalex", "0000-0001")

        self.assertEqual(first, second)
        self.assertNotEqual(first, other_authority)

    def test_relationship_identity_ignores_mutable_evidence(self) -> None:
        source = stable_id("Researcher", "orcid", "a")
        target = stable_id("Publication", "doi", "b")

        self.assertEqual(
            stable_relationship_id("AUTHORED", source, target),
            stable_relationship_id("AUTHORED", source, target),
        )
        self.assertNotEqual(
            stable_relationship_id("AUTHORED", source, target),
            stable_relationship_id("CITES", source, target),
        )


class ReciprocalRankFusionTests(unittest.TestCase):
    def test_overlap_across_channels_is_rewarded(self) -> None:
        rankings = {
            "keyword": (
                Candidate("shared", 4.0, "keyword", rank=1),
                Candidate("keyword-only", 3.0, "keyword", rank=2),
            ),
            "dense": (
                Candidate("dense-only", 0.9, "dense", rank=1),
                Candidate("shared", 0.8, "dense", rank=2),
            ),
        }

        fused = reciprocal_rank_fusion(rankings, k=60)
        normalised = normalise_scores(fused)

        self.assertGreater(fused["shared"], fused["keyword-only"])
        self.assertGreater(fused["shared"], fused["dense-only"])
        self.assertEqual(normalised["shared"], 1.0)

    def test_rrf_rejects_non_positive_k(self) -> None:
        with self.assertRaises(ValueError):
            reciprocal_rank_fusion({}, k=0)


if __name__ == "__main__":
    unittest.main()

