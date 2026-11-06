"""Env-gated per-stage timing for ``wiki_ingest`` (Aldeia-IT/aldeia-box#1485).

Off by default and free when off: ``span`` then returns a shared no-op context
manager and ``event`` returns at once, so nothing is measured, logged or changed.

``WIKI_PROFILE`` (read at call time, never cached) turns it on:

* ``1`` / ``true`` / ``yes`` / ``on``: one JSON line per finished span on stderr,
  prefixed ``[wiki-profile] ``.
* any other non-empty value except ``0`` / ``false`` / ``no`` / ``off``: the value
  is a file path and the same JSON lines are appended to it.

A span line is ``{"span": <name>, "seconds": <float>, ...meta}``; ``event`` writes
the same shape without a duration (``"seconds": null``). Writing the line never
raises: a profiling failure must not touch an ingest.
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
import time
from collections.abc import Iterator

_TRUTHY = ("1", "true", "yes", "on")
_FALSY = ("", "0", "false", "no", "off")
_PREFIX = "[wiki-profile] "


def profile_target() -> str | None:
    """Where timing lines go, or None when profiling is off.

    Returns:
        ``"stderr"`` for a truthy ``WIKI_PROFILE``, the file path for any other
        non-falsy value, ``None`` when unset or falsy.
    """
    raw = os.environ.get("WIKI_PROFILE", "").strip()
    if raw.lower() in _FALSY:
        return None
    return "stderr" if raw.lower() in _TRUTHY else raw


def _emit(record: dict) -> None:
    target = profile_target()
    if target is None:
        return
    line = json.dumps(record, default=str, sort_keys=False)
    try:
        if target == "stderr":
            print(_PREFIX + line, file=sys.stderr, flush=True)
        else:
            with open(target, "a", encoding="utf-8") as handle:
                handle.write(line + "\n")
    except OSError:
        pass


@contextlib.contextmanager
def _timed(name: str, meta: dict) -> Iterator[dict]:
    started = time.monotonic()
    try:
        yield meta
    finally:
        _emit({"span": name, "seconds": round(time.monotonic() - started, 3), **meta})


def span(name: str, /, **meta):
    """Time the ``with`` block as stage ``name``; extra ``meta`` rides on the line.

    The context manager yields the meta dict, so the block can add facts learned
    inside it (``with span("x") as m: m["n"] = 3``). Off: a no-op that yields a
    throwaway dict, so the same code runs unchanged.
    """
    if profile_target() is None:
        return contextlib.nullcontext({})
    return _timed(name, dict(meta))


def event(name: str, /, **meta) -> None:
    """Record a point fact (no duration) such as a model's token counters."""
    if profile_target() is None:
        return
    _emit({"span": name, "seconds": None, **meta})
