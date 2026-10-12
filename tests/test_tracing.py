"""Tests for JSON execution trace persistence."""

import json
from pathlib import Path

from agentos.events import AgentEvent
from agentos.tracing import JsonTraceStore, TraceRecord


def test_trace_record_rejects_another_run() -> None:
    trace = TraceRecord(run_id="run-1")

    try:
        trace.append(AgentEvent.create("agent.started", "run-2"))
    except ValueError as error:
        assert "does not match" in str(error)
    else:
        raise AssertionError("TraceRecord accepted an event from another run")


def test_trace_save_writes_expected_json_and_loads(tmp_path: Path) -> None:
    store = JsonTraceStore(tmp_path)
    event = AgentEvent.create("model.called", "run-1", {"step": 1})
    store.save(TraceRecord(run_id="run-1", events=[event]))

    document = json.loads(next(tmp_path.glob("*.json")).read_text(encoding="utf-8"))
    loaded = store.load("run-1")

    assert document == {
        "run_id": "run-1",
        "events": [
            {
                "event_type": "model.called",
                "timestamp": event.timestamp,
                "payload": {"step": 1},
            }
        ],
    }
    assert loaded == TraceRecord(run_id="run-1", events=[event])


def test_trace_store_append_creates_and_extends_trace(tmp_path: Path) -> None:
    store = JsonTraceStore(tmp_path)
    first = AgentEvent.create("agent.started", "run-1")
    second = AgentEvent.create("agent.finished", "run-1", {"finished": True})

    store.append(first)
    store.append(second)

    assert store.load("run-1").events == [first, second]
