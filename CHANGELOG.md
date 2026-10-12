# Changelog

All notable changes to AgentOS Runtime are documented in this file.

## [1.0.0] - 2026-10-12

### Added

- Agent Runtime foundation with bounded asynchronous execution and structured state.
- Planner layer and strict JSON decision protocol.
- Replaceable model interface, deterministic FakeModel, and MiniLLM-Serve adapter.
- Tool registry, safe executor, and resource-bounded calculator.
- Versioned JSON memory store and structured NPC player memory.
- Runtime events, JSON traces, latency profiling, and streaming interfaces.
- Response caching and asynchronous timeout controls.
- Deterministic evaluation cases, benchmark metrics, and Markdown reports.
- End-to-end calculator and spatial NPC protocol demonstrations.
- Multimodal interaction adapters and transport-neutral NPC actions.

### Architecture

- Core depends on ports; external systems are isolated behind adapters.
- Observability remains a failure-isolated side channel.
- Memory avoids hidden reasoning and sensitive biometric data.
