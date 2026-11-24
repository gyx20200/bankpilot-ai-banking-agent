"""D9 retrieval A/B evaluation without LLM calls or banking API access.

Run from repository root: python agent-service/scripts/evaluate_d9_retrieval.py --compare
Outputs only case ids, source identifiers and aggregate metrics (no personal data).
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "agent-service"))


def scores(rows: list[dict], k: int = 3) -> dict:
    if not rows:
        raise ValueError("evaluation cases cannot be empty")
    hits1, hits3, mrr = 0, 0, 0.0
    for row in rows:
        expected, ranked = set(row["expected"]), row["ranked"][:k]
        hits1 += int(bool(ranked and ranked[0] in expected))
        hits3 += int(any(x in expected for x in ranked))
        rank = next((i + 1 for i, x in enumerate(ranked) if x in expected), None)
        mrr += 1 / rank if rank else 0.0
    count = len(rows)
    return {"count": count, "hitAt1": round(hits1 / count, 4),
            "recallAt3": round(hits3 / count, 4), "mrrAt3": round(mrr / count, 4)}


def main() -> None:
    from app.rag.store import search
    from app.rag.rerank import rerank_hits
    parser = argparse.ArgumentParser()
    parser.add_argument("--compare", action="store_true", help="load BGE CrossEncoder; heavier on CPU")
    parser.add_argument("--min-similarity", type=float, default=0.68)
    args = parser.parse_args()
    cases = json.loads((ROOT / "knowledge" / "eval_d9_cases.json").read_text(encoding="utf-8"))["retrievalCases"]
    baseline, reranked = [], []
    base_latency, rerank_latency = [], []
    for case in cases:
        started = time.perf_counter()
        candidates = search(case["query"], top_k=5, min_similarity=args.min_similarity)
        base_latency.append((time.perf_counter() - started) * 1000)
        row = {"id": case["id"], "expected": case["expectedSourceIds"],
               "ranked": [hit["sourceId"] for hit in candidates[:3]]}
        baseline.append(row)
        print("BASE", case["id"], row["ranked"])
        if args.compare:
            started = time.perf_counter()
            best = rerank_hits(case["query"], candidates, top_n=3)
            rerank_latency.append((time.perf_counter() - started) * 1000)
            reranked.append({"id": case["id"], "expected": case["expectedSourceIds"],
                             "ranked": [hit["sourceId"] for hit in best]})
            print("RERANK", case["id"], reranked[-1]["ranked"])
    report = {"datasetVersion": "d9-v1", "similarityThreshold": args.min_similarity,
              "baseline": scores(baseline),
              "baselineMedianRetrievalMs": round(statistics.median(base_latency), 2)}
    if args.compare:
        report["rerank"] = scores(reranked)
        report["rerankMedianExtraMs"] = round(statistics.median(rerank_latency), 2)
        report["deltaHitAt1"] = round(report["rerank"]["hitAt1"] - report["baseline"]["hitAt1"], 4)
        report["deltaMRRAt3"] = round(report["rerank"]["mrrAt3"] - report["baseline"]["mrrAt3"], 4)
    out = ROOT / "agent-service" / "data" / "evaluation" / "d9_retrieval.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("EVALUATION", json.dumps(report, ensure_ascii=False))
    print("WRITTEN", out)


if __name__ == "__main__":
    main()
