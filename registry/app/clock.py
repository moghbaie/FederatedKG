"""Single source of time for every authorization and expiry decision.

In test mode the clock can be advanced so 24-hour expiry is testable; otherwise it is wall-clock UTC.
"""
from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone


def as_utc(dt: datetime) -> datetime:
    """Treat naive datetimes (e.g. read back from SQLite) as UTC."""
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


class Clock:
    def __init__(self, adjustable: bool = False):
        self._adjustable = adjustable
        self._offset = timedelta()
        self._lock = threading.Lock()

    def now(self) -> datetime:
        with self._lock:
            return datetime.now(timezone.utc) + self._offset

    @property
    def offset_seconds(self) -> float:
        return self._offset.total_seconds()

    def advance(self, seconds: float) -> None:
        if not self._adjustable:
            raise PermissionError("clock is not adjustable outside test mode")
        if seconds < 0:
            raise ValueError("the clock only moves forward")
        with self._lock:
            self._offset += timedelta(seconds=seconds)

    def reset(self) -> None:
        if not self._adjustable:
            raise PermissionError("clock is not adjustable outside test mode")
        with self._lock:
            self._offset = timedelta()
