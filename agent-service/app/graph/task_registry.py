"""BankPilot unified task registry: metadata only; does not invoke bank APIs."""
from dataclasses import dataclass
from typing import Iterable, Literal


RiskLevel = Literal['LOW','MEDIUM','HIGH']

@dataclass(frozen=True)
class TaskSpec:
    description: str
    executor_key: str
    risk_level: RiskLevel = 'LOW'
    required_params: tuple[str,...] = ()
    depends_on: tuple[str,...] = ()
    legacy_tool: str | None = None

TASK_REGISTRY: dict[str, TaskSpec] = {
    'get_balance': TaskSpec(description='查询当前用户余额', executor_key='balance',legacy_tool='get_balance'),
    'get_transactions': TaskSpec(description='查询当前用户历史交易流水',executor_key='transactions',legacy_tool='get_transactions'),
    'get_payees': TaskSpec(description='查询当前用户常用收款人',executor_key='payees',legacy_tool='get_payees'),
    'monthly_analytics': TaskSpec(description='分析指定月份收支',executor_key='monthly_analytics',required_params=('month',),legacy_tool='get_monthly_analytics'),
    'annual_analytics': TaskSpec(description='分析明确指定年份的年度收支、支出分类及月度趋势',executor_key='annual_analytics',required_params=('year',)),
    'transaction_anomalies': TaskSpec(description='检测明确指定月份的大额支出和疑似重复扣费规则事件',executor_key='transaction_anomalies',required_params=('month',)),
    'list_subscriptions': TaskSpec(description='查询当前用户订阅代扣协议',executor_key='subscriptions',legacy_tool='get_subscriptions'),
    'transfer_prepare': TaskSpec(description='创建待确认的转账订单，不执行转账',executor_key='transfer_prepare',risk_level='HIGH',required_params=('payee_name','payee_phone','amount','remark'),depends_on=('get_payees',),legacy_tool='prepare_transfer'),
    'schedule_transfer': TaskSpec(description='预约未来单次转账，固定收款人金额时间，预约时所有金额均强制OTP；到期银行自动执行',executor_key='schedule_transfer',risk_level='HIGH',required_params=('payee_name','payee_phone','amount','remark','time_expression','execute_at')),
    'create_aa_collection': TaskSpec(description='准备并经发起人确认后发布AA收款请求；不会替接收人付款',executor_key='aa_collection',risk_level='MEDIUM',required_params=('aa_participants','aa_mode','amount','aa_reason')),
    'cancel_subscription': TaskSpec(description='申请取消指定代扣，必须经独立人工审批与银行授权',executor_key='subscription_cancellation',risk_level='MEDIUM',required_params=('target_name',),depends_on=('list_subscriptions',)),
    'knowledge_search': TaskSpec(description='检索公开金融法规、存款保险、征信渠道及金融消费者保护知识；不查询个人账户',executor_key='knowledge_search',required_params=('query',),risk_level='LOW'),
    'skill_monthly_finance_review': TaskSpec(description='Agent Skill：月度财务体检，需明确年月；只读组合执行月度收支和异常规则查询',executor_key='skill',required_params=('month',)),
    'skill_account_snapshot': TaskSpec(description='Agent Skill：账户概览，同时只读查询本人余额和交易流水',executor_key='skill'),
    'skill_subscription_review': TaskSpec(description='Agent Skill：订阅巡检，同时只读查询本人订阅协议和流水，不执行取消',executor_key='skill'),
    'investment_compare': TaskSpec(description='比较 Java/MySQL 模拟理财产品与风险等级',executor_key='d13_investment_read'),
    'investment_portfolio': TaskSpec(description='查询本人模拟理财持仓',executor_key='d13_investment_read'),
    'investment_buy': TaskSpec(description='申购指定名称模拟理财产品的明确份额；必须人工审批',executor_key='d13_investment_write',risk_level='HIGH',required_params=('product_name','units')),
    'investment_redeem': TaskSpec(description='赎回本人指定模拟理财产品的明确份额；必须人工审批',executor_key='d13_investment_write',risk_level='HIGH',required_params=('product_name','units')),

}

def resolve_execution_order(requested:Iterable[str])->list[str]:
    ordered:list[str]=[];visited:set[str]=set();visiting:set[str]=set()
    def visit(task_type:str)->None:
        if task_type not in TASK_REGISTRY: raise ValueError(f'未注册任务：{task_type}')
        if task_type in visiting: raise ValueError(f'任务依赖存在循环：{task_type}')
        if task_type in visited: return
        visiting.add(task_type)
        for dependency in TASK_REGISTRY[task_type].depends_on:visit(dependency)
        visiting.remove(task_type);visited.add(task_type);ordered.append(task_type)
    for task_type in requested: visit(task_type)
    return ordered
