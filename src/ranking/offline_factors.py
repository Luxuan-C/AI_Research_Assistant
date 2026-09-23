"""Deterministic, read-only offline H/Q/I/T/A factor calculations.

This module calculates the corpus-derived I, Q, and A factors from a fixed
snapshot. It does not access Supabase or write any data. H and T remain owned
by the request-time retrieval and ranking implementation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from math import isfinite, log1p
from statistics import mean, median
from typing import Any, Mapping, Sequence


MIN_PEER_COHORT_SIZE = 5
TOP_AUTHOR_PAPERS = 5
I_COHORT_TIERS = ("field_year_type", "year_type", "year", "global")
Q_COHORT_TIERS = ("year", "year_plus_minus_one", "global")


@dataclass(frozen=True, slots=True)
class PaperFactors:
    paper_id: str
    citation_influence: float | None
    quality: float | None
    author_authority: float | None
    author_authority_status: str
    author_authority_imputation_prior: float | None
    citation_cohort: str | None
    quality_cohort: str | None


@dataclass(frozen=True, slots=True)
class OfflineFactorSnapshot:
    papers: Mapping[str, PaperFactors]
    academic_authority: Mapping[str, float | None]
    input_paper_rows: int
    duplicate_paper_rows: int
    missing_paper_id_rows: int
    papers_with_citation_data: int
    papers_with_year: int
    papers_with_type: int
    papers_with_author_links: int
    paper_author_relationships: int
    academics_used: int
    i_cohort_counts: Mapping[str, int]
    q_cohort_counts: Mapping[str, int]


@dataclass(frozen=True, slots=True)
class _Paper:
    paper_id: str
    year: int | None
    publication_type: str | None
    citations: float | None
    field_id: str | None
    author_ids: tuple[str, ...]

    def signature(self) -> tuple[object, ...]:
        return (
            self.year,
            self.publication_type,
            self.citations,
            self.field_id,
            self.author_ids,
        )


def calculate_offline_factors(
    papers: Sequence[Mapping[str, Any]],
    academic_paper_ids: Mapping[str, Sequence[object]] | None = None,
) -> OfflineFactorSnapshot:
    """Calculate I, Q, and A for a paper snapshot without external I/O.

    Paper authorship is the union of ``research_paper.academic_ids`` and the
    optional academic-to-paper mapping. Exact duplicate paper records collapse
    to one paper; conflicting records with the same ID fail closed.
    """

    by_id: dict[str, _Paper] = {}
    duplicate_rows = 0
    missing_id_rows = 0
    for row in papers:
        paper_id = _identifier(row.get("id"))
        if paper_id is None:
            missing_id_rows += 1
            continue
        paper = _paper_from_row(paper_id, row)
        previous = by_id.get(paper_id)
        if previous is not None:
            if previous.signature() != paper.signature():
                raise ValueError(f"Conflicting factor inputs for duplicate paper ID {paper_id!r}")
            duplicate_rows += 1
            continue
        by_id[paper_id] = paper

    papers_by_id = dict(sorted(by_id.items()))
    paper_ids = set(papers_by_id)

    authors_by_paper: dict[str, set[str]] = {
        paper_id: set(paper.author_ids) for paper_id, paper in papers_by_id.items()
    }
    academic_ids_in_snapshot: set[str] = set()
    for academic_id, linked_papers in (academic_paper_ids or {}).items():
        normalized_academic_id = _identifier(academic_id)
        if normalized_academic_id is None:
            continue
        academic_ids_in_snapshot.add(normalized_academic_id)
        for linked_paper_id in _identifiers(linked_papers):
            normalized_paper_id = _identifier(linked_paper_id)
            if normalized_paper_id in paper_ids:
                authors_by_paper[normalized_paper_id].add(normalized_academic_id)

    papers_by_id = {
        paper_id: _Paper(
            paper_id=paper.paper_id,
            year=paper.year,
            publication_type=paper.publication_type,
            citations=paper.citations,
            field_id=paper.field_id,
            author_ids=tuple(sorted(authors_by_paper[paper_id])),
        )
        for paper_id, paper in papers_by_id.items()
    }

    i_values, i_cohort_by_paper, i_cohort_counts = _citation_influence_values(
        papers_by_id
    )

    i_by_year: dict[int, list[tuple[str, float]]] = {}
    available_i = [(paper_id, score) for paper_id, score in i_values.items() if score is not None]
    for paper_id, score in available_i:
        year = papers_by_id[paper_id].year
        if year is not None:
            i_by_year.setdefault(year, []).append((paper_id, score))
    global_i = [score for _paper_id, score in available_i]

    q_values: dict[str, float | None] = {}
    q_cohort_by_paper: dict[str, str | None] = {}
    q_cohort_counts = {tier: 0 for tier in Q_COHORT_TIERS}
    for paper_id, paper in papers_by_id.items():
        value = i_values[paper_id]
        if value is None:
            q_values[paper_id] = None
            q_cohort_by_paper[paper_id] = None
            continue
        exact = i_by_year.get(paper.year, ()) if paper.year is not None else ()
        adjacent = (
            [entry for year in (paper.year - 1, paper.year, paper.year + 1) for entry in i_by_year.get(year, ())]
            if paper.year is not None
            else []
        )
        if len(exact) >= MIN_PEER_COHORT_SIZE:
            cohort = [score for _peer_id, score in exact]
            tier = "year"
        elif len(adjacent) >= MIN_PEER_COHORT_SIZE:
            cohort = [score for _peer_id, score in adjacent]
            tier = "year_plus_minus_one"
        else:
            cohort = global_i
            tier = "global"
        q_values[paper_id] = _percentile_rank(value, cohort)
        q_cohort_by_paper[paper_id] = tier
        q_cohort_counts[tier] += 1

    paper_ids_by_academic: dict[str, set[str]] = {}
    for paper_id, authors in authors_by_paper.items():
        for academic_id in authors:
            paper_ids_by_academic.setdefault(academic_id, set()).add(paper_id)
    for academic_id in academic_ids_in_snapshot:
        paper_ids_by_academic.setdefault(academic_id, set())

    academic_authority = _academic_authority_values(paper_ids_by_academic, i_values)

    paper_authority: dict[str, float | None] = {}
    paper_authority_status: dict[str, str] = {}
    paper_authority_prior: dict[str, float | None] = {}
    for paper_id, paper in papers_by_id.items():
        author_values: list[float] = []
        for academic_id in paper.author_ids:
            prior_i = sorted(
                (
                    i_values[other_id]
                    for other_id in paper_ids_by_academic.get(academic_id, ())
                    if other_id != paper_id and i_values[other_id] is not None
                ),
                reverse=True,
            )[:TOP_AUTHOR_PAPERS]
            if prior_i:
                author_values.append(mean(prior_i))
        if author_values:
            paper_authority[paper_id] = mean(author_values)
            paper_authority_status[paper_id] = "observed"
            paper_authority_prior[paper_id] = None
            continue

        # Build this paper's neutral prior from a snapshot that excludes the
        # paper completely. Recomputing I after removal also avoids letting the
        # paper's citations affect other papers through cohort normalization.
        prior_papers = {
            other_id: other_paper
            for other_id, other_paper in papers_by_id.items()
            if other_id != paper_id
        }
        prior_i_values, _prior_i_cohorts, _prior_cohort_counts = (
            _citation_influence_values(prior_papers)
        )
        prior_paper_ids_by_academic = {
            academic_id: linked_ids - {paper_id}
            for academic_id, linked_ids in paper_ids_by_academic.items()
        }
        prior_authority = _academic_authority_values(
            prior_paper_ids_by_academic,
            prior_i_values,
        )
        observed_prior_values = [
            authority
            for authority in prior_authority.values()
            if authority is not None
        ]
        imputation_prior = (
            _unit(median(observed_prior_values)) if observed_prior_values else None
        )
        paper_authority_prior[paper_id] = imputation_prior
        paper_authority[paper_id] = imputation_prior
        paper_authority_status[paper_id] = (
            "imputed" if imputation_prior is not None else "unavailable"
        )

    factors = {
        paper_id: PaperFactors(
            paper_id=paper_id,
            citation_influence=i_values[paper_id],
            quality=q_values[paper_id],
            author_authority=paper_authority[paper_id],
            author_authority_status=paper_authority_status[paper_id],
            author_authority_imputation_prior=paper_authority_prior[paper_id],
            citation_cohort=i_cohort_by_paper[paper_id],
            quality_cohort=q_cohort_by_paper[paper_id],
        )
        for paper_id in papers_by_id
    }
    relationship_count = sum(len(values) for values in authors_by_paper.values())
    return OfflineFactorSnapshot(
        papers=factors,
        academic_authority=academic_authority,
        input_paper_rows=len(papers),
        duplicate_paper_rows=duplicate_rows,
        missing_paper_id_rows=missing_id_rows,
        papers_with_citation_data=sum(paper.citations is not None for paper in papers_by_id.values()),
        papers_with_year=sum(paper.year is not None for paper in papers_by_id.values()),
        papers_with_type=sum(paper.publication_type is not None for paper in papers_by_id.values()),
        papers_with_author_links=sum(bool(paper.author_ids) for paper in papers_by_id.values()),
        paper_author_relationships=relationship_count,
        academics_used=len(paper_ids_by_academic),
        i_cohort_counts=i_cohort_counts,
        q_cohort_counts=q_cohort_counts,
    )


def _citation_influence_values(
    papers_by_id: Mapping[str, _Paper],
) -> tuple[dict[str, float | None], dict[str, str | None], dict[str, int]]:
    """Calculate I without authorship so a paper can be excluded for A priors."""

    citation_cohorts: dict[tuple[object, ...], list[str]] = {}
    for paper_id, paper in papers_by_id.items():
        if paper.citations is None:
            continue
        if paper.field_id is not None and paper.year is not None and paper.publication_type:
            citation_cohorts.setdefault(
                ("field_year_type", paper.field_id, paper.year, paper.publication_type), []
            ).append(paper_id)
        if paper.year is not None and paper.publication_type:
            citation_cohorts.setdefault(
                ("year_type", paper.year, paper.publication_type), []
            ).append(paper_id)
        if paper.year is not None:
            citation_cohorts.setdefault(("year", paper.year), []).append(paper_id)
        citation_cohorts.setdefault(("global",), []).append(paper_id)

    i_values: dict[str, float | None] = {}
    i_cohort_by_paper: dict[str, str | None] = {}
    i_cohort_counts = {tier: 0 for tier in I_COHORT_TIERS}
    for paper_id, paper in papers_by_id.items():
        if paper.citations is None:
            i_values[paper_id] = None
            i_cohort_by_paper[paper_id] = None
            continue
        candidates: list[tuple[str, tuple[object, ...]]] = []
        if paper.field_id is not None and paper.year is not None and paper.publication_type:
            candidates.append(("field_year_type", ("field_year_type", paper.field_id, paper.year, paper.publication_type)))
        if paper.year is not None and paper.publication_type:
            candidates.append(("year_type", ("year_type", paper.year, paper.publication_type)))
        if paper.year is not None:
            candidates.append(("year", ("year", paper.year)))
        candidates.append(("global", ("global",)))
        selected_tier, selected_key = next(
            (
                (tier, key)
                for tier, key in candidates
                if len(citation_cohorts.get(key, ())) >= MIN_PEER_COHORT_SIZE
            ),
            ("global", ("global",)),
        )
        cohort_ids = citation_cohorts.get(selected_key, ())
        maximum = max(
            (papers_by_id[item].citations or 0.0 for item in cohort_ids),
            default=0.0,
        )
        score = (
            0.0
            if maximum <= 0.0
            else log1p(max(paper.citations, 0.0)) / log1p(maximum)
        )
        i_values[paper_id] = _unit(score)
        i_cohort_by_paper[paper_id] = selected_tier
        i_cohort_counts[selected_tier] += 1
    return i_values, i_cohort_by_paper, i_cohort_counts


def _academic_authority_values(
    paper_ids_by_academic: Mapping[str, set[str]],
    i_values: Mapping[str, float | None],
) -> dict[str, float | None]:
    """Calculate mean(top five available I values) for each academic."""

    authorities: dict[str, float | None] = {}
    for academic_id, linked_ids in sorted(paper_ids_by_academic.items()):
        values = sorted(
            (
                i_values[paper_id]
                for paper_id in linked_ids
                if paper_id in i_values and i_values[paper_id] is not None
            ),
            reverse=True,
        )[:TOP_AUTHOR_PAPERS]
        authorities[academic_id] = mean(values) if values else None
    return authorities


def factor_distribution(values: Sequence[float | None]) -> Mapping[str, float | None]:
    """Return deterministic linearly interpolated summary quantiles."""

    ordered = sorted(value for value in values if value is not None)
    return {
        "min": _quantile(ordered, 0.0),
        "p25": _quantile(ordered, 0.25),
        "median": _quantile(ordered, 0.50),
        "p75": _quantile(ordered, 0.75),
        "p90": _quantile(ordered, 0.90),
        "max": _quantile(ordered, 1.0),
    }


def _paper_from_row(paper_id: str, row: Mapping[str, Any]) -> _Paper:
    field_id = _single_field_id(row)
    return _Paper(
        paper_id=paper_id,
        year=_year(row.get("publication_date")),
        publication_type=_text(row.get("publication_type")),
        citations=_citation_count(row.get("incoming_citation_count")),
        field_id=field_id,
        author_ids=tuple(sorted(set(_identifiers(row.get("academic_ids"))))),
    )


def _single_field_id(row: Mapping[str, Any]) -> str | None:
    direct = _identifier(row.get("field_id"))
    if direct is not None:
        return direct
    fields = tuple(sorted(set(_identifiers(row.get("field_ids")))))
    return fields[0] if len(fields) == 1 else None


def _identifier(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _identifiers(value: object) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple, set, frozenset)):
        return ()
    return tuple(item for raw in value if (item := _identifier(raw)) is not None)


def _text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().casefold()
    return normalized or None


def _year(value: object) -> int | None:
    if isinstance(value, date):
        return value.year
    if isinstance(value, int) and not isinstance(value, bool):
        return value if 1 <= value <= 9999 else None
    if isinstance(value, str) and len(value) >= 4 and value[:4].isdigit():
        year = int(value[:4])
        return year if 1 <= year <= 9999 else None
    return None


def _citation_count(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        count = float(value)
    except (TypeError, ValueError):
        return None
    if not isfinite(count):
        return None
    return max(0.0, count)


def _percentile_rank(value: float, cohort: Sequence[float]) -> float:
    ordered = sorted(cohort)
    if not ordered:
        return 0.5
    if len(ordered) == 1:
        return 0.5
    less = sum(peer < value for peer in ordered)
    equal = sum(peer == value for peer in ordered)
    return _unit((less + 0.5 * (equal - 1)) / (len(ordered) - 1))


def _quantile(ordered: Sequence[float], probability: float) -> float | None:
    if not ordered:
        return None
    position = (len(ordered) - 1) * probability
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + fraction * (ordered[upper] - ordered[lower])


def _unit(value: float) -> float:
    return max(0.0, min(1.0, value))
