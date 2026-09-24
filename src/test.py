# 1) adapter 是否可用
from ranking.gemini_generation import GeminiGenerationAdapter
g = GeminiGenerationAdapter.from_environment()
print("available:", g.available, "model:", g.model, "key_set:", bool(g.api_key))
# 期望 available=True；若 False，检查 GEMINI_API_KEY 和 google-genai 安装

# 2) 直接调 synthesize，绕过 orchestrator
from ranking.paper_ranking import EvidencePack
pack = EvidencePack(items=(), ranked_papers=(
    {"paper_id": "p1", "entity_id": "research_paper:p1", "title": "Test paper",
     "year": 2024, "doi": "10.1234/test", "rank": 1, "final_score": 1.0,
     "factor_scores": {}, "factor_availability": {}, "source_urls": ("https://example.com/a",)},
))
out = g.synthesize("What is this paper about?", pack)
print("status:", out.status, "answer:", out.answer[:200], "citations:", len(out.citations))
# 期望 status=generated；若 insufficient_evidence，看第 3 步