"""Ports used by the GraphRAG core.

Database schemas, retrieval engines, rerankers, embedding models, and LLMs are
all outside the core. Concrete adapters translate those systems into these
small contracts.
"""

from __future__ import annotations

from typing import Mapping, Protocol, Sequence

from .models import (
    Candidate,
    Entity,
    Evidence,
    GenerationContext,
    Relationship,
    RetrievalQuery,
    SourceRecord,
)


class AcademicGraphRepository(Protocol):
    def list_entities(
        self,
        *,
        entity_ids: Sequence[str] = (),
        entity_types: Sequence[str] = (),
        filters: Mapping[str, object] | None = None,
    ) -> Sequence[Entity]: ...

    def get_entities(self, entity_ids: Sequence[str]) -> Sequence[Entity]: ...

    def get_relationships(
        self,
        node_ids: Sequence[str],
        *,
        relation_types: Sequence[str] = (),
    ) -> Sequence[Relationship]: ...

    def get_evidence(self, supported_ids: Sequence[str]) -> Sequence[Evidence]: ...

    def get_sources(self, source_record_ids: Sequence[str]) -> Sequence[SourceRecord]: ...


class KeywordRetriever(Protocol):
    def search(self, query: RetrievalQuery, *, limit: int) -> Sequence[Candidate]: ...


class DenseRetriever(Protocol):
    def search(self, query: RetrievalQuery, *, limit: int) -> Sequence[Candidate]: ...


class EmbeddingProvider(Protocol):
    @property
    def dimensions(self) -> int: ...

    def embed(self, texts: Sequence[str]) -> Sequence[Sequence[float]]: ...


class Reranker(Protocol):
    def rerank(
        self,
        query: RetrievalQuery,
        candidates: Sequence[Candidate],
        entities: Mapping[str, Entity],
    ) -> Sequence[Candidate]: ...


class AcademicSignalProvider(Protocol):
    def score(self, entity: Entity, query: RetrievalQuery) -> Mapping[str, float]: ...


class LLMProvider(Protocol):
    """Future generation port; the first retrieval module does not call it."""

    def generate(self, context: GenerationContext) -> str: ...
