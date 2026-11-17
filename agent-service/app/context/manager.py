
"""BankPilot conversation context manager.

D2 implementation:
- Validate history records.
- Keep the latest N messages.
- Preserve chronological order.
- Avoid duplicating the current user message.

History must be loaded from the authenticated server-side
conversation API. Never trust history submitted by the browser.
"""

from collections.abc import Sequence
from typing import Any
from uuid import UUID

from app.context.models import ConversationTurn, PlannerContext


MAX_RECENT_TURNS = 10


def build_planner_context(
    *,
    conversation_id: UUID | str,
    current_message: str,
    history: Sequence[ConversationTurn | dict[str, Any]] = (),
    summary: str | None = None,
    history_limit: int = MAX_RECENT_TURNS,
) -> PlannerContext:
    """Build a validated context without performing I/O."""

    if (
        isinstance(history_limit, bool)
        or not isinstance(history_limit, int)
        or not 0 <= history_limit <= MAX_RECENT_TURNS
    ):
        raise ValueError(
            f"history_limit must be between 0 and {MAX_RECENT_TURNS}"
        )

    current = current_message.strip()

    parsed = [
        item if isinstance(item, ConversationTurn)
        else ConversationTurn.model_validate(item)
        for item in history
    ]

    # Java message IDs are monotonically increasing.
    # Sort when all records contain IDs; otherwise preserve API order.
    if parsed and all(item.message_id is not None for item in parsed):
        parsed.sort(key=lambda item: item.message_id or 0)

    # If the current user message was persisted before history retrieval,
    # remove its last occurrence to avoid giving it to the planner twice.
    if (
        parsed
        and parsed[-1].role == "USER"
        and parsed[-1].content == current
    ):
        parsed.pop()

    recent = parsed[-history_limit:] if history_limit else []

    return PlannerContext(
        conversation_id=conversation_id,
        current_message=current,
        recent_messages=recent,
        summary=summary,
    )
