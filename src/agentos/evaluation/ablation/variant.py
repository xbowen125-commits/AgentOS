"""Immutable experimental switches, separate from production runtime policy."""

from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class Variant:
    name: str
    parser_enabled: bool = False
    validator_enabled: bool = False
    retry_enabled: bool = False
    timeout_enabled: bool = False
    max_retries: int = 2
    timeout_seconds: float = 30.0

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Variant name must not be empty")
        for enabled in (self.parser_enabled, self.validator_enabled,
                        self.retry_enabled, self.timeout_enabled):
            if not isinstance(enabled, bool):
                raise TypeError("Feature switches must be bool")
        if (isinstance(self.max_retries, bool) or not isinstance(self.max_retries, int)
                or self.max_retries < 0):
            raise ValueError("max_retries must be a non-negative integer")
        if not isfinite(self.timeout_seconds) or self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive and finite")


def standard_variants() -> tuple[Variant, ...]:
    return (
        Variant("Baseline"), Variant("Parser", parser_enabled=True),
        Variant("Validator", parser_enabled=True, validator_enabled=True),
        Variant("Retry", parser_enabled=True, validator_enabled=True, retry_enabled=True),
        Variant("Full", parser_enabled=True, validator_enabled=True,
                retry_enabled=True, timeout_enabled=True),
    )
