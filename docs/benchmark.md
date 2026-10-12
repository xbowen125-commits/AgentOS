# Benchmark Framework

AgentOS evaluates runtime behavior from public Agent results and runtime traces. It does not depend
on an external evaluation service.

## Cases

`benchmarks/cases.json` contains versionable inputs, expected answers, tags, and deterministic model
responses for the bundled offline suite. The ten cases cover:

- addition, subtraction, multiplication, and division;
- negative and decimal values;
- multi-step tool execution;
- invalid input;
- calculator errors and missing-tool recovery.

## Metrics

`EvaluationMetrics` reports:

- total, successful, and failed cases;
- success rate;
- average latency;
- average model calls;
- average tool calls.

Failure details distinguish runtime exceptions, missing final answers, step-limit exits, and answer
mismatches. The performance report additionally includes P95 latency and cache hit rate.

## Run

```powershell
python -m benchmarks.evaluator
python -m benchmarks.performance
```

Reports are written to `benchmarks/output/report.md` and
`benchmarks/output/performance.md`.

## Reference result

The deterministic ten-case suite produced the following local reference result during v1.0.0
preparation:

| Metric | Result |
|---|---:|
| Success rate | 100% |
| Average latency | approximately 0.09 seconds |
| Average model calls | 2.00 per case |
| Average tool calls | 1.00 per case |
| Total tool calls | 10 |

Latency is environment-dependent and is not a service-level guarantee. Correctness and call-count
metrics are deterministic for the bundled fake-model responses.

## Extending evaluation

`BenchmarkRunner` accepts an Agent factory. A project can replace the offline factory with a
MiniLLM-backed runtime while keeping case execution, trace analysis, metrics, and reporting intact.
