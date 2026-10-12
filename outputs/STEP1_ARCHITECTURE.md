# AgentOS — MVP Architecture Baseline

Status: Step 1 design baseline  
Target: Python 3.11+  
Scope: Agent loop, memory, tools, state, and model abstraction

## 1. Product boundary

AgentOS is an orchestration runtime. It owns the agent execution lifecycle and the contracts between planning, models, memory, and tools. It does not own model inference, multimodal preprocessing, or a UI.

In the future stack:

```text
User / Spatial AI NPC
        |
 normalized text and multimodal references
        v
AgentOS Runtime
  |             |
  v             v
MiniLLM-Serve   Tool adapters
  |
  v
Local model
```

The MVP accepts text input. Multimodal payloads and NPC actions are future typed message and tool extensions, not special cases inside the loop.

## 2. Architecture decisions

### AD-001: Ports and adapters

Core runtime code depends on protocols or abstract base classes, never concrete model vendors, storage engines, or tools. JSON memory and a local/HTTP model implementation are adapters behind stable interfaces.

### AD-002: Bounded state-machine loop

`Agent.run()` is a bounded state machine, not an unconstrained `while True`. Each iteration produces exactly one typed decision: execute a tool or return a final answer. A configurable step limit and explicit terminal states prevent runaway agents.

### AD-003: Structured planner output

The planner converts model output into a typed `AgentDecision`. The runtime never searches arbitrary prose for tool calls. MVP transport can use JSON, validated at the boundary. Malformed output becomes a controlled planner error, with at most a configured repair attempt.

### AD-004: Runtime state is separate from durable memory

`AgentState` is run-scoped and represents execution progress. `MemoryManager` exposes conversational and durable memory. State may reference retrieved memory IDs but does not embed the storage implementation.

### AD-005: Async-first public runtime

The primary API is `async Agent.run(...)`. Model calls and future tools are I/O-heavy, so async avoids a later breaking redesign. Small synchronous tools can execute through the same async tool contract. A synchronous convenience wrapper may be added later.

### AD-006: Do not persist hidden chain-of-thought

History records decisions, tool arguments, observations, errors, timing, and optional short public rationale. It does not require or persist private model reasoning. This keeps logs safer and the model contract portable.

## 3. Proposed repository layout

The package uses a `src` layout to prevent tests from accidentally importing the working directory instead of the installed package.

```text
AgentOS/
├── pyproject.toml
├── README.md
├── LICENSE
├── src/
│   └── agentos/
│       ├── __init__.py
│       ├── agent/
│       │   ├── agent.py
│       │   ├── planner.py
│       │   ├── state.py
│       │   └── types.py
│       ├── memory/
│       │   ├── memory_item.py
│       │   ├── memory_store.py
│       │   ├── memory_manager.py
│       │   └── json_store.py
│       ├── tools/
│       │   ├── base.py
│       │   ├── registry.py
│       │   ├── calculator.py
│       │   ├── file_reader.py
│       │   └── time_tool.py
│       ├── models/
│       │   ├── base.py
│       │   ├── types.py
│       │   └── local_model.py
│       ├── prompts/
│       │   └── planner.py
│       └── errors.py
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fakes/
└── examples/
    └── basic_agent.py
```

The user-proposed modules remain recognizable, while concrete adapters (`json_store.py`, `local_model.py`) are separated from their interfaces.

## 4. Core contracts

The names below define responsibilities, not final implementation details.

### Agent

```text
Agent.run(user_input, session_id, context?) -> AgentResult
```

Responsibilities:

1. Create a run-scoped `AgentState`.
2. Load relevant short- and long-term memory through `MemoryManager`.
3. Ask `Planner` for the next typed decision.
4. Validate and execute tool decisions through `ToolRegistry`.
5. append an `ActionRecord` and observation to state.
6. Stop on a final response, cancellation, fatal error, or step limit.
7. Persist conversation events selected by the memory policy.

The `Agent` coordinates components; it does not build vendor-specific requests, read JSON files directly, or implement individual tools.

### Planner

```text
Planner.plan(state, available_tools, memories) -> AgentDecision
```

Decision union:

- `ToolCallDecision(tool_name, arguments, rationale?)`
- `FinalAnswerDecision(content)`

The planner owns prompt construction, model invocation, response validation, and optional one-shot format repair. It does not execute tools.

### AgentState

Suggested fields:

- `run_id`, `session_id`
- `status`: created / planning / executing / completed / failed / exhausted / cancelled
- `current_task`
- `messages`
- `actions: list[ActionRecord]`
- `current_observation`
- `memory_refs`
- `step_count`, `max_steps`
- timestamps and structured error information

State transitions are explicit and validated. An action record is append-only so a run can be inspected and reproduced.

### Model adapter

```text
BaseModel.generate(request) -> ModelResponse
BaseModel.chat(messages, options?) -> ModelResponse
```

`ModelResponse` normalizes text, finish reason, usage metadata, model identity, and raw provider metadata. Provider-specific payloads stay inside adapters. The first HTTP adapter should target MiniLLM-Serve through configuration (`base_url`, model, timeout), without coupling AgentOS to its final API shape.

Streaming, retries, authentication, and OpenAI/HuggingFace adapters are later extensions of this boundary.

### Tool

```text
Tool.name
Tool.description
Tool.input_schema
Tool.execute(arguments, context) -> ToolResult
```

`ToolResult` distinguishes success, output, and structured error. Tools do not raise ordinary user/input failures across the runtime boundary. `ToolRegistry` rejects duplicate names, exposes model-facing schemas, validates arguments, and resolves execution by exact name.

Initial tool safety rules:

- Calculator: parse an allow-listed arithmetic AST; never use unrestricted `eval`.
- File reader: resolve paths and enforce configured allowed roots, file-size limits, and text encodings.
- Time: return timezone-aware ISO 8601 values and accept explicit IANA timezone names.

### Memory

```text
MemoryStore.put(item)
MemoryStore.get(item_id)
MemoryStore.list(query)
MemoryStore.delete(item_id)

MemoryManager.add_message(...)
MemoryManager.remember(...)
MemoryManager.get_context(...)
```

`MemoryStore` is persistence. `MemoryManager` is policy and context assembly.

`MemoryItem` should include:

- stable ID
- type: conversation / user_profile / event / preference
- content and optional structured metadata
- session/user scope
- creation/update timestamps
- importance and tags

For MVP, short-term memory is the current session's bounded message history. Long-term memory is explicitly written user information, events, and preferences. Automatic semantic extraction is out of scope until the basic contracts are stable.

The JSON adapter uses a versioned document format, atomic replace-on-write, deterministic serialization, and injectable storage path. A process-local lock is sufficient for MVP; multi-process concurrency belongs to the SQLite phase.

## 5. Runtime flow

```text
receive input
    |
create state and append user message
    |
load memory context
    |
planner.plan
    |
    +-- final answer ----------------------+
    |                                      |
    +-- tool call -> validate -> execute   |
                         |                 |
                  append observation       |
                         |                 |
                  step limit reached?      |
                    no /       \ yes       |
                    loop       exhausted   |
                                       \   |
                                        AgentResult
```

`AgentResult` returns final content, terminal status, run ID, action records, and optional error metadata. Callers such as Spatial AI NPC can later consume typed action events instead of scraping response text.

## 6. Error model

Define a small exception hierarchy for programming or infrastructure failures:

- `AgentOSError`
- `ConfigurationError`
- `ModelError` and `ModelTimeoutError`
- `PlannerOutputError`
- `ToolNotFoundError`, `ToolValidationError`, `ToolExecutionError`
- `MemoryError`
- `StepLimitExceededError`

Expected tool-input problems become `ToolResult` observations so the planner may recover. Configuration corruption, unavailable storage, and exhausted retry budgets terminate the run with a typed status.

## 7. Configuration and dependency composition

Use constructor injection for core dependencies:

```text
Agent(planner, memory_manager, tool_registry, runtime_config)
```

No global registries or module-level mutable singletons. Environment variables are read only in an application/composition layer, then converted into typed configuration. This makes tests deterministic and allows two differently configured agents in one process.

## 8. Observability baseline

Use standard logging with run/session IDs and structured fields. Record lifecycle events such as run started, plan created, tool started/completed, model latency, and run completed. Never log secrets, entire private files, or hidden reasoning by default.

A future `EventSink` protocol can forward the same lifecycle events to tracing systems or the Unity/NPC event bus without changing the loop.

## 9. Testing strategy

Unit tests use deterministic fakes, especially a scripted `FakeModel`, and never need a live LLM.

Minimum acceptance coverage:

- direct final-answer path
- one and multiple tool-call iterations
- unknown tool and invalid argument handling
- malformed planner output and repair/failure behavior
- step-limit termination
- model/tool timeout behavior
- state transition and action-history correctness
- short-term context truncation
- JSON round trip, schema version, and atomic-write failure behavior
- calculator allow-list and file-reader path traversal protection

One integration test wires the real planner, registry, JSON store, and scripted model end to end. Live MiniLLM-Serve tests are optional and marked separately.

## 10. MVP scope and non-goals

Included:

- single-agent, single-process runtime
- sequential tool execution
- text messages
- JSON-backed memory
- deterministic schema-validated tool calls
- local/MiniLLM-Serve-ready adapter boundary

Deferred:

- multi-agent collaboration
- parallel tool execution
- vector retrieval and embeddings
- autonomous background jobs
- multimodal binary transport
- sandboxed code execution
- distributed state and multi-process JSON writes
- sophisticated planning trees, reflection, and self-modification

## 11. Delivery sequence and gates

### Step 2 — Project skeleton

Create packaging, `src` layout, test layout, lint/type/test configuration, license, and placeholder package modules. Gate: clean install plus empty test discovery succeeds.

### Step 3 — Minimal agent loop

Implement typed state, decisions, planner boundary, fake model, bounded `Agent.run`, and focused tests. No real tools or persistence yet. Gate: direct response, scripted tool observation, and step limit are deterministic.

### Step 4 — Memory

Implement items, store interface, manager policy, JSON adapter, and tests. Gate: round-trip persistence and bounded session context work without coupling the agent to JSON.

### Step 5 — Tools

Implement base contract, registry, calculator, file reader, time tool, validation, and safety tests. Gate: tools are discoverable by schema and failures become observations.

### Step 6 — Model adapter

Finalize normalized model types and implement the configurable local HTTP adapter against the confirmed MiniLLM-Serve API. Gate: mocked HTTP contract tests pass; optional live smoke test is documented.

### Step 7 — Test hardening

Add end-to-end integration, error-path, security-boundary, coverage, and type-check gates.

### Step 8 — README

Document architecture, quick start, a real example, extension guides, safety limits, roadmap, and integration points for MiniLLM-Serve and Spatial AI NPC.

## 12. Step 1 acceptance result

The MVP boundaries, dependency direction, public responsibilities, state transitions, safety constraints, test strategy, and phased gates are defined. No production code has been created in this step.
