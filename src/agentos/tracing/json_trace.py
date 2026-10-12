"""Local JSON adapter for execution traces."""

import hashlib
import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

from agentos.events.event import AgentEvent
from agentos.exceptions import TraceFormatError, TraceNotFoundError, TraceStoreError
from agentos.tracing.trace import TraceRecord


class JsonTraceStore:
    """Persist each execution trace as one human-readable JSON document."""

    def __init__(self, directory: str | Path) -> None:
        self.directory = Path(directory).resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def append(self, event: AgentEvent) -> None:
        """Append one event, creating its trace when necessary."""
        with self._lock:
            path = self._path_for(event.run_id)
            trace = self._load_unlocked(path, event.run_id) if path.exists() else TraceRecord(event.run_id)
            trace.append(event)
            self._save_unlocked(path, trace)

    def save(self, trace: TraceRecord) -> None:
        """Write a complete trace, replacing its prior document atomically."""
        with self._lock:
            self._save_unlocked(self._path_for(trace.run_id), trace)

    def load(self, run_id: str) -> TraceRecord:
        """Load a trace by run ID."""
        with self._lock:
            path = self._path_for(run_id)
            if not path.exists():
                raise TraceNotFoundError(f"Trace not found: {run_id}")
            return self._load_unlocked(path, run_id)

    def _path_for(self, run_id: str) -> Path:
        if not run_id:
            raise ValueError("run_id must not be empty")
        digest = hashlib.sha256(run_id.encode("utf-8")).hexdigest()
        return self.directory / f"{digest}.json"

    def _save_unlocked(self, path: Path, trace: TraceRecord) -> None:
        document = {
            "run_id": trace.run_id,
            "events": [self._event_document(event) for event in trace.events],
        }
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.directory,
                prefix=f"{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)
                json.dump(document, temporary_file, ensure_ascii=False, indent=2)
                temporary_file.write("\n")
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
            os.replace(temporary_path, path)
        except (OSError, TypeError, ValueError) as error:
            raise TraceStoreError(f"Unable to write trace: {trace.run_id}") from error
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    def _load_unlocked(self, path: Path, expected_run_id: str) -> TraceRecord:
        try:
            with path.open(encoding="utf-8") as trace_file:
                document: Any = json.load(trace_file)
        except json.JSONDecodeError as error:
            raise TraceFormatError(f"Trace contains invalid JSON: {expected_run_id}") from error
        except OSError as error:
            raise TraceStoreError(f"Unable to read trace: {expected_run_id}") from error

        if not isinstance(document, dict):
            raise TraceFormatError("Trace document must be a JSON object")
        run_id = document.get("run_id")
        if run_id != expected_run_id:
            raise TraceFormatError("Trace run ID does not match the requested run")
        raw_events = document.get("events")
        if not isinstance(raw_events, list):
            raise TraceFormatError("Trace document 'events' must be a JSON list")

        trace = TraceRecord(run_id=expected_run_id)
        for index, raw_event in enumerate(raw_events):
            if not isinstance(raw_event, dict):
                raise TraceFormatError(f"Trace event at index {index} must be a JSON object")
            try:
                trace.append(AgentEvent.from_dict(dict(raw_event), run_id=expected_run_id))
            except (KeyError, TypeError, ValueError) as error:
                raise TraceFormatError(f"Invalid trace event at index {index}") from error
        return trace

    @staticmethod
    def _event_document(event: AgentEvent) -> dict[str, Any]:
        event_data = event.to_dict()
        return {
            "event_type": event_data["event_type"],
            "timestamp": event_data["timestamp"],
            "payload": event_data["payload"],
        }
