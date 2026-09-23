# Academic GraphRAG

Academic GraphRAG retrieval, bounded evidence routing, and deterministic ranking.

## Requirements

- Python 3.11 or newer

## Install

From the repository root on Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install .
```

For development, use an editable install instead:

```powershell
python -m pip install -e .
```

## Retrieval and ranking boundary

`src/ranking` is the sole production pipeline package.
It keeps lexical and optional dense ranked lists separate until one RRF fusion,
projects read-only schema relationships into bounded graph paths, ranks
publications and researchers deterministically, and builds a bounded evidence
pack for one downstream generation call.

The ranking core has no Supabase, SQL, or LLM dependency. The database schema
and `src/database` implementation are owned externally. The ranking/RAG
subsystem accesses Supabase read-only through its own adapters under
`src/ranking`, using the existing schema as-is. It exposes deterministic
metadata/lexical retrieval only because this repository contains no production
vector column or RPC.

GraphRAG refers only to the bounded typed expansion behind
`GraphExpansionPort`; orchestration belongs to `RetrievalRankingPipeline`.

## HTTP API runtime

`src/api_server.py` is the production composition root for research data. At
server startup it validates `SUPABASE_URL` and `SUPABASE_KEY`, creates one
Supabase client, and constructs one shared read-only repository, retrieval
adapter, graph adapter, fusion service, and ranking service. Constructors do not
read tables or build the lexical corpus; those costs are paid lazily by the
first relevant request.

Run the API from the repository root with:

```bash
PYTHONPATH=src python3 -m api_server
```

The existing `/api/researchers`, `/api/researchers/{id}`, `/api/ask`, and
`/api/directory-options` routes keep their frontend-facing JSON fields. Internal
namespaced ranking IDs are converted back to raw database UUIDs at the HTTP
boundary. API reads use deterministic keyset pagination with a 4,000-row total
bound and expose `truncated` when either the data or result budget is reached.

The process-local repository uses a 60-second TTL. The tokenized lexical corpus
is a four-entry LRU keyed to repository table revisions, so TTL expiry or
explicit invalidation rebuilds it on demand. Cache state is shared safely by
handler threads, and cache coordination does not hold the repository state lock
during Supabase requests. Research retrieval and ranking fixtures under
`tests/` are test-only; the HTTP research-data routes do not import frontend or
Python mock datasets.

Ask keeps deterministic retrieval and ranking authoritative, then makes at
most one optional Gemini synthesis request through the existing generation
port. Configure `GEMINI_API_KEY` on the backend and optionally set
`GEMINI_MODEL` (default `gemini-3.8-flash`). The process starts without a key;
Ask then returns its existing ranked-paper fallback with a non-sensitive
`generation_status`. The current application does not ingest validated internal
excerpts, so when ranked papers are available the Gemini adapter uses at most
three validated paper URLs with URL Context and Google Search grounding. It
returns a generated answer only when provider citation annotations map to
sources. External sources are provenance-tagged and never enter the ranking or
receive paper factors. A successful Ask still returns the unchanged ranked
papers alongside the answer.

## Application profile integration

`application.search_papers` accepts a `RetrievalRankingPipeline` and
`QueryPlan`, then serializes the pipeline's ranked publication results. It
does not recreate a retrieval engine or apply another fusion/ranking pass.

Academic profile pages use `AcademicProfileSnapshot`, an immutable bounded
projection composed from ranking's `EntityRecord`, `GraphEdge`, and validated
`EvidenceItem` values. The profile service renders authored publications,
affiliation, and source-linked summaries only from that snapshot; without
validated evidence it returns `insufficient_information` rather than
fabricating a summary. Snapshots may also carry bounded `searchable_text` so
the application can retain user-facing name and keyword profile search without
reintroducing a second repository or retrieval pipeline.

The HTTP profile endpoint hydrates its requested academic by ID through the same
bounded repository and seed-driven graph adapter. It does not scan the academic
table to locate one profile. Profile summaries still fail closed when validated
evidence is unavailable. Ask can use the optional Gemini grounding path described
above, but missing provider configuration, provider errors, or absent grounded
citations preserve the ranked-paper fallback.

## Supabase smoke test

Keep `SUPABASE_URL` and `SUPABASE_KEY` in the ignored project-root `.env` file,
then run:

```bash
PYTHONPATH=src python3 -m ranking.supabase_live_check "assistive robotics"
```

The command first performs `limit(1)` read checks against all eight fixed-schema
tables. It stops at the first denied or failed table. On success it runs real
lexical retrieval, one fusion, seed-driven bounded graph expansion, and pure
deterministic ranking, then prints structured JSON. It never writes database
data and does not invoke an LLM.

Lexical scoring currently operates over a configurable bounded metadata scan
because the fixed contract supplies neither a database-owned full-text-search
RPC nor an index contract. Graph neighbors are fetched by ID in batches and are
bounded by hop and fan-out budgets.

## Future database capabilities (not implemented)

- Offline paper embeddings require database-owned durable vector storage plus
  model, dimension, version, and source-content provenance.
- Offline researcher embeddings require equivalent versioned storage derived
  from a defined researcher profile/publication snapshot.
- Production dense retrieval requires a database-owned vector capability,
  suitable index, and stable read RPC/query with filter and distance semantics.
- Precomputed ranking features require reproducible definitions, normalization,
  provenance, and versioning. The current `score` fields do not provide enough
  provenance, so the production adapter does not use them.

## Run tests

```powershell
python -m unittest discover -s tests -v
```
