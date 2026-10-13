# Agent Evaluation Layer

The evaluation layer compares public results with execution evidence. It reuses EventBus,
JsonTraceStore, RuntimeMetrics, and the existing benchmark case format without changing Agent
execution or tool behavior.

## Scoring a run

```python
from agentos.evaluation import Evaluator, ExpectedResult, write_markdown_report

evaluator = Evaluator(trace_store)
result = evaluator.evaluate_run(
    state.run_id,
    ExpectedResult(answer="56088", tool_names=("calculator",)),
    actual_answer=final_answer,
)
write_markdown_report([result], "evaluation_report.md")
```

Alternatively, call `evaluate(trace, expected_result, actual_answer=...)` with a TraceRecord.
`evaluate_case(trace, case, ...)` accepts existing BenchmarkCase objects through a structural
interface, so the installed evaluation package does not import the repository benchmark module.

Traces do not persist final answers. Supply the actual public answer returned by Agent/Workflow;
if a completed run has no answer evidence, its task success is N/A. Expected tool sequences are
also explicit: omitted expectations are N/A, while an empty sequence means no tool calls expected.
No answer is invented or reconstructed from metadata.

To collect new traces, create Evaluator with a JsonTraceStore and call `subscribe(event_bus)` once,
only if that store is not already subscribed to the bus. Reading saved traces needs no subscription.

## Metrics

| Metric | Definition |
| --- | --- |
| task_success_rate | Completed, non-failed runs with exact answer matches / assessed tasks |
| tool_selection_accuracy | Matching ordered positions / max(actual, expected) slots, aggregated |
| workflow_completion_rate | Completed workflows / runs containing workflow events |
| average_latency | Mean RuntimeMetrics.total_latency across all evaluated runs |
| retry_rate | Runs containing planner.retry.started / all runs |
| validation_failure_rate | Runs with validation failure evidence / all runs |

Coverage counts are included with every aggregate. Unobserved/inapplicable rates are N/A, not
zero; an empty evaluation has zero latency and zero retry/failure rates. If all assessed tool
sequences are empty and no tools were called, tool selection accuracy is 100%.

Validation evidence includes a planner retry starting after PlannerOutputError, explicit
planner.validation.failed events when supplied, or a terminal agent.failed of type
PlannerOutputError. A recovered validation failure still counts toward validation_failure_rate.
The existing events cannot distinguish JSON parsing failures from semantic decision failures, so
this rate intentionally covers both. Tool execution failures are tracked separately.

Retry/validation rates measure observed events. Pass the runtime EventBus into ModelPlanner to
record recovered failures; traces collected without that wiring cannot reveal hidden repairs.

A failed tool attempt can still lead to a successful task after recovery. An unfinished Agent
at its step limit is not successful merely because agent.finished was emitted. Workflow and Agent
lifecycle aliases do not double-count runs or tool calls; only tool.called defines tool selections.

## Benchmark report

Run the committed deterministic cases from the repository root:

```powershell
python -m examples.evaluate_agent
```

This writes `outputs/evaluation_report.md` and metadata-only traces to `traces/evaluation/`.
Reference decisions in the offline case fixtures supply expected tool sequences. The report
describes that deterministic setup, rather than real model quality. These cases are single-Agent
runs, so workflow completion is correctly shown as N/A. Evaluate Workflow traces through the
same API to obtain the workflow metric.

Markdown reports include run/case IDs, rates, counts, latency, and categorical issues. They omit
prompts, user input, actual/expected answer content, and raw exception messages.
