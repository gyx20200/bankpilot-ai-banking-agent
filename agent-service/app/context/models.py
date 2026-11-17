
"""BankPilot 2.0 conversation context models.

D2: define schemas only.
No database access, LLM calls or bank operations.
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ConversationTurn(BaseModel):
    """One persisted conversation message."""

    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        str_strip_whitespace=True,
    )

    message_id: int | None = Field(
        default=None,
        gt=0,
        alias="messageId",
    )

    role: Literal["USER", "ASSISTANT"]

    content: str = Field(
        min_length=1,
        max_length=2000,
    )

    created_at: datetime | None = Field(
        default=None,
        alias="createdAt",
    )


class PlannerContext(BaseModel):
    """Context supplied to the task planner in a future integration."""

    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        str_strip_whitespace=True,
    )

    conversation_id: UUID = Field(
        alias="conversationId",
    )

    current_message: str = Field(
        min_length=1,
        max_length=300,
    )

    recent_messages: list[ConversationTurn] = Field(
        default_factory=list,
        max_length=10,
    )

    summary: str | None = Field(
        default=None,
        max_length=2000,
    )
