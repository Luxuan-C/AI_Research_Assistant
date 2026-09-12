"""Reusable deterministic fixtures for the retrieval/ranking test suite."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date
import math
import re
from typing import Mapping, Sequence
from uuid import UUID, uuid5

from ranking import (
    PUBLICATION,
    RESEARCHER,
    EntityRecord,
    EvidenceItem,
    GraphBudget,
    QueryPlan,
    RetrievalHit,
    SchemaRelationshipGraph,
    edges_from_fixed_schema_rows,
)


_NAMESPACE = UUID("8f87b47c-c46f-4bcf-9404-b53674377058")
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
        "for",
        "from",
        "how",
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


def stable_id(kind: str, authority: str, external_id: str) -> str:
    material = "\x00".join((kind.strip().lower(), authority.strip().lower(), external_id.strip()))
    return f"{kind.strip().lower()}:{uuid5(_NAMESPACE, material)}"


def stable_relationship_id(
    relation_type: str,
    source_id: str,
    target_id: str,
    discriminator: str = "",
) -> str:
    material = "\x00".join((relation_type, source_id, target_id, discriminator))
    return f"relationship:{uuid5(_NAMESPACE, material)}"


def tokenize(value: str) -> tuple[str, ...]:
    return tuple(token for token in _TOKEN.findall(value.lower()) if token not in _STOPWORDS)


class DeterministicBM25RetrievalPort:
    """In-memory BM25 plus optional static dense ranks for tests only."""

    def __init__(
        self,
        entities: Sequence[EntityRecord],
        search_text: Mapping[str, str],
        *,
        attributes: Mapping[str, Mapping[str, object]] | None = None,
        dense_scores: Mapping[str, float] | None = None,
        k1: float = 1.5,
        b: float = 0.75,
    ) -> None:
        self.entities = {entity.entity_id: entity for entity in entities}
        self.search_text = dict(search_text)
        self.attributes = dict(attributes or {})
        self.dense_scores = dict(dense_scores) if dense_scores is not None else None
        self.k1 = k1
        self.b = b

    def retrieve(self, plan: QueryPlan) -> Mapping[str, Sequence[RetrievalHit]]:
        eligible = {
            entity_id: entity
            for entity_id, entity in self.entities.items()
            if entity.kind in plan.target_kinds and self._matches_filters(entity_id, plan.filters)
        }
        output: dict[str, Sequence[RetrievalHit]] = {
            "lexical": self._lexical(plan, eligible),
        }
        if self.dense_scores is not None:
            ranked_dense = sorted(
                (
                    (entity_id, score)
                    for entity_id, score in self.dense_scores.items()
                    if entity_id in eligible
                ),
                key=lambda item: (-item[1], item[0]),
            )[: plan.seed_limit]
            output["dense"] = tuple(
                RetrievalHit(eligible[entity_id], "dense", rank, score)
                for rank, (entity_id, score) in enumerate(ranked_dense, start=1)
            )
        return output

    def _lexical(
        self,
        plan: QueryPlan,
        entities: Mapping[str, EntityRecord],
    ) -> tuple[RetrievalHit, ...]:
        query_tokens = tokenize(plan.text)
        documents = {
            entity_id: tokenize(self.search_text.get(entity_id, entity.label))
            for entity_id, entity in entities.items()
        }
        if not query_tokens or not documents:
            return ()
        average_length = sum(len(tokens) for tokens in documents.values()) / len(documents)
        document_frequency = Counter(token for tokens in documents.values() for token in set(tokens))
        scored: list[tuple[str, float]] = []
        document_count = len(documents)
        for entity_id, tokens in documents.items():
            frequencies = Counter(tokens)
            score = 0.0
            for token in query_tokens:
                frequency = frequencies.get(token, 0)
                if frequency == 0:
                    continue
                frequency_documents = document_frequency[token]
                inverse_document_frequency = math.log(
                    1.0
                    + (document_count - frequency_documents + 0.5)
                    / (frequency_documents + 0.5)
                )
                denominator = frequency + self.k1 * (
                    1.0 - self.b + self.b * len(tokens) / max(1.0, average_length)
                )
                score += (
                    inverse_document_frequency
                    * frequency
                    * (self.k1 + 1.0)
                    / denominator
                )
            if score > 0.0:
                scored.append((entity_id, score))
        scored.sort(key=lambda item: (-item[1], item[0]))
        return tuple(
            RetrievalHit(entities[entity_id], "lexical", rank, score)
            for rank, (entity_id, score) in enumerate(scored[: plan.seed_limit], start=1)
        )

    def _matches_filters(self, entity_id: str, filters: Mapping[str, object]) -> bool:
        attributes = self.attributes.get(entity_id, {})
        return all(attributes.get(key) == expected for key, expected in filters.items())


@dataclass(frozen=True, slots=True)
class MockScenario:
    entities: tuple[EntityRecord, ...]
    retrieval: DeterministicBM25RetrievalPort
    graph: SchemaRelationshipGraph
    evidence: Mapping[str, EvidenceItem]


def build_mock_scenario(*, budget: GraphBudget | None = None) -> MockScenario:
    ids = {
        "alice": stable_id(RESEARCHER, "orcid", "0000-0001"),
        "bob": stable_id(RESEARCHER, "orcid", "0000-0002"),
        "paper_ai": stable_id(PUBLICATION, "doi", "10.1000/ai-aged-care"),
        "paper_robotics": stable_id(PUBLICATION, "doi", "10.1000/robotics-aged-care"),
        "paper_ev": stable_id(PUBLICATION, "doi", "10.1000/ev-emissions"),
        "usyd": stable_id("university", "ror", "03n0gvg35"),
    }
    evidence_ids = {name: stable_id("evidence", "mock", name) for name in ids}
    entities = (
        EntityRecord(ids["alice"], RESEARCHER, "Dr Alice Chen", evidence_ids=(evidence_ids["alice"],)),
        EntityRecord(ids["bob"], RESEARCHER, "Dr Bob Nguyen", evidence_ids=(evidence_ids["bob"],)),
        EntityRecord(
            ids["paper_ai"],
            PUBLICATION,
            "Trustworthy AI for Aged Care Monitoring",
            publication_date=date(2025, 1, 1),
            citation_score=0.55,
            evidence_ids=(evidence_ids["paper_ai"],),
        ),
        EntityRecord(
            ids["paper_robotics"],
            PUBLICATION,
            "Assistive Robotics in Residential Aged Care",
            publication_date=date(2024, 1, 1),
            citation_score=0.45,
            evidence_ids=(evidence_ids["paper_robotics"],),
        ),
        EntityRecord(
            ids["paper_ev"],
            PUBLICATION,
            "Life-cycle Emissions of Electric Vehicles",
            publication_date=date(2023, 1, 1),
            citation_score=0.70,
            evidence_ids=(evidence_ids["paper_ev"],),
        ),
        EntityRecord(ids["usyd"], "university", "The University of Sydney"),
    )
    academic_rows = (
        {
            "id": ids["alice"],
            "research_paper_ids": [ids["paper_ai"], ids["paper_robotics"]],
            "university_ids": [ids["usyd"]],
        },
        {
            "id": ids["bob"],
            "research_paper_ids": [ids["paper_robotics"]],
            "university_ids": [ids["usyd"]],
        },
    )
    paper_rows = (
        {"id": ids["paper_ai"], "academic_ids": [ids["alice"]]},
        {"id": ids["paper_robotics"], "academic_ids": [ids["alice"], ids["bob"]]},
        {"id": ids["paper_ev"], "academic_ids": []},
    )
    search_text = {
        ids["alice"]: "Alice Chen trustworthy artificial intelligence aged care",
        ids["bob"]: "Bob Nguyen assistive robotics residential aged care",
        ids["paper_ai"]: "Trustworthy AI artificial intelligence aged care monitoring",
        ids["paper_robotics"]: "Assistive robotics residential aged care robots",
        ids["paper_ev"]: "Electric vehicles life cycle emissions sustainability",
    }
    attributes = {
        ids["alice"]: {"institution": "The University of Sydney"},
        ids["bob"]: {"institution": "The University of Sydney"},
        ids["paper_ai"]: {"institution": "The University of Sydney"},
        ids["paper_robotics"]: {"institution": "The University of Sydney"},
        ids["paper_ev"]: {"institution": "Monash University"},
    }
    dense_scores = {
        ids["paper_ai"]: 0.91,
        ids["paper_robotics"]: 0.88,
        ids["alice"]: 0.82,
        ids["bob"]: 0.79,
    }
    evidence = {
        evidence_ids["alice"]: EvidenceItem(
            evidence_ids["alice"], ids["alice"], "https://example.edu/alice", "Alice researches trustworthy AI."
        ),
        evidence_ids["bob"]: EvidenceItem(
            evidence_ids["bob"], ids["bob"], "https://example.edu/bob", "Bob researches assistive robotics."
        ),
        evidence_ids["paper_ai"]: EvidenceItem(
            evidence_ids["paper_ai"], ids["paper_ai"], "https://doi.org/10.1000/ai-aged-care", "A study of AI monitoring in aged care."
        ),
        evidence_ids["paper_robotics"]: EvidenceItem(
            evidence_ids["paper_robotics"], ids["paper_robotics"], "https://doi.org/10.1000/robotics-aged-care", "A study of assistive robots in aged care."
        ),
        evidence_ids["paper_ev"]: EvidenceItem(
            evidence_ids["paper_ev"], ids["paper_ev"], "https://doi.org/10.1000/ev-emissions", "A study of electric-vehicle emissions."
        ),
    }
    retrieval = DeterministicBM25RetrievalPort(
        entities,
        search_text,
        attributes=attributes,
        dense_scores=dense_scores,
    )
    graph = SchemaRelationshipGraph(
        entities,
        edges_from_fixed_schema_rows(academics=academic_rows, research_papers=paper_rows),
        budget=budget,
    )
    return MockScenario(entities, retrieval, graph, evidence)
