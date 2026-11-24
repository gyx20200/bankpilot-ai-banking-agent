"""D9: optional second-stage reranker. Never changes the source provenance.

Retrieval is still subject to D8 public-only source and similarity gates.
CrossEncoder raw scores are ranking scores, NOT probabilities/confidence.
"""
from __future__ import annotations

import math
import os
from functools import lru_cache

MODEL_NAME = "BAAI/bge-reranker-base"


class RerankUnavailable(RuntimeError):
    pass


def rerank_mode() -> str:
    mode = os.getenv("BANKPILOT_RERANK_MODE", "off").lower().strip()
    if mode not in {"off", "on"}:
        raise RerankUnavailable("BANKPILOT_RERANK_MODE 必须是 on 或 off")
    return mode


@lru_cache(maxsize=1)
def _model():
    # Late load keeps offline policy tests and basic RAG mode lightweight.
    from sentence_transformers import CrossEncoder
    return CrossEncoder(MODEL_NAME, device="cpu", max_length=512)


def rerank_hits(question: str, hits: list[dict], *, top_n: int = 3) -> list[dict]:
    if not isinstance(question, str) or not question.strip():
        raise ValueError("invalid question")
    if not 1 <= top_n <= 5:
        raise ValueError("top_n must be 1..5")
    if not hits:
        return []
    if any(h.get("sourceId") is None or not isinstance(h.get("snippet"), str) for h in hits):
        raise RerankUnavailable("候选证据缺少来源或正文")
    pairs = [[question, h["snippet"][:1000]] for h in hits]
    try:
        values = _model().predict(pairs, batch_size=4, show_progress_bar=False)
        scores = [float(x) for x in values]
    except Exception as exc:
        raise RerankUnavailable("Rerank 模型加载或推断失败；不会悄悄退回普通检索") from exc
    if len(scores) != len(hits) or not all(math.isfinite(x) for x in scores):
        raise RerankUnavailable("Rerank 返回了无效分数")
    ranked = sorted(enumerate(hits), key=lambda pair: (-scores[pair[0]], pair[0]))
    return [{**hit, "rerankScore": round(scores[index], 5)} for index, hit in ranked[:top_n]]
