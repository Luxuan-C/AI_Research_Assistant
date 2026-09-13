"""Application-level orchestration for GraphRAG features."""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

from academic_profiles import AcademicProfile, AcademicProfileService
from ranking.paper_ranking import rank_retrieval_response

if TYPE_CHECKING:
    from academic_graphrag.interfaces import AcademicGraphRepository
    from academic_graphrag.models import RetrievalQuery
    from academic_graphrag.pipeline import GraphRAGEngine


def search_papers(
    engine: "GraphRAGEngine", query: "RetrievalQuery"
) -> list[dict[str, Any]]:
    """Retrieve papers with GraphRAG and return ranked publication results."""
    response = engine.retrieve(query)
    return rank_retrieval_response(response)


def search_academic_profiles_with_graphrag(
    engine: "GraphRAGEngine", query: "RetrievalQuery"
) -> list[AcademicProfile]:
    """Retrieve relevant researchers with GraphRAG and build their profiles."""
    response = engine.retrieve(query)
    profile_service = AcademicProfileService(engine.repository)
    profiles: list[AcademicProfile] = []
    seen_ids: set[str] = set()

    for result in response.results:
        academic = result.entity
        if academic.entity_type != "Researcher" or academic.id in seen_ids:
            continue
        profile = profile_service.get_profile(academic.id)
        if profile is not None:
            profiles.append(profile)
            seen_ids.add(academic.id)

    return profiles




def search_academic_profiles(
    repository: "AcademicGraphRepository", search_text: str
) -> list[AcademicProfile]:
    """Find academic profiles using a user-facing name or keyword search."""
    normalized_query = search_text.strip().casefold()
    if not normalized_query:
        return []

    profiles = AcademicProfileService(repository)
    matches = []
    for academic in repository.list_entities(entity_types=("Researcher",)):
        searchable_values = (
            academic.label,
            *academic.aliases,
            academic.text,
        )
        if not any(normalized_query in value.casefold() for value in searchable_values):
            continue
        profile = profiles.get_profile(academic.id)
        if profile is not None:
            matches.append(profile)
    return matches
