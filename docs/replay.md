# Trace Replay and Debugging

`TraceReplay` reconstructs observable execution steps from existing JSON traces. It never invokes
a model, planner, or tool and never rewrites a trace. This is an execution-history debugger, not a
second Agent loop or re-execution of side effects.

## Load by run ID or file

```python
from pathlib import Path

from agentos.replay import TraceReplay
from agentos.tracing import JsonTraceStore

replay = TraceReplay(JsonTraceStore("traces"))
result = replay.replay(run_id)
print(result.render_text())

exported = TraceReplay().replay(Path("exported_trace.json"))
print(exported.summary.to_dict())
```

Portable files follow the existing JsonTraceStore format: a `run_id` plus an `events` array.
The replay reader reuses AgentEvent validation and rejects invalid JSON or cross-run events.
Run IDs are strings; paths may be Path objects or JSON-file strings. Pass a TraceRecord directly
to inspect in-memory events.

CLI examples from the repository root:

```powershell
python examples/replay_trace.py --run-id YOUR_RUN_ID --trace-dir traces/real_backend
python examples/replay_trace.py --trace traces/evaluation/run_HASH.json
```

## Public steps and missing content

`result.events` retains every original event in persisted order. `result.steps` presents model
calls, planner decisions, tool executions, observations, final answers, and failures. Runtime and
validation aliases such as planner.finished/planner.decision and agent.finished/agent.completed
are collapsed in the logical steps, without discarding the original event timeline.

The default runtime trace omits decision arguments, Observation results, and final answer content.
Replay marks missing content with `content_available=false` and `final_result=None`. It does not
infer an answer from the expected result, tool name, or a successful status flag.

To inspect the complete public history while the original state is still available:

```python
result = replay.replay(state.run_id, state=state, expected_result="56088")
```

AgentState must belong to the same run. Enrichment checks available trace metadata for conflicts.
It never includes `state.user_input` or model prompts. An actual answer can also be explicitly
supplied with `actual_answer="56088"`; its correctness is scored only when expected_result is
provided. Existing traces that explicitly record a public final_answer can be read as well.

Enriched replay output can contain tool arguments and public results. It is returned to the caller
and is not automatically persisted.

## RunSummary

- `latency`: existing RuntimeMetrics total latency through the evaluation layer
- `model_calls`: Agent model.called attempts plus planner.retry.started repairs
- `tool_calls`: tool.called events, including failed attempts
- `retry_count`: number of planner.retry.started events
- `validation_failure`: observed parser/decision failure, including recovered failures
- `final_result`: supplied or explicitly recorded public answer, otherwise None
- `status`: completed, failed, or incomplete
- `tool_failures`, `issues`, and the existing EvaluationMetrics for further analysis

For a standalone native stream without Agent model.called events, stream.started supplies the
model-call count. A model stream finishing does not imply the Agent task finished. A failed tool
that is later recovered does not mark the whole run failed. Agent/workflow failures and step-limit
completion flags are distinguished from successful completion.

Counters describe recorded attempts. Recovered failures cannot be discovered when the original
Planner was not connected to its runtime EventBus. No expected answer means task correctness is
unassessed; debug summaries do not turn completion into a fabricated task-success score.
