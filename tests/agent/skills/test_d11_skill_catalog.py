"""D11: no model, bank service, local MCP server or Chroma needed."""
from pathlib import Path
import pytest
from app.skills.catalog import SKILLS, SkillError, get_skill, validate_catalog, activated_instructions
from app.mcp.policy import ALLOWED


def test_skill_document_catalog_matches_enforced_execution_steps():
    rows=validate_catalog()
    assert len(rows)==3
    assert {x['name'] for x in rows}==set(SKILLS)
    assert all(row['readOnly'] for row in rows)
    for spec in SKILLS.values():
        assert spec.steps
        assert all(step in ALLOWED for step in spec.steps)
        assert all('transfer' not in step and 'authorize' not in step and 'cancel' not in step for step in spec.steps)
        assert len(activated_instructions(spec.name))>40


def test_unknown_skill_is_fail_closed():
    for value in ['../secret', 'transfer_execute', 'skill_transfer', '', None]:
        with pytest.raises(SkillError):
            get_skill(value)


def test_modified_skill_metadata_is_detected(tmp_path,monkeypatch):
    import app.skills.catalog as catalog
    for spec in SKILLS.values():
        src=catalog.SKILLS_ROOT/spec.slug/'SKILL.md'
        dst=tmp_path/spec.slug/'SKILL.md';dst.parent.mkdir(parents=True)
        content=src.read_text(encoding='utf-8')
        if spec.name=='skill_account_snapshot':content=content.replace('name: bankpilot-account-snapshot','name: bankpilot-transfer-execute')
        dst.write_text(content,encoding='utf-8')
    monkeypatch.setattr(catalog,'SKILLS_ROOT',tmp_path)
    with pytest.raises(SkillError,match='mismatch'):
        catalog.validate_catalog()
