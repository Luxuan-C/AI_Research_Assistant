# RAG and GraphRAG

## Purpose

This subsystem turns research questions into a small, traceable set of relevant
researchers, papers, and supporting evidence. It combines search with a
read-only view of academic relationships so that the application can return
ranked results and, where validated evidence is available, support generation.

## Pipeline

```text
Query → Retrieval → Fusion → Graph Expansion → Ranking → Evidence Pack → Generation
```

The graph stage enriches retrieved seeds; it does not replace search. Generation
is downstream of ranking and requires validated internal evidence or citations
returned by an enabled external grounding tool.

## Retrieval and graph coverage

- Lexical retrieval is active for academic and research-paper metadata.
- Dense/vector retrieval is not currently available. It must not be assumed
  until the database team supplies a production vector capability.
- The graph uses the existing UUID array fields directly—no junction tables are
  required. Conceptual relationships include authorship and co-authorship,
  paper citations, academic affiliation with universities, discipline and field
  expertise, and paper links to universities, faculties, and journals.
- Publisher relationships and publisher support have been removed from the RAG
  scope.

## Database boundary

RAG is a read-only consumer of the externally owned Supabase database. It does
not modify the database, schema, SQL, or data model. UUID arrays are the source
of graph relationships and are projected at read time; the RAG team must not
add junction tables or normalise these fields.

## Ranking

Researcher ranking and paper/evidence ranking are separate responsibilities.
Both are deterministic and reproducible, so the same inputs produce the same
ordered results. Publisher authority or prestige is not a ranking signal.

## Live integration status

- 3,158 academic records are readable from Supabase.
- The HTTP researcher, profile, and ask routes now use the shared live Supabase
  retrieval, fusion, bounded graph expansion, and deterministic ranking stack.
- Supabase pagination beyond 1,000 rows works.
- The current live snapshot contains 16 `research_paper` rows representing eight
  duplicate DOI/title pairs. Duplicate live rows remain a database-data concern;
  the RAG adapter does not rewrite them.
- Academic and research-paper relationship arrays are currently unpopulated, so
  live graph traversal produces no relationship enrichment even though the HTTP
  graph stage executes.
- The live schema does not expose `academic.research_interests` or
  `academic.areas_of_expertise`; the API does not fabricate those fields.
- Ask uses the existing `GenerationPort` through a Gemini adapter. It makes at
  most one Interactions API request after deterministic ranking. When validated
  internal excerpts are absent, it can supply up to three validated ranked-paper
  URLs to URL Context and enable Google Search grounding in that same request.
  It accepts a generated answer only when response annotations map to sources;
  otherwise it retains the ranked-paper fallback.
- The live application currently has no validated internal excerpt ingestion.
  Gemini therefore treats paper titles and factor/rank metadata as discovery
  context only. URL Context and Google Search sources are labeled external and
  do not receive H/Q/I/T/A values or affect paper ranking.
- `GEMINI_API_KEY` is optional at startup; `GEMINI_MODEL` can override the
  default `gemini-3.8-flash`. Missing configuration, provider failures, and
  missing grounded citations preserve the existing `insufficient_information`
  fallback and expose a non-sensitive `generation_status`. Researcher profile
  summaries continue to fail closed without validated evidence.

The API constructs its shared client and services without table reads at
startup. Table projections are loaded lazily, bounded to 4,000 rows per table,
and cached in-process for 60 seconds. The bounded tokenized-corpus LRU is keyed
to repository revisions and rebuilt after TTL expiry or explicit invalidation.

## Data-team dependencies

To enable useful live graph traversal, the data team needs to populate the
existing relationship arrays, including academic `university_ids`,
`discipline_ids`, `field_ids`, and `research_paper_ids`, and the corresponding
research-paper relationships. Validated evidence ingestion remains necessary
before evidence-backed answer synthesis can operate live.

## Team ownership

- **Frontend:** present search, ranked results, relationship context, evidence,
  and clear empty/insufficient-information states. Do not infer relationships
  or ranking in the client.
- **Ranking:** own retrieval orchestration, one fusion step, graph expansion,
  deterministic ranking, and evidence-pack selection. Do not write to the
  database or assign publisher prestige.
- **Database:** own the schema, data ingestion, row visibility, and population
  of relationship arrays. Changes to those assets remain database-team work.

## Checks

From the repository root, run the automated suite:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

With read-only Supabase credentials in `.env`, run the live check:

```bash
PYTHONPATH=src python3 -m ranking.supabase_live_check "George Siemens" --row-limit 4000
```
