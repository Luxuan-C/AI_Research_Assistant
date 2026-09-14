from io import BytesIO
import json
import unittest
from unittest.mock import patch

from api_server import ApiHandler, create_live_application
from application import ResearchApplication
from test_supabase_retrieval import FakeSupabaseClient


def application_rows(*, academics=(), papers=()):
    return {
        "university": [{"id": "u1", "name": "Sydney University"}],
        "faculty": [],
        "discipline": [
            {"id": "d1", "name": "Computer Science", "faculty_id": None}
        ],
        "field": [],
        "journal": [],
        "academic": list(academics),
        "research_paper": list(papers),
    }


def academic_row(identifier, name, *, position=None, papers=()):
    return {
        "id": identifier,
        "name": name,
        "academic_position": position,
        "profile_url": f"https://example.edu/{identifier}",
        "orcid_url": None,
        "research_paper_ids": list(papers),
        "university_ids": ["u1"],
        "discipline_ids": ["d1"],
        "field_ids": [],
    }


def paper_row(identifier, title, *, keywords=(), academics=()):
    return {
        "id": identifier,
        "name": title,
        "publication_date": "2025-01-02",
        "doi": f"10.1000/{identifier}",
        "is_open_access": True,
        "open_access_url": f"https://example.org/{identifier}",
        "primary_url": None,
        "publication_type": "article",
        "incoming_citation_count": 0,
        "keywords": list(keywords),
        "outgoing_citations": [],
        "journal_id": None,
        "university_ids": [],
        "faculty_ids": [],
        "academic_ids": list(academics),
    }


class ApiIntegrationTests(unittest.TestCase):
    @staticmethod
    def get(application, path):
        captured = []
        handler = object.__new__(ApiHandler)
        handler.application = application
        handler.path = path
        handler.send_json = lambda status, payload: captured.append((status, payload))
        handler.do_GET()
        return captured[0]

    @staticmethod
    def post(application, path, payload):
        captured = []
        body = json.dumps(payload).encode("utf-8")
        handler = object.__new__(ApiHandler)
        handler.application = application
        handler.path = path
        handler.headers = {"Content-Length": str(len(body))}
        handler.rfile = BytesIO(body)
        handler.send_json = lambda status, result: captured.append((status, result))
        handler.do_POST()
        return captured[0]

    def test_researcher_endpoint_runs_pipeline_and_preserves_ranked_order(self):
        client = FakeSupabaseClient(
            application_rows(
                academics=(
                    academic_row("a2", "Robotics Researcher", position="robotics"),
                    academic_row(
                        "a1",
                        "Advanced Robotics Researcher",
                        position="robotics robotics",
                    ),
                )
            )
        )
        application = ResearchApplication.from_supabase_client(client, row_limit=2_000)

        status, payload = self.get(application, "/api/researchers?q=robotics")

        self.assertEqual(status, 200)
        self.assertEqual(
            [item["id"] for item in payload["researchers"]],
            ["a1", "a2"],
        )
        self.assertEqual(
            [item["rank"] for item in payload["researchers"]],
            [1, 2],
        )
        self.assertTrue(
            all(not item["id"].startswith("academic:") for item in payload["researchers"])
        )
        self.assertEqual(application.retrieval.corpus_build_count, 1)

    def test_researcher_beyond_first_supabase_page_is_returned(self):
        academics = [
            academic_row(f"{index:04d}", "Other Academic")
            for index in range(1, 1_001)
        ]
        academics.append(academic_row("1001", "Needle Academic"))
        client = FakeSupabaseClient(
            application_rows(academics=academics),
            server_page_cap=1_000,
        )
        application = ResearchApplication.from_supabase_client(client, row_limit=2_000)

        status, payload = self.get(
            application,
            "/api/researchers?q=Needle%20Academic",
        )

        self.assertEqual(status, 200)
        self.assertEqual(payload["researchers"][0]["id"], "1001")
        self.assertIn("1001", [item["id"] for item in payload["researchers"]])
        self.assertGreaterEqual(client.executions["academic"], 2)
        self.assertTrue(payload["truncated"])

    def test_researcher_search_uses_bounded_graph_enrichment(self):
        client = FakeSupabaseClient(
            application_rows(
                academics=(
                    academic_row("a1", "Graph Researcher", papers=("p1",)),
                ),
                papers=(
                    paper_row(
                        "p1",
                        "Assistive Robotics",
                        keywords=("assistive", "robotics"),
                        academics=("a1",),
                    ),
                ),
            )
        )
        application = ResearchApplication.from_supabase_client(client, row_limit=2_000)

        status, payload = self.get(
            application,
            "/api/researchers?q=assistive%20robotics",
        )

        self.assertEqual(status, 200)
        self.assertEqual([item["id"] for item in payload["researchers"]], ["a1"])

    def test_researcher_name_search_remains_case_insensitive_and_substring_based(self):
        client = FakeSupabaseClient(
            application_rows(
                academics=(academic_row("a1", "Ada Robotics Researcher"),)
            )
        )
        application = ResearchApplication.from_supabase_client(client, row_limit=2_000)

        status, payload = self.get(
            application,
            "/api/researchers?q=BOTICS%20RESE",
        )

        self.assertEqual(status, 200)
        self.assertEqual([item["id"] for item in payload["researchers"]], ["a1"])

    def test_ask_uses_ranked_publications_and_fails_closed_without_evidence(self):
        client = FakeSupabaseClient(
            application_rows(
                papers=(
                    paper_row("p2", "Care Systems", keywords=("robotics",)),
                    paper_row(
                        "p1",
                        "Robotics for Care",
                        keywords=("robotics", "robotics", "care"),
                    ),
                )
            )
        )
        application = ResearchApplication.from_supabase_client(client, row_limit=2_000)

        status, payload = self.post(
            application,
            "/api/ask",
            {"question": "robotics care"},
        )

        self.assertEqual(status, 200)
        self.assertEqual([paper["id"] for paper in payload["papers"]], ["p1", "p2"])
        self.assertEqual(payload["status"], "insufficient_information")
        self.assertEqual(payload["evidence_status"], "insufficient_evidence")
        self.assertIn("validated evidence", payload["answer"])
        self.assertNotIn("Supabase found", payload["answer"])

    def test_profile_hydrates_requested_id_through_bounded_repository(self):
        client = FakeSupabaseClient(
            application_rows(
                academics=(
                    academic_row(
                        "a1",
                        "Ada Researcher",
                        position="Professor",
                        papers=("p1", "p2", "p3"),
                    ),
                ),
                papers=(
                    paper_row(
                        "p1",
                        "Bounded Robotics",
                        keywords=("robotics",),
                        academics=("a1",),
                    ),
                    paper_row("p2", "Bounded Systems", academics=("a1",)),
                    paper_row("p3", "Bounded Evidence", academics=("a1",)),
                ),
            )
        )
        application = ResearchApplication.from_supabase_client(client, row_limit=2_000)

        status, payload = self.get(application, "/api/researchers/a1")

        self.assertEqual(status, 200)
        self.assertEqual(payload["id"], "a1")
        self.assertEqual(payload["university"], "Sydney University")
        self.assertEqual(payload["discipline"], "Computer Science")
        self.assertEqual(
            [paper["id"] for paper in payload["publications"]],
            ["p1", "p2", "p3"],
        )
        self.assertEqual(payload["summary_status"], "insufficient_information")
        self.assertIn("Insufficient verified information", payload["ai_summary"])
        self.assertEqual(client.executions["academic"], 1)
        self.assertEqual(client.executions["research_paper"], 1)

    def test_directory_options_preserve_frontend_shape_and_shared_repository(self):
        client = FakeSupabaseClient(application_rows())
        application = ResearchApplication.from_supabase_client(client, row_limit=2_000)

        first_status, first_payload = self.get(application, "/api/directory-options")
        second_status, second_payload = self.get(application, "/api/directory-options")

        self.assertEqual((first_status, second_status), (200, 200))
        self.assertEqual(first_payload, second_payload)
        self.assertEqual(first_payload["universities"], ["Sydney University"])
        self.assertEqual(first_payload["disciplines"], ["Computer Science"])
        self.assertIn("truncated", first_payload)
        self.assertEqual(client.executions["university"], 2)
        self.assertEqual(client.executions["discipline"], 2)

    def test_live_composition_is_lazy_and_uses_ranking_configuration(self):
        client = FakeSupabaseClient(application_rows())

        with patch("api_server.create_supabase_client", return_value=client) as create:
            application = create_live_application()

        create.assert_called_once_with()
        self.assertIsInstance(application, ResearchApplication)
        self.assertEqual(application.repository.row_limit, 4_000)
        self.assertEqual(sum(client.executions.values()), 0)


if __name__ == "__main__":
    unittest.main()
