# Real MiniLLM Backend Integration

This guide validates AgentOS against the sibling MiniLLM-Serve project using its real HTTP
contract. AgentOS does not start, stop, or manage the model server.

## Architecture

```text
MiniLLM-Serve / Qwen
        |
        v
OpenAI-compatible HTTP API
GET /health
POST /v1/chat/completions
        |
        v
MiniLLMModel Adapter
        |
        v
ModelPlanner -> AgentOS -> Calculator -> Final Answer
        |
        v
Sanitized JSON Trace
```

`MiniLLMModel` keeps the AgentOS `Model.generate(prompt) -> str` contract. It discovers the loaded
model name from `/health`, sends the planner prompt as one user message, and extracts text from
`choices[0].message.content`. HTTP, timeout, status, JSON, and response-shape failures are converted
to AgentOS MiniLLM exceptions.

## Configuration

Copy the committed template to the local configuration path:

```powershell
Copy-Item configs/mini_llm.example.json configs/mini_llm.json
```

The local file is ignored by Git. Its format is:

```json
{
  "base_url": "http://localhost:8000",
  "timeout": 30,
  "max_tokens": 256
}
```

No API key is required or stored. `base_url` must be the MiniLLM-Serve root, without
`/v1/chat/completions`.

## Running Demo

Start MiniLLM-Serve separately and wait until its health endpoint reports that the model is loaded:

```powershell
Invoke-RestMethod http://localhost:8000/health
```

Then run the complete AgentOS validation:

```powershell
python examples/real_mini_llm_agent.py
```

The fixed input is `计算 123*456`. A compatible model should first return the calculator tool-call
JSON, receive the public tool observation on the next planner step, and then return final-answer
JSON. The command prints the final answer, elapsed latency, model-call count, tool-call count, and
trace path.

The trace includes these validation lifecycle events:

- `agent.started`
- `planner.decision`
- `model.called`
- `tool.called`
- `agent.completed`

The validation trace handler maps the runtime's existing `planner.finished` and `agent.finished`
events to the two validation aliases. It does not change the Agent loop. Trace payloads contain
only step, decision type, tool name, status, and error metadata—never complete prompts, hidden
reasoning, or raw user input.

Run benchmarks offline by default, or explicitly opt into the real backend:

```powershell
python -m benchmarks.real_backend --backend fake
python -m benchmarks.real_backend --backend mini_llm
```

The real mode can consume model time and is never selected implicitly.

## Troubleshooting

### Configuration not found

Create `configs/mini_llm.json` from the example. Do not commit private overrides.

### Connection refused or timeout

Confirm MiniLLM-Serve is running independently, the configured port is correct, and `/health`
responds within the configured timeout. AgentOS does not automatically start the service.

### Model is not loaded

The health response must contain a non-empty `model` string. Wait for MiniLLM-Serve to finish
loading Qwen before retrying.

### Invalid planner JSON

AgentOS accepts only one JSON decision object with no Markdown wrapper or explanatory text. The
model must return either a `tool_call` or `final` object described by the planner prompt.

### HTTP status or response-shape error

Confirm the server exposes `POST /v1/chat/completions` and returns an OpenAI-compatible response
whose first choice contains `message.content` as a string.
