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

# Whether the extraction model emits reasoning ("thinking") tokens. Default False:
# the standard setup runs a thinking-capable model (e.g. qwen3.5-mlx) in
# non-thinking mode for extraction — reasoning tokens add latency and output bloat
# without improving structured extraction. Harmless (no-op) for non-thinking models.
DEFAULT_WIKI_EXTRACT_THINK = False

# Default per-request read timeout (seconds) for the extraction model call.
# 600s (10 min): large local models routinely take several minutes on a sizable
# source on reference hardware; a lower value trips the read timeout mid-generation.
DEFAULT_WIKI_EXTRACT_TIMEOUT = 600.0

# Default log level for wiki operations.
DEFAULT_WIKI_LOG_LEVEL = "info"

# Default cap on extraction/synthesis input tokens (token estimate: len // 4).
DEFAULT_WIKI_EXTRACT_MAX_INPUT_TOKENS = 8192

# v0.4.0 wiki_query tiered-retrieval / synthesis defaults.
DEFAULT_WIKI_INDEX_THRESHOLD = 200
DEFAULT_WIKI_FILE_BACK_MIN_SOURCES = 3
DEFAULT_WIKI_FILE_BACK_MIN_WORDS = 100
DEFAULT_WIKI_SYNTH_MAX_OBJECTS = 24
DEFAULT_WIKI_SYNTH_MAX_OBJECT_TOKENS = 1024


def _positive_int(env: str, default: int) -> int:
    """Resolve an int env var at call time; reject 0/negative → default (SF10).

    Non-numeric / unset values also fall back to ``default``.
    """
    raw = os.environ.get(env)
    if raw is None:
        return default
    try:
        val = int(raw)
    except (ValueError, TypeError):
        return default
    return val if val > 0 else default


def _bounded_float(env: str, default: float, lo: float = 0.0, hi: float = 1.0) -> float:
    """Resolve a float env var at call time, clamped to the inclusive [lo, hi] range.

    Reads ``os.environ`` on each call (never cached at import). Unset, non-numeric,
    or out-of-range ``[lo, hi]`` values fall back to ``default`` (SF10/B1 guard).
    """
    raw = os.environ.get(env)
    if raw is None:
        return default
    try:
        val = float(raw)
    except (ValueError, TypeError):
        return default
    if val < lo or val > hi:
        return default
    return val


# v0.5.0 wiki_lint structural-health-check defaults.
DEFAULT_WIKI_LINT_OVERSIZED_CHARS = 2000
DEFAULT_WIKI_LINT_ORPHAN_GRACE_DAYS = 7
DEFAULT_WIKI_LINT_STALE_NEEDS_REVIEW_DAYS = 30
DEFAULT_WIKI_LINT_MAX_OBJECTS = 2000
DEFAULT_WIKI_LINT_PIPELINE_WINDOW_SECONDS = 300
DEFAULT_WIKI_LINT_DUPLICATE_MAX_SCORE = 0.85


def lint_oversized_chars() -> int:
    """Resolve WIKI_LINT_OVERSIZED_CHARS — oversized-description cap (default 2000)."""
    return _positive_int(
        "WIKI_LINT_OVERSIZED_CHARS", DEFAULT_WIKI_LINT_OVERSIZED_CHARS
    )


def lint_orphan_grace_days() -> int:
    """Resolve WIKI_LINT_ORPHAN_GRACE_DAYS — orphan age grace period (default 7)."""
    return _positive_int(
        "WIKI_LINT_ORPHAN_GRACE_DAYS", DEFAULT_WIKI_LINT_ORPHAN_GRACE_DAYS
    )


def lint_stale_needs_review_days() -> int:
    """Resolve WIKI_LINT_STALE_NEEDS_REVIEW_DAYS — stale needs-review cutoff (default 30)."""
    return _positive_int(
        "WIKI_LINT_STALE_NEEDS_REVIEW_DAYS",
        DEFAULT_WIKI_LINT_STALE_NEEDS_REVIEW_DAYS,
    )


def lint_max_objects() -> int:
    """Resolve WIKI_LINT_MAX_OBJECTS — duplicate-sweep object cap (default 2000)."""
    return _positive_int("WIKI_LINT_MAX_OBJECTS", DEFAULT_WIKI_LINT_MAX_OBJECTS)


def lint_pipeline_window_seconds() -> int:
    """Resolve WIKI_LINT_PIPELINE_WINDOW_SECONDS — pipeline_orphan ±window (default 300)."""
    return _positive_int(
        "WIKI_LINT_PIPELINE_WINDOW_SECONDS",
        DEFAULT_WIKI_LINT_PIPELINE_WINDOW_SECONDS,
    )


def lint_duplicate_max_score() -> float:
    """Resolve WIKI_LINT_DUPLICATE_MAX_SCORE — duplicate band upper bound (default 0.85).

    Bounded to [0, 1]; out-of-range or non-numeric values fall back to the default.
    """
    return _bounded_float(
        "WIKI_LINT_DUPLICATE_MAX_SCORE",
        DEFAULT_WIKI_LINT_DUPLICATE_MAX_SCORE,
        0.0,
        1.0,
    )


def extract_max_input_tokens() -> int:
    """Resolve WIKI_EXTRACT_MAX_INPUT_TOKENS (default 8192)."""
    return _positive_int(
        "WIKI_EXTRACT_MAX_INPUT_TOKENS", DEFAULT_WIKI_EXTRACT_MAX_INPUT_TOKENS
    )


def index_threshold() -> int:
    """Resolve WIKI_INDEX_THRESHOLD — Tier-1/Tier-2 object-count flip (default 200)."""
    return _positive_int("WIKI_INDEX_THRESHOLD", DEFAULT_WIKI_INDEX_THRESHOLD)


def file_back_min_sources() -> int:
    """Resolve WIKI_FILE_BACK_MIN_SOURCES — file-back source-count gate (default 3)."""
    return _positive_int(
        "WIKI_FILE_BACK_MIN_SOURCES", DEFAULT_WIKI_FILE_BACK_MIN_SOURCES
    )


def file_back_min_words() -> int:
    """Resolve WIKI_FILE_BACK_MIN_WORDS — file-back answer-length gate (default 100)."""
    return _positive_int(
        "WIKI_FILE_BACK_MIN_WORDS", DEFAULT_WIKI_FILE_BACK_MIN_WORDS
    )


def synth_max_input_tokens() -> int:
    """Resolve WIKI_SYNTH_MAX_INPUT_TOKENS — total synthesis context cap.

    Defaults to ``extract_max_input_tokens()`` (8192) when unset/invalid.
    """
    return _positive_int("WIKI_SYNTH_MAX_INPUT_TOKENS", extract_max_input_tokens())


def synth_max_objects() -> int:
    """Resolve WIKI_SYNTH_MAX_OBJECTS — max objects in synthesis context (default 24)."""
    return _positive_int("WIKI_SYNTH_MAX_OBJECTS", DEFAULT_WIKI_SYNTH_MAX_OBJECTS)


def synth_max_object_tokens() -> int:
    """Resolve WIKI_SYNTH_MAX_OBJECT_TOKENS — per-object token cap (default 1024)."""
    return _positive_int(
        "WIKI_SYNTH_MAX_OBJECT_TOKENS", DEFAULT_WIKI_SYNTH_MAX_OBJECT_TOKENS
    )


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

    Defaults to 600s (10 min) — large local models (e.g. a ~20GB model) routinely
    take several minutes on a sizable source; a lower timeout would trip the read
    timeout mid-generation and silently degrade extraction to heading-derived
    candidates only. Lower it for a fast model if you want quicker failure on a
    hung endpoint. Non-numeric or non-positive values fall back to the default.
    """
    raw = os.environ.get("WIKI_EXTRACT_TIMEOUT")
    if raw is None:
        return DEFAULT_WIKI_EXTRACT_TIMEOUT
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return DEFAULT_WIKI_EXTRACT_TIMEOUT
    return val if val > 0 else DEFAULT_WIKI_EXTRACT_TIMEOUT


def extract_think() -> bool:
    """Resolve WIKI_EXTRACT_THINK — whether the extraction model emits reasoning
    ("thinking") tokens.

    Defaults to False so a thinking-capable model (e.g. qwen3.5-mlx) runs terse
    for extraction. Accepts 1/true/yes/on (case-insensitive) to enable.
    """
    raw = os.environ.get("WIKI_EXTRACT_THINK")
    if raw is None:
        return DEFAULT_WIKI_EXTRACT_THINK
    return raw.strip().lower() in ("1", "true", "yes", "on")


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
