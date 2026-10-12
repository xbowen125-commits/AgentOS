# AgentOS Runtime

Lightweight modular LLM Agent Runtime with multimodal interaction support.

AgentOS implements the execution infrastructure behind maintainable agent systems: structured
planning, replaceable models, safe tools, memory ports, runtime events, traces, evaluation, and
external interaction adapters. The core is implemented directly in Python without using a complete
agent framework such as LangChain or AutoGen.

> Release candidate: v1.0.0 · Python 3.10+ · MIT License

## Features

- Bounded asynchronous Agent Loop with explicit state and structured decisions
- Strict JSON `ModelPlanner` protocol without free-form action parsing
- Replaceable `Model` interface with FakeModel and MiniLLM-Serve adapters
- Tool registry, failure-isolated executor, and safe AST calculator
- Versioned JSON memory behind a replaceable `MemoryStore` port
- Runtime EventBus, JSON execution traces, and latency profiling
- Streaming interface, response caching, and asynchronous timeout controls
- Deterministic evaluation cases and Markdown benchmark reports
- Engine-neutral perception, NPC action, and structured player-memory adapters
- Type annotations, unit tests, Ruff checks, and mypy validation

## Architecture

```text
Users / Unity / Spatial Inputs
             |
       Input Adapters
             |
     +-------v-------+
     | Agent Runtime |
     +-------+-------+
             |
      +------+------+----------------+
      |             |                |
   Planner       ToolExecutor     MemoryStore
      |             |                |
 Model Interface  ToolRegistry   JSON / NPC Memory
      |
 FakeModel / CachedModel / MiniLLMModel
      |
 MiniLLM-Serve

Agent Events -> EventBus -> JsonTraceStore -> Metrics / Benchmarks
```

Core modules depend on abstractions. HTTP, JSON files, caching, and spatial environments remain in
replaceable adapters. See [Architecture](docs/architecture.md) and
[Design Principles](docs/design_principles.md).

## Quick Start

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pytest
```

Verify the installed version:

```powershell
python -c "import agentos; print(agentos.__version__)"
```

For the MiniLLM calculator demo, configure `configs/default.json`, start MiniLLM-Serve, and run:

```powershell
python examples/calculator_agent.py
```

Detailed setup instructions are in [Getting Started](docs/getting_started.md).

## Examples

- `examples/calculator_agent.py` — MiniLLM-backed planning, calculator execution, final answer, and
  JSON trace.
- `examples/npc_bridge_demo.py` — minimal transport-neutral Unity message contract.
- `examples/spatial_agent_demo.py` — complete offline perception, interaction, memory, Agent, and
  NPC action flow.

The NPC examples require no Unity SDK, camera, microphone, OpenCV, UDP, or WebSocket service.

## Benchmark

Run the deterministic ten-case evaluation suite and performance report:

```powershell
python -m benchmarks.evaluator
python -m benchmarks.performance
```

The v1.0.0 preparation reference run completed all 10 cases successfully, averaging 2.00 model
calls and 1.00 tool call per case. Latency is machine-dependent; the local reference was
approximately 0.09 seconds per case. See [Benchmark Framework](docs/benchmark.md).

## Spatial AI NPC Integration

```text
Vision / Speech / Unity
          |
  PerceptionEvent
          |
 InteractionAdapter
          |
    AgentOS + LLM
          |
      NPCAction
          |
        Unity
```

AgentOS accepts structured interaction events such as `player.wave` and `player.speech`, converts
them into Agent inputs, and returns JSON-compatible actions. NPC memory stores only player ID,
interaction count, last action, and relationship level—never raw images, audio, faces, or biometric
data. See [NPC Integration](docs/npc_integration.md).

## Roadmap

- MiniLLM-Serve streaming transport
- Additional Tool and MemoryStore adapters
- Concurrency and load benchmark suites
- Versioned interaction protocol schemas
- Optional vector retrieval as an external adapter rather than a core dependency

## Documentation

- [Architecture](docs/architecture.md)
- [Getting Started](docs/getting_started.md)
- [Benchmark Framework](docs/benchmark.md)
- [Spatial AI NPC Integration](docs/npc_integration.md)
- [Design Principles](docs/design_principles.md)
- [Changelog](CHANGELOG.md)

## License

AgentOS Runtime is available under the [MIT License](LICENSE).
