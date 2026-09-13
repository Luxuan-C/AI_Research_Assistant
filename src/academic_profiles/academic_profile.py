
# Academic Profiles

# This package contains the academic profile page feature.

# Planned responsibilities:

# - Load an individual researcher profile.
# - Present structured academic information.
# - Build concise summaries from verified evidence.
# - Attach citations and source links to supported statements.
# - Report insufficient information when the evidence is incomplete.



from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from academic_graphrag.interfaces import AcademicGraphRepository
from academic_graphrag.models import Entity, Evidence, Relationship


@dataclass(frozen=True, slots=True)
class ProfileCitation:
    evidence_id: str
    source_id: str
    uri: str
    excerpt: str


@dataclass(frozen=True, slots=True)
class AcademicProfileSummary:
    status: str
    text: str
    citations: tuple[ProfileCitation, ...]


@dataclass(frozen=True, slots=True)
class AcademicProfile:
    academic: Entity
    structured_information: Mapping[str, Any]
    relationships: tuple[Relationship, ...]
    publications: tuple[Entity, ...]
    summary: AcademicProfileSummary


class AcademicProfileService:
    """Build profiles using only graph entities and verified source evidence."""

    def __init__(self, repository: AcademicGraphRepository) -> None:
        self.repository = repository

    def get_profile(self, academic_id: str) -> AcademicProfile | None:
        academic = self._find_academic(academic_id)
        if academic is None:
            return None

        relationships = tuple(
            sorted(
                self.repository.get_relationships((academic.id,)),
                key=lambda item: item.id,
            )
        )
        related_ids = tuple(
            edge.target_id if edge.source_id == academic.id else edge.source_id
            for edge in relationships
        )
        related_entities = {
            entity.id: entity
            for entity in self.repository.get_entities(related_ids)
        }
        publications = tuple(
            entity
            for edge in relationships
            if edge.relation_type == "AUTHORED"
            for entity in (related_entities.get(edge.target_id),)
            if entity is not None and entity.entity_type == "Publication"
        )
        evidence = self._profile_evidence(academic, relationships, publications)
        citations = self._citations(evidence)
        summary = _build_grounded_summary(academic, publications, evidence, citations)
        institution = self._affiliation(academic, relationships, related_entities)

        structured_information = {
            "id": academic.id,
            "name": academic.label,
            "entity_type": academic.entity_type,
            "description": academic.text,
            "aliases": academic.aliases,
            "metadata": dict(academic.metadata),
            "institution": institution,
        }
        return AcademicProfile(
            academic=academic,
            structured_information=structured_information,
            relationships=relationships,
            publications=publications,
            summary=summary,
        )

    def _find_academic(self, academic_id: str) -> Entity | None:
        entities = self.repository.get_entities((academic_id,))
        if not entities or entities[0].entity_type != "Researcher":
            return None
        return entities[0]

    def _profile_evidence(
        self,
        academic: Entity,
        relationships: Sequence[Relationship],
        publications: Sequence[Entity],
    ) -> tuple[Evidence, ...]:
        supported_ids = (
            academic.id,
            *(edge.id for edge in relationships),
            *(publication.id for publication in publications),
        )
        evidence = self.repository.get_evidence(supported_ids)
        return tuple(sorted(evidence, key=lambda item: (-item.confidence, item.id)))

    def _citations(self, evidence: Sequence[Evidence]) -> tuple[ProfileCitation, ...]:
        sources = {
            source.id: source
            for source in self.repository.get_sources(
                tuple(item.source_record_id for item in evidence)
            )
        }
        return tuple(
            ProfileCitation(
                evidence_id=item.id,
                source_id=item.source_record_id,
                uri=sources[item.source_record_id].uri,
                excerpt=item.excerpt,
            )
            for item in evidence
            if item.source_record_id in sources
        )

    @staticmethod
    def _affiliation(
        academic: Entity,
        relationships: Sequence[Relationship],
        entities: Mapping[str, Entity],
    ) -> str | None:
        for edge in relationships:
            if edge.relation_type != "AFFILIATED_WITH":
                continue
            related_id = edge.target_id if edge.source_id == academic.id else edge.source_id
            institution = entities.get(related_id)
            if institution is not None:
                return institution.label
        return None


def _build_grounded_summary(
    academic: Entity,
    publications: Sequence[Entity],
    evidence: Sequence[Evidence],
    citations: Sequence[ProfileCitation],
) -> AcademicProfileSummary:
    citation_by_evidence = {item.evidence_id: item for item in citations}
    academic_evidence = next(
        (item for item in evidence if academic.id in item.supports_ids),
        None,
    )
    publication_evidence = [
        item
        for item in evidence
        if any(publication.id in item.supports_ids for publication in publications)
    ]

    if academic_evidence is None and not publication_evidence:
        return AcademicProfileSummary(
            status="insufficient_information",
            text="Insufficient verified information is available to produce a reliable academic summary.",
            citations=tuple(citations),
        )

    paragraphs: list[str] = []
    if academic_evidence is not None:
        citation = citation_by_evidence.get(academic_evidence.id)
        if citation is not None:
            paragraphs.append(
                f"Current research directions and expertise: {academic_evidence.excerpt} "
                f"[{citation.evidence_id}]({citation.uri})"
            )

    if publications and publication_evidence:
        publication_names = "; ".join(item.label for item in publications)
        citation = citation_by_evidence.get(publication_evidence[0].id)
        if citation is not None:
            paragraphs.append(
                f"Representative research publications: {publication_names}. "
                f"The available source describes this research as: {publication_evidence[0].excerpt} "
                f"[{citation.evidence_id}]({citation.uri})"
            )

    if not paragraphs:
        return AcademicProfileSummary(
            status="insufficient_information",
            text="Insufficient verified information is available to produce a reliable academic summary.",
            citations=tuple(citations),
        )
    return AcademicProfileSummary(
        status="ok",
        text="\n\n".join(paragraphs),
        citations=tuple(citations),
    )
