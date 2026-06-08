"""Durable per-space subject work-log (stdlib-only).

The remember/ingest drain consolidates one extracted *subject* at a time, each
under the exclusive per-space ingest lock. Historically a run truncated the
subject list to a fixed cap and **silently dropped** the remainder — unbounded
data loss with no record of what was lost. This module replaces that with a
write-ahead log: every extracted subject is recorded *durably before* the drain
begins, marked done as it is consolidated, and the record is cleared only once
all of its subjects have been processed. If a drain is interrupted (crash, kill,
timeout, lock loss) the next run for that space replays the log and finishes the
outstanding subjects. No subject is ever dropped.

Design notes
------------
- **No new dependency.** Pure stdlib (``json``/``os``/``uuid``). The log is a
  JSONL file per space under ``WIKI_WORKLOG_DIR`` (defaults beside the lock dir,
  the same local-state model the server already uses). It is *not* a database
  and *not* a service.
- **Crash safety.** Each record is a single appended line followed by
  ``flush + os.fsync``. A process that dies mid-append can only corrupt the
  trailing line; the replay skips an unparseable final line. Once a ``begin``
  record is durably written, its subjects survive a crash.
- **Serialization.** Writers always hold the per-space ingest lock (the caller's
  responsibility), so there is never more than one concurrent writer per file.
  ``load_pending`` is a read-only replay and is safe without the lock.
- **Append-only with tombstones.** ``done`` and ``clear`` are appended, never
  rewritten in place. ``compact`` deletes the file once nothing is pending.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid

from . import config

__all__ = [
    "begin",
    "mark_done",
    "clear",
    "load_pending",
    "compact",
    "log_path",
]


def _safe_space_id(space_id: str) -> str:
    """Sanitize ``space_id`` for use in a filename (mirrors space_ingest_lock).

    Replaces every character outside ``[A-Za-z0-9._-]`` with ``_``; an all-unsafe
    id falls back to a short hash so the name is never empty.
    """
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", space_id)
    if not safe:
        safe = hashlib.sha256(space_id.encode("utf-8")).hexdigest()[:16]
    return safe


def _worklog_dir() -> str:
    d = config.worklog_dir()
    os.makedirs(d, mode=0o700, exist_ok=True)
    # makedirs honors umask; set the mode explicitly afterwards.
    try:
        os.chmod(d, 0o700)
    except OSError:
        pass
    return d


def log_path(space_id: str) -> str:
    """Absolute path of the JSONL work-log for ``space_id``."""
    return os.path.join(_worklog_dir(), f"work-{_safe_space_id(space_id)}.jsonl")


def _append(space_id: str, record: dict) -> None:
    """Append one JSON record as a line, durably (flush + fsync)."""
    path = log_path(space_id)
    line = json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
    fd = os.open(path, os.O_CREAT | os.O_WRONLY | os.O_APPEND, 0o600)
    try:
        os.write(fd, line.encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)


def begin(space_id: str, subjects: list[dict], meta: dict | None = None) -> tuple[str, list[dict]]:
    """Durably record a new batch of subjects to process.

    Each subject dict should carry at least ``name``/``kind``/``facts``. A stable
    per-subject ``id`` is assigned (and returned on the echoed list) so completion
    can be recorded individually. Returns ``(work_id, subjects_with_ids)``.

    The caller MUST hold the per-space ingest lock. The ``begin`` record is
    fsync'd before this returns, so once it returns the subjects are durable.
    """
    work_id = uuid.uuid4().hex
    enriched: list[dict] = []
    for i, subj in enumerate(subjects):
        sid = subj.get("id") or f"{work_id}-{i}"
        item = {
            "id": sid,
            "name": subj.get("name", ""),
            "kind": subj.get("kind", "entity"),
            "facts": subj.get("facts", ""),
        }
        enriched.append(item)
    _append(space_id, {
        "t": "begin",
        "work_id": work_id,
        "subjects": enriched,
        "meta": meta or {},
    })
    # Echo the enriched subjects (with ids) so the caller processes the same ids.
    return work_id, [dict(s) for s in enriched]


def mark_done(space_id: str, work_id: str, subject_id: str) -> None:
    """Durably record that one subject of ``work_id`` has been processed."""
    _append(space_id, {"t": "done", "work_id": work_id, "id": subject_id})


def clear(space_id: str, work_id: str) -> None:
    """Durably tombstone an entire ``work_id`` (all its subjects are accounted for)."""
    _append(space_id, {"t": "clear", "work_id": work_id})


def _replay(space_id: str) -> dict:
    """Replay the JSONL log into in-memory state.

    Returns ``{work_id: {"meta": dict, "subjects": {id: subject}, "done": set,
    "cleared": bool}}``. An unparseable line (e.g. a torn trailing write after a
    crash) is skipped — never fatal.
    """
    path = log_path(space_id)
    state: dict[str, dict] = {}
    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.readlines()
    except FileNotFoundError:
        return state
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except (ValueError, TypeError):
            continue  # torn / partial line — skip
        if not isinstance(rec, dict):
            continue
        wid = rec.get("work_id")
        t = rec.get("t")
        if not wid or not t:
            continue
        entry = state.setdefault(
            wid, {"meta": {}, "subjects": {}, "done": set(), "cleared": False}
        )
        if t == "begin":
            entry["meta"] = rec.get("meta") or {}
            for subj in rec.get("subjects") or []:
                if isinstance(subj, dict) and subj.get("id"):
                    entry["subjects"][subj["id"]] = subj
        elif t == "done":
            sid = rec.get("id")
            if sid:
                entry["done"].add(sid)
        elif t == "clear":
            entry["cleared"] = True
    return state


def load_pending(space_id: str) -> list[dict]:
    """Return subjects recorded but not yet done across all un-cleared batches.

    Each returned dict carries ``id``/``name``/``kind``/``facts`` plus ``_work_id``
    and ``_meta`` so the caller can re-apply the batch's relations/source context.
    Insertion order is preserved (begin order, then per-subject order).
    """
    state = _replay(space_id)
    pending: list[dict] = []
    for wid, entry in state.items():
        if entry["cleared"]:
            continue
        for sid, subj in entry["subjects"].items():
            if sid in entry["done"]:
                continue
            pending.append({
                "id": sid,
                "name": subj.get("name", ""),
                "kind": subj.get("kind", "entity"),
                "facts": subj.get("facts", ""),
                "_work_id": wid,
                "_meta": entry["meta"],
            })
    return pending


def compact(space_id: str) -> None:
    """Delete the log file when nothing is pending (all batches cleared or done).

    A no-op if any subject is still outstanding. Safe to call after every drain.
    """
    if load_pending(space_id):
        return
    try:
        os.remove(log_path(space_id))
    except FileNotFoundError:
        pass
    except OSError:
        pass
