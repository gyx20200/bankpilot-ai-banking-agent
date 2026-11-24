"""Validate D9 gold set against approved public sources, no model calls."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GOLD = ROOT / 'knowledge' / 'eval_d9_cases.json'
SOURCES = ROOT / 'knowledge' / 'approved_sources.json'


def main():
    gold = json.loads(GOLD.read_text(encoding='utf-8'))
    approved = {s['source_id'] for s in json.loads(SOURCES.read_text(encoding='utf-8'))}
    seen: set[str] = set()
    for kind in ('retrievalCases', 'routeCases', 'faithfulnessCases'):
        rows = gold.get(kind)
        assert isinstance(rows, list) and rows, kind
        for row in rows:
            case_id = row.get('id')
            assert isinstance(case_id, str) and case_id and case_id not in seen, case_id
            seen.add(case_id)
            if kind == 'retrievalCases':
                assert isinstance(row.get('query'), str) and row['query'].strip()
                expected = row.get('expectedSourceIds')
                assert isinstance(expected, list) and expected and set(expected) <= approved, case_id
            elif kind == 'routeCases':
                assert isinstance(row.get('message'), str) and row['message'].strip()
                assert isinstance(row.get('expectedTaskTypes'), list) and row['expectedTaskTypes'], case_id
            else:
                assert isinstance(row.get('answer'), str)
                assert isinstance(row.get('snippets'), list) and row['snippets']
                assert type(row.get('expectedPassed')) is bool, case_id
    print(f'D9 GOLD DATASET VALID: retrieval={len(gold["retrievalCases"])} '
          f'route={len(gold["routeCases"])} faithfulness={len(gold["faithfulnessCases"])} sources={len(approved)}')


if __name__ == '__main__':
    main()
