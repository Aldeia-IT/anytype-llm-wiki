"""Repair of the chain relations stored before typed links (Aldeia-IT/aldeia-box#1486).

Before typed links, ingest wrote each page's entities and concepts into one another's
untyped ``wiki_relations``/``wiki_related`` id lists as a chain (A-B, B-C, ...). Those
ids carry no meaning. This module clears them in a space where that is provably safe:
a space written only by ``wiki_ingest``. ``wiki_remember`` writes real, hand-picked
relations that must never be touched, so the space is classified first from read-only
evidence, and the write path is gated on a digest the operator saw in a dry run.

Safety contract (spec section 9, D13, D16):

- ``classify_space`` and ``plan_chain_repair`` only read.
- ``apply_chain_repair`` runs inside the per-space lock, re-plans, refuses unless the
  space is ``ingest-only`` and the live digest equals the expected one, writes the
  backup (``O_CREAT|O_EXCL``, mode 0600, fsynced) and only then PATCHes.
- Every refusal raises ``RepairRefusedError`` and writes nothing.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone

import httpx

from .links import parse_link
from .util import (
    _rel_key,
    _relation_ids,
    object_type_key,
    scrub_credentials,
    space_ingest_lock,
)
from .wiki_client import WikiClient

_ACTION_KEY = "wiki_action"
_SOURCE_TYPE_KEY = "wiki_source_type"
_LOG_TYPE = "wiki_log"
_SOURCE_TYPE = "wiki_source"
_KIND_BY_TYPE = {"wiki_entity": "entity", "wiki_concept": "concept"}
_MIXED_SOURCE_TYPES = frozenset({"agent", "conversation"})
_LOG_NAME_REMEMBER = "remember"
_LOCK_REF = "repair-chain-relations"


class RepairRefusedError(Exception):
    """A refused repair; writes nothing.

    Attributes:
        reason: ``kind``, ``confirm_list``, ``digest_mismatch`` or ``backup_exists``.
        exit_code: 3 for ``digest_mismatch``, else 2.
        live_digest: the digest of the live plan ("" when none was computed).
        plan: the live ``plan_chain_repair``-shaped result (``{}`` when none).
    """

    def __init__(self, reason: str, message: str, *, live_digest: str = "", plan: dict | None = None):
        super().__init__(message)
        self.reason = reason
        self.exit_code = 3 if reason == "digest_mismatch" else 2
        self.live_digest = live_digest
        self.plan = plan if plan is not None else {}


def _select_name(obj: dict, key: str) -> str:
    """The ``select.name`` of property ``key``; "" for a missing, untagged or text prop."""
    props = obj.get("properties")
    if not isinstance(props, list):
        return ""
    for prop in props:
        if isinstance(prop, dict) and prop.get("key") == key:
            select = prop.get("select")
            if isinstance(select, dict):
                name = select.get("name")
                return name if isinstance(name, str) else ""
            return ""
    return ""


def classify_space(
    objects: list[dict], *, confirmed_untagged: frozenset[str] = frozenset()
) -> dict:
    """Classify a space ``ingest-only``, ``mixed`` or ``unknown`` from read-only evidence.

    Reads only WikiLog ``wiki_action`` and Source ``wiki_source_type`` tags
    (``properties[key].select.name``). ``mixed`` (decided first): a ``remember`` log, a
    WikiLog named ``remember ...`` (tagged or not, confirmed or not), or an
    ``agent``/``conversation`` Source. Else ``unknown``: no ``ingest``/``remember``
    log, or an untagged log/Source not in ``confirmed_untagged``. Else ``ingest-only``.

    Args:
        objects: every object of the space.
        confirmed_untagged: ids of pre-tag logs/Sources the operator confirmed as
            ingest records; they are no longer listed as untagged.

    Returns:
        ``{kind, evidence: {actions, source_types}, untagged}`` where ``untagged`` lists
        ``{id, name, type}`` of the untagged logs/Sources that are not confirmed.
    """
    actions: dict[str, int] = {}
    source_types: dict[str, int] = {}
    untagged: list[dict] = []
    mixed = False
    for obj in objects:
        if not isinstance(obj, dict):
            continue
        type_key = object_type_key(obj)
        if type_key == _LOG_TYPE:
            action = _select_name(obj, _ACTION_KEY)
            name = obj.get("name") or ""
            if action:
                actions[action] = actions.get(action, 0) + 1
            if action == _LOG_NAME_REMEMBER or name.lower().split()[:1] == [_LOG_NAME_REMEMBER]:
                mixed = True
            if not action and obj.get("id") not in confirmed_untagged:
                untagged.append({"id": obj.get("id"), "name": name, "type": type_key})
        elif type_key == _SOURCE_TYPE:
            source_type = _select_name(obj, _SOURCE_TYPE_KEY)
            if source_type:
                source_types[source_type] = source_types.get(source_type, 0) + 1
                if source_type in _MIXED_SOURCE_TYPES:
                    mixed = True
            elif obj.get("id") not in confirmed_untagged:
                untagged.append(
                    {"id": obj.get("id"), "name": obj.get("name") or "", "type": type_key}
                )
    if mixed:
        kind = "mixed"
    elif untagged or not (actions.get("ingest") or actions.get("remember")):
        kind = "unknown"
    else:
        kind = "ingest-only"
    return {
        "kind": kind,
        "evidence": {"actions": actions, "source_types": source_types},
        "untagged": untagged,
    }


def _digest(kind: str, confirmed: frozenset[str], items: list[dict]) -> str:
    """sha256 over the kind, the sorted confirmed ids and the sorted clear pairs."""
    pairs = sorted(f"{i['object_id']}:{c['id']}" for i in items for c in i["clear"])
    payload = json.dumps([kind, sorted(confirmed), pairs], ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _build_items(objects: list[dict]) -> list[dict]:
    """Per entity/concept: the relation ids to clear (chain ids with no link) and keep."""
    nodes = {
        o["id"]: o
        for o in objects
        if isinstance(o, dict) and o.get("id") and object_type_key(o) in _KIND_BY_TYPE
    }
    linked: set[frozenset[str]] = set()
    for obj in objects:
        rec = parse_link(obj)
        if rec is not None:
            linked.add(frozenset((rec.from_id, rec.to_id)))
    items: list[dict] = []
    for oid, obj in nodes.items():
        key = _rel_key(_KIND_BY_TYPE[object_type_key(obj)])
        clear: list[dict] = []
        keep: list[str] = []
        for rid in _relation_ids(obj, key):
            if rid in nodes and frozenset((oid, rid)) not in linked:
                target = nodes[rid]
                clear.append(
                    {"id": rid, "name": target.get("name") or "", "type": object_type_key(target)}
                )
            else:
                keep.append(rid)
        items.append(
            {
                "object_id": oid,
                "name": obj.get("name") or "",
                "type": object_type_key(obj),
                "key": key,
                "clear": clear,
                "keep": keep,
            }
        )
    return items


def _plan_from_objects(
    space_id: str, objects: list[dict], confirmed: frozenset[str]
) -> dict:
    classified = classify_space(objects, confirmed_untagged=confirmed)
    items = _build_items(objects)
    return {
        "space_id": space_id,
        "kind": classified["kind"],
        "evidence": classified["evidence"],
        "untagged": classified["untagged"],
        "plan": items,
        "digest": _digest(classified["kind"], confirmed, items),
        "status": "ok",
        "error": None,
        "warnings": [],
    }


def plan_chain_repair(
    space_id: str, *, confirmed_untagged: frozenset[str] = frozenset()
) -> dict:
    """Read-only plan: classification, per-object relation ids to clear, digest.

    An id is cleared only if it is an entity/concept of the space and no ``wiki_link``
    joins the pair in either direction; every other id (queries, dangling ids, linked
    pairs) is kept. The digest covers the kind, the confirmed ids and the clear pairs.
    Only ``list_objects`` is called.
    """
    confirmed = frozenset(confirmed_untagged)
    client = WikiClient()
    try:
        try:
            objects = client.list_objects(space_id)
        except (httpx.HTTPError, ConnectionError) as exc:
            return {
                "space_id": space_id,
                "kind": "unknown",
                "evidence": {"actions": {}, "source_types": {}},
                "untagged": [],
                "plan": [],
                "digest": "",
                "status": "error",
                "error": scrub_credentials(f"anytype_unavailable: {exc}"),
                "warnings": [],
            }
        return _plan_from_objects(space_id, objects, confirmed)
    finally:
        client.close()


def _write_backup(path: str, payload: dict) -> None:
    """Create ``path`` exclusively (0600), write the payload and fsync it.

    Raises:
        FileExistsError: the path exists, or is a symlink (dangling or not).
        OSError: any other write failure (missing directory, fsync error).
    """
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.flush()
        os.fsync(handle.fileno())


def apply_chain_repair(
    space_id: str,
    *,
    expect_digest: str,
    backup_path: str,
    confirmed_untagged: frozenset[str] = frozenset(),
) -> dict:
    """Clear the planned ids; refuses a non-ingest-only space or a digest mismatch.

    Inside the space lock: lists the space, refuses (``RepairRefusedError``, nothing
    written) when the confirm list is not exactly the untagged ids, the space is not
    ``ingest-only``, the live digest differs from ``expect_digest``, or the backup path
    exists. Then writes and fsyncs the backup and PATCHes each key with ids to clear to
    its ``keep`` list; objects with nothing to clear are not PATCHed.

    Returns:
        ``{space_id, kind, digest, backup_path, objects_modified, ids_cleared, status,
        error, warnings}``; ``status`` is ``ok``, ``partial`` (a PATCH failed) or
        ``error`` (lock busy, Anytype unavailable, backup not written).

    Raises:
        RepairRefusedError: any refusal.
    """
    confirmed = frozenset(confirmed_untagged)
    result: dict = {
        "space_id": space_id,
        "kind": "unknown",
        "digest": "",
        "backup_path": backup_path,
        "objects_modified": 0,
        "ids_cleared": 0,
        "status": "ok",
        "error": None,
        "warnings": [],
    }
    try:
        with space_ingest_lock(space_id, _LOCK_REF):
            client = WikiClient()
            try:
                return _apply_locked(
                    client, space_id, expect_digest, backup_path, confirmed, result
                )
            finally:
                client.close()
    except (RuntimeError, OSError) as exc:
        # RuntimeError: the lock is busy; OSError: the lock file could not be taken.
        result["status"] = "error"
        result["error"] = scrub_credentials(str(exc))
        return result


def _apply_locked(
    client: WikiClient,
    space_id: str,
    expect_digest: str,
    backup_path: str,
    confirmed: frozenset[str],
    result: dict,
) -> dict:
    try:
        objects = client.list_objects(space_id)
    except (httpx.HTTPError, ConnectionError) as exc:
        result["status"] = "error"
        result["error"] = scrub_credentials(f"anytype_unavailable: {exc}")
        return result

    live = _plan_from_objects(space_id, objects, confirmed)
    result["kind"] = live["kind"]
    result["digest"] = live["digest"]
    all_untagged = {u["id"] for u in classify_space(objects)["untagged"]}
    if confirmed != all_untagged:
        raise RepairRefusedError(
            "confirm_list",
            "the confirm list must equal the untagged ids of the space",
            live_digest=live["digest"],
            plan=live,
        )
    if live["kind"] != "ingest-only":
        raise RepairRefusedError(
            "kind",
            f"space is {live['kind']}, not ingest-only",
            live_digest=live["digest"],
            plan=live,
        )
    if live["digest"] != expect_digest:
        raise RepairRefusedError(
            "digest_mismatch",
            "the live plan digest differs from --expect-digest",
            live_digest=live["digest"],
            plan=live,
        )
    if os.path.lexists(backup_path):
        raise RepairRefusedError(
            "backup_exists",
            f"backup path already exists: {backup_path}",
            live_digest=live["digest"],
            plan=live,
        )

    todo = [i for i in live["plan"] if i["clear"]]
    stored = {o["id"]: o for o in objects if isinstance(o, dict) and o.get("id")}
    backup = {
        "space_id": space_id,
        "digest": live["digest"],
        "written_at": datetime.now(timezone.utc).isoformat(),
        "objects": [
            {
                "object_id": i["object_id"],
                "key": i["key"],
                "prior_ids": _relation_ids(stored[i["object_id"]], i["key"]),
            }
            for i in todo
        ],
    }
    try:
        _write_backup(backup_path, backup)
    except FileExistsError:
        raise RepairRefusedError(
            "backup_exists",
            f"backup path already exists: {backup_path}",
            live_digest=live["digest"],
            plan=live,
        ) from None
    except OSError as exc:
        result["status"] = "error"
        result["error"] = scrub_credentials(f"backup_write_failed: {exc}")
        return result

    for item in todo:
        try:
            client.update_object(
                space_id,
                item["object_id"],
                {"properties": [{"key": item["key"], "objects": list(item["keep"])}]},
            )
        except (httpx.HTTPError, KeyError, ValueError, TypeError) as exc:
            result["status"] = "partial"
            result["warnings"].append(
                scrub_credentials(f"repair_failed {item['object_id']}: {exc}")
            )
            continue
        result["objects_modified"] += 1
        result["ids_cleared"] += len(item["clear"])
    return result
