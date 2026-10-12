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
