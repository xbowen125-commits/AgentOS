# AgentOS Evaluation Report

Runs: 10

| Metric | Value |
| --- | ---: |
| Task Success Rate | 100.0% |
| Tool Selection Accuracy | 100.0% |
| Workflow Completion Rate | N/A |
| Average Latency | 0.1341s |
| Retry Rate | 0.0% |
| Validation Failure Rate | 0.0% |

Coverage: tasks=10/10; tool sequences=10/10; workflows=0/10.

N/A means unobserved or inapplicable. Retry and validation failure rates are run-level; recovered validation failures remain counted. Tool accuracy counts ordered matching positions over max(actual, expected) sequence length, aggregated across assessed runs.

## Run Results

| Case / Run | Task | Tools | Workflow | Latency | Retries | Tool Failures | Issues |
| --- | --- | ---: | --- | ---: | ---: | ---: | --- |
| calc_001 | passed | 100.0% | N/A | 0.1331s | 0 | 0 | none |
| calc_002 | passed | 100.0% | N/A | 0.1441s | 0 | 0 | none |
| calc_003 | passed | 100.0% | N/A | 0.1302s | 0 | 0 | none |
| calc_004 | passed | 100.0% | N/A | 0.1353s | 0 | 0 | none |
| calc_005 | passed | 100.0% | N/A | 0.2151s | 0 | 0 | none |
| calc_006 | passed | 100.0% | N/A | 0.1291s | 0 | 0 | none |
| calc_007 | passed | 100.0% | N/A | 0.1345s | 0 | 0 | none |
| calc_008 | passed | 100.0% | N/A | 0.1283s | 0 | 1 | tool_failure |
| calc_009 | passed | 100.0% | N/A | 0.1270s | 0 | 1 | tool_failure |
| calc_010 | passed | 100.0% | N/A | 0.0639s | 0 | 0 | none |
