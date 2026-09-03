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

