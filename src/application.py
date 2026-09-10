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


def get_academic_profile(
    repository: "AcademicGraphRepository", academic_id: str
) -> AcademicProfile | None:
    """Load an evidence-grounded academic profile by entity ID."""
    return AcademicProfileService(repository).get_profile(academic_id)
