# Offline Q/I/A factors

`ranking.offline_factors` calculates the offline paper quality (Q), citation
influence (I), and author authority (A) factors from the checked-in paper and
academic snapshot. It does not connect to or write to Supabase. Q and I retain
their existing calculation.

## Author authority

Academic authority is the mean of the academic's top five available paper I
values. An observed paper A is the mean of the available leave-one-out
authorities: the paper being scored is excluded from each author's history.
Observed A values keep that calculation unchanged.

If no author has an available leave-one-out authority, the calculator excludes
the target paper, recalculates I over the remaining snapshot, calculates each
academic's observed authority from that remaining I history, and uses the
median of available academic authorities as the paper's imputation prior. This
per-paper leave-one-out prior also prevents the target paper's citations from
changing peer I through citation-cohort normalization. If no observed academic
authority remains, A stays unavailable. Every emitted A is in `[0,1]`.

Each offline `PaperFactors` value carries `author_authority_status` with one of
`observed`, `imputed`, or `unavailable`; imputed values also carry the prior
used for that paper. The import-ready `score_qia_backfill.json` row shape stays
unchanged. Pass `--metadata-output` to write the ID-keyed status and prior
sidecar separately.

## Runtime provenance limitation

The current `public.score` projection stores `author_authority_score` but has
no provenance column. The API can distinguish a numeric value from SQL NULL,
but it cannot tell whether a persisted numeric A was observed or imputed. The
runtime must not infer provenance from the score value. Persisting provenance
requires a database-owned nullable status field (for example,
`author_authority_status` constrained to `observed`, `imputed`, or
`unavailable`, nullable for legacy rows) or a companion table keyed by
`research_paper_id`, followed by an application projection/API update. The
offline sidecar is for review and does not itself update runtime provenance.

## Live update boundary

The next live update requires the database owner to approve and deploy the
status column or companion table, then the application read projection/API can
expose that status. After reviewing the generated score and metadata artifacts,
an authorized backfill can upsert by the existing unique `research_paper_id`
key: write Q/I/A to the three score columns and write status from the sidecar if
the database-owned status field has been approved. This tool never performs
that update. A remains display-only; it is not part of final ranking weights.
