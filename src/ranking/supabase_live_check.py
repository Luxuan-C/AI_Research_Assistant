"""Read-only command-line smoke test for the real Supabase ranking path."""

from __future__ import annotations

import argparse
from datetime import date
import json
import sys

from .paper_ranking import (
    FusionService,
    QueryPlanner,
    RankingService,
    RetrievalRankingPipeline,
)
from .supabase_config import SupabaseConfigurationError, create_supabase_client
from .supabase_retrieval import (
    SupabaseReadError,
    SupabaseReadRepository,
    SupabaseRetrievalPort,
    SupabaseSchemaRelationshipGraph,
    safe_error_detail,
    smoke_test_read_access,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run read-only Supabase retrieval, graph expansion, and ranking (no LLM)."
    )
    parser.add_argument("query", help="Lexical research query")
    parser.add_argument("--limit", type=int, default=10, help="Maximum ranked results")
    parser.add_argument("--seed-limit", type=int, default=20, help="Maximum lexical seeds")
    parser.add_argument(
        "--row-limit",
        type=int,
        default=1000,
        help="Maximum rows read from each table in this bounded smoke run",
    )
    return parser


def run(query: str, *, limit: int, seed_limit: int, row_limit: int) -> dict[str, object]:
    client = create_supabase_client()
    readable_tables = smoke_test_read_access(client)
    repository = SupabaseReadRepository(client, row_limit=row_limit)
    pipeline = RetrievalRankingPipeline(
        retrieval=SupabaseRetrievalPort(repository),
        fusion=FusionService(),
        expansion=SupabaseSchemaRelationshipGraph(repository),
        ranking=RankingService(),
    )
    plan = QueryPlanner().plan(
        query,
        as_of=date.today(),
        limit=limit,
        seed_limit=seed_limit,
    )
    result = pipeline.retrieve_and_rank(plan)
    return {
        "status": "ok",
        "query": query,
        "readable_tables": list(readable_tables),
        "visible_candidate_rows": {
            "academic": len(repository.rows("academic")),
            "research_paper": len(repository.rows("research_paper")),
        },
        "retrieval_channels": ["lexical"],
        "dense_available": False,
        "fused_seed_count": len(result.fused),
        "graph_truncated": result.expansion.truncated,
        "ranked_results": [
            {
                "rank": item.rank,
                "entity_id": item.entity.entity_id,
                "kind": item.entity.kind,
                "label": item.entity.label,
                "eligible": item.eligible,
                "score": item.final_score,
                "score_breakdown": dict(item.score_breakdown),
                "graph_hops": item.graph_path.hops if item.graph_path else None,
                "source_urls": list(item.entity.source_urls),
            }
            for item in result.ranked
        ],
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        output = run(
            args.query,
            limit=args.limit,
            seed_limit=args.seed_limit,
            row_limit=args.row_limit,
        )
    except SupabaseConfigurationError as error:
        output = {"status": "configuration_error", "error": str(error)}
        print(json.dumps(output, indent=2, sort_keys=True), file=sys.stderr)
        return 2
    except SupabaseReadError as error:
        output = {
            "status": "read_error",
            "failing_table": error.table,
            "error": error.detail,
        }
        print(json.dumps(output, indent=2, sort_keys=True), file=sys.stderr)
        return 3
    except Exception as error:
        output = {"status": "client_error", "error": safe_error_detail(error)}
        print(json.dumps(output, indent=2, sort_keys=True), file=sys.stderr)
        return 4

    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
