"""Inspect an existing trace without running a model, planner, or tool."""

import argparse
import sys
from pathlib import Path

from agentos.exceptions import TraceNotFoundError, TraceStoreError
from agentos.replay import TraceReplay
from agentos.tracing import JsonTraceStore


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--run-id")
    source.add_argument("--trace", type=Path)
    parser.add_argument("--trace-dir", type=Path, default=Path("traces"))
    parser.add_argument("--actual-answer")
    parser.add_argument("--expected-answer")
    options = parser.parse_args()
    try:
        store = None
        if options.run_id is not None:
            if not options.trace_dir.is_dir():
                raise TraceNotFoundError(f"Trace directory not found: {options.trace_dir}")
            store = JsonTraceStore(options.trace_dir)
        result = TraceReplay(store).replay(
            options.trace if options.trace is not None else options.run_id,
            actual_answer=options.actual_answer,
            expected_result=options.expected_answer,
        )
    except (TraceStoreError, ValueError) as error:
        print(f"Trace replay failed: {error}", file=sys.stderr)
        return 1
    print(result.render_text())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
