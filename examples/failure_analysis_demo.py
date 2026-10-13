"""Demonstrate classification of a public synthetic tool-failure trace."""

from agentos.evaluation.failure import FailureAnalyzer
from agentos.events import AgentEvent
from agentos.tracing import TraceRecord


def main() -> None:
    trace = TraceRecord("demo", [AgentEvent.create("tool.finished", "demo", {
        "step": 1, "tool_name": "calculator", "success": False,
        "error_type": "ToolArgumentError", "error_message": "calculator missing expression",
    })])
    analysis = FailureAnalyzer().analyze(trace)
    assert analysis is not None and analysis.category is not None
    print("AgentOS Failure Analysis")
    print(f"\nCategory:\n{analysis.category.value}")
    print(f"\nEvidence:\n{analysis.evidence}")


if __name__ == "__main__":
    main()
