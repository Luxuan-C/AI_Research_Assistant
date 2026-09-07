"""
Vecton AI Research Assistant ranking stage.

Pipeline:
    mock GraphRAG output
      -> hybrid retrieval score H (RRF)
         1.BM25(keyword matching)
         2.dense vector search (semantic understanding)
         3.Merge results via RRF (Reciprocal Rank Fusion)
         
      -> combined relevance R
      -> eligibility gates
      -> Quality Q / citation influence I/ temporal validity T/ innovation interaction N/ Author Authority A
      -> final score S=(w_R)​R+(w_Q)​Q+(w_I)​I+(w_T)​T+(w_N)​Q*N+(w_A)​A
      -> evidence-backed explanation

GraphRAG RetrievalResponse objects can be converted with
``candidates_from_retrieval_response`` and ranked with
``rank_retrieval_response``.
"""

from dataclasses import dataclass, asdict
from datetime import date
from math import exp
from typing import List, Optional, Dict, Any, TYPE_CHECKING
import json

if TYPE_CHECKING:
    from academic_graphrag.interfaces import AcademicGraphRepository
    from academic_graphrag.models import RetrievalQuery, RetrievalResponse
    from academic_graphrag.pipeline import GraphRAGEngine

TODAY = date(2026, 9, 4)
RRF_K = 60
TAU_H = 0.20
TAU_E = 0.70
TAU_S = 0.45
QUALITY_KAPPA = 5.0

PROFILES = {
    "GENERAL":       {"wH": .55, "wQ": .16, "wI": .12, "wT": .08, "wN": .06, "wA": .03, "half_life": 8,  "beta": .25},
    "RECENT":        {"wH": .50, "wQ": .14, "wI": .07, "wT": .23, "wN": .03, "wA": .03, "half_life": 2,  "beta": 0},
    "FOUNDATIONAL":  {"wH": .42, "wQ": .14, "wI": .32, "wT": .03, "wN": .04, "wA": .05, "half_life": 25, "beta": .50},
    "EMERGING":      {"wH": .46, "wQ": .14, "wI": .06, "wT": .10, "wN": .21, "wA": .03, "half_life": 4,  "beta": .15},
    "RELATIONSHIP":  {"wH": .63, "wQ": .12, "wI": .08, "wT": .06, "wN": .08, "wA": .03, "half_life": 10, "beta": .25},
}

@dataclass
class Evidence:
    evidence_id: str
    source_type: str
    confidence: float
    supports: str

@dataclass
class CandidatePaper:
    paper_id: str
    title: str
    bm25_rank: Optional[int]
    dense_rank: Optional[int]
    evidence: List[Evidence]
    publication_date: str
    publication_type: str
    status: str
    venue_prior: float
    venue_count: int
    document_prior: float
    quality_confidence: float
    citation_influence: float
    innovation: float
    author_authority: float


def candidates_from_retrieval_response(response: "RetrievalResponse") -> List[CandidatePaper]:
    """Convert GraphRAG publication results into ranking candidates.

    Researcher results are intentionally ignored because this stage ranks
    papers. Missing metadata uses conservative defaults so the adapter remains
    compatible with partial provider records.
    """
    candidates = []
    for result in response.results:
        # This stage currently ranks publications; researcher results are
        # reserved for a future researcher-ranking stage.
        if result.entity.entity_type != "Publication":
            continue

        metadata = result.entity.metadata
        evidence = [
            Evidence(
                evidence_id=item.evidence.id,
                source_type=item.source.provider,
                confidence=item.evidence.confidence,
                supports=item.evidence.excerpt,
            )
            for item in result.evidence
        ]
        year = metadata.get("year", metadata.get("latest_publication_year"))
        if year is None:
            raise ValueError(f"Publication {result.entity.id} is missing year metadata")

        candidates.append(
            CandidatePaper(
                paper_id=result.entity.id,
                title=result.entity.label,
                bm25_rank=result.rank,
                dense_rank=result.rank,
                evidence=evidence,
                publication_date=f"{int(year):04d}-01-01",
                publication_type=str(metadata.get("publication_type", "journal-article")),
                status=str(metadata.get("status", "valid")),
                venue_prior=_number01(metadata.get("venue_quality"), 0.5),
                venue_count=_nonnegative_int(metadata.get("venue_count"), 0),
                document_prior=_number01(metadata.get("document_prior"), 0.5),
                quality_confidence=_number01(metadata.get("quality_confidence"), 0.5),
                citation_influence=_number01(
                    result.score.components.get("citation_influence"), 0.0
                ),
                innovation=_number01(metadata.get("innovation"), 0.0),
                author_authority=_number01(metadata.get("author_authority"), 0.0),
            )
        )
    return candidates


def rank_retrieval_response(response: "RetrievalResponse") -> List[Dict[str, Any]]:
    """Rank the publication candidates contained in a GraphRAG response."""
    # The ranking profile is selected by the upstream RetrievalQuery.
    selected_profile = _profile_from_response(response)
    return rank_candidates(candidates_from_retrieval_response(response), selected_profile)


def retrieve_and_rank(
    engine: "GraphRAGEngine", query: "RetrievalQuery"
) -> List[Dict[str, Any]]:
    """Call GraphRAG and rank papers returned in its RetrievalResponse.

    The caller owns the engine and query. This function only connects the RAG
    retrieval result to the paper-ranking output. The candidates are taken from
    ``response.results``; the local ``MOCK`` data is not used.
    """
    response = engine.retrieve(query)
    print_ranking(response)
    return rank_retrieval_response(response)


def _profile_from_response(response: "RetrievalResponse") -> str:
    profile = response.query.ranking_profile
    if profile not in PROFILES:
        raise ValueError(f"Unknown profile: {profile}")
    return profile


def _number01(value: object, default: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    return max(0.0, min(1.0, float(value)))


def _nonnegative_int(value: object, default: int) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    return max(0, int(value))

def validate01(x: float, name: str):
    if not 0 <= x <= 1:
        raise ValueError(f"{name} must be in [0,1], got {x}")

def validate(p: CandidatePaper):
    for name in ["venue_prior", "document_prior", "quality_confidence",
                 "citation_influence", "innovation", "author_authority"]:
        validate01(getattr(p, name), name)
    for e in p.evidence:
        validate01(e.confidence, f"evidence {e.evidence_id} confidence")
    if p.bm25_rank is not None and p.bm25_rank < 1:
        raise ValueError("bm25_rank must be >= 1 or None")
    if p.dense_rank is not None and p.dense_rank < 1:
        raise ValueError("dense_rank must be >= 1 or None")
    date.fromisoformat(p.publication_date)

def rrf(rank: Optional[int]) -> float:
    return 0.0 if rank is None else (RRF_K + 1) / (RRF_K + rank)

def hybrid_relevance(p: CandidatePaper, bm25_weight=.5, dense_weight=.5) -> float:
    return bm25_weight * rrf(p.bm25_rank) + dense_weight * rrf(p.dense_rank)

def evidence_confidence(p: CandidatePaper) -> float:
    # Use the strongest supporting evidence; do not reward duplicate evidence.
    return max((e.confidence for e in p.evidence), default=0.0)

def quality(p: CandidatePaper) -> float:
    # Conservative venue smoothing:
    # V' = (nV*V + kappa*0.5)/(nV+kappa)
    v_prime = (p.venue_count * p.venue_prior + QUALITY_KAPPA * .5) / (p.venue_count + QUALITY_KAPPA)
    return p.quality_confidence * (.6 * v_prime + .4 * p.document_prior) + (1-p.quality_confidence) * .5

def temporal(p: CandidatePaper, profile: str, q: float) -> float:
    cfg = PROFILES[profile]
    age = max(0, (TODAY - date.fromisoformat(p.publication_date)).days / 365.25)
    h_eff = cfg["half_life"] * (1 + cfg["beta"] * q * p.innovation)
    return 2 ** (-age / h_eff)

def eligible(p: CandidatePaper, h: float, e: float):
    reasons = []
    if p.status.lower() != "valid":
        reasons.append(f"status={p.status}")
    if h < TAU_H:
        reasons.append(f"H={h:.3f} < {TAU_H:.2f}")
    if e < TAU_E:
        reasons.append(f"E={e:.3f} < {TAU_E:.2f}")
    return len(reasons) == 0, reasons

def rank_candidates(candidates: List[CandidatePaper], profile="GENERAL") -> List[Dict[str, Any]]:
    if profile not in PROFILES:
        raise ValueError(f"Unknown profile: {profile}")
    cfg = PROFILES[profile]
    results = []

    for p in candidates:
        validate(p)
        H = hybrid_relevance(p)
        E = evidence_confidence(p)
        ok, reasons = eligible(p, H, E)

        Q = quality(p)
        I = p.citation_influence
        T = temporal(p, profile, Q)
        N = p.innovation
        A = p.author_authority
        QN = Q * N

        contributions = {
            "H": cfg["wH"] * H,
            "Q": cfg["wQ"] * Q,
            "I": cfg["wI"] * I,
            "T": cfg["wT"] * T,
            "QN": cfg["wN"] * QN,
            "A": cfg["wA"] * A,
        }

        S = sum(contributions.values()) if ok else 0.0

        if ok and S < TAU_S:
            ok = False
            reasons.append(f"S={S:.3f} < {TAU_S:.2f}")
            S = 0.0
            contributions = {k: 0.0 for k in contributions}

        result = {
            "paper_id": p.paper_id,
            "title": p.title,
            "eligible": ok,
            "final_score": round(S, 6),
            "score_breakdown": {
                "H_hybrid_relevance": round(H, 6),
                "Q_quality": round(Q, 6),
                "I_citation_influence": round(I, 6),
                "T_temporal_validity": round(T, 6),
                "N_innovation": round(N, 6),
                "QN_quality_x_innovation": round(QN, 6),
                "A_author_authority": round(A, 6),
            },
            "weighted_contributions": {k: round(v, 6) for k, v in contributions.items()},
            "evidence": {
                "confidence": round(E, 6),
                "ids": [e.evidence_id for e in p.evidence],
            },
            "eligibility_reasons": reasons,
        }

        if ok:
            strongest = max(contributions, key=contributions.get)
            result["explanation"] = (
                f"Strongest weighted factor: {strongest}={contributions[strongest]:.3f}. "
                f"H={H:.3f}, Q={Q:.3f}, I={I:.3f}, T={T:.3f}, "
                f"N={N:.3f}, A={A:.3f}. Final S={S:.3f}. "
                f"Evidence IDs: {', '.join(result['evidence']['ids']) or 'none'}."
            )
        else:
            result["explanation"] = (
                "Rejected by deterministic gates: " +
                "; ".join(reasons) +
                f". Evidence IDs: {', '.join(result['evidence']['ids']) or 'none'}."
            )

        results.append(result)

    # Stable deterministic ordering.
    results.sort(key=lambda x: (not x["eligible"], -x["final_score"], x["paper_id"]))
    for i, r in enumerate(results, 1):
        r["rank"] = i
    return results



def print_ranking(response: "RetrievalResponse") -> None:
    """Print readable paper-ranking output for an existing RAG response."""
    results = rank_retrieval_response(response)
    query = response.query.text

    print("=" * 78)
    print("Academic GraphRAG -> Paper Ranking")
    print("=" * 78)
    print(f"Query: {query}")
    print(f"Papers returned: {len(results)}")
    print()

    for result in results:
        breakdown = result["score_breakdown"]
        status = "ELIGIBLE" if result["eligible"] else "REJECTED"
        evidence_ids = result["evidence"]["ids"]

        print("-" * 78)
        print(f"Rank {result['rank']}: {result['title']}")
        print(f"Paper ID: {result['paper_id']}")
        print(f"Status: {status}")
        print(f"Final score: {result['final_score']:.4f}")
        print("Score breakdown:")
        print(f"  Hybrid relevance (H): {breakdown['H_hybrid_relevance']:.3f}")
        print(f"  Quality (Q):          {breakdown['Q_quality']:.3f}")
        print(f"  Citation influence (I): {breakdown['I_citation_influence']:.3f}")
        print(f"  Temporal validity (T):  {breakdown['T_temporal_validity']:.3f}")
        print(f"  Innovation (N):       {breakdown['N_innovation']:.3f}")
        print(f"  Author authority (A): {breakdown['A_author_authority']:.3f}")
        print(f"Evidence confidence: {result['evidence']['confidence']:.3f}")
        print(f"Evidence IDs: {', '.join(evidence_ids) or 'none'}")
        if result["eligibility_reasons"]:
            print("Eligibility reasons: " + "; ".join(result["eligibility_reasons"]))
        print(f"Explanation: {result['explanation']}")

    print("-" * 78)


def main(response: "RetrievalResponse") -> None:
    """Print ranking output for a RetrievalResponse supplied by RAG."""
    print_ranking(response)


if __name__ == "__main__":
    main()