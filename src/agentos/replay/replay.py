"""Load and replay observable execution steps without executing any runtime code."""

import json
from copy import deepcopy
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from agentos.core.decision import FinalAnswerDecision, ToolCallDecision
from agentos.core.observation import Observation
from agentos.core.state import AgentState
from agentos.evaluation import ExpectedResult
from agentos.events import AgentEvent
from agentos.exceptions import TraceFormatError, TraceNotFoundError, TraceStoreError
from agentos.replay.summary import RunSummary
from agentos.tracing import JsonTraceStore, TraceRecord


@dataclass(frozen=True)
class ReplayStep:
    kind: str
    event_type: str
    timestamp: str
    step_number: int | None
    details: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ReplayResult:
    run_id: str
    events: tuple[AgentEvent, ...]
    steps: tuple[ReplayStep, ...]
    summary: RunSummary

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def render_text(self) -> str:
        lines = [f"Run: {self.run_id}", f"Status: {self.summary.status}"]
        for step in self.steps:
            number = "?" if step.step_number is None else str(step.step_number)
            lines.append(
                f"[{number}] {step.kind}: {json.dumps(step.details, ensure_ascii=False)}"
            )
        lines.extend([
            f"Latency: {self.summary.latency:.4f}s",
            (
                f"Model Calls: {self.summary.model_calls}; Tool Calls: {self.summary.tool_calls}; "
                f"Retries: {self.summary.retry_count}"
            ),
            f"Final Result: {self.summary.final_result if self.summary.final_result is not None else 'unavailable'}",
        ])
        return "\n".join(lines)


class TraceReplay:
    """Inspect traces by store run ID, portable JSON path, or TraceRecord.

    Events retain persisted order. Optional same-run AgentState enriches content
    deliberately omitted from traces. No model, planner, or tool is invoked.
    """

    def __init__(self, trace_store: JsonTraceStore | None = None) -> None:
        self.trace_store = trace_store

    def replay(
        self,
        source: str | Path | TraceRecord,
        *,
        state: AgentState | None = None,
        actual_answer: str | None = None,
        expected_result: ExpectedResult | str | None = None,
    ) -> ReplayResult:
        trace = self._load(source)
        if state is not None and state.run_id != trace.run_id:
            raise ValueError("AgentState must belong to the replayed run")
        decisions: dict[int, ToolCallDecision | FinalAnswerDecision] = {}
        observations: dict[int, Observation] = {}
        if state is not None:
            history_number = 0
            for index, item in enumerate(state.history):
                if isinstance(item, (ToolCallDecision, FinalAnswerDecision)):
                    history_number += 1
                    decisions[history_number] = item
                    if isinstance(item, ToolCallDecision) and index + 1 < len(state.history):
                        observed = state.history[index + 1]
                        if isinstance(observed, Observation):
                            observations[history_number] = observed
            answers = [item.answer for item in decisions.values() if isinstance(item, FinalAnswerDecision)]
            if answers:
                if actual_answer is not None and actual_answer != answers[-1]:
                    raise ValueError("Supplied answer conflicts with AgentState")
                actual_answer = answers[-1]
        summary = RunSummary.from_trace(
            trace, actual_answer=actual_answer, expected_result=expected_result
        )
        steps: list[ReplayStep] = []
        planner_steps: set[int] = set()
        final_seen = False
        current_step: int | None = None
        has_model_calls = any(event.event_type == "model.called" for event in trace.events)
        for event in trace.events:
            number = event.payload.get("step")
            number = number if isinstance(number, int) and not isinstance(number, bool) else None
            if event.event_type == "planner.started":
                current_step = number
            details = deepcopy(event.payload)
            kind = None
            if event.event_type in ("planner.finished", "planner.decision"):
                if number is not None and number in planner_steps:
                    continue
                if number is not None:
                    planner_steps.add(number)
                kind = "planner_decision"
                decision = decisions.get(number) if number is not None else None
                if decision is not None:
                    recorded_type = details.get("decision_type")
                    if recorded_type is not None and recorded_type != type(decision).__name__:
                        raise ValueError("AgentState decision type conflicts with trace")
                    details["decision"] = {
                        "type": "tool_call" if isinstance(decision, ToolCallDecision) else "final",
                        **asdict(decision),
                    }
                    details["content_available"] = True
                else:
                    details["content_available"] = isinstance(details.get("decision"), dict)
            elif event.event_type == "model.called" or (
                event.event_type == "stream.started" and not has_model_calls
            ):
                kind = "model_call"
            elif event.event_type == "planner.retry.started":
                kind = "model_call"
                number = current_step
                details["retry"] = True
            elif event.event_type == "tool.called":
                kind = "tool_execution"
                decision = decisions.get(number) if number is not None else None
                if isinstance(decision, ToolCallDecision):
                    if details.get("tool_name") != decision.tool_name:
                        raise ValueError("AgentState tool name conflicts with trace")
                    if "arguments" in details and details["arguments"] != decision.arguments:
                        raise ValueError("AgentState arguments conflict with trace")
                    details["arguments"] = deepcopy(decision.arguments)
                details["content_available"] = "arguments" in details
            elif event.event_type == "tool.finished":
                kind = "observation"
                observation = observations.get(number) if number is not None else None
                if observation is not None:
                    if "success" in details and details["success"] != observation.success:
                        raise ValueError("AgentState observation status conflicts with trace")
                    if "result" in details and details["result"] != observation.result:
                        raise ValueError("AgentState observation result conflicts with trace")
                    details.update(observation.to_dict())
                details["content_available"] = "result" in details
            elif event.event_type in ("agent.finished", "agent.completed", "workflow.completed"):
                is_finished = event.event_type == "workflow.completed" or details.get("finished") is True
                if not is_finished or final_seen:
                    continue
                final_seen = True
                kind = "final_answer"
                number = details.get("step_count", current_step)
                number = number if isinstance(number, int) and not isinstance(number, bool) else None
                details["answer"] = summary.final_result
                details["content_available"] = summary.final_result is not None
            elif event.event_type in ("agent.failed", "workflow.failed", "planner.retry.failed"):
                kind = "failure"
                number = number if number is not None else current_step
            if kind is not None:
                steps.append(ReplayStep(kind, event.event_type, event.timestamp, number, details))
        return ReplayResult(trace.run_id, tuple(trace.events), tuple(steps), summary)

    def _load(self, source: str | Path | TraceRecord) -> TraceRecord:
        if isinstance(source, TraceRecord):
            return deepcopy(source)
        if isinstance(source, Path) or source.endswith(".json") or Path(source).is_file():
            return self._load_file(Path(source))
        if self.trace_store is None:
            raise ValueError("A JsonTraceStore is required to replay by run_id")
        return self.trace_store.load(source)

    @staticmethod
    def _load_file(path: Path) -> TraceRecord:
        try:
            with path.open(encoding="utf-8") as trace_file:
                document: Any = json.load(trace_file)
        except FileNotFoundError:
            raise TraceNotFoundError(f"Trace file not found: {path}") from None
        except OSError:
            raise TraceStoreError(f"Unable to read trace file: {path}") from None
        except ValueError:
            raise TraceFormatError("Trace file contains invalid JSON") from None
        if not isinstance(document, dict):
            raise TraceFormatError("Trace document must be a JSON object")
        run_id = document.get("run_id")
        events = document.get("events")
        if not isinstance(run_id, str) or not run_id or not isinstance(events, list):
            raise TraceFormatError("Trace must contain run_id and events")
        trace = TraceRecord(run_id)
        for raw in events:
            if not isinstance(raw, dict) or raw.get("run_id", run_id) != run_id:
                raise TraceFormatError("Trace event must belong to the document run")
            try:
                trace.append(AgentEvent.from_dict(raw, run_id=run_id))
            except (KeyError, TypeError, ValueError):
                raise TraceFormatError("Trace file contains an invalid event") from None
        return trace
