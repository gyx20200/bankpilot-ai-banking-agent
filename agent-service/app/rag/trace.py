"""D9 minimal, local, content-free JSONL trace.

No chat text, evidence snippets, answers, bearer tokens, OTPs or account ids.
Set BANKPILOT_RAG_TRACE_ENABLED=true to enable. The file remains under ignored data/.
"""
from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

DEFAULT_TRACE_FILE = Path(__file__).resolve().parents[2] / "data" / "traces" / "d9-rag.jsonl"
ALLOWED_STAGES = {"retrieval", "rerank", "generation", "verification", "completed"}
ALLOWED_KEYS = {"retrievedCount", "evidenceCount", "rerankMode", "grounded", "reasonCode"}


def new_trace_id() -> str:
    return uuid4().hex


def _write(event: dict) -> None:
    if os.getenv("BANKPILOT_RAG_TRACE_ENABLED", "false").strip().lower() != "true":
        return
    path = Path(os.getenv("BANKPILOT_RAG_TRACE_PATH", str(DEFAULT_TRACE_FILE))).resolve()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        # A single Uvicorn worker is expected in D9, as in D5-D8.
        with path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")
    except OSError:
        # Observability failure must not turn a read-only knowledge answer into a bank error.
        import logging
        logging.getLogger("bankpilot.rag.trace").warning("RAG_TRACE_WRITE_FAILED")


@contextmanager
def span(trace_id: str, stage: str, **metadata):
    if stage not in ALLOWED_STAGES:
        raise ValueError("unsupported trace stage")
    start = time.perf_counter()
    event = {"traceId": trace_id, "stage": stage}
    for key, value in metadata.items():
        if key in ALLOWED_KEYS and type(value) in {str, bool, int, float}:
            event[key] = value
    try:
        yield
    except Exception as exc:
        event["status"] = "ERROR"
        # Class name only; exception messages may contain private content.
        event["errorType"] = type(exc).__name__
        raise
    else:
        event["status"] = "OK"
    finally:
        event["durationMs"] = round((time.perf_counter() - start) * 1000, 2)
        _write(event)
