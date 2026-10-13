# AgentOS Reliability Experiment Report

Experiment: fe27f976-cf78-4e4c-8715-79b327bbacf9

Dataset digest: d4a60ea8e38b5ddd4518acbfa631d7aa1ed8a8f6ed35b70e295e700093d3e07e

Sequential prototype; pinned metadata is caller supplied. Missing revisions are marked unknown. No causal or tau-bench score claims.

## Model: fake

# AgentOS Runtime Ablation Report

| Variant | Trials | pass@1 | pass^1 | pass^2 | pass^4 | pass^8 | Average Latency |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Baseline | 4 | 100.0% | 100.0% | 100.0% | 100.0% | N/A | 0.1855s |
| Parser | 4 | 100.0% | 100.0% | 100.0% | 100.0% | N/A | 0.1642s |
| Validator | 4 | 100.0% | 100.0% | 100.0% | 100.0% | N/A | 0.1738s |
| Retry | 4 | 100.0% | 100.0% | 100.0% | 100.0% | N/A | 0.1883s |
| Full | 4 | 100.0% | 100.0% | 100.0% | 100.0% | N/A | 0.1827s |

## Feature Configuration

| Variant | Parser | Validator | Retry | Timeout |
| --- | --- | --- | --- | --- |
| Baseline | False | False | False (max=2) | False (30.0s) |
| Parser | True | False | False (max=2) | False (30.0s) |
| Validator | True | True | False (max=2) | False (30.0s) |
| Retry | True | True | True (max=2) | False (30.0s) |
| Full | True | True | True (max=2) | True (30.0s) |

## Failure Distribution

| Variant | Category | Failed Trials |
| --- | --- | ---: |
| Baseline | none | 0 |
| Parser | none | 0 |
| Validator | none | 0 |
| Retry | none | 0 |
| Full | none | 0 |

## Evidence Coverage

- Baseline: tasks=1, trace=4/4.
- Parser: tasks=1, trace=4/4.
- Validator: tasks=1, trace=4/4.
- Retry: tasks=1, trace=4/4.
- Full: tasks=1, trace=4/4.

pass^k measures all-k success, not best-of-k. N/A means insufficient trials or no data. Average latency includes failed runs.
Parser disabled means strict JSON decoding, not execution of raw text. ToolExecutor contracts and sandbox boundaries remain active in Baseline.
Timeout bounds one planner decision including repair requests; it does not bound tool execution or the entire Agent run.
Configurations run sequentially; no confidence intervals or causal improvement claims are produced by this prototype.


- Baseline: success rate=100.0%; observed recovery rate=N/A (0/0).
- Parser: success rate=100.0%; observed recovery rate=N/A (0/0).
- Validator: success rate=100.0%; observed recovery rate=N/A (0/0).
- Retry: success rate=100.0%; observed recovery rate=N/A (0/0).
- Full: success rate=100.0%; observed recovery rate=N/A (0/0).
