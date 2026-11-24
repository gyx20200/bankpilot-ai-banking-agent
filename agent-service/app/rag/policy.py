"""Simple deterministic boundary checks, not a substitute for model output validation."""
import re


class KnowledgeRejected(ValueError):
    pass


SENSITIVE = re.compile(
    r'我的(?:余额|账户|流水|交易|银行卡|信用报告|征信报告|验证码|密码|授信|额度|订阅)|'
    r'(?:给.{0,20}转账|帮我转|替我支付|帮我取消|查询我的|替我申请|帮我查本人)',
    re.I,
)


def validate_public_query(value: str) -> str:
    if not isinstance(value, str) or not 4 <= len(value.strip()) <= 300:
        raise KnowledgeRejected('金融知识问题长度必须为4至300字符')
    query = value.strip()
    if SENSITIVE.search(query):
        raise KnowledgeRejected('该问题涉及个人银行业务，应通过登录后的 Java 银行业务工具处理')
    return query


def ensure_verbatim_query(query: str, current_message: str):
    """The model must copy a clause from this turn; never use historical private data."""
    query = validate_public_query(query)
    if query not in current_message:
        raise KnowledgeRejected('知识检索问题必须逐字来自当前用户消息')
    return query
