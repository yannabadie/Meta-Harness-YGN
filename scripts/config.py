"""Shared configuration and storage utilities for Meta-Harness.

Single source of truth for paths, constants, frontier I/O, and timestamps.
Used by both meta_harness.py (CLI) and mh_server.py (MCP server).
"""
from __future__ import annotations

import contextlib
import csv
import datetime as dt
import os
import pathlib
import re
import tempfile
from collections.abc import Iterable, Iterator

# ---------------------------------------------------------------------------
# Cross-platform file locking
# ---------------------------------------------------------------------------

try:
    import fcntl

    def _lock_sh(f):  # type: ignore[no-untyped-def]
        fcntl.flock(f, fcntl.LOCK_SH)

    def _lock_ex(f):  # type: ignore[no-untyped-def]
        fcntl.flock(f, fcntl.LOCK_EX)

    def _unlock(f):  # type: ignore[no-untyped-def]
        fcntl.flock(f, fcntl.LOCK_UN)

except ImportError:
    # Windows fallback
    import msvcrt

    def _lock_sh(f):  # type: ignore[no-untyped-def]
        msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 1)

    def _lock_ex(f):  # type: ignore[no-untyped-def]
        msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 1)

    def _unlock(f):  # type: ignore[no-untyped-def]
        msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)


# ---------------------------------------------------------------------------
# Paths — unified defaults
# ---------------------------------------------------------------------------

DEFAULT_PLUGIN_DATA = "/tmp/meta-harness-lab"

PLUGIN_DATA = pathlib.Path(
    os.environ.get(
        "MH_PLUGIN_DATA",
        os.environ.get("CLAUDE_PLUGIN_DATA", DEFAULT_PLUGIN_DATA),
    )
)
PLUGIN_ROOT = pathlib.Path(
    os.environ.get("MH_PLUGIN_ROOT",
                    os.environ.get("CLAUDE_PLUGIN_ROOT",
                                   str(pathlib.Path(__file__).resolve().parents[1])))
)
FRONTIER = PLUGIN_DATA / "frontier.tsv"
RUNS_DIR = PLUGIN_DATA / "runs"
SESSIONS_DIR = PLUGIN_DATA / "sessions"
FRONTIER_LOCK = PLUGIN_DATA / ".frontier.lock"

# ---------------------------------------------------------------------------
# TSV schema
# ---------------------------------------------------------------------------

TSV_HEADER = [
    "run_id", "status", "primary_score", "avg_latency_ms",
    "avg_input_tokens", "risk",
    "consistency", "instruction_adherence", "tool_efficiency", "error_count",
    "note", "timestamp",
]

# ---------------------------------------------------------------------------
# Directory initialization
# ---------------------------------------------------------------------------


def ensure_dirs() -> None:
    """Create plugin data directories and frontier TSV if missing."""
    PLUGIN_DATA.mkdir(parents=True, exist_ok=True)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    FRONTIER_LOCK.touch(exist_ok=True)
    if not FRONTIER.exists():
        with FRONTIER.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f, delimiter="\t")
            writer.writerow(TSV_HEADER)


# ---------------------------------------------------------------------------
# Timestamps — consistent ISO 8601 format everywhere
# ---------------------------------------------------------------------------


def utc_now() -> dt.datetime:
    """Return current UTC datetime."""
    return dt.datetime.now(dt.timezone.utc)


def iso_timestamp() -> str:
    """Return consistent ISO 8601 timestamp: YYYY-MM-DDTHH:MM:SSZ."""
    return utc_now().strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Frontier I/O — atomic writes with file locking
# ---------------------------------------------------------------------------


@contextlib.contextmanager
def frontier_lock(shared: bool = False) -> Iterator[None]:
    """Serialize frontier access through a dedicated lock file."""
    ensure_dirs()
    with FRONTIER_LOCK.open("a+") as lock_f:
        (_lock_sh if shared else _lock_ex)(lock_f)
        try:
            yield
        finally:
            _unlock(lock_f)


def _read_frontier_unlocked() -> list[dict[str, str]]:
    with FRONTIER.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        return list(reader)


def read_frontier() -> list[dict[str, str]]:
    """Read frontier.tsv and return rows as dicts. Creates file if missing."""
    with frontier_lock(shared=True):
        return _read_frontier_unlocked()


def _write_frontier_unlocked(rows: Iterable[dict[str, str]]) -> None:
    fd, tmp_path = tempfile.mkstemp(
        dir=str(PLUGIN_DATA), suffix=".tsv.tmp", prefix="frontier-"
    )
    try:
        with os.fdopen(fd, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=TSV_HEADER, delimiter="\t")
            writer.writeheader()
            for row in rows:
                writer.writerow({k: row.get(k, "") for k in TSV_HEADER})
        os.replace(tmp_path, str(FRONTIER))
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
        raise


def write_frontier(rows: Iterable[dict[str, str]]) -> None:
    """Write frontier.tsv atomically via temp file + rename."""
    with frontier_lock(shared=False):
        _write_frontier_unlocked(rows)


def upsert_frontier_row(new_row: dict[str, str]) -> None:
    """Insert or update one row in frontier.tsv under an exclusive lock."""
    with frontier_lock(shared=False):
        rows = _read_frontier_unlocked()
        for row in rows:
            if row.get("run_id") == new_row.get("run_id"):
                row.update({k: new_row.get(k, "") for k in TSV_HEADER})
                break
        else:
            rows.append({k: new_row.get(k, "") for k in TSV_HEADER})
        _write_frontier_unlocked(rows)


def update_frontier_row(run_id: str, **updates: str) -> bool:
    """Update an existing frontier row under an exclusive lock."""
    with frontier_lock(shared=False):
        rows = _read_frontier_unlocked()
        updated = False
        for row in rows:
            if row.get("run_id") == run_id:
                row.update(updates)
                updated = True
                break
        if updated:
            _write_frontier_unlocked(rows)
        return updated


# ---------------------------------------------------------------------------
# Run ID allocation — with lock to prevent collisions
# ---------------------------------------------------------------------------


def next_run_id() -> str:
    """Reserve the next sequential run ID (run-NNNN).

    Uses a lock file to prevent collisions in parallel allocation.
    Creates the run directory while holding the lock.
    """
    ensure_dirs()
    lock_path = PLUGIN_DATA / ".run-id.lock"
    lock_path.touch(exist_ok=True)
    with lock_path.open("r+") as lock_f:
        _lock_ex(lock_f)
        try:
            existing = []
            for p in RUNS_DIR.iterdir():
                if p.is_dir() and re.fullmatch(r"run-\d{4}", p.name):
                    existing.append(int(p.name.split("-")[1]))
            n = max(existing, default=0) + 1
            run_id = f"run-{n:04d}"
            (RUNS_DIR / run_id).mkdir(parents=True, exist_ok=True)
            return run_id
        finally:
            _unlock(lock_f)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def as_float(value: str) -> float:
    """Parse string to float, returning NaN on failure."""
    try:
        return float(value)
    except (ValueError, TypeError):
        return float("nan")


def session_path() -> pathlib.Path:
    """Return the log file path for the current session."""
    sid = os.environ.get("CLAUDE_SESSION_ID") or utc_now().strftime("session-%Y%m%d-%H%M%S")
    return SESSIONS_DIR / f"{sid}.log"
