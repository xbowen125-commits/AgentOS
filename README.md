# AgentOS Runtime Framework

AgentOS is a lightweight and extensible runtime framework for large language model agents.

The project focuses on the core runtime mechanisms required by maintainable agent systems,
including planning, state management, memory, tool calling, and model adapters.

## Project status

- Step 1: Architecture completed
- Step 2: Project skeleton
- Step 3: Minimal Agent Loop
- Step 4: Tool Runtime and JSON Memory
- Step 4.5: Runtime Architecture Hardening
- Step 5: Model Adapter Layer
- Step 6: MiniLLM-Serve Model Adapter
- Step 7: Runtime Observability Layer
- Step 8: End-to-End Agent Runtime Demo
- Step 9: Evaluation and Benchmark Layer
- Step 10: Runtime Performance Optimization
- Step 11: Spatial AI NPC Integration

## Architecture

```text
AgentOS Runtime
      |
Model Interface
      |
MiniLLM Adapter
      |
MiniLLM-Serve
```

AgentOS core depends only on the `Model` interface. `FakeModel` provides deterministic local
testing, while `MiniLLMModel` translates the same interface into MiniLLM-Serve HTTP requests.
MiniLLM-Serve is a replaceable inference backend and is not coupled to the Agent execution loop.

The current adapter targets `POST /generate` with a prompt and maximum token count. Tests use an
in-memory mock transport and do not require a running model server.

## Observability architecture

```text
Agent
  |
Runtime Events
  |
  +----------------+----------------+
  |                                 |
EventBus                       JsonTraceStore
  |                                 |
Sync/Async Handlers             JSON Traces
```

AgentOS emits structured lifecycle events for agent runs, planner/model boundaries, and tool
execution. Event handlers are isolated from the runtime control path, so a failing observer does
not interrupt the agent or prevent other handlers from running. `JsonTraceStore` can subscribe
directly to the event bus and persists events grouped by run ID without storing hidden reasoning.

The `Model` interface also supports asynchronous streaming. `FakeModel` and `MiniLLMModel`
preserve chunk order; the current MiniLLM implementation calls the non-streaming `/generate`
endpoint once and yields its response as character chunks. A true streaming transport can replace
this placeholder without changing AgentOS core.

## End-to-end demo

```text
User
  |
Agent
  |
ModelPlanner
  |
MiniLLMModel -> MiniLLM-Serve
  |
JSON Decision
  |
Calculator Tool
  |
Observation -> Final Answer
  |
JSON Trace
```

The calculator example demonstrates the complete runtime path without adding model or tool logic
to Agent core. Model connection settings come from `configs/default.json`.

Start MiniLLM-Serve, then run:

```powershell
python examples/calculator_agent.py
```

Enter `计算 123*456`. A compatible MiniLLM-Serve model first returns a structured calculator tool
decision and then a final answer based on the observation. AgentOS prints the answer and writes the
run events to `traces/run_<id>.json`. See `examples/README.md` for the expected decision flow.

## Evaluation

AgentOS includes a lightweight, trace-based evaluation layer with no external evaluation service.
It supports:

- versionable JSON benchmark cases;
- success-rate and failure-reason reporting;
- average latency, model-call, and tool-call metrics;
- metrics derived from existing runtime events and traces;
- deterministic offline runs and Markdown reports.

Run the bundled ten-case benchmark with:

```powershell
python -m benchmarks.evaluator
```

The command prints an `AgentOS Benchmark Report` and writes the same Markdown report under
`benchmarks/output/`. The bundled suite uses `FakeModel` for deterministic offline measurement;
`BenchmarkRunner` accepts a replaceable Agent factory for evaluating MiniLLM-backed runtimes.

## Performance

AgentOS provides performance controls and profiling without coupling them to Agent core:

- `RuntimeMetrics` derives total, planner, model, and tool latency from runtime traces;
- `CachedModel` decorates any model adapter with a replaceable response cache;
- `MemoryCache` provides a thread-safe process-local cache adapter;
- cache hit and miss events join the active run trace through `EventBus`;
- `TimeoutController` bounds asynchronous model or tool operations with AgentOS errors;
- performance aggregation reports average latency, P95 latency, call counts, and cache hit rate.

After generating benchmark traces, create a performance report with:

```powershell
python -m benchmarks.performance
```

The report is written to `benchmarks/output/performance.md`. Streaming calls continue to use the
wrapped model's native stream and are not buffered by `CachedModel`.

## Spatial AI NPC integration

AgentOS can serve as the reasoning backend for multimodal and spatial AI agents while keeping
engine-specific dependencies outside the runtime core:

```text
Vision / Speech / Unity
          |
  PerceptionEvent
          |
 InteractionAdapter
          |
    AgentOS Runtime
     /          \
NPC Memory    Planner -> Model
          |
      NPCAction
          |
        Unity
```

The adapter accepts structured events such as `player.wave`, `player.look`, and `player.speech`,
converts them into Agent inputs, and returns transport-neutral NPC actions. Runtime events include
`interaction.received`, `npc.action.generated`, and `memory.updated`.

NPC memory stores only a player ID, interaction count, last action, and bounded relationship level.
It does not store faces, raw images, audio, or biometric data.

Run the protocol-only bridge example with:

```powershell
python examples/npc_bridge_demo.py
```

The example simulates a Unity message and returns a JSON action without UDP, WebSocket, Unity SDK,
camera, microphone, OpenCV, or other game-engine dependencies.

