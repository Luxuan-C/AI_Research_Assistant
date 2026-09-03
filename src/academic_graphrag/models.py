"""Provider-neutral domain and response models for the academic GraphRAG core."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Mapping


Metadata = Mapping[str, Any]


class RetrievalStatus(StrEnum):
    OK = "ok"
    INSUFFICIENT_INFORMATION = "insufficient_information"


@dataclass(frozen=True, slots=True)
class Entity:
    """An extensible graph entity.

    ``entity_type`` is deliberately a string instead of a closed enum so that a
    future schema can add entity types without changing the GraphRAG core.
    """

    id: str
    entity_type: str
    label: str
    text: str = ""
    aliases: tuple[str, ...] = ()
    metadata: Metadata = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Relationship:
    """A directed, typed relationship with optional evidence references."""

    id: str
    source_id: str
    target_id: str
    relation_type: str
    confidence: float = 1.0
    evidence_ids: tuple[str, ...] = ()
    metadata: Metadata = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SourceRecord:
    id: str
    provider: str
    uri: str
    external_id: str | None = None
    observed_at: datetime | None = None
    metadata: Metadata = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Evidence:
    """A sourced excerpt or structured fact supporting graph object IDs."""

    id: str
    source_record_id: str
    supports_ids: tuple[str, ...]
    excerpt: str
    confidence: float = 1.0
    locator: str | None = None
    metadata: Metadata = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RetrievalQuery:
    text: str
    limit: int = 5
    entity_types: tuple[str, ...] = ("Researcher", "Publication")
    filters: Metadata = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Candidate:
    entity_id: str
    score: float
    channel: str
    rank: int = 0
    metadata: Metadata = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class EvidenceWithSource:
    evidence: Evidence
    source: SourceRecord


@dataclass(frozen=True, slots=True)
class ScoreBreakdown:
    components: Mapping[str, float]
    weights: Mapping[str, float]
    final_score: float


@dataclass(frozen=True, slots=True)
class GraphPath:
    seed_id: str
    target_id: str
    relationship_ids: tuple[str, ...]

    @property
    def hops(self) -> int:
        return len(self.relationship_ids)


@dataclass(frozen=True, slots=True)
class ContextPassage:
    entity_id: str
    text: str
    evidence_ids: tuple[str, ...]
    provenance_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class GenerationContext:
    query: str
    passages: tuple[ContextPassage, ...]
    relationships: tuple[Relationship, ...]
    provenance_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RankedResult:
    rank: int
    entity: Entity
    relationships_used: tuple[Relationship, ...]
    score: ScoreBreakdown
    evidence: tuple[EvidenceWithSource, ...]
    provenance_ids: tuple[str, ...]
    context: str


@dataclass(frozen=True, slots=True)
class RetrievalResponse:
    status: RetrievalStatus
    query: RetrievalQuery
    results: tuple[RankedResult, ...]
    relationships_used: tuple[Relationship, ...]
    generation_context: GenerationContext
    truncated: bool
    message: str | None = None

