# Design Principles

## 1. Core depends on abstractions

The runtime coordinates interfaces for planning, models, tools, and memory. Concrete HTTP clients,
file formats, and environments stay outside the core loop.

## 2. Adapters isolate external systems

MiniLLM-Serve, JSON persistence, response caching, and spatial NPC protocols are adapters. They can
be replaced independently, and AgentOS does not import Unity, LangChain, databases, or game-engine
SDKs.

## 3. Observability is a side channel

Runtime events and traces make execution observable without controlling it. Handler failures are
isolated so logging or trace persistence cannot determine whether an Agent succeeds.

## 4. Memory avoids sensitive data

Memory stores structured, explicit application state rather than hidden reasoning. NPC memory uses
a fixed profile schema and excludes faces, raw media, audio, and biometric identifiers.

## 5. Evaluation drives improvement

Changes should be measured with repeatable cases, trace-derived metrics, and reports. Correctness,
latency, model calls, tool calls, failures, and cache behavior are visible before optimization.

## Additional constraints

- Structured decisions are preferred over parsing free-form model prose.
- Failures crossing adapter boundaries become explicit domain errors or observations.
- Defaults remain local and deterministic where possible.
- New capabilities should compose around the runtime rather than enlarge the Agent Loop.
