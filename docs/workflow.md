# Multi Tool Workflow Runtime

`Workflow` assembles the existing Agent, ModelPlanner, ToolRegistry, and ToolExecutor into an
observable sequence of tool attempts. Agent.run remains the only execution loop.

```text
User -> Planner -> Tool A -> Observation -> Planner -> Tool B -> Observation -> Final
         ^                                  ^
         |                                  |
         +------ all registry tool contracts ------+

Agent lifecycle/tool events -> Workflow events -> EventBus -> Trace subscribers
```

## Automatic tool contracts

`describe_tool(tool)` generates `name`, `description`, and `input_schema`. Tool names come from
the tool's existing `name`. Descriptions use an explicit `description` attribute or the tool
docstring. Schema generation uses the typed execute signature unless the tool declares an
explicit `input_schema`.

For example, `async execute(value: str)` becomes an object schema with a required string `value`
property. Tools implemented through unrestricted `**kwargs` should declare an explicit schema
when they have required arguments. Calculator declares its actual `expression` contract.

The schema generator supports common JSON-compatible annotations. Unsupported annotations must
be replaced with an explicit schema using the subset supported by DecisionValidator. No third
party schema or workflow framework is required.

`ModelPlanner.from_registry(model, registry)` injects every registered tool's description and
schema into the prompt and the existing validator. `Workflow` uses this factory automatically.
Contracts are snapshotted at construction; create a new Workflow after adding tools.

## Running a workflow

```python
from agentos.workflow import Workflow

workflow = Workflow(
    model=model,
    registry=registry,
    memory=memory,
    event_bus=event_bus,
    max_steps=10,
    max_retries=2,
)
result = await workflow.run("Use the first tool's result as input to the second tool.")
print(result.answer)
for step in result.steps:
    print(step.index, step.decision.tool_name, step.observation.success)
```

The model chooses the next tool using the public history. Each completed tool attempt appears as
a `WorkflowStep` containing a decision and an observation. Arguments/results are not substituted
by a second executor or a separate workflow language. Optional `required_tool` retains the
existing guardrail requiring a final answer grounded in the selected tool's latest success.

Run the deterministic offline example:

```powershell
python examples/multi_tool_workflow.py
```

Expected output:

```text
Step 1: calculator -> 56088
Step 2: format_result -> Result: 56088
Final: Result: 56088
```

## Recovery and limits

A tool failure remains a failed Observation, available to the Planner on its next decision.
The Planner can correct the call or select another declared tool. Failed attempts remain in
`result.steps`; later success does not erase them. Invalid model decisions use the existing bounded
planner retry controller. Model/Planner exceptions still propagate to the caller.

Reaching max_steps produces an unfinished result and `workflow.failed` with reason `step_limit`.
A failed tool attempt followed by successful recovery can still finish the workflow normally.
There is no automatic retry of a side-effecting tool outside Planner decisions.

## Events and traces

- `workflow.started`
- `workflow.step.started`
- `workflow.step.completed` or `workflow.step.failed`
- `workflow.completed` or `workflow.failed`

Workflow events reuse the Agent run ID. Payloads contain step numbers, tool names, status, and
error types, without raw prompts, arguments, results, or user input. Subscribe JsonTraceStore to
the same EventBus to retain the original Agent events and workflow lifecycle events together.
Handler failures remain isolated from execution. Workflow event subscriptions filter unrelated
run IDs, including when multiple Workflow instances share an EventBus.

Execution state is run-local. Concurrent calls still require thread/task-safe model and tool
adapters; a stateful FakeModel response sequence is intended for isolated tests.
