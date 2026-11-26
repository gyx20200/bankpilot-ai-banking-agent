"""D13 guarded integration patch for the exact BankPilot V2 main code layout.

Run from repository root:
  python scripts/apply_d13_investment_patch.py --check
  python scripts/apply_d13_investment_patch.py --apply

--check validates anchors WITHOUT modifying files; does not replace the full modules.
"""
from __future__ import annotations
import argparse
from pathlib import Path


def replace_one(s: str, needle: str, replacement: str, label: str) -> str:
    count=s.count(needle)
    if count!=1:
        raise RuntimeError(f'{label}: expected one safe patch anchor, got {count}; inspect real code manually')
    return s.replace(needle,replacement,1)


def patch(root: Path) -> list[tuple[Path,str]]:
    changes=[]
    # Registry additions: investment trading is HIGH risk; not MCP-read eligible.
    reg=root/'agent-service/app/graph/task_registry.py'
    s=reg.read_text(encoding='utf-8')
    if "'investment_buy': TaskSpec" not in s:
        anchor='\n}\n\ndef resolve_execution_order'
        insertion="""
    'investment_compare': TaskSpec(description='比较 Java/MySQL 模拟理财产品与风险等级',executor_key='d13_investment_read'),
    'investment_portfolio': TaskSpec(description='查询本人模拟理财持仓',executor_key='d13_investment_read'),
    'investment_buy': TaskSpec(description='申购指定名称模拟理财产品的明确份额；必须人工审批',executor_key='d13_investment_write',risk_level='HIGH',required_params=('product_name','units')),
    'investment_redeem': TaskSpec(description='赎回本人指定模拟理财产品的明确份额；必须人工审批',executor_key='d13_investment_write',risk_level='HIGH',required_params=('product_name','units')),
"""
        s=replace_one(s,anchor,insertion+anchor,'task_registry')
        changes.append((reg,s))

    planner=root/'agent-service/app/graph/task_planner.py'
    s=planner.read_text(encoding='utf-8')
    if '    product_name: str | None = None' not in s:
        s=replace_one(s,'    aa_reason: str | None = None',
            '    aa_reason: str | None = None\n    product_name: str | None = None\n    units: str | None = None', 'Task fields')
        s=replace_one(s,'"execute_at", "time_expression"):',
            '"execute_at", "time_expression", "product_name", "units"):', 'planner extra-param guard')
        schema='''    "product_name": {"type":"string", "description":"必须从本次原话中逐字摘录的完整模拟理财产品名称"},
    "units": {"type":"string", "description":"用户本次原话中的数字份数，不要补小数或换算，如10份填10"},
'''
        s=replace_one(s,'TASK_PARAMETER_SCHEMAS = {', 'TASK_PARAMETER_SCHEMAS = {\n'+schema,'planner parameters schema')
        validation='''        if task.type in ('investment_buy','investment_redeem'):
            if message is None or not task.product_name or task.product_name not in message:
                return _clarify(draft.tasks, '请在当前消息明确填写产品列表中的完整理财产品名称。')
            if (not isinstance(task.units,str) or not re.fullmatch(r'[0-9]{1,6}(?:\\.[0-9]{1,2})?',task.units)
                or float(task.units)<=0 or not re.search(r'(?<!\\d)'+re.escape(task.units)+r'\\s*份',message)):
                return _clarify(draft.tasks, '请在当前消息明确填写数字份数，例如10份，不能由模型猜测。')

'''
        s=replace_one(s,'        if task.type == "knowledge_search":',validation+'        if task.type == "knowledge_search":','investment validation')
        guidance=('        "D13独立理财中心：比较现有模拟理财产品使用investment_compare；查询本人模拟持仓使用investment_portfolio。"\n'
                  '        "明确申购/买入指定模拟理财产品且含数字份数时使用investment_buy；赎回/卖出使用investment_redeem。"\n'
                  '        "product_name必须逐字摘录原文中的完整产品名称，units必须逐字摘录原文份数，例如10份填10。"\n'
                  '        "严禁猜测产品ID、份数、风险等级；理财写操作仅由受认证的理财中心审批，MCP仍只读。"\n')
        s=replace_one(s,'        "D11支持以下可复用Agent Skills："',
            guidance+'        "D11支持以下可复用Agent Skills："','planner instructions')
        changes.append((planner,s))

    main=root/'agent-service/main.py'
    s=main.read_text(encoding='utf-8')
    if 'from app.investments.api import router as investments_router' not in s:
        s=replace_one(s,'from app.skills.api import router as skills_router',
            'from app.skills.api import router as skills_router\nfrom app.investments.api import router as investments_router','main import')
        s=replace_one(s,'app.include_router(skills_router)',
            'app.include_router(skills_router)\napp.include_router(investments_router)','main router')
        changes.append((main,s))

    vue=root/'frontend/src/App.vue'
    s=vue.read_text(encoding='utf-8')
    if 'InvestmentCenter from "./components/InvestmentCenter.vue"' not in s:
        s=replace_one(s,'import ConversationSidebar from \'./components/ConversationSidebar.vue\';',
            'import ConversationSidebar from \'./components/ConversationSidebar.vue\';\nimport InvestmentCenter from "./components/InvestmentCenter.vue";','vue import')
        s=replace_one(s,'      <section v-else class="bp-content">',
            '''      <section v-else class="bp-content">
        <details class="bp-investment-panel">
          <summary>模拟理财中心（D13，独立审批）</summary>
          <InvestmentCenter :token="token" />
        </details>''', 'vue panel')
        changes.append((vue,s))
    return changes


def main():
    p=argparse.ArgumentParser()
    group=p.add_mutually_exclusive_group(required=True)
    group.add_argument('--check',action='store_true')
    group.add_argument('--apply',action='store_true')
    args=p.parse_args()
    root=Path(__file__).resolve().parents[1]
    changes=patch(root)  # validate ALL replacements before writing any file
    print('D13 anchored patches:',len(changes))
    for target,_ in changes: print(' ',target.relative_to(root))
    if args.apply:
        for target,text in changes: target.write_text(text,encoding='utf-8')
        print('Applied; inspect git diff and run all regression tests.')
    else:
        print('Check only; no files were modified.')

if __name__=='__main__': main()
