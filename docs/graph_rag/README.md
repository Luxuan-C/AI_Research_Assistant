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
is only appropriate when the evidence pack is sufficient and validated.

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
- Live academic retrieval, fusion, and ranking have been verified.
- Supabase pagination beyond 1,000 rows works.
- `research_paper` currently has no live rows.
- Academic relationship arrays are currently unpopulated, so live graph
  traversal is waiting on data.

## Data-team dependencies

To enable useful live graph traversal, the data team needs to populate the
academic relationship arrays: `university_ids`, `discipline_ids`, `field_ids`,
and `research_paper_ids`. Research-paper ingestion is also required before
paper retrieval, citation paths, and paper-based evidence can operate live.

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
