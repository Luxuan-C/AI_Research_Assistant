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

## Supabase smoke test

Keep `SUPABASE_URL` and `SUPABASE_KEY` in the ignored project-root `.env` file,
then run:

```bash
PYTHONPATH=src python3 -m ranking.supabase_live_check "assistive robotics"
```

The command first performs `limit(1)` read checks against all nine fixed-schema
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
