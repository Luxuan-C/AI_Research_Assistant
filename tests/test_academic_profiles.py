from datetime import date
import unittest

from academic_profiles import AcademicProfileService, AcademicProfileSnapshot
from application import (
    search_academic_profiles,
    search_academic_profiles_with_ranking,
    search_papers,
)
from ranking import RESEARCHER, FusionService, QueryPlanner, RankingService, RetrievalRankingPipeline
from support import build_mock_scenario


class AcademicProfileTests(unittest.TestCase):
    def setUp(self) -> None:
        self.scenario = build_mock_scenario()
        self.alice = next(
            entity
            for entity in self.scenario.entities
            if entity.label == "Dr Alice Chen"
        )
        self.bob = next(
            entity
            for entity in self.scenario.entities
            if entity.label == "Dr Bob Nguyen"
        )

    def profile_snapshot(
        self,
        academic=None,
        *,
        evidence=None,
        searchable_text=(),
    ) -> AcademicProfileSnapshot:
        academic = self.alice if academic is None else academic
        return AcademicProfileSnapshot(
            academic=academic,
            entities={entity.entity_id: entity for entity in self.scenario.entities},
            relationships=tuple(self.scenario.graph.edges.values()),
            validated_evidence_by_id=self.scenario.evidence if evidence is None else evidence,
            searchable_text=searchable_text
            or ("Alice Chen", "trustworthy artificial intelligence aged care"),
        )

    def test_profile_contains_structured_data_publications_and_citations(self) -> None:
        profile = AcademicProfileService().get_profile(self.profile_snapshot())

        self.assertEqual(profile.structured_information["name"], "Dr Alice Chen")
        self.assertEqual(
            profile.structured_information["institution"],
            "The University of Sydney",
        )
        self.assertTrue(profile.publications)
        self.assertEqual(profile.summary.status, "ok")
        self.assertIn("[", profile.summary.text)
        self.assertTrue(all(citation.uri for citation in profile.summary.citations))

    def test_unknown_name_does_not_produce_a_profile(self) -> None:
        profiles = search_academic_profiles((self.profile_snapshot(),), "missing")

        self.assertEqual(profiles, [])

    def test_users_can_find_profiles_without_knowing_academic_id(self) -> None:
        profiles = search_academic_profiles((self.profile_snapshot(),), "alice chen")

        self.assertEqual(
            [profile.structured_information["name"] for profile in profiles],
            ["Dr Alice Chen"],
        )

    def test_users_can_find_profiles_by_snapshot_keyword(self) -> None:
        profiles = search_academic_profiles((self.profile_snapshot(),), "trustworthy")

        self.assertEqual(
            [profile.structured_information["name"] for profile in profiles],
            ["Dr Alice Chen"],
        )

    def test_ranked_researchers_are_connected_to_academic_profiles(self) -> None:
        pipeline = RetrievalRankingPipeline(
            retrieval=self.scenario.retrieval,
            fusion=FusionService(),
            expansion=self.scenario.graph,
            ranking=RankingService(),
        )
        plan = QueryPlanner().plan(
            "artificial intelligence aged care",
            as_of=date(2026, 9, 13),
            target_kinds=(RESEARCHER,),
            limit=5,
        )

        profiles = search_academic_profiles_with_ranking(
            pipeline,
            plan,
            (
                self.profile_snapshot(),
                self.profile_snapshot(
                    self.bob,
                    searchable_text=("Bob Nguyen", "assistive robotics aged care"),
                ),
            ),
        )

        self.assertEqual(
            [profile.structured_information["name"] for profile in profiles],
            ["Dr Alice Chen", "Dr Bob Nguyen"],
        )
        self.assertTrue(all(profile.summary.status == "ok" for profile in profiles))

    def test_profile_without_supporting_evidence_is_insufficient(self) -> None:
        profile = AcademicProfileService().get_profile(self.profile_snapshot(evidence={}))

        self.assertEqual(profile.summary.status, "insufficient_information")
        self.assertIn("Insufficient verified information", profile.summary.text)

    def test_paper_search_uses_the_current_retrieval_ranking_pipeline(self) -> None:
        pipeline = RetrievalRankingPipeline(
            retrieval=self.scenario.retrieval,
            fusion=FusionService(),
            expansion=self.scenario.graph,
            ranking=RankingService(),
        )
        plan = QueryPlanner().plan("aged care", as_of=date(2026, 9, 13))

        results = search_papers(pipeline, plan)

        self.assertTrue(results)
        self.assertTrue(all("paper_id" in result for result in results))
        self.assertTrue(all("title" in result for result in results))


if __name__ == "__main__":
    unittest.main()
