"""Single clock helper. Naive UTC, swappable in tests via monkeypatch."""

from datetime import UTC, datetime


def now() -> datetime:
    """Naive UTC. Stays naive so SQLite columns don't need to deal with tzinfo yet."""
    return datetime.now(UTC).replace(tzinfo=None)
