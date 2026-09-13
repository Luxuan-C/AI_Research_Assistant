"""Academic profiles projected from the public ranking contracts.

The profile page does not own retrieval or a second graph repository. Its
caller supplies one immutable, bounded snapshot made of the ranking package's
entity, relationship, and validated-evidence projections.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from ranking import (
    PUBLICATION,
    RESEARCHER,
    EntityRecord,
    EvidenceItem,
    GraphEdge,
)


@dataclass(frozen=True, slots=True)
class AcademicProfileSnapshot:
    """The bounded ranking data needed to render one researcher profile."""

    academic: EntityRecord
    entities: Mapping[str, EntityRecord]
    relationships: tuple[GraphEdge, ...]
    validated_evidence_by_id: Mapping[str, EvidenceItem]
    searchable_text: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.academic.kind != RESEARCHER:
            raise ValueError("Academic profiles require a researcher entity")
        if self.entities.get(self.academic.entity_id) != self.academic:
            raise ValueError("Profile snapshot entities must include its researcher")
        if any(not isinstance(value, str) for value in self.searchable_text):
            raise ValueError("Profile search text must contain only strings")


@dataclass(frozen=True, slots=True)
class ProfileCitation:
    evidence_id: str
    uri: str
    excerpt: str


@dataclass(frozen=True, slots=True)
class AcademicProfileSummary:
    status: str
    text: str
    citations: tuple[ProfileCitation, ...]


@dataclass(frozen=True, slots=True)
class AcademicProfile:
    academic: EntityRecord
    structured_information: Mapping[str, Any]
    relationships: tuple[GraphEdge, ...]
    publications: tuple[EntityRecord, ...]
    summary: AcademicProfileSummary


class AcademicProfileService:
    """Build an evidence-grounded profile from one ranking snapshot."""

    def get_profile(self, snapshot: AcademicProfileSnapshot) -> AcademicProfile:
        academic = snapshot.academic
        relationships = tuple(
            sorted(
                (
                    edge
                    for edge in snapshot.relationships
                    if academic.entity_id in (edge.source_id, edge.target_id)
                ),
                key=lambda item: item.edge_id,
            )
        )
        publications = tuple(
            sorted(
                (
                    entity
                    for edge in relationships
                    if edge.relation_type == "AUTHORED"
                    for related_id in (_related_id(edge, academic.entity_id),)
                    for entity in (snapshot.entities.get(related_id),)
                    if entity is not None and entity.kind == PUBLICATION
                ),
                key=lambda item: item.entity_id,
            )
        )
        evidence = self._profile_evidence(snapshot, relationships, publications)
        citations = tuple(
            ProfileCitation(item.evidence_id, item.source_url, item.excerpt)
            for item in evidence
        )
        institution = self._affiliation(academic, relationships, snapshot.entities)

        structured_information = {
            "id": academic.entity_id,
            "name": academic.label,
            "entity_type": academic.kind,
            "source_urls": academic.source_urls,
            "institution": institution,
        }
        return AcademicProfile(
            academic=academic,
            structured_information=structured_information,
            relationships=relationships,
            publications=publications,
            summary=_build_grounded_summary(academic, publications, evidence, citations),
        )

    @staticmethod
    def _profile_evidence(
        snapshot: AcademicProfileSnapshot,
        relationships: Sequence[GraphEdge],
        publications: Sequence[EntityRecord],
    ) -> tuple[EvidenceItem, ...]:
        evidence_ids = tuple(
            dict.fromkeys(
                (
                    *snapshot.academic.evidence_ids,
                    *(
                        evidence_id
                        for edge in relationships
                        for evidence_id in edge.evidence_ids
                    ),
                    *(
                        evidence_id
                        for publication in publications
                        for evidence_id in publication.evidence_ids
                    ),
                )
            )
        )
        return tuple(
            sorted(
                (
                    snapshot.validated_evidence_by_id[evidence_id]
                    for evidence_id in evidence_ids
                    if evidence_id in snapshot.validated_evidence_by_id
                ),
                key=lambda item: (-item.confidence, item.evidence_id),
            )
        )

    @staticmethod
    def _affiliation(
        academic: EntityRecord,
        relationships: Sequence[GraphEdge],
        entities: Mapping[str, EntityRecord],
    ) -> str | None:
        for edge in relationships:
            if edge.relation_type != "AFFILIATED_WITH":
                continue
            institution = entities.get(_related_id(edge, academic.entity_id))
            if institution is not None:
                return institution.label
        return None


def _related_id(edge: GraphEdge, entity_id: str) -> str:
    return edge.target_id if edge.source_id == entity_id else edge.source_id


def _build_grounded_summary(
    academic: EntityRecord,
    publications: Sequence[EntityRecord],
    evidence: Sequence[EvidenceItem],
    citations: Sequence[ProfileCitation],
) -> AcademicProfileSummary:
    citation_by_evidence = {item.evidence_id: item for item in citations}
    academic_evidence = next(
        (item for item in evidence if item.entity_id == academic.entity_id),
        None,
    )
    publication_ids = {publication.entity_id for publication in publications}
    publication_evidence = [
        item for item in evidence if item.entity_id in publication_ids
    ]

    if academic_evidence is None and not publication_evidence:
        return _insufficient_summary(citations)

    paragraphs: list[str] = []
    if academic_evidence is not None:
        citation = citation_by_evidence[academic_evidence.evidence_id]
        paragraphs.append(
            f"Current research directions and expertise: {academic_evidence.excerpt} "
            f"[{citation.evidence_id}]({citation.uri})"
        )

    if publications and publication_evidence:
        citation = citation_by_evidence[publication_evidence[0].evidence_id]
        publication_names = "; ".join(item.label for item in publications)
        paragraphs.append(
            f"Representative research publications: {publication_names}. "
            f"The available source describes this research as: {publication_evidence[0].excerpt} "
            f"[{citation.evidence_id}]({citation.uri})"
        )

    return (
        AcademicProfileSummary("ok", "\n\n".join(paragraphs), tuple(citations))
        if paragraphs
        else _insufficient_summary(citations)
    )


def _insufficient_summary(citations: Sequence[ProfileCitation]) -> AcademicProfileSummary:
    return AcademicProfileSummary(
        status="insufficient_information",
        text="Insufficient verified information is available to produce a reliable academic summary.",
        citations=tuple(citations),
    )
