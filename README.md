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

