"""Trusted D11 Skills catalog; repository SKILL.md documents are NOT executable code.

Only hard-coded Task -> MCP sequences can execute. Never interpret Markdown/YAML
or a model-generated step as a bank command.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import re

SKILLS_ROOT = Path(__file__).resolve().parents[2] / 'skills'

@dataclass(frozen=True)
class SkillSpec:
    name: str
    slug: str
    title: str
    description: str
    steps: tuple[str, ...]
    required_params: tuple[str, ...] = ()


SKILLS: dict[str, SkillSpec] = {
    'skill_monthly_finance_review': SkillSpec(
        name='skill_monthly_finance_review',
        slug='bankpilot-monthly-finance-review',
        title='月度财务体检',
        description='基于当前用户真实模拟银行数据，联合查询指定月收支和异常规则；不确认盗刷、不修改资金。',
        steps=('monthly_analytics', 'transaction_anomalies'),
        required_params=('month',),
    ),
    'skill_account_snapshot': SkillSpec(
        name='skill_account_snapshot',
        slug='bankpilot-account-snapshot',
        title='账户概览',
        description='同时查询当前用户余额和交易流水，生成只读账户概览。',
        steps=('get_balance', 'get_transactions'),
    ),
    'skill_subscription_review': SkillSpec(
        name='skill_subscription_review',
        slug='bankpilot-subscription-review',
        title='订阅巡检',
        description='查看当前用户订阅代扣和交易流水，不自动取消、代扣或认定重复扣费。',
        steps=('list_subscriptions', 'get_transactions'),
    ),
}


class SkillError(ValueError):
    pass


def get_skill(name: str) -> SkillSpec:
    if not isinstance(name, str) or name not in SKILLS:
        raise SkillError('未注册的 Agent Skill')
    return SKILLS[name]


def validate_catalog() -> list[dict]:
    """Validate trusted SKILL.md name/description frontmatter and read-only step map."""
    from app.mcp.policy import ALLOWED
    rows = []
    for spec in SKILLS.values():
        if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', spec.slug):
            raise SkillError('Skill name format is invalid')
        if not spec.steps or len(spec.steps) > 3 or any(step not in ALLOWED for step in spec.steps):
            raise SkillError('Skill contains unapproved or excess MCP steps')
        if spec.required_params not in ((), ('month',)):
            raise SkillError('Skill parameters are not allowlisted')
        path = SKILLS_ROOT / spec.slug / 'SKILL.md'
        try:
            content = path.read_text(encoding='utf-8')
        except OSError as exc:
            raise SkillError('Skill document missing') from exc
        if len(content)>12000 or not content.startswith('---\n'):
            raise SkillError('Skill document frontmatter invalid')
        parts=content.split('---\n',2)
        if len(parts)!=3:
            raise SkillError('Skill document missing metadata')
        metadata={}
        for line in parts[1].splitlines():
            if ':' not in line: raise SkillError('Skill metadata invalid')
            key,value=line.split(':',1)
            if key.strip() in metadata: raise SkillError('Duplicate skill metadata')
            metadata[key.strip()]=value.strip().strip('"').strip("'")
        if metadata.get('name')!=spec.slug or metadata.get('description')!=spec.description:
            raise SkillError('Skill description mismatch with trusted catalog')
        rows.append({'name':spec.name,'documentName':spec.slug,'title':spec.title,'description':spec.description,
                     'requires':list(spec.required_params),'readOnly':True,'stepCount':len(spec.steps)})
    return rows


def activated_instructions(name: str) -> str:
    """Progressively disclose the selected local SKILL.md, never execute its content."""
    get_skill(name)
    validate_catalog()
    text=(SKILLS_ROOT/get_skill(name).slug/'SKILL.md').read_text(encoding='utf-8')
    return text.split('---\n',2)[2].strip()
