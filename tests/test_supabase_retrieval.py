from collections import Counter
from datetime import date
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from ranking.supabase_config import (
    SupabaseConfigurationError,
    load_supabase_settings,
)
from ranking.supabase_retrieval import (
    READABLE_TABLES,
    SupabaseReadError,
    SupabaseReadRepository,
    SupabaseRetrievalPort,
    SupabaseSchemaRelationshipGraph,
    safe_error_detail,
    smoke_test_read_access,
)
from ranking import (
    FusionService,
    GraphBudget,
    QueryPlanner,
    RankingService,
    RetrievalRankingPipeline,
)


class FakeQuery:
    def __init__(self, client, table):
        self.client = client
        self.table = table
        self.maximum = None
        self.identifiers = None
        self.after_id = None

    def select(self, _columns):
        return self

    def order(self, _column):
        return self

    def limit(self, maximum):
        self.maximum = maximum
        return self

    def in_(self, _column, identifiers):
        self.identifiers = {str(value) for value in identifiers}
        return self

    def gt(self, _column, value):
        self.after_id = str(value)
        return self

    def execute(self):
        self.client.executions[self.table] += 1
        if self.table in self.client.failures:
            raise RuntimeError(self.client.failures[self.table])
        rows = sorted(self.client.data.get(self.table, ()), key=lambda row: str(row.get("id") or ""))
        if self.identifiers is not None:
            rows = [row for row in rows if str(row.get("id")) in self.identifiers]
        if self.after_id is not None:
            rows = [row for row in rows if str(row.get("id") or "") > self.after_id]
        if self.maximum is not None:
            rows = rows[: min(self.maximum, self.client.server_page_cap)]
        return SimpleNamespace(data=rows)


class FakeSupabaseClient:
    def __init__(self, data=None, failures=None, *, server_page_cap=1000):
        self.data = dict(data or {})
        self.failures = dict(failures or {})
        self.server_page_cap = server_page_cap
        self.executions = Counter()

    def table(self, table):
        return FakeQuery(self, table)


def supabase_rows():
    return {
        "university": [
            {"id": "u1", "name": "Sydney University", "ror_url": "https://ror.org/u1"}
        ],
        "faculty": [{"id": "fac1", "name": "Engineering"}],
        "discipline": [{"id": "d1", "name": "Computer Science", "faculty_id": "fac1"}],
        "field": [{"id": "f1", "name": "Robotics", "discipline_id": "d1"}],
        "journal": [{"id": "j1", "name": "Robotics Journal"}],
        "academic": [
            {
                "id": "a1",
                "name": "Ada Researcher",
                "academic_position": "Professor",
                "profile_url": "https://example.edu/ada",
                "orcid_url": "https://orcid.org/a1",
                "research_paper_ids": ["p1"],
                "university_ids": ["u1"],
                "discipline_ids": ["d1"],
                "field_ids": ["f1"],
            }
        ],
        "research_paper": [
            {
                "id": "p1",
                "name": "Assistive Robotics in Care",
                "publication_date": "2025-01-02",
                "doi": "10.1000/robotics",
                "is_open_access": True,
                "open_access_url": "https://example.org/p1",
                "primary_url": None,
                "publication_type": "article",
                "incoming_citation_count": 500,
                "keywords": ["robotics", "care"],
                "outgoing_citations": ["p2"],
                "journal_id": "j1",
                "university_ids": ["u1"],
                "faculty_ids": ["fac1"],
                "academic_ids": ["a1"],
            },
            {
                "id": "p2",
                "name": "Foundations of Human Machine Interaction",
                "publication_date": "2020-01-02",
                "keywords": ["interaction"],
                "outgoing_citations": [],
                "is_open_access": False,
                "publication_type": "book",
                "university_ids": [],
                "faculty_ids": [],
                "academic_ids": [],
            },
        ],
        "score": [
            {
                "id": "s1",
                "research_paper_id": "p1",
            }
        ],
    }


class SupabaseConfigurationTests(unittest.TestCase):
    def test_required_environment_variables_are_validated_without_values(self):
        with self.assertRaises(SupabaseConfigurationError) as raised:
            load_supabase_settings({"SUPABASE_URL": "secret-url"})

        self.assertIn("SUPABASE_KEY", str(raised.exception))
        self.assertNotIn("secret-url", str(raised.exception))

    def test_sdk_errors_redact_configured_url_and_key(self):
        with patch.dict(
            "os.environ",
            {"SUPABASE_URL": "https://secret-project", "SUPABASE_KEY": "secret-key"},
        ):
            detail = safe_error_detail(
                RuntimeError("request https://secret-project authorization=secret-key failed")
            )

        self.assertNotIn("secret-project", detail)
        self.assertNotIn("secret-key", detail)
        self.assertIn("<redacted>", detail)


class SupabaseBoundaryTests(unittest.TestCase):
    @staticmethod
    def filtered_entity_ids(query: str, filters: dict[str, object]) -> set[str]:
        client = FakeSupabaseClient(supabase_rows())
        retrieval = SupabaseRetrievalPort(SupabaseReadRepository(client))
        plan = QueryPlanner().plan(query, as_of=date(2026, 9, 9), filters=filters)
        return {hit.entity.entity_id for hit in retrieval.retrieve(plan)["lexical"]}

    def test_read_only_smoke_checks_every_fixed_table(self):
        client = FakeSupabaseClient(supabase_rows())

        readable = smoke_test_read_access(client)

        self.assertEqual(readable, READABLE_TABLES)
        self.assertEqual(set(client.executions), set(READABLE_TABLES))
        self.assertTrue(all(client.executions[table] == 1 for table in READABLE_TABLES))

    def test_read_failure_names_exact_table_and_stops(self):
        client = FakeSupabaseClient(supabase_rows(), {"discipline": "permission denied by RLS"})

        with self.assertRaises(SupabaseReadError) as raised:
            smoke_test_read_access(client)

        self.assertEqual(raised.exception.table, "discipline")
        self.assertEqual(raised.exception.detail, "permission denied by RLS")
        self.assertEqual(client.executions["field"], 0)

    def test_retrieval_exposes_lexical_only_and_preserves_raw_schema_as_metadata(self):
        client = FakeSupabaseClient(supabase_rows())
        retrieval = SupabaseRetrievalPort(SupabaseReadRepository(client))
        plan = QueryPlanner().plan("assistive robotics", as_of=date(2026, 9, 9))

        channels = retrieval.retrieve(plan)

        self.assertEqual(tuple(channels), ("lexical",))
        self.assertTrue(channels["lexical"])
        self.assertEqual(channels["lexical"][0].entity.entity_id, "research_paper:p1")
        paper = next(hit.entity for hit in channels["lexical"] if hit.entity.kind == "publication")
        self.assertIsNone(paper.citation_score)
        self.assertIsNone(paper.paper_authority_score)

    def test_pagination_retrieves_a_matching_academic_beyond_the_first_server_page(self):
        academics = [
            {
                "id": f"{index:04d}",
                "name": "Other Researcher",
                "research_paper_ids": [],
                "university_ids": [],
                "discipline_ids": [],
                "field_ids": [],
            }
            for index in range(1, 1_001)
        ]
        academics.append(
            {
                "id": "1001",
                "name": "Jayavardhana Gubbi",
                "research_paper_ids": [],
                "university_ids": [],
                "discipline_ids": [],
                "field_ids": [],
            }
        )
        client = FakeSupabaseClient({"academic": academics})
        repository = SupabaseReadRepository(client, row_limit=2_000)
        retrieval = SupabaseRetrievalPort(repository)
        plan = QueryPlanner().plan(
            "Jayavardhana Gubbi",
            as_of=date(2026, 9, 12),
            target_kinds=("researcher",),
        )

        channels = retrieval.retrieve(plan)

        self.assertEqual([hit.entity.entity_id for hit in channels["lexical"]], ["academic:1001"])
        self.assertEqual(len(repository.rows("academic")), 1_001)
        self.assertEqual(client.executions["academic"], 3)

    def test_id_batch_reads_paginate_without_duplicates_or_skips(self):
        academics = [{"id": f"{index:04d}", "name": "Researcher"} for index in range(1, 1_501)]
        client = FakeSupabaseClient({"academic": academics})
        repository = SupabaseReadRepository(client, row_limit=1_500)

        rows = repository.rows_by_ids(
            "academic",
            [row["id"] for row in academics],
            batch_size=2_000,
        )

        self.assertEqual([row["id"] for row in rows], [row["id"] for row in academics])
        self.assertEqual(len({row["id"] for row in rows}), 1_500)
        self.assertEqual(client.executions["academic"], 2)

    def test_filters_only_evaluate_fields_supported_by_each_entity_kind(self):
        query = "Ada Assistive Foundations"

        with self.subTest("shared university filter"):
            self.assertEqual(
                self.filtered_entity_ids(query, {"university_id": "u1"}),
                {"academic:a1", "research_paper:p1"},
            )
        with self.subTest("academic faculty filter is unsupported"):
            self.assertEqual(
                self.filtered_entity_ids(query, {"faculty_id": "fac1"}),
                {"research_paper:p1"},
            )
        with self.subTest("discipline filter is academic-only"):
            self.assertEqual(
                self.filtered_entity_ids(query, {"discipline_id": "d1"}),
                {"academic:a1"},
            )
        with self.subTest("field filter is academic-only"):
            self.assertEqual(
                self.filtered_entity_ids(query, {"field_id": "f1"}),
                {"academic:a1"},
            )
        with self.subTest("open-access filter is paper-only"):
            self.assertEqual(
                self.filtered_entity_ids(query, {"is_open_access": True}),
                {"research_paper:p1"},
            )
        with self.subTest("publication type filter is paper-only"):
            self.assertEqual(
                self.filtered_entity_ids(query, {"publication_type": "book"}),
                {"research_paper:p2"},
            )

    def test_pipeline_reuses_batched_reads_and_expands_fixed_relationships(self):
        client = FakeSupabaseClient(supabase_rows())
        repository = SupabaseReadRepository(client)
        pipeline = RetrievalRankingPipeline(
            retrieval=SupabaseRetrievalPort(repository),
            fusion=FusionService(),
            expansion=SupabaseSchemaRelationshipGraph(repository),
            ranking=RankingService(),
        )
        plan = QueryPlanner().plan("assistive robotics", as_of=date(2026, 9, 9))

        first = pipeline.retrieve_and_rank(plan)
        second = pipeline.retrieve_and_rank(plan)

        self.assertEqual(first, second)
        self.assertTrue(first.ranked)
        self.assertIn("discipline:d1", first.expansion.paths)
        self.assertEqual(client.executions["academic"], 2)
        self.assertEqual(client.executions["research_paper"], 2)
        self.assertTrue(
            all(
                client.executions[table] <= 2
                for table in SupabaseSchemaRelationshipGraph.GRAPH_TABLES
            )
        )

    def test_graph_prefetch_obeys_neighbor_budget(self):
        client = FakeSupabaseClient(supabase_rows())
        repository = SupabaseReadRepository(client)
        retrieval = SupabaseRetrievalPort(repository)
        plan = QueryPlanner().plan("assistive robotics", as_of=date(2026, 9, 9))
        fused = FusionService().fuse(retrieval.retrieve(plan))
        graph = SupabaseSchemaRelationshipGraph(
            repository,
            budget=GraphBudget(
                max_hops=2,
                max_entities=20,
                max_relationships=20,
                max_neighbors_per_node=1,
            ),
        )

        expansion = graph.expand(plan, fused)

        self.assertTrue(expansion.truncated)
        self.assertEqual(client.executions["discipline"], 1)
        self.assertEqual(client.executions["university"], 0)
        self.assertEqual(client.executions["faculty"], 0)
        self.assertEqual(client.executions["journal"], 0)


if __name__ == "__main__":
    unittest.main()
