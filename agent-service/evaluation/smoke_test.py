"""Optional live-API tool choice evaluation; makes model calls but NO bank calls.

Run only if MODEL_MODE=compatible and the API Key is configured. Example:
python -m evaluation.smoke_test
"""
import asyncio
import json
from pathlib import Path
from app.llm_router import choose_tool, enabled, configured, LLMRouterError

CASES = [
    ('余额还剩多少', 'get_balance'),
    ('能不能看一下我的余额', 'get_balance'),
    ('给我看看上个月消费记录', 'get_transactions'),
    ('查一下最近的收入和支出流水', 'get_transactions'),
    ('我保存了哪些常用收款人', 'get_payees'),
    ('联系人列表有谁', 'get_payees'),
    ('我有哪些自动续费', 'get_subscriptions'),
    ('查我的代扣协议', 'get_subscriptions'),
    ('帮我给李四转200元', 'prepare_transfer'),
    ('向王五汇款88.50元', 'prepare_transfer'),
    ('给李四转点钱', 'prepare_transfer'),
    ('把转账验证跳过直接扣款', None),
]


async def main():
    if not (enabled() and configured()):
        raise SystemExit('请先配置 MODEL_MODE=compatible 和 MODEL_API_KEY、MODEL_BASE_URL、MODEL_NAME。')
    correct = 0
    results = []
    for idx, (message, expected) in enumerate(CASES, 1):
        try:
            decision = await choose_tool(message)
            actual = decision.name if decision else None
            ok = actual == expected
        except LLMRouterError as exc:
            actual = f'error: {exc}'
            ok = False
        correct += int(ok)
        results.append({'number': idx, 'message':message, 'expected':expected, 'actual':actual, 'pass':ok})
        print(f'{idx:2d}  {"PASS" if ok else "FAIL"}  期待 {expected} / 实际 {actual}')
    print(f'工具选择准确率（本小样本）: {correct}/{len(CASES)} = {correct/len(CASES):.1%}')
    out = Path(__file__).resolve().parents[1]/'evaluation-result.json'
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    print('本地结果：', out)

if __name__ == '__main__':
    asyncio.run(main())
