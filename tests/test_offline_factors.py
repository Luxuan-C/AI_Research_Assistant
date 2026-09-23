from datetime import date
from statistics import mean, median
import unittest

from ranking.offline_factors import (
    MIN_PEER_COHORT_SIZE,
    calculate_offline_factors,
    factor_distribution,
)
from ranking.paper_ranking import DEFAULT_PROFILES, _recency


def paper(
    paper_id,
    citations,
    year=2020,
    publication_type="journal-article",
    authors=(),
    **extra,
):
    row = {
        "id": paper_id,
        "publication_date": f"{year}-06-01" if year is not None else None,
        "publication_type": publication_type,
        "incoming_citation_count": citations,
        "academic_ids": list(authors),
    }
    row.update(extra)
    return row


class OfflineFactorTests(unittest.TestCase):
    def test_citation_influence_is_monotonic_compressed_and_cohort_normalized(self):
        rows = [paper(str(i), citations) for i, citations in enumerate((0, 1, 10, 100, 10_000))]

        result = calculate_offline_factors(rows)
        scores = [result.papers[str(i)].citation_influence for i in range(5)]

        self.assertEqual(scores[0], 0.0)
        self.assertEqual(scores[-1], 1.0)
        self.assertTrue(all(left < right for left, right in zip(scores[1:], scores[2:])))
        self.assertGreater(scores[2], scores[1])
        self.assertLess(scores[2], 0.5)
        self.assertLess(scores[3], 1.0)
        self.assertEqual(result.i_cohort_counts["year_type"], 5)

    def test_sparse_citation_cohorts_fall_back_from_year_type_to_year(self):
        rows = [paper(f"a{i}", i + 1, year=2020, publication_type="article") for i in range(4)]
        rows.append(paper("book", 20, year=2020, publication_type="book"))

        result = calculate_offline_factors(rows)

        self.assertTrue(all(item.citation_cohort == "year" for item in result.papers.values()))
        self.assertEqual(result.i_cohort_counts["year"], 5)

    def test_sparse_years_fall_back_to_global_and_multifield_is_not_primary(self):
        rows = [
            paper("a", 1, year=2018, field_ids=["f1"]),
            paper("b", 2, year=2019, field_ids=["f1", "f2"]),
            paper("c", 3, year=2020),
            paper("d", 4, year=2021),
            paper("e", 5, year=2022),
        ]

        result = calculate_offline_factors(rows)

        self.assertTrue(all(item.citation_cohort == "global" for item in result.papers.values()))
        self.assertEqual(result.i_cohort_counts["global"], 5)

    def test_field_year_type_is_used_only_for_a_single_explicit_paper_field(self):
        rows = [paper(str(i), i + 1, field_id="f1") for i in range(MIN_PEER_COHORT_SIZE)]

        result = calculate_offline_factors(rows)

        self.assertTrue(all(item.citation_cohort == "field_year_type" for item in result.papers.values()))

    def test_missing_citations_remain_unavailable_and_empty_or_singleton_are_defined(self):
        result = calculate_offline_factors([paper("missing", None)])
        self.assertIsNone(result.papers["missing"].citation_influence)
        self.assertIsNone(result.papers["missing"].quality)
        self.assertIsNone(result.papers["missing"].author_authority)
        self.assertEqual(calculate_offline_factors([]).papers, {})

        singleton = calculate_offline_factors([paper("only", 7)])
        self.assertEqual(singleton.papers["only"].citation_influence, 1.0)
        self.assertEqual(singleton.papers["only"].quality, 0.5)
        self.assertEqual(singleton.papers["only"].citation_cohort, "global")

    def test_missing_year_type_and_citation_are_counted_without_fabricated_scores(self):
        rows = [
            paper("no-year", 0, year=None),
            paper("no-type", 4, publication_type=None),
            paper("no-citations", None),
            {"publication_date": "2020-01-01", "incoming_citation_count": 3},
        ]

        result = calculate_offline_factors(rows)

        self.assertEqual(result.missing_paper_id_rows, 1)
        self.assertEqual(result.papers_with_citation_data, 2)
        self.assertEqual(result.papers_with_year, 2)
        self.assertEqual(result.papers_with_type, 2)
        self.assertEqual(result.papers["no-year"].citation_cohort, "global")
        self.assertEqual(result.papers["no-type"].citation_cohort, "global")
        self.assertIsNone(result.papers["no-citations"].citation_influence)

    def test_quality_uses_percentile_rank_and_year_plus_minus_one_fallback(self):
        rows = [paper(f"y{i}", i + 1, year=2020, publication_type=f"type-{i}") for i in range(4)]
        rows.extend(
            paper(f"n{i}", citations, year=2019, publication_type=f"other-{i}")
            for i, citations in enumerate((200, 2, 3))
        )

        result = calculate_offline_factors(rows)

        self.assertTrue(all(item.quality_cohort == "year_plus_minus_one" for item in result.papers.values()))
        self.assertEqual(result.papers["y0"].quality, 0.0)
        self.assertGreater(result.papers["y3"].quality, result.papers["y0"].quality)
        for item in result.papers.values():
            self.assertGreaterEqual(item.quality, 0.0)
            self.assertLessEqual(item.quality, 1.0)
        self.assertNotEqual(result.papers["y2"].quality, result.papers["y2"].citation_influence)
        self.assertEqual(
            result.papers,
            calculate_offline_factors(list(reversed(rows))).papers,
        )

    def test_quality_uses_global_fallback_when_year_and_adjacent_are_sparse(self):
        rows = [paper("a", 1, year=2000)]
        rows.extend(paper(f"b{i}", i + 1, year=2010 + i) for i in range(4))

        result = calculate_offline_factors(rows)

        self.assertTrue(all(item.quality_cohort == "global" for item in result.papers.values()))

    def test_academic_authority_uses_mean_of_top_five_papers(self):
        rows = [paper(f"p{i}", citations, authors=("a1",)) for i, citations in enumerate((1, 2, 3, 4, 5, 100))]
        result = calculate_offline_factors(rows)
        scores = sorted(
            (item.citation_influence for item in result.papers.values()),
            reverse=True,
        )

        self.assertAlmostEqual(result.academic_authority["a1"], sum(scores[:5]) / 5)

    def test_paper_authority_is_leave_one_out_and_averages_available_authors(self):
        rows = [
            paper("p1", 100, authors=("a1", "a2")),
            paper("p2", 10, authors=("a1",)),
            paper("p3", 50, authors=("a2",)),
        ]
        result = calculate_offline_factors(rows)
        i = {key: item.citation_influence for key, item in result.papers.items()}

        self.assertAlmostEqual(result.papers["p1"].author_authority, (i["p2"] + i["p3"]) / 2)
        self.assertEqual(result.papers["p2"].author_authority, i["p1"])
        self.assertEqual(result.papers["p3"].author_authority, i["p1"])
        self.assertTrue(
            all(
                result.papers[paper_id].author_authority_status == "observed"
                for paper_id in ("p1", "p2", "p3")
            )
        )
        solo = calculate_offline_factors([paper("solo", 5, authors=("lonely",))])
        self.assertIsNone(solo.papers["solo"].author_authority)
        self.assertEqual(solo.papers["solo"].author_authority_status, "unavailable")

    def test_no_history_uses_median_observed_academic_authority(self):
        peers = [
            paper(f"peer-{index}", citations, authors=(f"peer-author-{index}",))
            for index, citations in enumerate((10, 20, 30, 40, 50), start=1)
        ]
        rows = [paper("target", 5, authors=("target-author",)), *peers]

        result = calculate_offline_factors(rows)
        leave_target_out = calculate_offline_factors(peers)
        observed_authorities = [
            value
            for value in leave_target_out.academic_authority.values()
            if value is not None
        ]
        expected_prior = median(observed_authorities)
        target = result.papers["target"]

        self.assertEqual(target.author_authority_status, "imputed")
        self.assertEqual(target.author_authority, expected_prior)
        self.assertEqual(target.author_authority_imputation_prior, expected_prior)
        self.assertGreaterEqual(target.author_authority, 0.0)
        self.assertLessEqual(target.author_authority, 1.0)

    def test_imputation_median_is_robust_to_an_authority_outlier(self):
        peer_citations = (1, 2, 3, 4, 5, 1_000_000_000)
        peers = [
            paper(f"peer-{index}", citations, authors=(f"peer-author-{index}",))
            for index, citations in enumerate(peer_citations)
        ]
        rows = [paper("target", 7, authors=("target-author",)), *peers]

        result = calculate_offline_factors(rows)
        reference = calculate_offline_factors(peers)
        authorities = [value for value in reference.academic_authority.values() if value is not None]
        target = result.papers["target"]

        self.assertEqual(target.author_authority_imputation_prior, median(authorities))
        self.assertNotEqual(target.author_authority_imputation_prior, mean(authorities))

    def test_fallback_does_not_use_the_target_papers_own_citation_influence(self):
        peers = [
            paper(f"peer-{index}", citations, authors=(f"peer-author-{index}",))
            for index, citations in enumerate((1, 2, 3, 4, 5))
        ]
        low_target = paper("target", 1, authors=("target-author",))
        high_target = paper("target", 1_000_000_000, authors=("target-author",))

        low = calculate_offline_factors([low_target, *peers]).papers["target"]
        high = calculate_offline_factors([high_target, *peers]).papers["target"]

        self.assertNotEqual(low.citation_influence, high.citation_influence)
        self.assertEqual(low.author_authority_status, "imputed")
        self.assertEqual(high.author_authority_status, "imputed")
        self.assertEqual(low.author_authority, high.author_authority)
        self.assertEqual(
            low.author_authority_imputation_prior,
            high.author_authority_imputation_prior,
        )

    def test_fallback_preserves_unavailable_when_no_other_authority_exists(self):
        rows = [paper("target", 9, authors=("only-author",))]

        result = calculate_offline_factors(rows)
        target = result.papers["target"]

        self.assertIsNone(target.author_authority)
        self.assertIsNone(target.author_authority_imputation_prior)
        self.assertEqual(target.author_authority_status, "unavailable")

    def test_authority_fallback_does_not_change_q_or_i(self):
        rows = [
            paper("target", 12, authors=("target-author",)),
            *(
                paper(f"peer-{index}", citations, authors=(f"peer-author-{index}",))
                for index, citations in enumerate((1, 3, 5, 7, 9))
            ),
        ]
        without_authors = [{**row, "academic_ids": []} for row in rows]

        with_authors = calculate_offline_factors(rows)
        no_author_path = calculate_offline_factors(without_authors)

        self.assertEqual(
            {
                paper_id: (factor.quality, factor.citation_influence)
                for paper_id, factor in with_authors.papers.items()
            },
            {
                paper_id: (factor.quality, factor.citation_influence)
                for paper_id, factor in no_author_path.papers.items()
            },
        )

    def test_author_relationships_are_union_deduplicated_and_unavailable_values_stay_missing(self):
        rows = [paper("p1", 10), paper("p2", 20, authors=("a1", "a1"))]
        result = calculate_offline_factors(rows, {"a1": ["p1", "p2", "p2"], "a2": ["absent"]})

        self.assertEqual(result.paper_author_relationships, 2)
        self.assertEqual(result.papers_with_author_links, 2)
        self.assertEqual(result.academics_used, 2)
        self.assertIsNotNone(result.papers["p1"].author_authority)
        self.assertIsNone(result.academic_authority["a2"])

    def test_exact_duplicate_papers_collapse_and_conflicting_duplicates_fail_closed(self):
        row = paper("p1", 5)
        result = calculate_offline_factors([row, dict(row)])
        self.assertEqual(len(result.papers), 1)
        self.assertEqual(result.duplicate_paper_rows, 1)

        with self.assertRaisesRegex(ValueError, "Conflicting factor inputs"):
            calculate_offline_factors([row, paper("p1", 6)])

    def test_distribution_reports_requested_quantiles_and_missing_coverage(self):
        stats = factor_distribution([0.0, 0.25, 0.5, 0.75, 1.0, None])

        self.assertEqual(stats, {"min": 0.0, "p25": 0.25, "median": 0.5, "p75": 0.75, "p90": 0.9, "max": 1.0})
        self.assertTrue(all(value is None for value in factor_distribution([None]).values()))

    def test_h_t_and_profile_semantics_remain_unchanged(self):
        self.assertEqual(
            {
                name: (
                    profile.publication_retrieval_weight,
                    profile.publication_graph_weight,
                    profile.citation_weight,
                    profile.recency_weight,
                    profile.paper_authority_weight,
                    profile.publication_half_life_years,
                )
                for name, profile in DEFAULT_PROFILES.items()
            },
            {
                "GENERAL": (0.65, 0.20, 0.07, 0.03, 0.05, 8.0),
                "RECENT": (0.60, 0.18, 0.04, 0.18, 0.00, 2.0),
                "FOUNDATIONAL": (0.65, 0.20, 0.12, 0.00, 0.03, 25.0),
            },
        )
        self.assertEqual(_recency(date(2018, 1, 1), date(2026, 1, 1), 8.0), 0.5)


if __name__ == "__main__":
    unittest.main()
