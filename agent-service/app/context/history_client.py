
import os
from uuid import UUID

import httpx
from fastapi import HTTPException
from pydantic import ValidationError

from app.context.manager import build_planner_context


def context_from_java_response(
        conversation_id: UUID,
        current_message: str,
        response: dict,
):
    if not isinstance(response, dict):
        raise ValueError("历史响应格式不正确")

    if response.get("conversationId") != str(conversation_id):
        raise ValueError("会话 ID 不一致")

    items = response.get("items")
    if not isinstance(items, list):
        raise ValueError("历史消息列表格式不正确")

    return build_planner_context(
        conversation_id=conversation_id,
        current_message=current_message,
        history=items,
    )

async def load_planner_context(
        conversation_id: UUID,
        current_message: str,
        authorization: str | None,
):
    # Load recent messages from Java's authenticated conversation API.
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="请先登录")

    api_base = os.getenv(
        "BANK_CONVERSATION_API_BASE",
        "http://127.0.0.1:8080/api/conversations",
    ).rstrip("/")

    try:
        async with httpx.AsyncClient(
            timeout=8,
            follow_redirects=False,
        ) as client:
            response = await client.get(
                f"{api_base}/{conversation_id}/messages",
                headers={"Authorization": authorization},
                params={"limit": 20},
            )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail="无法读取银行会话历史",
        ) from exc

    if response.status_code != 200:
        status = response.status_code
        if status not in (401, 403, 404):
            status = 502
        raise HTTPException(
            status_code=status,
            detail="银行会话历史读取失败",
        )

    try:
        payload = response.json()
        return context_from_java_response(
            conversation_id=conversation_id,
            current_message=current_message,
            response=payload,
        )
    except (ValueError, KeyError, TypeError, ValidationError) as exc:
        raise HTTPException(
            status_code=502,
            detail="历史消息格式校验失败",
        ) from exc