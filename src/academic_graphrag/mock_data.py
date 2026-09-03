"""Small public-style academic graph for local development and unit tests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from .identity import stable_id, stable_relationship_id
from .in_memory import (
    BM25KeywordRetriever,
    DeterministicHashEmbeddingProvider,
    InMemoryAcademicRepository,
    InMemoryDenseRetriever,
    PassthroughReranker,
)
from .models import Entity, Evidence, Relationship, SourceRecord
from .pipeline import GraphRAGEngine, PipelineConfig
from .ranking import MetadataAcademicSignalProvider


@dataclass(frozen=True, slots=True)
class MockBackend:
    repository: InMemoryAcademicRepository
    engine: GraphRAGEngine


def build_mock_backend(config: PipelineConfig | None = None) -> MockBackend:
    data = _build_data()
    repository = InMemoryAcademicRepository(**data)
    embeddings = DeterministicHashEmbeddingProvider(dimensions=1024)
    engine = GraphRAGEngine(
        repository=repository,
        keyword_retriever=BM25KeywordRetriever(repository),
        dense_retriever=InMemoryDenseRetriever(repository, embeddings),
        reranker=PassthroughReranker(),
        signal_provider=MetadataAcademicSignalProvider(current_year=2026),
        config=config,
    )
    return MockBackend(repository=repository, engine=engine)


def _build_data() -> dict[str, tuple[object, ...]]:
    ids = {
        "usyd": stable_id("Institution", "ror", "03n0gvg35"),
        "monash": stable_id("Institution", "ror", "02bfwt286"),
        "alice": stable_id("Researcher", "orcid", "0000-0001-1000-1001"),
        "bob": stable_id("Researcher", "orcid", "0000-0002-2000-2002"),
        "carol": stable_id("Researcher", "orcid", "0000-0003-3000-3003"),
        "p_ai_aged": stable_id("Publication", "doi", "10.1000/ai-aged-care"),
        "p_robotics": stable_id("Publication", "doi", "10.1000/assistive-robotics"),
        "p_ev": stable_id("Publication", "doi", "10.1000/ev-emissions"),
        "p_health_ai": stable_id("Publication", "doi", "10.1000/human-health-ai"),
        "t_ai": stable_id("Topic", "mock-taxonomy", "artificial-intelligence"),
        "t_aged": stable_id("Topic", "mock-taxonomy", "aged-care"),
        "t_robotics": stable_id("Topic", "mock-taxonomy", "assistive-robotics"),
        "t_ev": stable_id("Topic", "mock-taxonomy", "electric-vehicles"),
        "t_sustainability": stable_id("Topic", "mock-taxonomy", "sustainability"),
    }

    source_ids = {
        "alice": stable_id("SourceRecord", "usyd", "alice-chen-profile"),
        "bob": stable_id("SourceRecord", "usyd", "bob-nguyen-profile"),
        "carol": stable_id("SourceRecord", "monash", "carol-smith-profile"),
        "p_ai_aged": stable_id("SourceRecord", "crossref", "10.1000/ai-aged-care"),
        "p_robotics": stable_id("SourceRecord", "crossref", "10.1000/assistive-robotics"),
        "p_ev": stable_id("SourceRecord", "crossref", "10.1000/ev-emissions"),
        "p_health_ai": stable_id("SourceRecord", "crossref", "10.1000/human-health-ai"),
    }
    evidence_ids = {
        key: stable_id("Evidence", "mock", key)
        for key in source_ids
    }

    entities = (
        Entity(ids["usyd"], "Institution", "The University of Sydney", metadata={"country": "Australia"}),
        Entity(ids["monash"], "Institution", "Monash University", metadata={"country": "Australia"}),
        Entity(
            ids["alice"],
            "Researcher",
            "Dr Alice Chen",
            "Researches trustworthy artificial intelligence and human-centred monitoring for aged care.",
            aliases=("Alice Chen",),
            metadata={
                "institution": "The University of Sydney",
                "discipline": "Computer Science",
                "topics": ("artificial intelligence", "aged care", "health AI"),
                "citation_count": 420,
                "latest_publication_year": 2026,
                "venue_quality": 0.84,
            },
        ),
        Entity(
            ids["bob"],
            "Researcher",
            "Dr Bob Nguyen",
            "Develops assistive robotics and safe human-robot interaction for residential aged care.",
            aliases=("Bob Nguyen",),
            metadata={
                "institution": "The University of Sydney",
                "discipline": "Engineering",
                "topics": ("assistive robotics", "aged care", "human robot interaction"),
                "citation_count": 180,
                "latest_publication_year": 2024,
                "venue_quality": 0.76,
            },
        ),
        Entity(
            ids["carol"],
            "Researcher",
            "Professor Carol Smith",
            "Studies life-cycle emissions, transport policy, and environmental impacts of electric vehicles.",
            aliases=("Carol Smith",),
            metadata={
                "institution": "Monash University",
                "discipline": "Environmental Engineering",
                "topics": ("electric vehicles", "life cycle emissions", "sustainability"),
                "citation_count": 650,
                "latest_publication_year": 2023,
                "venue_quality": 0.88,
            },
        ),
        Entity(
            ids["p_ai_aged"],
            "Publication",
            "Trustworthy AI for Aged Care Monitoring",
            "A study of interpretable machine learning for safe monitoring in residential aged care.",
            metadata={
                "doi": "10.1000/ai-aged-care",
                "year": 2025,
                "citation_count": 42,
                "venue_quality": 0.91,
                "topics": ("artificial intelligence", "aged care", "trustworthy AI"),
                "institution": "The University of Sydney",
            },
        ),
        Entity(
            ids["p_robotics"],
            "Publication",
            "Assistive Robotics in Residential Aged Care",
            "Co-designed mobile robots that support older adults and care workers.",
            metadata={
                "doi": "10.1000/assistive-robotics",
                "year": 2024,
                "citation_count": 30,
                "venue_quality": 0.83,
                "topics": ("assistive robotics", "aged care"),
                "institution": "The University of Sydney",
            },
        ),
        Entity(
            ids["p_ev"],
            "Publication",
            "Life-cycle Emissions of Electric Vehicles in Australia",
            "Compares manufacturing, electricity generation, and operating emissions for electric vehicles.",
            metadata={
                "doi": "10.1000/ev-emissions",
                "year": 2023,
                "citation_count": 85,
                "venue_quality": 0.89,
                "topics": ("electric vehicles", "life cycle emissions", "sustainability"),
                "institution": "Monash University",
            },
        ),
        Entity(
            ids["p_health_ai"],
            "Publication",
            "Human-centred Evaluation of Health AI",
            "A framework for evaluating clinical usefulness, transparency, and user trust in health AI.",
            metadata={
                "doi": "10.1000/human-health-ai",
                "year": 2026,
                "citation_count": 8,
                "venue_quality": 0.80,
                "topics": ("health AI", "human centred design", "artificial intelligence"),
                "institution": "The University of Sydney",
            },
        ),
        Entity(ids["t_ai"], "Topic", "Artificial Intelligence", metadata={"topics": ("artificial intelligence",)}),
        Entity(ids["t_aged"], "Topic", "Aged Care", metadata={"topics": ("aged care",)}),
        Entity(ids["t_robotics"], "Topic", "Assistive Robotics", metadata={"topics": ("assistive robotics",)}),
        Entity(ids["t_ev"], "Topic", "Electric Vehicles", metadata={"topics": ("electric vehicles",)}),
        Entity(ids["t_sustainability"], "Topic", "Sustainability", metadata={"topics": ("sustainability",)}),
    )

    def edge(
        relation_type: str,
        source: str,
        target: str,
        evidence_key: str,
    ) -> Relationship:
        return Relationship(
            id=stable_relationship_id(relation_type, source, target),
            source_id=source,
            target_id=target,
            relation_type=relation_type,
            confidence=0.95,
            evidence_ids=(evidence_ids[evidence_key],),
        )

    academic_edges = (
        edge("AUTHORED", ids["alice"], ids["p_ai_aged"], "p_ai_aged"),
        edge("AUTHORED", ids["alice"], ids["p_robotics"], "p_robotics"),
        edge("AUTHORED", ids["bob"], ids["p_robotics"], "p_robotics"),
        edge("AUTHORED", ids["carol"], ids["p_ev"], "p_ev"),
        edge("AUTHORED", ids["alice"], ids["p_health_ai"], "p_health_ai"),
        edge("AFFILIATED_WITH", ids["alice"], ids["usyd"], "alice"),
        edge("AFFILIATED_WITH", ids["bob"], ids["usyd"], "bob"),
        edge("AFFILIATED_WITH", ids["carol"], ids["monash"], "carol"),
        edge("ABOUT", ids["p_ai_aged"], ids["t_ai"], "p_ai_aged"),
        edge("ABOUT", ids["p_ai_aged"], ids["t_aged"], "p_ai_aged"),
        edge("ABOUT", ids["p_robotics"], ids["t_robotics"], "p_robotics"),
        edge("ABOUT", ids["p_robotics"], ids["t_aged"], "p_robotics"),
        edge("ABOUT", ids["p_ev"], ids["t_ev"], "p_ev"),
        edge("ABOUT", ids["p_ev"], ids["t_sustainability"], "p_ev"),
        edge("ABOUT", ids["p_health_ai"], ids["t_ai"], "p_health_ai"),
        edge("CITES", ids["p_health_ai"], ids["p_ai_aged"], "p_health_ai"),
    )
    edge_by_key = {
        (item.relation_type, item.source_id, item.target_id): item.id
        for item in academic_edges
    }

    sources = (
        SourceRecord(source_ids["alice"], "university", "https://example.edu/alice-chen", observed_at=datetime(2026, 8, 20, tzinfo=UTC)),
        SourceRecord(source_ids["bob"], "university", "https://example.edu/bob-nguyen", observed_at=datetime(2026, 8, 20, tzinfo=UTC)),
        SourceRecord(source_ids["carol"], "university", "https://example.edu/carol-smith", observed_at=datetime(2026, 8, 20, tzinfo=UTC)),
        SourceRecord(source_ids["p_ai_aged"], "Crossref", "https://doi.org/10.1000/ai-aged-care", external_id="10.1000/ai-aged-care", observed_at=datetime(2026, 8, 21, tzinfo=UTC)),
        SourceRecord(source_ids["p_robotics"], "Crossref", "https://doi.org/10.1000/assistive-robotics", external_id="10.1000/assistive-robotics", observed_at=datetime(2026, 8, 21, tzinfo=UTC)),
        SourceRecord(source_ids["p_ev"], "Crossref", "https://doi.org/10.1000/ev-emissions", external_id="10.1000/ev-emissions", observed_at=datetime(2026, 8, 21, tzinfo=UTC)),
        SourceRecord(source_ids["p_health_ai"], "Crossref", "https://doi.org/10.1000/human-health-ai", external_id="10.1000/human-health-ai", observed_at=datetime(2026, 8, 21, tzinfo=UTC)),
    )

    evidence = (
        Evidence(
            evidence_ids["alice"],
            source_ids["alice"],
            (
                ids["alice"],
                edge_by_key[("AFFILIATED_WITH", ids["alice"], ids["usyd"])],
            ),
            "Alice Chen is a University of Sydney researcher working on trustworthy AI and aged care.",
            0.98,
            "profile summary",
        ),
        Evidence(
            evidence_ids["bob"],
            source_ids["bob"],
            (
                ids["bob"],
                edge_by_key[("AFFILIATED_WITH", ids["bob"], ids["usyd"])],
            ),
            "Bob Nguyen researches assistive robotics for residential aged care at the University of Sydney.",
            0.98,
            "profile summary",
        ),
        Evidence(
            evidence_ids["carol"],
            source_ids["carol"],
            (
                ids["carol"],
                edge_by_key[("AFFILIATED_WITH", ids["carol"], ids["monash"])],
            ),
            "Carol Smith studies environmental impacts of electric vehicles at Monash University.",
            0.98,
            "profile summary",
        ),
        Evidence(
            evidence_ids["p_ai_aged"],
            source_ids["p_ai_aged"],
            (
                ids["p_ai_aged"],
                edge_by_key[("AUTHORED", ids["alice"], ids["p_ai_aged"])],
                edge_by_key[("ABOUT", ids["p_ai_aged"], ids["t_ai"])],
                edge_by_key[("ABOUT", ids["p_ai_aged"], ids["t_aged"])],
            ),
            "The publication evaluates interpretable AI for safe monitoring in residential aged care.",
            0.95,
            "title and abstract",
        ),
        Evidence(
            evidence_ids["p_robotics"],
            source_ids["p_robotics"],
            (
                ids["p_robotics"],
                edge_by_key[("AUTHORED", ids["alice"], ids["p_robotics"])],
                edge_by_key[("AUTHORED", ids["bob"], ids["p_robotics"])],
                edge_by_key[("ABOUT", ids["p_robotics"], ids["t_robotics"])],
                edge_by_key[("ABOUT", ids["p_robotics"], ids["t_aged"])],
            ),
            "Alice Chen and Bob Nguyen co-authored a publication about assistive robots in aged care.",
            0.95,
            "author and subject metadata",
        ),
        Evidence(
            evidence_ids["p_ev"],
            source_ids["p_ev"],
            (
                ids["p_ev"],
                edge_by_key[("AUTHORED", ids["carol"], ids["p_ev"])],
                edge_by_key[("ABOUT", ids["p_ev"], ids["t_ev"])],
                edge_by_key[("ABOUT", ids["p_ev"], ids["t_sustainability"])],
            ),
            "The publication compares life-cycle greenhouse emissions for electric vehicles in Australia.",
            0.95,
            "title and abstract",
        ),
        Evidence(
            evidence_ids["p_health_ai"],
            source_ids["p_health_ai"],
            (
                ids["p_health_ai"],
                edge_by_key[("AUTHORED", ids["alice"], ids["p_health_ai"])],
                edge_by_key[("ABOUT", ids["p_health_ai"], ids["t_ai"])],
                edge_by_key[("CITES", ids["p_health_ai"], ids["p_ai_aged"])],
            ),
            "The publication proposes a human-centred evaluation framework for health AI and cites the aged-care monitoring study.",
            0.95,
            "title, abstract, and references",
        ),
    )
    support_edges = tuple(
        Relationship(
            id=stable_relationship_id("SUPPORTS", item.source_record_id, item.id),
            source_id=item.source_record_id,
            target_id=item.id,
            relation_type="SUPPORTS",
            confidence=item.confidence,
        )
        for item in evidence
    )

    return {
        "entities": entities,
        "relationships": (*academic_edges, *support_edges),
        "evidence": evidence,
        "sources": sources,
    }
