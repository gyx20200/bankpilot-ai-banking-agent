"""D11 reusable deterministic skill runner backed exclusively by D10 MCP reads."""
from __future__ import annotations
from datetime import datetime
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo
import re
from typing import Any

from app.mcp.dispatch import execute_mcp_read
from app.mcp.policy import ALLOWED, MCPReadError, read_mode, tool_for_task
from .catalog import SKILLS, SkillError, get_skill, activated_instructions

class SkillExecutionError(RuntimeError):
    '''A verified skill could not finish; this is not a user parameter error.'''

CN = ZoneInfo('Asia/Shanghai')


def validate_skill_input(skill_name: str, params: dict | None) -> dict[str, str]:
    spec=get_skill(skill_name)
    if not isinstance(params,dict):
        raise SkillError('Skill parameters must be an object')
    if set(params)!=set(spec.required_params):
        raise SkillError('Skill parameters do not match its exact schema')
    if 'month' not in spec.required_params:
        return {}
    month=params['month']
    if not isinstance(month,str) or not re.fullmatch(r'[1-9][0-9]{3}-(0[1-9]|1[0-2])',month):
        raise SkillError('month must be YYYY-MM')
    if month>datetime.now(CN).strftime('%Y-%m'):
        raise SkillError('Cannot analyze a future month')
    return {'month':month}


def _decimal(value: Any) -> Decimal:
    try:
        if isinstance(value,bool) or value is None: raise ValueError()
        number=Decimal(str(value))
        if not number.is_finite(): raise ValueError()
        return number
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise SkillError('Invalid bank amount') from exc


def validate_step_result(step: str, data: Any, params: dict[str,str]) -> None:
    if step in ('get_transactions','list_subscriptions','get_payees'):
        if not isinstance(data,list): raise SkillError('Bank list response invalid')
    elif step=='get_balance':
        if not isinstance(data,dict) or 'balance' not in data:
            raise SkillError('Bank balance response invalid')
        _decimal(data['balance'])
    elif step=='monthly_analytics':
        if not isinstance(data,dict) or data.get('month')!=params['month'] or data.get('source')!='mysql':
            raise SkillError('Monthly bank report identity invalid')
        for field in ('totalIncome','totalExpense','netCashFlow'):
            _decimal(data.get(field))
    elif step=='transaction_anomalies':
        if not isinstance(data,dict) or data.get('month')!=params['month'] or data.get('source')!='mysql':
            raise SkillError('Anomaly bank report identity invalid')
        if type(data.get('anomalyCount')) is not int or data['anomalyCount']<0:
            raise SkillError('Anomaly bank count invalid')
    else:
        raise SkillError('Unapproved skill step')


def summarize(skill_name: str, data: dict) -> str:
    if skill_name=='skill_monthly_finance_review':
        m=data['monthly_analytics']; a=data['transaction_anomalies'];
        return (f"{m['month']}：收入 ¥{_decimal(m['totalIncome']):,.2f}，"
                f"支出 ¥{_decimal(m['totalExpense']):,.2f}，"
                f"发现 {a['anomalyCount']} 条规则提示（不是已确认的盗刷或重复扣费）。")
    if skill_name=='skill_account_snapshot':
        return (f"查询时余额 ¥{_decimal(data['get_balance']['balance']):,.2f}；"
                f"返回 {len(data['get_transactions'])} 条交易流水。最新余额请重新查询。")
    if skill_name=='skill_subscription_review':
        subscriptions=data['list_subscriptions'];active=sum(1 for x in subscriptions if isinstance(x,dict) and x.get('status')=='ACTIVE')
        return (f"当前查询到 {len(subscriptions)} 项订阅，其中 {active} 项有效；"
                f"同时读取 {len(data['get_transactions'])} 条流水。未取消任何订阅，不能据此判定重复扣费。")
    raise SkillError('Unknown skill')


async def run_skill(skill_name: str, params: dict | None, bearer: str) -> dict:
    spec=get_skill(skill_name)
    args=validate_skill_input(skill_name,params)
    if read_mode()!='on':
        raise SkillError('Agent Skills require BANKPILOT_MCP_READ_MODE=on')
    if not isinstance(bearer,str) or not bearer.startswith('Bearer ') or not bearer[7:].strip():
        raise SkillError('Missing authenticated user')
    # Integrity check and on-demand instructions: no text is evaluated as code.
    activated_instructions(skill_name)
    data={}
    completed=[]
    for step in spec.steps:
        if step not in ALLOWED: raise SkillError('Skill step is not a permitted MCP read')
        task={'type':step}
        if step in ('monthly_analytics','transaction_anomalies'):
            task['month']=args['month']
        tool_name,_=tool_for_task(task)
        try:
            response=await execute_mcp_read(task,bearer)
        except MCPReadError as exc:
            raise SkillExecutionError(f'Skill read step {step} failed, no completed report') from exc
        try:
            validate_step_result(step,response,args)
        except SkillError as exc:
            raise SkillExecutionError(f'Skill bank response invalid for {step}') from exc
        data[step]=response
        completed.append({'taskType':step,'mcpTool':tool_name,'status':'SUCCESS'})
    return {
        'skillId':spec.name,'title':spec.title,'status':'COMPLETED',
        'readOnly':True,'dataOrigin':'JAVA_MYSQL_VIA_MCP',
        'summary':summarize(spec.name,data),
        'steps':completed,'results':data,
    }
