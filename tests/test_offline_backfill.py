import unittest

from ranking.offline_backfill import (
    build_provenance_report,
    build_score_records,
    summarize_backfill,
)


class OfflineBackfillTests(unittest.TestCase):
    def test_backfill_builds_one_uuid_keyed_qia_record_per_paper(self):
        papers = [
            {
                "id": f"paper-{index}",
                "publication_date": "2020-01-01",
                "publication_type": "journal-article",
                "incoming_citation_count": index * 10,
                "academic_ids": ["a1"] if index < 2 else [f"a{index}"],
            }
            for index in range(5)
        ]
        academics = [
            {"id": "a1", "research_paper_ids": ["paper-0", "paper-1"]},
            *(
                {"id": f"a{index}", "research_paper_ids": [f"paper-{index}"]}
                for index in range(2, 5)
            ),
        ]

        records, snapshot = build_score_records(papers, academics)
        summary = summarize_backfill(records, snapshot, papers)

        self.assertEqual(len(records), 5)
        self.assertEqual(
            set(records[0]),
            {
                "research_paper_id",
                "paper_authority_score",
                "citation_influence_score",
                "author_authority_score",
            },
        )
        by_id = {row["research_paper_id"]: row for row in records}
        self.assertEqual(by_id["paper-0"]["citation_influence_score"], 0.0)
        self.assertIsNotNone(by_id["paper-0"]["author_authority_score"])
        self.assertTrue(summary["every_output_id_maps_to_source_paper"])
        self.assertEqual(summary["author_authority_status_count"]["observed"], 2)
        self.assertEqual(summary["author_authority_status_count"]["imputed"], 3)
        self.assertEqual(summary["author_authority_status_count"]["unavailable"], 0)
        self.assertEqual(summary["null_author_authority_rows"], 0)

        provenance = build_provenance_report(snapshot, summary)
        self.assertEqual(len(provenance["papers"]), 5)
        self.assertEqual(
            set(provenance["papers"][0]),
            {
                "research_paper_id",
                "author_authority_status",
                "author_authority_imputation_prior",
            },
        )
        self.assertNotIn("author_authority_status", records[0])

    def test_backfill_collapses_exact_duplicates_and_rejects_conflicts(self):
        row = {
            "id": "paper-1",
            "publication_date": "2020-01-01",
            "publication_type": "article",
            "incoming_citation_count": 2,
            "academic_ids": [],
        }
        records, snapshot = build_score_records([row, dict(row)], [])
        self.assertEqual(len(records), 1)
        self.assertEqual(snapshot.duplicate_paper_rows, 1)

        with self.assertRaisesRegex(ValueError, "Conflicting factor inputs"):
            build_score_records([row, {**row, "incoming_citation_count": 3}], [])


if __name__ == "__main__":
    unittest.main()
