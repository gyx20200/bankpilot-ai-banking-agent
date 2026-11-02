"""Shared import setup for BankPilot's Python tests (no network calls)."""
import sys
from pathlib import Path

AGENT_ROOT = Path(__file__).resolve().parent.parent / "agent-service"
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))
