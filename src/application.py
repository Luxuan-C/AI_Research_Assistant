"""Application-level adapters over the public ranking and profile contracts."""

from __future__ import annotations

from typing import Any, Sequence

from academic_profiles import AcademicProfile, AcademicProfileService, AcademicProfileSnapshot
from ranking import PUBLICATION, RESEARCHER, QueryPlan, RetrievalRankingPipeline


def search_papers(
    pipeline: RetrievalRankingPipeline,
    plan: QueryPlan,
) -> list[dict[str, Any]]:
    """Retrieve and deterministically rank publication results once."""

    result = pipeline.retrieve_and_rank(plan)
    return [
        {
            "rank": ranked.rank,
            "paper_id": ranked.entity.entity_id,
            "title": ranked.entity.label,
            "eligible": ranked.eligible,
            "score": ranked.final_score,
            "score_breakdown": dict(ranked.score_breakdown),
            "evidence_ids": ranked.evidence_ids,
            "source_urls": ranked.entity.source_urls,
        }
        for ranked in result.ranked
        if ranked.entity.kind == PUBLICATION
    ]


def search_academic_profiles_with_ranking(
    pipeline: RetrievalRankingPipeline,
    plan: QueryPlan,
    snapshots: Sequence[AcademicProfileSnapshot],
) -> list[AcademicProfile]:
    """Render profiles for researchers returned by the ranking pipeline.

    Snapshots are caller-provided, bounded projections. This keeps profile
    rendering independent of storage while preserving ranked researcher order.
    """

    snapshots_by_id = {snapshot.academic.entity_id: snapshot for snapshot in snapshots}
    profile_service = AcademicProfileService()
    profiles: list[AcademicProfile] = []
    seen_ids: set[str] = set()
    for ranked in pipeline.retrieve_and_rank(plan).ranked:
        academic_id = ranked.entity.entity_id
        if ranked.entity.kind != RESEARCHER or academic_id in seen_ids:
            continue
        snapshot = snapshots_by_id.get(academic_id)
        if snapshot is None:
            continue
        profiles.append(profile_service.get_profile(snapshot))
        seen_ids.add(academic_id)
    return profiles


def search_academic_profiles(
    snapshots: Sequence[AcademicProfileSnapshot],
    search_text: str,
) -> list[AcademicProfile]:
    """Find researcher profiles by user-facing name from bounded snapshots."""

    normalized_query = search_text.strip().casefold()
    if not normalized_query:
        return []

    profiles = AcademicProfileService()
    return [
        profiles.get_profile(snapshot)
        for snapshot in sorted(snapshots, key=lambda item: item.academic.entity_id)
        if any(
            normalized_query in value.casefold()
            for value in (snapshot.academic.label, *snapshot.searchable_text)
        )
    ]
