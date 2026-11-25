"""Authenticated Agent Skills catalog + explicit read-only debugging/execution API."""
from __future__ import annotations
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from app import workflow_api
from app.mcp.policy import MCPReadError
from .catalog import SkillError, validate_catalog, get_skill, activated_instructions
from .runtime import run_skill, SkillExecutionError

router=APIRouter(prefix='/api/agent/skills',tags=['BankPilot Agent Skills'])

class SkillInput(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    month: str | None = Field(default=None,max_length=7)

@router.get('')
async def catalog(authorization: str|None=Header(default=None)):
    await workflow_api._authenticated_user(authorization)
    return {'skills':validate_catalog(),'executionMode':'MCP_READ_ONLY'}

@router.get('/{name}')
async def detail(name: str, authorization: str|None=Header(default=None)):
    await workflow_api._authenticated_user(authorization)
    try:
        spec=get_skill(name)
        return {'name':spec.name,'title':spec.title,'description':spec.description,
                'instructions':activated_instructions(name),'readOnly':True,
                'requiredParams':list(spec.required_params)}
    except SkillError as exc:
        raise HTTPException(404,str(exc)) from exc

@router.post('/{name}/execute')
async def execute(name: str, body: SkillInput, authorization: str|None=Header(default=None)):
    await workflow_api._authenticated_user(authorization)
    try:
        params = body.model_dump(exclude_unset=True)
        return await run_skill(name,params,authorization)
    except SkillExecutionError as exc:
        raise HTTPException(503,str(exc)) from exc
    except SkillError as exc:
        raise HTTPException(422,str(exc)) from exc
    except MCPReadError as exc:
        raise HTTPException(503,'Skill MCP read unavailable; no bank writes') from exc
