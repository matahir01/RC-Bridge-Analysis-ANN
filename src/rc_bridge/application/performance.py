from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from time import perf_counter
from typing import TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class ApplicationPerformanceRecord:
    operation: str
    duration_s: float
    cache_hit: bool
    detail: str = ""

    def __post_init__(self) -> None:
        if not self.operation.strip():
            raise ValueError("Performance operation name cannot be empty.")
        if self.duration_s < 0.0:
            raise ValueError("Performance duration cannot be negative.")


def timed_call(
    operation: str,
    callback: Callable[[], T],
    *,
    detail: str = "",
) -> tuple[T, ApplicationPerformanceRecord]:
    started = perf_counter()
    value = callback()
    return value, ApplicationPerformanceRecord(
        operation=operation,
        duration_s=perf_counter() - started,
        cache_hit=False,
        detail=detail,
    )


def cache_hit_record(operation: str, *, detail: str = "") -> ApplicationPerformanceRecord:
    return ApplicationPerformanceRecord(
        operation=operation,
        duration_s=0.0,
        cache_hit=True,
        detail=detail,
    )
