# AgentOS Architecture

AgentOS is a lightweight runtime for executing structured LLM agent decisions. The core coordinates
planning, tools, state, and memory through interfaces; adapters connect models, persistence, and
external interaction environments.

## System overview

```text
                         External Inputs
                    User / Unity / Spatial NPC
                               |
                     Interaction Adapters
                               |
                        +-------------+
                        |    Agent    |
                        | Runtime Loop|
                        +------+------+
                               |
                  +------------+------------+
                  |                         |
              Planner                  MemoryStore
                  |                         |
             Model Interface            Adapters
                  |                   JSON / future DB
        +---------+----------+
        |                    |
    FakeModel        MiniLLMModel / CachedModel
                             |
                       MiniLLM-Serve

Agent -> Decision -> ToolExecutor -> ToolRegistry -> Tool -> Observation
  |
  +-> EventBus -> Handlers / JsonTraceStore -> Runtime Metrics / Evaluation
```

## Core runtime

`Agent.run()` owns one execution state and repeats a small protocol:

1. Ask the `Planner` for a structured decision.
2. Record the decision in `AgentState`.
3. Finish on `FinalAnswerDecision`, or execute `ToolCallDecision` through `ToolExecutor`.
4. Record the resulting `Observation` and continue until completion or the step limit.

The loop depends on planner, tool-executor, and memory ports. It does not know about HTTP, Unity,
JSON files, cameras, or model vendors.

## Planner and model boundary

`ModelPlanner` builds a public prompt from user input and public execution history. It accepts only
the JSON decision protocol. Models implement the asynchronous `Model` interface:

- `FakeModel` supplies deterministic responses for tests and offline benchmarks.
- `MiniLLMModel` translates generation calls to MiniLLM-Serve HTTP requests.
- `CachedModel` decorates another model without changing the planner.

## Tool runtime

Tools implement a small execution interface. `ToolRegistry` enforces unique names and
`ToolExecutor` converts lookup, validation, and execution failures into serializable observations.
The built-in calculator uses an AST whitelist and resource limits; it does not use `eval`.

## Memory runtime

`MemoryStore` is the persistence port. `JsonMemory` is the local versioned adapter and can be
replaced without changing consumers. `NPCMemory` stores only approved structured player state.

## Observability

`EventBus` is a failure-isolated side channel. Agent execution continues if an event handler or
trace writer fails. `JsonTraceStore` groups serializable events by run ID. Runtime metrics derive
latency, call counts, cache efficiency, and failures from traces rather than from hidden reasoning.

## Evaluation

The benchmark layer runs versioned cases through the public Agent API. It computes success rate,
latency, model calls, tool calls, and failure reasons, then renders Markdown reports. The same
runner can use deterministic fake models or an Agent factory backed by MiniLLM-Serve.
