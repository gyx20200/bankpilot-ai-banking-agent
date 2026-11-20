"""D5 FastAPI lifespan: own the AsyncSqliteSaver for the entire server lifetime.

In tests and the legacy mode, the existing compiled InMemory graph is retained.
Persistent mode fails at startup when SQLite cannot be opened; no silent fallback.
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

logger = logging.getLogger('bankpilot.checkpoints')


def checkpoint_mode() -> str:
    mode = os.getenv('BANKPILOT_CHECKPOINT_MODE', 'memory').strip().lower()
    if mode not in {'memory', 'sqlite'}:
        raise RuntimeError('BANKPILOT_CHECKPOINT_MODE must be memory or sqlite')
    return mode


def persistent_enabled() -> bool:
    return checkpoint_mode() == 'sqlite'


@asynccontextmanager
async def checkpoint_lifespan(app):
    import app.workflow_api as workflow_api
    from app.graph.dynamic_cancellation_workflow import build_dynamic_graph

    if checkpoint_mode() == 'memory':
        app.state.checkpoint_mode = 'memory'
        yield
        return

    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

    default_path = Path(__file__).resolve().parents[1] / 'data' / 'checkpoints.sqlite'
    path = Path(os.getenv('BANKPILOT_CHECKPOINT_PATH', str(default_path))).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)

    original = workflow_api.dynamic_graph
    # In a new process these will naturally be empty. Explicitly clear on lifespan
    # re-entry (e.g. TestClient restarts) to prohibit stale approvals.
    workflow_api._sessions.clear()
    workflow_api._locks.clear()
    try:
        async with AsyncSqliteSaver.from_conn_string(str(path)) as saver:
            # A harmless read initializes the SQLite schema and fails fast.
            # AsyncSqliteSaver.setup() is invoked internally on first use.
            await saver.aget_tuple({'configurable': {'thread_id': '_bankpilot_d5_startup_probe_'}})
            workflow_api.dynamic_graph = build_dynamic_graph(saver)
            app.state.checkpoint_mode = 'sqlite'
            logger.info('LangGraph persistent checkpoint initialized')
            try:
                yield
            finally:
                workflow_api.dynamic_graph = original
                workflow_api._sessions.clear()
                workflow_api._locks.clear()
                app.state.checkpoint_mode = 'stopped'
    except Exception:
        workflow_api.dynamic_graph = original
        app.state.checkpoint_mode = 'unavailable'
        logger.exception('Could not initialize or close LangGraph SQLite checkpoint')
        raise
