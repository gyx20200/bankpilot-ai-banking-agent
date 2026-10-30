"""Validate an LLM-normalized schedule timestamp; never parse natural-language dates.

Natural-language understanding belongs to the planner LLM. This module only
checks an explicit, timezone-aware ISO 8601 value and the future-time constraint.
"""
import re
from datetime import datetime, timedelta, timezone

CN = timezone(timedelta(hours=8))

# Require an explicit +08:00 offset and seconds (optional), rather than accepting
# naive local time, a date-only string, or a time zone inferred by the server.
_ISO_LOCAL = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?\+08:00\Z")


def validate_schedule_time(execute_at: str | None, now: datetime | None = None) -> str | None:
    """Return canonical YYYY-MM-DDTHH:MM:SS+08:00 or None.

    This deliberately does not interpret words such as '明天' or '下周五'.
    The bank and user must still confirm the exact timestamp before OTP.
    """
    if not isinstance(execute_at, str) or not _ISO_LOCAL.fullmatch(execute_at):
        return None
    try:
        target = datetime.fromisoformat(execute_at)
        current = (now or datetime.now(CN)).astimezone(CN)
    except (ValueError, OverflowError, TypeError):
        return None
    if target <= current:
        return None
    return target.isoformat(timespec="seconds")
