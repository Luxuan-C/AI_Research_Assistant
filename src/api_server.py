"""Local HTTP API over the unified live Supabase ranking application."""

from __future__ import annotations
from pathlib import Path
from dotenv import load_dotenv
_env_path = Path(__file__).resolve().parent.parent / ".env"
print("DEBUG env path:", _env_path)
print("DEBUG env exists:", _env_path.exists())
_loaded = load_dotenv(_env_path)
print("DEBUG load_dotenv returned:", _loaded)

import os
print("DEBUG keys seen:", sorted(os.environ.keys() & {"GEMINI_API_KEY", "GEMINI_MODEL", "SUPABASE_KEY", "SUPABASE_URL"}))
print("DEBUG gemini value set:", bool(os.environ.get("GEMINI_API_KEY")))

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from application import (
    DEFAULT_API_ROW_LIMIT,
    DEFAULT_CACHE_TTL_SECONDS,
    HydratedAcademicProfile,
    PublicationResult,
    ResearchApplication,
    ResearcherResult,
)
from ranking.supabase_config import (
    SupabaseConfigurationError,
    create_supabase_client,
)
from ranking.supabase_retrieval import safe_error_detail


def create_live_application() -> ResearchApplication:
    """Construct shared services without reading any Supabase table."""

    return ResearchApplication.from_supabase_client(
        create_supabase_client(),
        row_limit=DEFAULT_API_ROW_LIMIT,
        cache_ttl_seconds=DEFAULT_CACHE_TTL_SECONDS,
    )


def researcher_payload(researcher: ResearcherResult) -> dict[str, Any]:
    return {
        "id": researcher.raw_id,
        "name": researcher.name,
        "university": researcher.institution,
        "discipline": researcher.discipline,
        "research_interests": list(researcher.research_interests),
        "description": researcher.position
        or "No verified research description is available.",
        "ai_summary": (
            "Insufficient verified information is available to produce a reliable "
            "academic summary."
        ),
        "summary_status": "insufficient_information",
        "publications": [],
        "official_profile_url": next(iter(researcher.source_urls), None),
        "rank": researcher.rank,
    }


def paper_payload(paper: PublicationResult) -> dict[str, Any]:
    ranking = getattr(paper, "score_breakdown", {})
    availability = getattr(paper, "factor_availability", {})

    def factor_value(name: str, component: str) -> float | None:
        value = ranking.get(component)
        if not availability.get(name) or value is None:
            return None
        return round(value, 6)

    evidence = {
        "confidence": 0.0,
        "source_url": paper.source_url,
        "source_type": "Ranked Supabase record; validated evidence unavailable",
        "citation_count": None,
    }
    return {
        "id": paper.raw_id,
        "title": paper.title,
        "year": str(paper.publication_date.year) if paper.publication_date else None,
        "doi": paper.doi,
        "url": paper.source_url,
        "rank": paper.rank,
        "final_score": round(paper.score, 6),
        "score_breakdown": {
            "H_hybrid_relevance": round(ranking.get("retrieval", paper.score), 6),
            "Q_quality": factor_value("Q", "paper_authority"),
            "I_citation_influence": factor_value("I", "citation"),
            "T_temporal_validity": round(ranking.get("recency", 0.0), 6),
            "N_innovation": 0.0,
            "A_author_authority": factor_value("A", "author_authority"),
            "G_graph_enrichment": round(ranking.get("graph", 0.0), 6),
        },
        "factor_availability": {
            "Q": bool(availability.get("Q")),
            "I": bool(availability.get("I")),
            "A": bool(availability.get("A")),
        },
        "evidence": evidence,
    }


def profile_payload(profile: HydratedAcademicProfile) -> dict[str, Any]:
    return {
        "id": profile.raw_id,
        "name": profile.name,
        "university": profile.institution,
        "discipline": profile.discipline,
        "research_interests": list(profile.research_interests),
        "description": profile.position
        or "No verified research description is available.",
        "ai_summary": profile.summary_text,
        "summary_status": profile.summary_status,
        "publications": [paper_payload(paper) for paper in profile.publications],
        "official_profile_url": profile.official_profile_url,
        "citations": [
            {
                "evidence_id": citation.evidence_id,
                "source_url": citation.uri,
                "excerpt": citation.excerpt,
            }
            for citation in profile.citations
        ],
        "truncated": profile.truncated,
    }


class ApiHandler(BaseHTTPRequestHandler):
    application: ResearchApplication | None = None

    def send_json(self, status: int, payload: Any) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _application(self) -> ResearchApplication:
        if self.application is None:
            raise RuntimeError("API application services have not been configured")
        return self.application

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        params = {key: values[0] for key, values in parse_qs(parsed.query).items()}
        try:
            application = self._application()
            if parsed.path == "/api/researchers":
                result = application.search_researchers(
                    params.get("q", ""),
                    university=params.get("university", ""),
                    discipline=params.get("discipline", ""),
                )
                self.send_json(
                    200,
                    {
                        "researchers": [
                            researcher_payload(item) for item in result.researchers
                        ],
                        "truncated": result.truncated,
                    },
                )
                return
            if parsed.path == "/api/directory-options":
                options = application.directory_options()
                self.send_json(
                    200,
                    {
                        "universities": list(options.universities),
                        "disciplines": list(options.disciplines),
                        "truncated": options.truncated,
                    },
                )
                return
            if parsed.path.startswith("/api/researchers/"):
                researcher_id = parsed.path.rsplit("/", 1)[-1]
                profile = application.get_academic_profile(researcher_id)
                if profile is None:
                    self.send_json(404, {"error": "Researcher not found"})
                else:
                    self.send_json(200, profile_payload(profile))
                return
            self.send_json(404, {"error": "Endpoint not found"})
        except Exception as error:
            self.send_json(500, {"error": safe_error_detail(error)})

    def do_POST(self) -> None:
        if self.path != "/api/ask":
            self.send_json(404, {"error": "Endpoint not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
            question = str(payload.get("question", "")).strip()
            if not question:
                self.send_json(400, {"error": "Question cannot be empty"})
                return
            result = self._application().search_publications(question)
            papers = [paper_payload(item) for item in result.publications]
            ranked_record_citations = [
                {
                    "source_title": paper["title"],
                    "source_url": paper["url"],
                    "evidence": paper["evidence"],
                    "source_origin": "internal_database_record",
                }
                for paper in papers
                if paper["url"]
            ]
            generated = result.generation_status == "generated" and bool(result.answer)
            citations = list(result.citations) if generated else ranked_record_citations
            answer = result.answer if generated else (
                "Ranked research papers were found, but validated evidence is not "
                "available to synthesize a reliable answer."
                if papers
                else "No ranked research papers were found for this question."
            )
            self.send_json(
                200,
                {
                    "answer": answer,
                    "citations": citations,
                    "papers": papers,
                    "status": "generated" if generated else "insufficient_information",
                    "evidence_status": result.evidence_status,
                    "generation_status": result.generation_status,
                    "generation_provider": result.generation_provider,
                    "external_sources": list(result.external_sources),
                    "truncated": result.truncated,
                },
            )
        except (ValueError, json.JSONDecodeError) as error:
            self.send_json(400, {"error": safe_error_detail(error)})
        except Exception as error:
            self.send_json(500, {"error": safe_error_detail(error)})

    def log_message(self, format: str, *args: Any) -> None:
        print(f"API: {format % args}")


def configured_handler(application: ResearchApplication) -> type[ApiHandler]:
    """Bind one shared application instance to all request-handler threads."""

    class ConfiguredApiHandler(ApiHandler):
        pass

    ConfiguredApiHandler.application = application
    return ConfiguredApiHandler


def main() -> None:
    try:
        application = create_live_application()
    except SupabaseConfigurationError as error:
        raise SystemExit(f"API configuration error: {error}") from error
    server = ThreadingHTTPServer(
        ("127.0.0.1", 8000),
        configured_handler(application),
    )
    print("Unified Supabase ranking API running at http://127.0.0.1:8000")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()


if __name__ == "__main__":
    main()
