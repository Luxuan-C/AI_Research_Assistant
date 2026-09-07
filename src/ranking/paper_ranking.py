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

The mock GraphRAG result is represented by CandidatePaper objects.
In the real system, replace MOCK_CANDIDATES with the JSON returned by
the GraphRAG/retrieval teammate.
"""

from dataclasses import dataclass, asdict
from datetime import date
from math import exp
from typing import List, Optional, Dict, Any
import json

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



MOCK = [
    CandidatePaper(
        "P001", "Deep Learning for Medical Image Analysis", 1, 2,
        [Evidence("EV001", "OpenAlex", .98, "metadata"),
         Evidence("EV002", "abstract", .95, "medical imaging relevance")],
        "2024-05-20", "journal-article", "valid",
        .78, 120, .92, .93, .72, .58, .70
    ),
    CandidatePaper(
        "P002", "A Survey of Artificial Intelligence in Healthcare", 3, 4,
        [Evidence("EV003", "Crossref", .97, "bibliographic metadata"),
         Evidence("EV004", "abstract", .91, "AI and healthcare scope")],
        "2019-08-10", "review-article", "valid",
        .85, 300, .95, .96, .96, .15, .82
    ),
    CandidatePaper(
        "P003", "Graph Neural Networks for Drug Discovery", 8, 3,
        [Evidence("EV005", "abstract", .88, "AI and healthcare context")],
        "2025-02-15", "journal-article", "valid",
        .70, 40, .90, .85, .42, .80, .55
    ),
    CandidatePaper(
        "P004", "A Highly Cited Paper About Classical Cryptography", 55, 60,
        [Evidence("EV006", "Crossref", .80, "paper metadata")],
        "2010-03-12", "journal-article", "valid",
        .92, 500, .95, .95, .99, .05, .99
    ),
    CandidatePaper(
        "P005", "AI Methods for Health Data", 5, 5,
        [Evidence("EV007", "weak_unverified_source", .55, "weak support")],
        "2025-10-01", "preprint", "valid",
        .50, 2, .65, .40, .10, .60, .30
    ),
    CandidatePaper(
        "P006", "Medical Imaging Methods - Retracted Study", 2, 2,
        [Evidence("EV008", "Crossref", .99, "retraction/publication record")],
        "2023-06-01", "journal-article", "retracted",
        .80, 100, .90, .90, .80, .40, .70
    ),
]

if __name__ == "__main__":
    for profile in ["GENERAL", "RECENT", "FOUNDATIONAL", "EMERGING"]:
        print("\n" + "="*90)
        print(profile)
        print("="*90)
        results = rank_candidates(MOCK, profile)
        for r in results:
            print(f"#{r['rank']} {r['paper_id']} | {r['title']}")
            print(f"  eligible={r['eligible']}  score={r['final_score']:.4f}")
            print("  " + " | ".join(
                f"{k.split('_')[0]}={v:.3f}" for k, v in r["score_breakdown"].items()
            ))
            print(f"  evidence={r['evidence']}")
            if r["eligibility_reasons"]:
                print("  gate:", "; ".join(r["eligibility_reasons"]))
            print("  why:", r["explanation"])

    print("\nExample JSON:")
    print(json.dumps(rank_candidates(MOCK, "GENERAL")[0], indent=2))
