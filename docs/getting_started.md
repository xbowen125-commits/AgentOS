# Getting Started

## Requirements

- Python 3.10 or newer
- PowerShell examples below, or an equivalent shell
- MiniLLM-Serve only for the live calculator adapter demo

## Install

Create and activate a virtual environment, then install AgentOS in editable mode:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .
```

Install development tools when running tests and quality checks:

```powershell
pip install -e ".[dev]"
```

Verify the package import and version:

```powershell
python -c "import agentos; print(agentos.__version__)"
```

## Configure MiniLLM-Serve

Edit `configs/default.json`:

```json
{
  "model": {
    "type": "mini_llm",
    "base_url": "http://localhost:8000"
  }
}
```

The adapter calls `POST /generate` with `prompt` and `max_tokens`, and expects a JSON response with
a string `text` field. `ModelPlanner` expects that text to contain exactly one structured decision.

## Run the calculator agent

Start MiniLLM-Serve, then run:

```powershell
python examples/calculator_agent.py
```

Enter `计算 123*456`. A compatible model should request the calculator and then return `56088`.
The run writes lifecycle events to the ignored local `traces/` directory.

## Run the NPC protocol demos

The bridge and complete spatial demos are offline and do not require Unity:

```powershell
python examples/npc_bridge_demo.py
python examples/spatial_agent_demo.py
```

They use `FakeModel` to demonstrate the integration contract deterministically.

## Run tests and benchmarks

```powershell
pytest
python -m benchmarks.evaluator
python -m benchmarks.performance
```

Generated benchmark output is written under `benchmarks/output/` and ignored by Git.
