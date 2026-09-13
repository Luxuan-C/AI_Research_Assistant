"""Local HTTP API backed by the live Supabase database."""

from __future__ import annotations

import json
import time
from threading import Lock
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from database.database import Database


DATABASE = Database()
_ROW_CACHE: dict[tuple[str, str, str], tuple[float, list[dict[str, Any]]]] = {}
_CACHE_SECONDS = 60.0
_ROW_CACHE_LOCK = Lock()


def rows(table: str, columns: str = "*", limit: int | None = None) -> list[dict[str, Any]]:
    cache_key = (table, columns, str(limit))
    with _ROW_CACHE_LOCK:
        cached = _ROW_CACHE.get(cache_key)
        if cached is not None and time.monotonic() - cached[0] < _CACHE_SECONDS:
            return cached[1]

        last_error: Exception | None = None
        for attempt in range(3):
            try:
                request = DATABASE.connection.table(table).select(columns)
                if limit is not None:
                    request = request.limit(limit)
                result = request.execute().data or []
                _ROW_CACHE[cache_key] = (time.monotonic(), result)
                return result
            except Exception as error:
                last_error = error
                if attempt == 2:
                    raise
                time.sleep(0.25 * (attempt + 1))
    raise last_error  # type: ignore[misc]


def first_value(value: Any) -> Any:
    if isinstance(value, list):
        return value[0] if value else None
    return value


def paper_url(paper: dict[str, Any]) -> str | None:
    return (
        paper.get("open_access_url")
        or paper.get("primary_url")
        or (f"https://doi.org/{paper['doi']}" if paper.get("doi") else None)
    )


def university_name(university_ids: list[Any] | None) -> str | None:
    ids = set(university_ids or [])
    if not ids:
        return None
    for university in rows("university", "id,name"):
        if university.get("id") in ids:
            return university.get("name")
    return None


def discipline_name(discipline_ids: list[Any] | None) -> str | None:
    ids = set(discipline_ids or [])
    if not ids:
        return None
    for discipline in rows("discipline", "id,name"):
        if discipline.get("id") in ids:
            return discipline.get("name")
    return None


def papers_for(academic: dict[str, Any]) -> list[dict[str, Any]]:
    paper_ids = set(academic.get("research_paper_ids") or [])
    if not paper_ids:
        return []
    return [
        paper
        for paper in rows("research_paper")
        if paper.get("id") in paper_ids
    ]


def profile_payload(
    academic: dict[str, Any],
    universities: dict[Any, str] | None = None,
    disciplines: dict[Any, str] | None = None,
    papers: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if papers is None:
        papers = papers_for(academic)
    interests = academic.get("research_interests") or academic.get("areas_of_expertise") or []
    university = (
        next((universities.get(item) for item in academic.get("university_ids") or [] if item in universities), None)
        if universities is not None
        else university_name(academic.get("university_ids"))
    )
    discipline = (
        next((disciplines.get(item) for item in academic.get("discipline_ids") or [] if item in disciplines), None)
        if disciplines is not None
        else discipline_name(academic.get("discipline_ids"))
    )
    description = academic.get("academic_position") or "No verified research description is available."
    summary = f"{academic.get('name', 'This researcher')} is listed in the live academic database."
    return {
        "id": academic.get("id"),
        "name": academic.get("name"),
        "university": university,
        "discipline": discipline,
        "research_interests": interests,
        "description": description,
        "ai_summary": summary,
        "summary_status": "ok" if academic.get("name") else "insufficient_information",
        "publications": [paper_payload(paper) for paper in papers],
        "official_profile_url": academic.get("profile_url") or academic.get("orcid_url"),
    }


def paper_payload(paper: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": paper.get("id"),
        "title": paper.get("name"),
        "year": str(paper.get("publication_date", ""))[:4] or None,
        "doi": paper.get("doi"),
        "url": paper_url(paper),
    }


def search_researchers(query: str, university: str, discipline: str) -> list[dict[str, Any]]:
    normalized = query.casefold().strip()
    universities = {item["id"]: item["name"] for item in rows("university", "id,name")}
    disciplines = {item["id"]: item["name"] for item in rows("discipline", "id,name")}
    results = []
    academic_columns = "id,name,academic_position,profile_url,orcid_url,university_ids,discipline_ids"
    for academic in rows("academic", academic_columns, limit=25):
        profile = profile_payload(academic, universities, disciplines, papers=[])
        searchable = " ".join(
            [
                str(profile.get("name") or ""),
                str(profile.get("description") or ""),
                " ".join(str(item) for item in profile.get("research_interests") or []),
            ]
        ).casefold()
        if normalized and normalized not in searchable:
            continue
        if university and profile.get("university") != university:
            continue
        if discipline and profile.get("discipline") != discipline:
            continue
        results.append(profile)
    return results


def directory_options() -> dict[str, list[str]]:
    return {
        "universities": sorted({item["name"] for item in rows("university", "name", limit=100) if item.get("name")} ),
        "disciplines": sorted({item["name"] for item in rows("discipline", "name", limit=100) if item.get("name")} ),
    }


def ask_payload(question: str) -> dict[str, Any]:
    normalized = question.casefold().strip()
    papers = []
    seen_papers: set[str] = set()
    for paper in rows("research_paper"):
        searchable = " ".join(
            [str(paper.get("name") or ""), " ".join(str(item) for item in paper.get("keywords") or [])]
        ).casefold()
        if not normalized or any(token in searchable for token in normalized.split()):
            paper_key = str(paper.get("doi") or paper.get("id") or paper.get("name"))
            if paper_key in seen_papers:
                continue
            seen_papers.add(paper_key)
            papers.append(paper_payload(paper))

    citations = [
        {"source_title": paper["title"], "source_url": paper["url"]}
        for paper in papers
        if paper.get("url")
    ]
    if papers:
        answer = f"Supabase found {len(papers)} research paper(s) related to your question."
        status = "ok"
    else:
        answer = "No matching research papers with verified source links were found in Supabase."
        status = "insufficient_information"
    return {"answer": answer, "citations": citations, "papers": papers, "status": status}


class ApiHandler(BaseHTTPRequestHandler):
    def send_json(self, status: int, payload: Any) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        params = {key: values[0] for key, values in parse_qs(parsed.query).items()}
        try:
            if parsed.path == "/api/researchers":
                self.send_json(200, {"researchers": search_researchers(
                    params.get("q", ""), params.get("university", ""), params.get("discipline", "")
                )})
                return
            if parsed.path == "/api/directory-options":
                self.send_json(200, directory_options())
                return
            if parsed.path.startswith("/api/researchers/"):
                researcher_id = parsed.path.rsplit("/", 1)[-1]
                match = next((item for item in rows("academic") if item.get("id") == researcher_id), None)
                if match is None:
                    self.send_json(404, {"error": "Researcher not found"})
                else:
                    self.send_json(200, profile_payload(match))
                return
            self.send_json(404, {"error": "Endpoint not found"})
        except Exception as error:
            self.send_json(500, {"error": str(error)})

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
            self.send_json(200, ask_payload(question))
        except (ValueError, json.JSONDecodeError) as error:
            self.send_json(400, {"error": str(error)})

    def log_message(self, format: str, *args: Any) -> None:
        print(f"API: {format % args}")


def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 8000), ApiHandler)
    print("Live Supabase API running at http://127.0.0.1:8000")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()


if __name__ == "__main__":
    main()
