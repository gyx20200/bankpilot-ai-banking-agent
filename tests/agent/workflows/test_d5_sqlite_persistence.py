"""Checkpoint round-trip across two independent database connection lifetimes."""
import asyncio

import pytest

pytest.importorskip('langgraph.checkpoint.sqlite.aio')

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import StateGraph, START, END
from langgraph.types import Command, interrupt
from typing import TypedDict


class State(TypedDict, total=False):
    value: int
    approved: bool


def wait_for_user(state):
    decision = interrupt({'message': 'only a harmless toy graph'})
    return {'approved': decision}


def build(saver):
    g=StateGraph(State)
    g.add_node('wait',wait_for_user)
    g.add_edge(START,'wait')
    g.add_edge('wait',END)
    return g.compile(checkpointer=saver)


async def cycle(path):
    config={'configurable':{'thread_id':'d5-isolated-test'}}
    async with AsyncSqliteSaver.from_conn_string(str(path)) as saver:
        graph=build(saver)
        output=await graph.ainvoke({'value':9},config,durability='sync')
        assert output.get('__interrupt__')
        before=await graph.aget_state(config)
        assert before.values['value']==9
        assert 'wait' in before.next

    # Entire saver connection closed, new graph object and new connection.
    async with AsyncSqliteSaver.from_conn_string(str(path)) as saver:
        graph=build(saver)
        recovered=await graph.aget_state(config)
        assert recovered.values['value']==9
        assert recovered.next == ('wait',)
        # ONLY the isolated no-bank test graph is resumed in D5.
        result=await graph.ainvoke(Command(resume=True),config,durability='sync')
        assert result['approved'] is True


def test_sqlite_persists_after_reopen(tmp_path):
    asyncio.run(cycle(tmp_path/'checkpoints.sqlite'))
