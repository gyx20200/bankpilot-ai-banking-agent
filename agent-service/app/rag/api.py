"""Direct RAG diagnostic endpoint; actual Agent routing uses knowledge_search task."""
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app import workflow_api
from .answer import answer_public_question, RagAnswerError
from .policy import KnowledgeRejected

router = APIRouter(prefix='/api/agent/knowledge', tags=['BankPilot Public Knowledge RAG'])


class AskBody(BaseModel):
    model_config = ConfigDict(extra='forbid')
    question: str = Field(min_length=4, max_length=300)


@router.post('/ask')
async def ask(body: AskBody, authorization: str | None = Header(default=None)):
    await workflow_api._authenticated_user(authorization)
    try:
        return await answer_public_question(body.question)
    except KnowledgeRejected as exc:
        raise HTTPException(422, str(exc)) from exc
    except RagAnswerError as exc:
        raise HTTPException(503, str(exc)) from exc
