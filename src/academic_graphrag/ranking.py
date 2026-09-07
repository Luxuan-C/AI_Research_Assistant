"""RRF and schema-tolerant academic ranking signals."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Iterable, Mapping, Sequence

from .models import Candidate, Entity, RetrievalQuery, ScoreBreakdown


_TOKEN = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "can",
        "for",
        "from",
        "how",
        "i",
        "in",
        "is",
        "of",
        "on",
        "or",
        "that",
        "the",
        "to",
        "what",
        "with",
    }
)


def tokenize(value: str) -> tuple[str, ...]:
    return tuple(token for token in _TOKEN.findall(value.lower()) if token not in _STOPWORDS)


def reciprocal_rank_fusion(
    rankings: Mapping[str, Sequence[Candidate]],
    *,
    k: int = 60,
) -> dict[str, float]:
    if k <= 0:
        raise ValueError("RRF k must be positive")
    scores: dict[str, float] = {}
    for items in rankings.values():
        seen: set[str] = set()
        for fallback_rank, item in enumerate(items, start=1):
            if item.entity_id in seen:
                continue
            seen.add(item.entity_id)
            rank = item.rank if item.rank > 0 else fallback_rank
            scores[item.entity_id] = scores.get(item.entity_id, 0.0) + 1.0 / (k + rank)
    return scores


def normalise_scores(scores: Mapping[str, float]) -> dict[str, float]:
    if not scores:
        return {}
    maximum = max(scores.values())
    if maximum <= 0:
        return {key: 0.0 for key in scores}
    return {key: max(0.0, value / maximum) for key, value in scores.items()}


def clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


@dataclass(frozen=True, slots=True)
class RankingWeights:
    semantic_relevance: float = 0.55
    citation_influence: float = 0.10
    recency: float = 0.10
    venue_quality: float = 0.10
    topic_coverage: float = 0.15

    def as_dict(self) -> dict[str, float]:
        values = {
            "semantic_relevance": self.semantic_relevance,
            "citation_influence": self.citation_influence,
            "recency": self.recency,
            "venue_quality": self.venue_quality,
            "topic_coverage": self.topic_coverage,
        }
        if any(value < 0 for value in values.values()):
            raise ValueError("Ranking weights cannot be negative")
        if sum(values.values()) <= 0:
            raise ValueError("At least one ranking weight must be positive")
        return values


@dataclass(slots=True)
class MetadataAcademicSignalProvider:
    """Initial signal adapter over open metadata.

    A production adapter may compute these values from SQL views or a feature
    service without changing the pipeline.
    """

    current_year: int = field(default_factory=lambda: datetime.now(UTC).year)
    citation_reference: int = 1000
    recency_half_life_years: float = 5.0
    citation_key: str = "citation_count"
    year_keys: tuple[str, ...] = ("year", "latest_publication_year")
    venue_quality_key: str = "venue_quality"
    topics_key: str = "topics"

    def score(self, entity: Entity, query: RetrievalQuery) -> Mapping[str, float]:
        citations = _number(entity.metadata.get(self.citation_key), 0.0)
        citation_denominator = math.log1p(max(1, self.citation_reference))
        citation_influence = clamp(math.log1p(max(0.0, citations)) / citation_denominator)

        year = next(
            (_number(entity.metadata.get(key), 0.0) for key in self.year_keys if entity.metadata.get(key) is not None),
            0.0,
        )
        if year <= 0:
            recency = 0.0
        else:
            age = max(0.0, self.current_year - year)
            recency = clamp(0.5 ** (age / max(0.1, self.recency_half_life_years)))

        venue_quality = clamp(_number(entity.metadata.get(self.venue_quality_key), 0.0))
        topic_values = _strings(entity.metadata.get(self.topics_key))
        topic_tokens = set(tokenize(" ".join(topic_values)))
        query_tokens = set(tokenize(query.text))
        topic_coverage = len(query_tokens & topic_tokens) / len(query_tokens) if query_tokens else 0.0

        return {
            "citation_influence": citation_influence,
            "recency": recency,
            "venue_quality": venue_quality,
            "topic_coverage": clamp(topic_coverage),
        }


def build_score_breakdown(
    *,
    semantic_relevance: float,
    rrf_score: float,
    graph_hops: int,
    evidence_confidence: float,
    signals: Mapping[str, float],
    weights: RankingWeights,
) -> ScoreBreakdown:
    weight_map = weights.as_dict()
    components = {
        "rrf": clamp(rrf_score),
        "semantic_relevance": clamp(semantic_relevance),
        "citation_influence": clamp(signals.get("citation_influence", 0.0)),
        "recency": clamp(signals.get("recency", 0.0)),
        "venue_quality": clamp(signals.get("venue_quality", 0.0)),
        "topic_coverage": clamp(signals.get("topic_coverage", 0.0)),
        "evidence_confidence": clamp(evidence_confidence),
        "graph_hops": float(max(0, graph_hops)),
    }
    denominator = sum(weight_map.values())
    final_score = sum(components[key] * value for key, value in weight_map.items()) / denominator
    return ScoreBreakdown(components=components, weights=weight_map, final_score=clamp(final_score))


def max_channel_relevance(rankings: Iterable[Sequence[Candidate]]) -> dict[str, float]:
    """Keep absolute channel relevance; RRF alone only expresses ordering."""

    values: dict[str, float] = {}
    for ranking in rankings:
        for item in ranking:
            if item.channel == "keyword":
                score = item.score / (1.0 + max(0.0, item.score))
            else:
                score = clamp(item.score)
            values[item.entity_id] = max(values.get(item.entity_id, 0.0), score)
    return values


def _number(value: object, default: float) -> float:
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    return default


def _strings(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    if isinstance(value, (list, tuple, set, frozenset)):
        return tuple(item for item in value if isinstance(item, str))
    return ()
