
from uuid import UUID

from app.context.manager import build_planner_context


def context_from_java_response(
        conversation_id: UUID,
        current_message: str,
        response: dict,
):
    if response.get("conversationId") != str(conversation_id):
        raise ValueError("会话 ID 不一致")

    return build_planner_context(
        conversation_id=conversation_id,
        current_message=current_message,
        history=response["items"],
    )

async def load_planner_context(
        conversation_id,
        current_message,
        authorization,
):
    ...