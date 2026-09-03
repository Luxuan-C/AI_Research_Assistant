## Current scope

Implemented:

- extensible `Researcher`, `Publication`, `Institution`, `Topic`, `SourceRecord`, and `Evidence` models;
- opaque deterministic IDs and typed relationships;
- repository, keyword, dense, embedding, reranking, academic-signal, and future LLM interfaces;
- an in-memory repository and sourced mock academic dataset;
- BM25 keyword retrieval and a deterministic mock embedding adapter;
- Reciprocal Rank Fusion (RRF);
- relation-aware graph expansion with hop, entity, relationship, neighbor, and confidence limits;
- configurable semantic relevance, citation influence, recency, venue quality, and topic coverage;
- sourced evidence selection, explainable score components, and generation-ready context;
- configurable relevance/evidence thresholds with fail-closed `insufficient_information` responses.

Not implemented in this version:

- a production Supabase/PostgreSQL repository;
- production full-text or pgvector queries;
- a real semantic embedding model or cross-encoder reranker;
- LLM generation or citation validation after generation;
- HTTP routes or deployment configuration;
- a final production database schema.

## Module boundaries

```text
src/academic_graphrag/
  models.py       Open domain, query, score, evidence, and response contracts
  interfaces.py   Repository and provider ports
  identity.py     Storage-independent deterministic identities
  in_memory.py    In-memory repository, BM25, mock embeddings, dense search
  ranking.py      RRF and configurable academic ranking signals
  traversal.py    Bounded academic graph expansion
  pipeline.py     Public GraphRAGEngine orchestration
  mock_data.py    Sourced local academic graph and ready-to-run engine
```

The core depends on interfaces, not database or provider SDKs:

```text
KeywordRetriever ----\
DenseRetriever -------+--> RRF --> bounded graph expansion --> Reranker
Repository -----------/                                      |
                                                             v
AcademicSignalProvider --> weighted scoring --> Evidence --> thresholds
                                                        |
                                                        v
                                              structured RetrievalResponse
```

`LLMProvider` is defined as a future port, but `GraphRAGEngine` does not call it. The response already contains a bounded `GenerationContext` with passages, evidence IDs, relationships, and provenance IDs.

## Domain contract

Entity and relationship types are strings rather than closed database enums. Additional fields live in open metadata until the production schema stabilises. The current canonical academic relationships are:

- `Researcher -AUTHORED-> Publication`
- `Researcher -AFFILIATED_WITH-> Institution`
- `Publication -ABOUT-> Topic`
- `Publication -CITES-> Publication`
- `SourceRecord -SUPPORTS-> Evidence`

The repository stores only the canonical authorship facts. Co-authorship is derived by traversing `Researcher -> Publication <- Researcher`; the unit tests demonstrate this two-hop path.

`Evidence.supports_ids` may reference an entity or relationship. Each evidence item identifies a `SourceRecord`, allowing every returned context passage to retain the original provider/source identifier.

## Run locally

Python 3.11 or later is required. The first version has no third-party runtime dependencies.

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Example:

```python
from academic_graphrag import RetrievalQuery
from academic_graphrag.mock_data import build_mock_backend

backend = build_mock_backend()
response = backend.engine.retrieve(
    RetrievalQuery(
        "How can artificial intelligence improve aged care?",
        limit=5,
        filters={"institution": "The University of Sydney"},
    )
)

print(response.status)
for result in response.results:
    print(result.rank, result.entity.label, result.score.final_score)
    print(result.score.components)
    print(result.provenance_ids)
```

The deterministic hash embedding adapter is only a local test double. It provides the dense retrieval contract without selecting a final model and should not be used as evidence of semantic-search quality.

## Retrieval flow

1. The keyword and dense adapters independently retrieve candidate entities.
2. RRF combines their ranks while absolute channel scores remain available for relevance.
3. The highest-ranked seeds are expanded over an allowlist of academic relationships.
4. Expansion is hard-bounded and treats relationships as traversable in either direction for discovery while preserving their canonical direction in output.
5. A reranker adapter receives the combined candidate pool. The default adapter preserves retrieval relevance; a future BGE cross-encoder adapter can replace it.
6. Academic signals are calculated by a replaceable provider and combined with configurable weights.
7. Evidence supporting the entity and graph path is joined to its source record.
8. Results below either the relevance or evidence-confidence threshold are rejected.
9. If nothing qualifies, the API returns `insufficient_information` with no generation passages.

RRF is reported as an explainability component, but final relevance does not depend on rank position alone. This prevents a weak top result from becoming confident merely because it ranked first in a low-quality channel.

## Configuration

`PipelineConfig` controls retrieval limits, RRF `k`, graph decay, evidence count, relevance/evidence thresholds, ranking weights, and traversal budgets. `TraversalConfig` controls allowed relationship types, maximum hops, maximum entities/relationships/neighbors, and minimum relationship confidence.

The initial `MetadataAcademicSignalProvider` reads configurable metadata keys. A production feature adapter may instead calculate citation, recency, venue, and topic signals from SQL views or another service without changing `GraphRAGEngine`.

## Future Supabase/PostgreSQL integration

Add adapters; do not change the core models or pipeline:

1. Implement `AcademicGraphRepository` in a separate infrastructure package.
2. Translate the current database rows/views into `Entity`, `Relationship`, `Evidence`, and `SourceRecord` at the adapter boundary.
3. Keep all Supabase table names, SQL columns, joins, and row-level-security details inside that adapter.
4. Implement `KeywordRetriever` with PostgreSQL full-text or another BM25-capable search and return provider-neutral `Candidate` objects.
5. Implement `DenseRetriever` with pgvector or another vector store behind the same interface.
6. Add a model-specific `EmbeddingProvider` and a BGE or equivalent `Reranker` adapter only after evaluation.
7. Add an `LLMProvider` adapter later; pass only `RetrievalResponse.generation_context` to it and validate generated citations separately.

The repository's `list_entities` method supports optional entity IDs, types, and open filters. A SQL adapter should translate those values to its current schema rather than exposing schema details to the core.

## Testing and limitations

The unit suite covers stable identity, RRF, BM25 and filters, derived co-authorship, traversal truncation, score/evidence output, generation context, configurable thresholds, and unrelated-query rejection.

The mock records and URLs are synthetic. They validate module behavior, not retrieval quality, real academic coverage, source correctness, or production performance. Evaluation against the client-approved query set and real sourced data remains required by the tutorial notes.
