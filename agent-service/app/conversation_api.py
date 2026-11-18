
"""Authenticated conversation API gateway.

D3: proxy conversation operations to Java.
Java remains authoritative for user ownership.
"""

import os
from uuid import UUID

import httpx
from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ConfigDict

router = APIRouter(
    prefix="/api/agent/conversations",
    tags=["Conversations"],
)

JAVA_BASE = os.getenv(
    "BANK_CONVERSATION_API_BASE",
    "http://127.0.0.1:8080/api/conversations",
).rstrip("/")


class CreateConversation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(default="新会话", max_length=100)


class UserMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: str = Field(min_length=1, max_length=2000)
    requestId: str = Field(
        min_length=8,
        max_length=64,
        pattern=r"^[A-Za-z0-9_-]+$",
    )


async def forward(method, path, authorization, payload=None, params=None):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "请先登录")

    try:
        async with httpx.AsyncClient(
            timeout=10,
            follow_redirects=False,
        ) as client:
            response = await client.request(
                method,
                JAVA_BASE + path,
                headers={"Authorization": authorization},
                json=payload,
                params=params,
            )
    except httpx.HTTPError as exc:
        raise HTTPException(
            502, "银行会话服务暂时不可用"
        ) from exc

    try:
        data = response.json()
    except ValueError:
        raise HTTPException(
            502, "银行会话服务返回格式异常"
        )

    return JSONResponse(
        status_code=response.status_code,
        content=data,
    )


@router.post("", status_code=201)
async def create(body: CreateConversation,
                 authorization: str | None = Header(default=None)):
    return await forward(
        "POST", "", authorization, body.model_dump()
    )


@router.get("")
async def list_conversations(
        authorization: str | None = Header(default=None)):
    return await forward("GET", "", authorization)


@router.get("/{conversation_id}")
async def get_conversation(
        conversation_id: UUID,
        authorization: str | None = Header(default=None)):
    return await forward(
        "GET", f"/{conversation_id}", authorization
    )


@router.get("/{conversation_id}/messages")
async def get_messages(
        conversation_id: UUID,
        limit: int = 20,
        beforeId: int | None = None,
        authorization: str | None = Header(default=None)):
    return await forward(
        "GET",
        f"/{conversation_id}/messages",
        authorization,
        params={"limit": limit, "beforeId": beforeId}
    )


@router.post("/{conversation_id}/messages", status_code=201)
async def append_user_message(
        conversation_id: UUID,
        body: UserMessage,
        authorization: str | None = Header(default=None)):
    return await forward(
        "POST",
        f"/{conversation_id}/messages",
        authorization,
        body.model_dump(),
    )
