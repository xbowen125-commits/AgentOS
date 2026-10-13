"""Dataset validation, multi-model isolation and portable experiment artifacts."""

import json
from pathlib import Path

import pytest

from agentos.evaluation.ablation import Variant
from agentos.evaluation.experiment import ExperimentDataset, ExperimentRunner, ModelBackend
from agentos.models.fake import FakeModel
from agentos.models.http_client import HttpClient
from agentos.models.mini_llm import MiniLLMConfig, MiniLLMModel
from examples.run_reliability_experiment import default_dataset, session_factory
from tests.fakes.fake_mini_llm_server import FakeMiniLLMServer


def fake_success() -> FakeModel:
    return FakeModel([
        '{"type":"tool_call","tool_name":"set_status","arguments":{"status":"done"}}',
        '{"type":"final","answer":"Done"}',
    ])


def test_json_dataset_loading(tmp_path: Path) -> None:
    data = [{"task_id": "one", "description": "Set done", "initial_state": {"status": "new"},
             "goal_state": {"status": "done"}, "expected_tools": ["set_status"], "metadata": {}}]
    path = tmp_path / "tasks.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    dataset = ExperimentDataset.load(path)
    assert dataset.tasks[0].expected_tools == ["set_status"]
    assert dataset.digest == ExperimentDataset.from_data(data).digest
    data[0]["initial_state"]["status"] = "changed"
    assert dataset.tasks[0].initial_state == {"status": "new"}


@pytest.mark.parametrize("data", [[], {}, [{"task_id": "one"}]])
def test_invalid_dataset(data: object) -> None:
    with pytest.raises(ValueError):
        ExperimentDataset.from_data(data)


def test_duplicate_and_nonfinite_json(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text('[{"task_id":"one","task_id":"two"}]', encoding="utf-8")
    with pytest.raises(ValueError):
        ExperimentDataset.load(path)
    data = json.loads(json.dumps([{
        "task_id": "one", "description": "test", "initial_state": {}, "goal_state": {},
        "expected_tools": [], "metadata": {"bad": float("nan")},
    }]))
    with pytest.raises(ValueError):
        ExperimentDataset.from_data(data)


@pytest.mark.asyncio
async def test_multiple_models_variants_trials_and_outputs(tmp_path: Path) -> None:
    models = []
    sessions = []

    def create():
        model = fake_success()
        models.append(model)
        return model

    def factory(model, variant, task, index):
        session = session_factory(model, variant, task, index)
        sessions.append(session)
        return session

    runner = ExperimentRunner(factory, repeats=2, k_values=(1, 2, 4))
    result = await runner.run(default_dataset(), [
        ModelBackend("first", create), ModelBackend("second", create),
    ], [Variant("baseline"), Variant("full", True, True, True, True)])
    assert len(models) == 8 and len({id(model) for model in models}) == 8
    assert len({id(session.runner.state) for session in sessions}) == 8
    for ablation in result.models.values():
        for benchmark in ablation.benchmarks.values():
            assert benchmark.metrics.pass_at_1 == 1
            assert benchmark.metrics.pass_power_k[2] == 1
            assert benchmark.metrics.pass_power_k[4] is None
    paths = result.write(tmp_path / "results")
    assert [path.name for path in paths] == [
        "benchmark.json", "failure_report.json", "experiment_report.md",
    ]
    benchmark = json.loads(paths[0].read_text(encoding="utf-8"))
    assert benchmark["manifest"]["repeats"] == 2
    assert benchmark["models"]["first"]["baseline"]["average_latency"] >= 0
    assert json.loads(paths[1].read_text(encoding="utf-8"))["failures"] == []
    assert "pass^2" in paths[2].read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_failure_collection() -> None:
    result = await ExperimentRunner(session_factory, repeats=2).run(
        default_dataset(), [ModelBackend("bad", lambda: FakeModel(["not JSON"]))],
        [Variant("baseline")],
    )
    benchmark = result.models["bad"].benchmarks["baseline"]
    assert benchmark.metrics.success_rate == 0
    assert len(result.failure_dict()["failures"]) == 2
    assert all(trial.failure is not None for trial in benchmark.trials)
    assert result.failure_dict()["raw_evidence_omitted"]


@pytest.mark.asyncio
async def test_duplicate_models_rejected() -> None:
    backend = ModelBackend("same", fake_success)
    with pytest.raises(ValueError):
        await ExperimentRunner(session_factory).run(
            default_dataset(), [backend, backend], [Variant("baseline")],
        )


@pytest.mark.asyncio
async def test_mini_llm_adapter_with_mock_http() -> None:
    servers = []

    def create():
        server = FakeMiniLLMServer(responses=[
            '{"type":"tool_call","tool_name":"set_status","arguments":{"status":"done"}}',
            '{"type":"final","answer":"Done"}',
        ])
        servers.append(server)
        return MiniLLMModel(MiniLLMConfig("http://mini.test"),
                            HttpClient(transport=server.transport))

    result = await ExperimentRunner(session_factory, repeats=2).run(
        default_dataset(), [ModelBackend("mock-mini", create)], [Variant("baseline")],
    )
    assert result.models["mock-mini"].benchmarks["baseline"].metrics.pass_at_1 == 1
    assert len(servers) == 2 and all(len(s.chat_requests) == 2 for s in servers)
    for server in servers:
        assert "expected_tools" not in server.chat_requests[0].content.decode()
