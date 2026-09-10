"""Public API for the standalone academic GraphRAG core."""

from .identity import stable_id, stable_relationship_id
from .interfaces import (
    AcademicGraphRepository,
    AcademicSignalProvider,
    DenseRetriever,
    EmbeddingProvider,
    KeywordRetriever,
    LLMProvider,
    Reranker,
)
from .models import (
    Entity,
    Evidence,
    GenerationContext,
    RankedResult,
    Relationship,
    RetrievalQuery,
    RetrievalResponse,
    RetrievalStatus,
    SourceRecord,
)
from .pipeline import GraphRAGEngine, PipelineConfig
from .ranking import MetadataAcademicSignalProvider, RankingWeights
from .traversal import BoundedGraphExpander, TraversalConfig

__all__ = [
    "AcademicGraphRepository",
    "AcademicProfile",
    "AcademicProfileService",
    "AcademicProfileSummary",
    "AcademicSignalProvider",
    "BoundedGraphExpander",
    "DenseRetriever",
    "EmbeddingProvider",
    "Entity",
    "Evidence",
    "GenerationContext",
    "GraphRAGEngine",
    "KeywordRetriever",
    "LLMProvider",
    "MetadataAcademicSignalProvider",
    "PipelineConfig",
    "ProfileCitation",
    "RankedResult",
    "RankingWeights",
    "Relationship",
    "Reranker",
    "RetrievalQuery",
    "RetrievalResponse",
    "RetrievalStatus",
    "SourceRecord",
    "TraversalConfig",
    "stable_id",
    "stable_relationship_id",
]


def __getattr__(name: str):
    """Load profile types lazily to avoid a GraphRAG/profile import cycle."""
    if name in {
        "AcademicProfile",
        "AcademicProfileService",
        "AcademicProfileSummary",
        "ProfileCitation",
    }:
        from academic_profiles.academic_profile import (
            AcademicProfile,
            AcademicProfileService,
            AcademicProfileSummary,
            ProfileCitation,
        )

        return {
            "AcademicProfile": AcademicProfile,
            "AcademicProfileService": AcademicProfileService,
            "AcademicProfileSummary": AcademicProfileSummary,
            "ProfileCitation": ProfileCitation,
        }[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

