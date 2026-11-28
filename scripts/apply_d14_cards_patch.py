"""D14 minimal patcher for D13 main. --check validates exact anchors; --apply edits only owned paths."""
from __future__ import annotations
from pathlib import Path
import argparse
import sys

ROOT=Path(__file__).resolve().parents[1]

EDIT={
    'agent-service/app/graph/task_registry.py': [
       ("\n}\n\ndef resolve_execution_order", "\n    'card_list': TaskSpec(description='查询本人模拟虚拟卡与限制配置；只读', executor_key='d14_card_read', risk_level='LOW'),\n    'card_apply': TaskSpec(description='申请虚拟模拟借记卡；只准备订单，必须本人审批', executor_key='d14_card_write', risk_level='MEDIUM'),\n}\n\ndef resolve_execution_order", 'card_apply'),
    ],
    'agent-service/app/graph/task_planner.py': [
       ('        "D11支持以下可复用Agent Skills："',
        '        "D14独立卡片中心：查询我的虚拟模拟卡/卡片限制请选择card_list；明确申请虚拟模拟银行卡请选择card_apply。"\n'
        '        "card_apply只生成待审批申请，必须由用户在独立卡片中心确认，不能触发支付、授信、锁卡或挂失。"\n'
        '        "D11支持以下可复用Agent Skills："', 'D14独立卡片中心'),
    ],
    'agent-service/main.py': [
       ('from app.investments.api import router as investments_router',
        'from app.investments.api import router as investments_router\nfrom app.cards.api import router as cards_router', 'from app.cards.api import router as cards_router'),
       ('app.include_router(investments_router)',
        'app.include_router(investments_router)\napp.include_router(cards_router)', 'app.include_router(cards_router)'),
    ],
    'frontend/src/App.vue': [
       ('import InvestmentCenter from "./components/InvestmentCenter.vue";',
        'import InvestmentCenter from "./components/InvestmentCenter.vue";\nimport CardCenter from "./components/CardCenter.vue";', 'import CardCenter from'),
       ('          <InvestmentCenter :token="token" />\n        </details>',
        '          <InvestmentCenter :token="token" />\n        </details>\n'
        '        <details class="bp-investment-panel">\n'
        '          <summary>模拟卡片中心（D14，独立审批）</summary>\n'
        '          <CardCenter :token="token" />\n'
        '        </details>', '<CardCenter :token='),
    ],
}

def patch(text: str, file: str):
    original=text
    for anchor,replacement,signature in EDIT[file]:
        if signature in text:
            continue  # idempotent; already installed
        if text.count(anchor)!=1:
            raise RuntimeError(f'{file}: expected exactly one unmodified anchor, got {text.count(anchor)}: {anchor[:100]}')
        text=text.replace(anchor,replacement,1)
    return text, original!=text

def main():
    parser=argparse.ArgumentParser()
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--check',action='store_true')
    group.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    modifications=[]
    for name in EDIT:
        path=ROOT/name
        if not path.exists():raise RuntimeError(f'missing file: {path}')
        content=path.read_text(encoding='utf-8')
        result,changed=patch(content,name)
        modifications.append((path,result,changed))
    if args.apply:
        for path,content,changed in modifications:
            if changed:
                path.write_text(content,encoding='utf-8')
                print('APPLIED',path.relative_to(ROOT))
            else:print('UNCHANGED',path.relative_to(ROOT))
    else:
        for path,_,changed in modifications:
            print('READY' if changed else 'ALREADY_APPLIED',path.relative_to(ROOT))
    print('D14 PATCH VALIDATION PASSED')

if __name__=='__main__':
    try:main()
    except Exception as e:
        print(f'D14 patch stopped safely: {e}',file=sys.stderr)
        sys.exit(1)
