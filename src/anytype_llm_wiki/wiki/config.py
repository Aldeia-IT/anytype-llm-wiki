"""v0.2.0 wiki configuration — environment variables with defaults.

Mirrors the style of ``anytype_llm_wiki.config`` but for the wiki module.

IMPORTANT: values that tests monkeypatch at call time (notably ``WIKI_LOCK_DIR``
and ``WIKI_FETCH_EXTRA_PORTS``) are resolved through functions that read
``os.environ`` on each call. Do NOT cache them at import time — ``space_ingest_lock``
and ``run_doctor`` rely on ``monkeypatch.setenv`` taking effect after import.
"""

import os
from pathlib import Path

# Default lock directory (resolved at call time via lock_dir()).
DEFAULT_WIKI_LOCK_DIR = os.path.expanduser("~/.local/share/anytype-llm-wiki/locks")

# Placeholder extraction model for the v0.3.0 extraction pipeline.
DEFAULT_WIKI_EXTRACT_MODEL = "qwen2.5:7b"

# Default per-request read timeout (seconds) for the extraction model call.
DEFAULT_WIKI_EXTRACT_TIMEOUT = 120.0

# Default log level for wiki operations.
DEFAULT_WIKI_LOG_LEVEL = "info"


def lock_dir() -> str:
    """Resolve WIKI_LOCK_DIR from the environment at call time.

    Falls back to the default under ~/.local/share when unset.
    """
    return os.environ.get("WIKI_LOCK_DIR", DEFAULT_WIKI_LOCK_DIR)


def extract_model() -> str:
    """Resolve WIKI_EXTRACT_MODEL (placeholder for v0.3.0 extraction)."""
    return os.environ.get("WIKI_EXTRACT_MODEL", DEFAULT_WIKI_EXTRACT_MODEL)


def extract_timeout() -> float:
    """Resolve WIKI_EXTRACT_TIMEOUT — the per-request read timeout (seconds) for
    the extraction model call.

    Defaults to 120s. Raise it for slow/large local models: a ~20GB model can
    exceed 120s on a sizable source, which would otherwise trip the read timeout
    and silently degrade extraction to heading-derived candidates only.
    Non-numeric or non-positive values fall back to the default.
    """
    raw = os.environ.get("WIKI_EXTRACT_TIMEOUT")
    if raw is None:
        return DEFAULT_WIKI_EXTRACT_TIMEOUT
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return DEFAULT_WIKI_EXTRACT_TIMEOUT
    return val if val > 0 else DEFAULT_WIKI_EXTRACT_TIMEOUT


def log_level() -> str:
    """Resolve WIKI_LOG_LEVEL from the environment at call time."""
    return os.environ.get("WIKI_LOG_LEVEL", DEFAULT_WIKI_LOG_LEVEL)


def fetch_extra_ports() -> list[int]:
    """Resolve WIKI_FETCH_EXTRA_PORTS — a comma-separated list of extra ports.

    Returns an empty list when unset or empty. Non-integer entries are skipped.
    """
    raw = os.environ.get("WIKI_FETCH_EXTRA_PORTS", "")
    ports: list[int] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ports.append(int(part))
        except ValueError:
            continue
    return ports


def lock_dir_path() -> Path:
    """Convenience: WIKI_LOCK_DIR resolved to a pathlib.Path at call time."""
    return Path(lock_dir())
