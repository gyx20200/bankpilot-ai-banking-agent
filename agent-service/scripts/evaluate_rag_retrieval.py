"""D8 offline retrieval recall at K, using human-reviewed source references."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'agent-service'))
from app.rag.store import search


def main():
    records = json.loads((ROOT / 'knowledge' / 'eval_d8_queries.json').read_text(encoding='utf-8'))
    passed = 0
    for row in records:
        hits = search(row['query'], top_k=3, min_similarity=0.0)
        ids = [x['sourceId'] for x in hits]
        ok = row['expected_source_id'] in ids
        passed += int(ok)
        print(('PASS' if ok else 'FAIL'), row['query'], 'top3=', ids)
    print(f'RECALL_AT_3={passed}/{len(records)}')
    if passed != len(records):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
