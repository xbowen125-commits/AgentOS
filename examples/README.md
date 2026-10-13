# Calculator Agent Demo

This example assembles the complete AgentOS runtime around the MiniLLM-Serve adapter. It exercises
strict JSON planning, calculator tool execution, the follow-up model decision, and JSON tracing.

## Prerequisites

1. Install AgentOS with its development dependencies.
2. Start MiniLLM-Serve at the URL configured in `configs/default.json`.
3. Ensure the model returns one of the JSON decision formats documented by `ModelPlanner`.

## Run

```powershell
python examples/calculator_agent.py
```

Enter:

```text
计算 123*456
```

For this task, MiniLLM-Serve should first return a calculator tool call and then use the recorded
observation to return a final decision. The expected answer is:

```text
Final Answer:

56088
```

Each run writes its lifecycle events to `traces/run_<id>.json`. Local trace and memory files are
ignored by Git.

## Real MiniLLM-Serve Validation

Copy `configs/mini_llm.example.json` to the ignored `configs/mini_llm.json`, start MiniLLM-Serve
separately, and run:

```powershell
python examples/real_mini_llm_agent.py
```

See `docs/real_backend.md` for the HTTP contract, trace guarantees, and troubleshooting.

## Native SSE Calculator Demo

With the same local MiniLLM configuration and running server:

```powershell
python examples/real_mini_llm_stream.py
```

This demo prints native streaming chunks while the existing Agent performs planning, calculator
execution, and observation-grounded final answering. See `docs/streaming.md` for lifecycle events.

## Multi Tool Workflow Demo

Run the deterministic offline calculator-to-formatter workflow:

```powershell
python examples/multi_tool_workflow.py
```

The runtime automatically injects both registered tool contracts and records each tool attempt
and workflow event. This example uses FakeModel and requires no serving backend. See
`docs/workflow.md` for composition, failure recovery, and limits.
