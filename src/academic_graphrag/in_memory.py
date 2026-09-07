"""Dependency-free in-memory adapters used for the first working version."""

from __future__ import annotations

import hashlib
import math
from collections import Counter
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence, TypeVar

from .interfaces import AcademicGraphRepository, EmbeddingProvider
from .models import Candidate, Entity, Evidence, Relationship, RetrievalQuery, SourceRecord
from .ranking import clamp, tokenize


class InMemoryAcademicRepository:
    def __init__(
        self,
        *,
        entities: Sequence[Entity],
        relationships: Sequence[Relationship],
        evidence: Sequence[Evidence],
        sources: Sequence[SourceRecord],
    ) -> None:
        self._entities = _unique_by_id(entities, "entity")
        self._relationships = _unique_by_id(relationships, "relationship")
        self._evidence = _unique_by_id(evidence, "evidence")
        self._sources = _unique_by_id(sources, "source")

    def list_entities(
        self,
        *,
        entity_ids: Sequence[str] = (),
        entity_types: Sequence[str] = (),
        filters: Mapping[str, object] | None = None,
    ) -> Sequence[Entity]:
        allowed_ids = set(entity_ids)
        allowed_types = set(entity_types)
        requested_filters = filters or {}
        return tuple(
            entity
            for entity in self._entities.values()
            if (not allowed_ids or entity.id in allowed_ids)
            and (not allowed_types or entity.entity_type in allowed_types)
            and _matches_filters(entity, requested_filters)
        )

    def get_entities(self, entity_ids: Sequence[str]) -> Sequence[Entity]:
        return tuple(self._entities[item] for item in dict.fromkeys(entity_ids) if item in self._entities)

    def get_relationships(
        self,
        node_ids: Sequence[str],
        *,
        relation_types: Sequence[str] = (),
    ) -> Sequence[Relationship]:
        ids = set(node_ids)
        allowed = set(relation_types)
        return tuple(
            edge
            for edge in self._relationships.values()
            if (edge.source_id in ids or edge.target_id in ids)
            and (not allowed or edge.relation_type in allowed)
        )

    def get_evidence(self, supported_ids: Sequence[str]) -> Sequence[Evidence]:
        ids = set(supported_ids)
        return tuple(
            item
            for item in self._evidence.values()
            if ids.intersection(item.supports_ids)
        )

    def get_sources(self, source_record_ids: Sequence[str]) -> Sequence[SourceRecord]:
        return tuple(self._sources[item] for item in dict.fromkeys(source_record_ids) if item in self._sources)


class BM25KeywordRetriever:
    """Small BM25 adapter suitable for mock data and deterministic unit tests."""

    def __init__(
        self,
        repository: AcademicGraphRepository,
        *,
        k1: float = 1.5,
        b: float = 0.75,
    ) -> None:
        self.repository = repository
        self.k1 = k1
        self.b = b

    def search(self, query: RetrievalQuery, *, limit: int) -> Sequence[Candidate]:
        query_tokens = tokenize(query.text)
        if not query_tokens or limit <= 0:
            return ()
        entities = self.repository.list_entities(entity_types=query.entity_types, filters=query.filters)
        documents = {entity.id: tokenize(_entity_search_text(entity)) for entity in entities}
        if not documents:
            return ()
        average_length = sum(len(tokens) for tokens in documents.values()) / len(documents)
        document_frequency = Counter(
            token
            for tokens in documents.values()
            for token in set(tokens)
        )
        scored: list[tuple[str, float]] = []
        count = len(documents)
        for entity_id, tokens in documents.items():
            frequencies = Counter(tokens)
            score = 0.0
            for token in query_tokens:
                frequency = frequencies.get(token, 0)
                if not frequency:
                    continue
                df = document_frequency[token]
                inverse_document_frequency = math.log(1.0 + (count - df + 0.5) / (df + 0.5))
                denominator = frequency + self.k1 * (
                    1.0 - self.b + self.b * len(tokens) / max(1.0, average_length)
                )
                score += inverse_document_frequency * frequency * (self.k1 + 1.0) / denominator
            if score > 0:
                scored.append((entity_id, score))
        scored.sort(key=lambda item: (-item[1], item[0]))
        return tuple(
            Candidate(entity_id=entity_id, score=score, channel="keyword", rank=rank)
            for rank, (entity_id, score) in enumerate(scored[:limit], start=1)
        )


@dataclass(slots=True)
class DeterministicHashEmbeddingProvider:
    """A deterministic local test embedding, not a production semantic model."""

    dimensions: int = 128

    def __post_init__(self) -> None:
        if self.dimensions <= 0:
            raise ValueError("Embedding dimensions must be positive")

    def embed(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        return tuple(self._embed_one(text) for text in texts)

    def _embed_one(self, text: str) -> tuple[float, ...]:
        vector = [0.0] * self.dimensions
        for token in tokenize(text):
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=16).digest()
            index = int.from_bytes(digest[:8], "big") % self.dimensions
            sign = 1.0 if digest[8] & 1 else -1.0
            vector[index] += sign
        magnitude = math.sqrt(sum(value * value for value in vector))
        if magnitude == 0:
            return tuple(vector)
        return tuple(value / magnitude for value in vector)


class InMemoryDenseRetriever:
    def __init__(
        self,
        repository: AcademicGraphRepository,
        embedding_provider: EmbeddingProvider,
        *,
        minimum_similarity: float = 0.10,
    ) -> None:
        self.repository = repository
        self.embedding_provider = embedding_provider
        self.minimum_similarity = minimum_similarity

    def search(self, query: RetrievalQuery, *, limit: int) -> Sequence[Candidate]:
        if not query.text.strip() or limit <= 0:
            return ()
        entities = self.repository.list_entities(entity_types=query.entity_types, filters=query.filters)
        if not entities:
            return ()
        query_vector = self.embedding_provider.embed((query.text,))[0]
        entity_vectors = self.embedding_provider.embed(tuple(_entity_search_text(entity) for entity in entities))
        scored = [
            (entity.id, _cosine(query_vector, vector))
            for entity, vector in zip(entities, entity_vectors, strict=True)
        ]
        scored = [item for item in scored if item[1] >= self.minimum_similarity]
        scored.sort(key=lambda item: (-item[1], item[0]))
        return tuple(
            Candidate(entity_id=entity_id, score=clamp(score), channel="dense", rank=rank)
            for rank, (entity_id, score) in enumerate(scored[:limit], start=1)
        )


class PassthroughReranker:
    """Preserves retrieval relevance while providing a replaceable reranking port."""

    def rerank(
        self,
        query: RetrievalQuery,
        candidates: Sequence[Candidate],
        entities: Mapping[str, Entity],
    ) -> Sequence[Candidate]:
        del query, entities
        reranked = [
            Candidate(
                entity_id=item.entity_id,
                score=clamp(float(item.metadata.get("retrieval_relevance", item.score))),
                channel="reranker",
                metadata=item.metadata,
            )
            for item in candidates
        ]
        reranked.sort(key=lambda item: (-item.score, item.entity_id))
        return tuple(
            Candidate(
                entity_id=item.entity_id,
                score=item.score,
                channel=item.channel,
                rank=rank,
                metadata=item.metadata,
            )
            for rank, item in enumerate(reranked, start=1)
        )


def _entity_search_text(entity: Entity) -> str:
    metadata_text = " ".join(_flatten_strings(entity.metadata.values()))
    return " ".join((entity.label, *entity.aliases, entity.text, metadata_text))


def _flatten_strings(values: Iterable[object]) -> tuple[str, ...]:
    output: list[str] = []
    for value in values:
        if isinstance(value, str):
            output.append(value)
        elif isinstance(value, (list, tuple, set, frozenset)):
            output.extend(item for item in value if isinstance(item, str))
    return tuple(output)


def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right):
        raise ValueError("Embedding vectors must have matching dimensions")
    return sum(a * b for a, b in zip(left, right, strict=True))


def _matches_filters(entity: Entity, filters: Mapping[str, object]) -> bool:
    for key, expected in filters.items():
        actual = entity.metadata.get(key)
        if isinstance(actual, (list, tuple, set, frozenset)):
            if expected not in actual:
                return False
        elif actual != expected:
            return False
    return True


_T = TypeVar("_T")


def _unique_by_id(items: Sequence[_T], label: str) -> dict[str, _T]:
    output: dict[str, _T] = {}
    for item in items:
        item_id = getattr(item, "id")
        if item_id in output:
            raise ValueError(f"Duplicate {label} ID: {item_id}")
        output[item_id] = item
    return output
