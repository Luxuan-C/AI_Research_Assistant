from datetime import date
from types import SimpleNamespace
import unittest
import json
from unittest.mock import patch

from ranking import (
    Answer,
    AnswerOrchestrator,
    EvidenceItem,
    EvidencePack,
    EvidencePackBuilder,
    FusionService,
    QueryPlanner,
    RankingService,
    RetrievalRankingPipeline,
)
from ranking.gemini_generation import (
    GeminiGenerationAdapter,
    build_generation_prompt,
    normalize_doi,
)
from support import build_mock_scenario


def interaction(answer, annotations=(), context_results=()):
    steps = []
    for result in context_results:
        steps.append(
            SimpleNamespace(
                type="url_context_result",
                content=[SimpleNamespace(url=result[0], status=result[1])],
            )
        )
    steps.append(
        SimpleNamespace(
            type="model_output",
            content=[
                SimpleNamespace(
                    type="text",
                    text=answer,
                    annotations=list(annotations),
                )
            ],
        )
    )
    return SimpleNamespace(steps=steps)


class FakeInteractions:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


class FakeGeminiClient:
    def __init__(self, response):
        self.interactions = FakeInteractions(response)


class GeminiGenerationTests(unittest.TestCase):
    def test_internal_evidence_is_cited_and_sent_without_external_tools(self):
        source = EvidenceItem(
            "ev-1",
            "paper-1",
            "https://papers.example.org/1",
            "The study evaluated a supervised learning method.",
        )
        pack = EvidencePack(
            "ready",
            (source,),
            ("paper-1",),
            ({"paper_id": "paper-1", "title": "Evidence Paper", "rank": 1},),
        )
        client = FakeGeminiClient(interaction("The paper evaluates a supervised method [S1]."))
        adapter = GeminiGenerationAdapter(api_key="test-key", client=client)

        generated = adapter.synthesize("What method was evaluated?", pack)

        self.assertEqual(generated.status, "generated")
        self.assertEqual(generated.citations[0].evidence_id, "ev-1")
        self.assertEqual(generated.citations[0].source_title, "Evidence Paper")
        self.assertEqual(generated.citations[0].source_origin, "internal")
        self.assertEqual(client.interactions.calls[0]["tools"], [])
        self.assertEqual(len(client.interactions.calls), 1)
        self.assertFalse(client.interactions.calls[0]["store"])
        self.assertIn("title alone never supports", client.interactions.calls[0]["input"])

    def test_external_url_context_and_search_citations_keep_provenance(self):
        url_context_url = "https://papers.example.org/article.pdf"
        search_url = "https://journals.example.org/review"
        pack = EvidencePack(
            "insufficient_evidence",
            (),
            ("paper-1",),
            ({
                "paper_id": "paper-1",
                "title": "Discovery title only",
                "source_urls": (url_context_url,),
                "factor_scores": {"A_author_authority": 0.9},
                "factor_availability": {"Q": False, "I": False, "A": False},
            },),
        )
        citations = [
            SimpleNamespace(type="url_citation", title="Article", url=url_context_url),
            SimpleNamespace(type="url_citation", title="Review", url=search_url),
        ]
        client = FakeGeminiClient(
            interaction(
                "The sources discuss the methods.",
                citations,
                ((url_context_url, "success"),),
            )
        )
        adapter = GeminiGenerationAdapter(api_key="test-key", client=client)

        generated = adapter.synthesize("Compare the research", pack)

        self.assertEqual(generated.status, "generated")
        self.assertEqual(
            [source.source_origin for source in generated.external_sources],
            ["external_url_context", "external_google_search"],
        )
        self.assertTrue(all(not hasattr(source, "factor_scores") for source in generated.external_sources))
        self.assertEqual(
            client.interactions.calls[0]["tools"],
            [{"type": "url_context"}, {"type": "google_search"}],
        )
        self.assertIn(url_context_url, client.interactions.calls[0]["input"])
        prompt_context = json.loads(client.interactions.calls[0]["input"].rsplit("\n", 1)[-1])
        factor_scores = prompt_context["ranked_papers_discovery_context_only"][0]["factor_scores"]
        self.assertIsNone(factor_scores["A_author_authority"])

    def test_no_grounded_citation_remains_fail_closed(self):
        pack = EvidencePack(
            "insufficient_evidence",
            (),
            ("paper-1",),
            ({"paper_id": "paper-1", "title": "Metadata only", "source_urls": ()},),
        )
        client = FakeGeminiClient(interaction("An uncited answer"))
        adapter = GeminiGenerationAdapter(api_key="test-key", client=client)

        generated = adapter.synthesize("Ask", pack)

        self.assertEqual(generated.status, "insufficient_evidence")
        self.assertEqual(generated.answer, "")
        self.assertEqual(generated.citations, ())

    def test_inaccessible_url_context_result_is_not_accepted_as_evidence(self):
        url = "https://papers.example.org/unavailable.pdf"
        pack = EvidencePack(
            "insufficient_evidence",
            (),
            ("paper-1",),
            ({"paper_id": "paper-1", "title": "Paper", "source_urls": (url,)},),
        )
        citation = SimpleNamespace(type="url_citation", title="Paper", url=url)
        client = FakeGeminiClient(
            interaction("Unsupported text", [citation], ((url, "unsafe"),))
        )
        adapter = GeminiGenerationAdapter(api_key="test-key", client=client)

        generated = adapter.synthesize("Question", pack)

        self.assertEqual(generated.status, "insufficient_evidence")
        self.assertEqual(generated.citations, ())

    def test_missing_key_is_unavailable_and_never_constructs_a_client(self):
        adapter = GeminiGenerationAdapter(api_key=None)
        self.assertFalse(adapter.available)
        self.assertEqual(adapter.unavailable_status, "provider_unavailable")

    def test_environment_model_and_timeout_are_applied_to_client(self):
        response = interaction(
            "Grounded answer",
            [SimpleNamespace(
                type="url_citation",
                title="Source",
                url="https://source.example.org/paper",
            )],
        )
        client = FakeGeminiClient(response)
        client_configuration = []

        def client_factory(api_key, timeout_ms):
            client_configuration.append((api_key, timeout_ms))
            return client

        with patch.dict(
            "os.environ",
            {"GEMINI_API_KEY": "test-secret", "GEMINI_MODEL": "gemini-test-model"},
            clear=False,
        ):
            adapter = GeminiGenerationAdapter.from_environment(
                client_factory=client_factory
            )

        pack = EvidencePack(
            "insufficient_evidence",
            (),
            ("paper-1",),
            ({"paper_id": "paper-1", "title": "Paper", "source_urls": ()},),
        )
        adapter.synthesize("Question", pack)

        self.assertEqual(client_configuration, [("test-secret", 30_000)])
        self.assertEqual(client.interactions.calls[0]["model"], "gemini-test-model")

    def test_doi_url_normalization_repairs_repeated_host_and_rejects_bad_doi(self):
        self.assertEqual(
            normalize_doi("https://doi.org/https://doi.org/10.1000/test"),
            "https://doi.org/10.1000/test",
        )
        self.assertIsNone(normalize_doi("https://doi.org/not-a-doi"))

    def test_prompt_does_not_forward_malformed_or_local_doi_candidates(self):
        pack = EvidencePack(
            "insufficient_evidence",
            (),
            ("paper-1",),
            ({
                "paper_id": "paper-1",
                "title": "Paper",
                "source_urls": (
                    "https://doi.org/https://doi.org/10.1000/test",
                    "https://localhost/private.pdf",
                    "http://example.org/insecure",
                ),
            },),
        )

        prompt = build_generation_prompt("Question", pack)

        self.assertIn("https://doi.org/10.1000/test", prompt)
        self.assertNotIn("https://doi.org/https://doi.org", prompt)
        self.assertNotIn("localhost", prompt)
        self.assertNotIn("http://example.org", prompt)

    def test_external_url_candidates_are_bounded_globally(self):
        papers = tuple(
            {
                "paper_id": f"paper-{index}",
                "title": f"Paper {index}",
                "doi": f"10.1000/{index}",
                "source_urls": (
                    f"https://papers.example.org/{index}.pdf",
                    f"https://repos.example.org/{index}",
                ),
            }
            for index in range(1, 8)
        )

        prompt = build_generation_prompt(
            "Question", EvidencePack("insufficient_evidence", (), (), papers)
        )
        context = json.loads(prompt.rsplit("\n", 1)[-1])

        self.assertEqual(len(context["bounded_url_context_candidates"]), 3)
        self.assertTrue(
            all(not doi.startswith("https://") for paper in context["ranked_papers_discovery_context_only"] for doi in (paper.get("doi"),) if doi)
        )
        source_urls = [
            url
            for paper in context["ranked_papers_discovery_context_only"]
            for url in paper["source_urls"]
        ]
        self.assertEqual(set(source_urls), set(context["bounded_url_context_candidates"]))

    def test_orchestration_uses_precomputed_ranking_without_reordering(self):
        scenario = build_mock_scenario()
        ranking_calls = []

        class CountingRankingService(RankingService):
            def rank(self, plan, candidates):
                ranking_calls.append("rank")
                return super().rank(plan, candidates)

        pipeline = RetrievalRankingPipeline(
            retrieval=scenario.retrieval,
            fusion=FusionService(),
            expansion=scenario.graph,
            ranking=CountingRankingService(),
        )
        plan = QueryPlanner().plan(
            "aged care robotics", as_of=date(2026, 9, 8), require_evidence=True
        )
        precomputed = pipeline.retrieve_and_rank(plan)
        ranking_calls.clear()

        class ExternalGenerator:
            supports_external_grounding = True

            def synthesize(self, question, evidence):
                return {"answer": "grounded", "paper_ids": [p["paper_id"] for p in evidence.ranked_papers]}

        orchestrator = AnswerOrchestrator(
            retrieval_ranking=pipeline,
            evidence_builder=EvidencePackBuilder(),
            generation=ExternalGenerator(),
        )
        paper_context = tuple(
            {"paper_id": item.entity.entity_id, "title": item.entity.label, "rank": item.rank}
            for item in precomputed.ranked
            if item.entity.kind == "publication"
        )

        answer = orchestrator.answer_ranked(plan, precomputed, {}, ranked_papers=paper_context)

        self.assertIsInstance(answer, Answer)
        self.assertEqual(answer.retrieval_ranking, precomputed)
        self.assertEqual(ranking_calls, [])
        self.assertEqual(
            [item.rank for item in answer.retrieval_ranking.ranked],
            [item.rank for item in precomputed.ranked],
        )


if __name__ == "__main__":
    unittest.main()
