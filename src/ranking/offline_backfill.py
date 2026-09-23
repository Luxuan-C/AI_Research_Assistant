"""Generate import-ready Q/I/A score records from checked-in data snapshots.

The command is dry-run by default: without ``--output`` it prints a summary
only. Supplying ``--output`` writes a local JSON or CSV artifact. It never
connects to or writes to Supabase.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

from .offline_factors import OfflineFactorSnapshot, calculate_offline_factors, factor_distribution


OUTPUT_FIELDS = (
    "research_paper_id",
    "paper_authority_score",
    "citation_influence_score",
    "author_authority_score",
)
AUTHOR_AUTHORITY_STATUSES = ("observed", "imputed", "unavailable")
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIRECTORY = REPOSITORY_ROOT / "src/data_collector/data/filtered"


def build_score_records(
    papers: Sequence[Mapping[str, Any]],
    academics: Sequence[Mapping[str, Any]],
) -> tuple[tuple[dict[str, Any], ...], OfflineFactorSnapshot]:
    """Return one Q/I/A import row per unique paper ID in the input snapshot."""

    academic_paper_ids = {
        str(row["id"]): row.get("research_paper_ids")
        for row in academics
        if row.get("id") is not None
    }
    snapshot = calculate_offline_factors(papers, academic_paper_ids)
    records = tuple(
        {
            "research_paper_id": paper_id,
            "paper_authority_score": factors.quality,
            "citation_influence_score": factors.citation_influence,
            "author_authority_score": factors.author_authority,
        }
        for paper_id, factors in sorted(snapshot.papers.items())
    )
    source_ids = {
        str(row["id"]).strip()
        for row in papers
        if row.get("id") is not None and str(row["id"]).strip()
    }
    output_ids = [str(row["research_paper_id"]) for row in records]
    if len(output_ids) != len(set(output_ids)):
        raise ValueError("Backfill output contains duplicate research_paper_id values")
    if not set(output_ids).issubset(source_ids):
        raise ValueError("Backfill output contains IDs absent from the paper snapshot")
    return records, snapshot


def summarize_backfill(
    records: Sequence[Mapping[str, Any]],
    snapshot: OfflineFactorSnapshot,
    source_papers: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Summarize coverage, distributions, and source-ID mapping validation."""

    count = len(records)
    availability = {
        field: sum(row.get(field) is not None for row in records)
        for field in OUTPUT_FIELDS[1:]
    }
    distributions = {
        field: factor_distribution([row.get(field) for row in records])
        for field in OUTPUT_FIELDS[1:]
    }
    author_factors = tuple(snapshot.papers.values())
    author_status_counts = {
        status: sum(factor.author_authority_status == status for factor in author_factors)
        for status in AUTHOR_AUTHORITY_STATUSES
    }
    prior_distribution = factor_distribution(
        [
            factor.author_authority_imputation_prior
            for factor in author_factors
            if factor.author_authority_status == "imputed"
        ]
    )
    source_ids = {
        str(row["id"]).strip()
        for row in source_papers
        if row.get("id") is not None and str(row["id"]).strip()
    }
    output_ids = [str(row["research_paper_id"]) for row in records]
    return {
        "output_rows": count,
        "availability_count": availability,
        "null_author_authority_rows": count - availability["author_authority_score"],
        "author_authority_status_count": author_status_counts,
        "author_authority_median_prior_used": prior_distribution["median"],
        "author_authority_imputation_prior_distribution": prior_distribution,
        "author_authority_distribution": distributions["author_authority_score"],
        "distributions_min_median_max": {
            field: {
                key: stats[key]
                for key in ("min", "median", "max")
            }
            for field, stats in distributions.items()
        },
        "duplicate_paper_rows_collapsed": snapshot.duplicate_paper_rows,
        "missing_paper_id_rows_skipped": snapshot.missing_paper_id_rows,
        "every_output_id_maps_to_source_paper": (
            len(output_ids) == len(set(output_ids)) and set(output_ids).issubset(source_ids)
        ),
        "i_cohort_counts": dict(snapshot.i_cohort_counts),
        "q_cohort_counts": dict(snapshot.q_cohort_counts),
    }


def build_provenance_report(
    snapshot: OfflineFactorSnapshot,
    summary: Mapping[str, Any],
) -> dict[str, Any]:
    """Return a sidecar that leaves the established score importer shape intact."""

    return {
        "format_version": 1,
        "factor": "author_authority_score",
        "status_values": list(AUTHOR_AUTHORITY_STATUSES),
        "imputation_method": (
            "For each paper without observed leave-one-out authority, remove that "
            "paper from the snapshot, recalculate I for the remaining papers, "
            "calculate each academic's mean of their top five available I values, "
            "then take the median of available academic authorities."
        ),
        "summary": {
            "total_papers": len(snapshot.papers),
            "status_count": summary["author_authority_status_count"],
            "median_prior_used": summary["author_authority_median_prior_used"],
            "imputation_prior_distribution": summary[
                "author_authority_imputation_prior_distribution"
            ],
            "author_authority_distribution": summary[
                "author_authority_distribution"
            ],
        },
        "papers": [
            {
                "research_paper_id": paper_id,
                "author_authority_status": factors.author_authority_status,
                "author_authority_imputation_prior": (
                    factors.author_authority_imputation_prior
                ),
            }
            for paper_id, factors in sorted(snapshot.papers.items())
        ],
    }


def _read_rows(path: Path) -> list[Mapping[str, Any]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise ValueError(f"Expected a JSON array of objects in {path}")
    return value


def _write_records(
    path: Path,
    records: Sequence[Mapping[str, Any]],
    output_format: str,
) -> None:
    if output_format == "json":
        path.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        writer.writerows(records)


def _write_provenance_report(path: Path, report: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--papers",
        type=Path,
        default=DEFAULT_DATA_DIRECTORY / "research_papers_supabase.json",
    )
    parser.add_argument(
        "--academics",
        type=Path,
        default=DEFAULT_DATA_DIRECTORY / "academics_supabase.json",
    )
    parser.add_argument("--output", type=Path, help="Write a local import-ready artifact; no DB write occurs")
    parser.add_argument(
        "--metadata-output",
        type=Path,
        help="Write a separate local A provenance report without changing score-row fields",
    )
    parser.add_argument("--format", choices=("json", "csv"), default="json")
    args = parser.parse_args(argv)

    papers = _read_rows(args.papers)
    academics = _read_rows(args.academics)
    records, snapshot = build_score_records(papers, academics)
    summary = summarize_backfill(records, snapshot, papers)
    if args.output is None and args.metadata_output is None:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        written: dict[str, str] = {}
        if args.output is not None:
            _write_records(args.output, records, args.format)
            written["output_path"] = str(args.output)
        if args.metadata_output is not None:
            report = build_provenance_report(snapshot, summary)
            _write_provenance_report(args.metadata_output, report)
            written["metadata_output_path"] = str(args.metadata_output)
        print(json.dumps({**written, **summary}, ensure_ascii=False, indent=2), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
