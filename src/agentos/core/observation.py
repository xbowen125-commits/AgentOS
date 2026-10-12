"""Serializable observations produced by tool execution."""

from dataclasses import asdict, dataclass

ObservationValue = bool | str | None


@dataclass(frozen=True)
class Observation:
    """A JSON-serializable tool execution result."""

    success: bool
    result: str | None = None
    error_type: str | None = None
    error_message: str | None = None

    def to_dict(self) -> dict[str, ObservationValue]:
        """Return a representation accepted by standard JSON encoders."""
        return asdict(self)
