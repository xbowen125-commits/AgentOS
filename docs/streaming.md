# Native Streaming Runtime

`MiniLLMModel.stream(prompt)` now reads the real MiniLLM-Serve SSE endpoint:

```text
Model.stream(prompt)
        |
POST /v1/chat/completions (stream=true)
        |
SSE data: choices[0].delta.content
        |
StreamingManager -> EventBus -> subscribers
```

The `generate()` interface remains unchanged. Streaming consumes data as it arrives, rather than
splitting a completed generation into characters. Each yielded string is a server text chunk;
it can contain multiple characters or tokenizer tokens.

## Using the manager

```python
from contextlib import aclosing

from agentos.events import EventBus
from agentos.models.mini_llm import MiniLLMConfig, MiniLLMModel
from agentos.streaming import StreamingManager

bus = EventBus()
model = MiniLLMModel(MiniLLMConfig("http://localhost:8000"))
manager = StreamingManager(model, bus)

async def show(prompt: str) -> None:
    async with aclosing(manager.stream(prompt)) as stream:
        async for chunk in stream:
            print(chunk, end="", flush=True)
```

Subscribers receive JSON-compatible `StreamEvent` instances using the existing EventBus contract:

| Event | Payload |
| --- | --- |
| `stream.started` | `{}` |
| `model.token` | `token` text and zero-based `index` |
| `model.completed` | `chunk_count` |
| `stream.finished` | `status`, `chunk_count`, `error_type` |

A full successful stream emits `model.completed` followed by `stream.finished` with
`status="completed"`. Failures propagate through the existing MiniLLM exception hierarchy and emit
`stream.finished` with `status="failed"`. Explicit early closure or task cancellation uses
`status="cancelled"` and does not emit `model.completed`.

Use `aclosing` when breaking out early so the HTTP response and client close immediately. Event
handler failures are isolated. Token events contain model output, so attach persistent subscribers
only when storing that content is appropriate. The included demo persists metadata only.

## SSE protocol and failure handling

The adapter handles fragmented bytes, split UTF-8 characters, CRLF, comments, and multiline data
messages. Role-only deltas and empty terminal deltas do not produce text tokens. A valid stream
must contain a completion chunk and the `[DONE]` marker. HTTP errors, a wrong content type,
malformed chunks, in-stream server errors, and premature EOF raise explicit errors.

## Real calculator streaming demo

Configure `configs/mini_llm.json` as described in [real_backend.md](real_backend.md), start
MiniLLM-Serve separately, and run:

```powershell
python examples/real_mini_llm_stream.py
```

The example-only `StreamingPlannerModel` collects one complete SSE response for each existing
Planner generation request. It prints live chunks through EventBus and sends the completed text
through normal parsing, validation, and bounded repair. Partial JSON never becomes a Decision.
Agent Core, Decision structures, and Model Interface stay unchanged.

Expected complete flow:

```text
User: 计算 123*456
SSE decision: calculator(expression="123*456")
Tool observation: 56088
SSE final decision: answer="56088"
Final Answer: 56088
```

Metadata traces are written to `traces/real_backend/streaming/`, without token content or prompts.
