import unittest

from academic_graphrag import AcademicProfileService, RetrievalQuery
from academic_graphrag.mock_data import build_mock_backend
from application import search_academic_profiles, search_academic_profiles_with_graphrag


class AcademicProfileTests(unittest.TestCase):
    def test_profile_contains_structured_data_publications_and_citations(self) -> None:
        backend = build_mock_backend()
        academic = next(
            entity
            for entity in backend.repository.list_entities(entity_types=("Researcher",))
            if entity.label == "Dr Alice Chen"
        )

        profile = AcademicProfileService(backend.repository).get_profile(academic.id)

        self.assertIsNotNone(profile)
        assert profile is not None
        self.assertEqual(profile.structured_information["name"], "Dr Alice Chen")
        self.assertEqual(
            profile.structured_information["institution"],
            "The University of Sydney",
        )
        self.assertTrue(profile.publications)
        self.assertEqual(profile.summary.status, "ok")
        self.assertIn("[", profile.summary.text)
        self.assertTrue(all(citation.uri for citation in profile.summary.citations))

    def test_unknown_entity_does_not_produce_a_profile(self) -> None:
        backend = build_mock_backend()

        profile = AcademicProfileService(backend.repository).get_profile("missing")

        self.assertIsNone(profile)

    def test_users_can_find_profiles_without_knowing_academic_id(self) -> None:
        backend = build_mock_backend()

        profiles = search_academic_profiles(backend.repository, "Alice Chen")

        self.assertEqual([profile.structured_information["name"] for profile in profiles], ["Dr Alice Chen"])

    def test_graphrag_results_are_connected_to_academic_profiles(self) -> None:
        backend = build_mock_backend()

        profiles = search_academic_profiles_with_graphrag(
            backend.engine,
            RetrievalQuery("artificial intelligence aged care", limit=5),
        )

        self.assertEqual(
            [profile.structured_information["name"] for profile in profiles],
            ["Dr Alice Chen", "Dr Bob Nguyen"],
        )
        self.assertTrue(all(profile.summary.status == "ok" for profile in profiles))

    def test_profile_without_supporting_evidence_is_insufficient(self) -> None:
        backend = build_mock_backend()
        academic = next(
            entity
            for entity in backend.repository.list_entities(entity_types=("Researcher",))
            if entity.label == "Dr Alice Chen"
        )
        repository = _RepositoryWithoutEvidence(backend.repository, academic.id)

        profile = AcademicProfileService(repository).get_profile(academic.id)

        self.assertIsNotNone(profile)
        assert profile is not None
        self.assertEqual(profile.summary.status, "insufficient_information")
        self.assertIn("Insufficient verified information", profile.summary.text)


class _RepositoryWithoutEvidence:
    def __init__(self, repository, academic_id: str) -> None:
        self.repository = repository
        self.academic_id = academic_id

    def get_entities(self, entity_ids):
        return self.repository.get_entities(entity_ids)

    def get_relationships(self, node_ids, *, relation_types=()):
        return self.repository.get_relationships(node_ids, relation_types=relation_types)

    def get_evidence(self, supported_ids):
        return ()

    def get_sources(self, source_record_ids):
        return ()


if __name__ == "__main__":
    unittest.main()