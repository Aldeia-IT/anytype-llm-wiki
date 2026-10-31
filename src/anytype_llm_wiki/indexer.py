"""Incremental indexer: Anytype → chunks → embeddings → Qdrant."""

import fcntl
import json
import os
import tempfile
import uuid
from contextlib import contextmanager
from pathlib import Path

import httpx
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)

from . import config
from .anytype_client import get_object, list_objects, list_spaces
from .chunker import chunk_object, extract_payload_metadata
from .embedder import embed, embed_query
from .wiki.util import object_type_key

# The newest payload-schema version whose migration needed a full re-embed
# (v3: source_type/domain_tags). Later versions add payload-only fields that
# _run_reindex backfills with set_payload (v4: wiki_url).
_LAST_REEMBED_SCHEMA_VERSION = 3
_WIKI_SOURCE_TYPE = "wiki_source"


def _qdrant() -> QdrantClient:
    return QdrantClient(url=config.QDRANT_URL, api_key=config.QDRANT_API_KEY or None)


def _chunk_to_payload(chunk: dict) -> dict:
    """Build the Qdrant point payload from a chunk dict.

    Shared by ``reindex`` and ``reembed_object`` so the payload shape never
    drifts. The optional ``last_modified_date`` is written only when present in
    the chunk (a missing key is cleaner than an explicit null for Qdrant
    range filtering).
    """
    payload = {
        "object_id": chunk["object_id"],
        "space_id": chunk["space_id"],
        "object_name": chunk["object_name"],
        "type_key": chunk["type_key"],
        "heading": chunk["heading"],
        "text": chunk["text"],
    }
    if "last_modified_date" in chunk:
        payload["last_modified_date"] = chunk["last_modified_date"]
    if "source_type" in chunk:
        payload["source_type"] = chunk["source_type"]
    if "domain_tags" in chunk:
        payload["domain_tags"] = chunk["domain_tags"]
    if "wiki_url" in chunk:
        payload["wiki_url"] = chunk["wiki_url"]
    return payload


def build_search_hit(payload: dict | None, score: float) -> dict:
    """Build one search hit dict from a Qdrant point's payload and score.

    The single hit shape shared by every Qdrant search path (today
    ``semantic_search_core``; PR anytype-llm-wiki#59 adopts it too), so the
    hit keys never drift between callers.

    Args:
        payload: the point payload (``with_payload=True``); ``None`` is treated
            as an empty payload.
        score: the similarity score; rounded to 4 decimals.

    Returns:
        A dict with the six base keys ``object_name``, ``object_id``, ``type``
        (from ``type_key``), ``heading``, ``text`` (first 500 chars) and
        ``score``. ``wiki_url`` is added only when the payload carries a
        non-empty one (sources ingested from a URL, Aldeia-IT/aldeia-box#1413);
        otherwise the key is absent. ``source_type`` and ``domain_tags`` are
        filters only and never appear in a hit.
    """
    payload = payload or {}
    hit = {
        "object_name": payload.get("object_name", ""),
        "object_id": payload.get("object_id", ""),
        "type": payload.get("type_key", ""),
        "heading": payload.get("heading", ""),
        "text": (payload.get("text") or "")[:500],
        "score": round(score, 4),
    }
    wiki_url = payload.get("wiki_url")
    if isinstance(wiki_url, str) and wiki_url:
        hit["wiki_url"] = wiki_url
    return hit


def _ensure_payload_indexes(client: QdrantClient) -> None:
    """Create payload indexes used by the metadata filters.

    Idempotent; called once per full ``reindex``, never on the per-object
    ``reembed_object`` hot path. ``last_modified_date`` is a DATETIME index so
    ``DatetimeRange`` filters resolve efficiently.
    """
    from qdrant_client.models import PayloadSchemaType

    create_index = getattr(client, "create_payload_index", None)
    if create_index is None:
        return
    for field, schema in [
        ("type_key", PayloadSchemaType.KEYWORD),
        ("space_id", PayloadSchemaType.KEYWORD),
        ("last_modified_date", PayloadSchemaType.DATETIME),
        ("source_type", PayloadSchemaType.KEYWORD),  # NEW in #336
        ("domain_tags", PayloadSchemaType.KEYWORD),  # NEW in #336
    ]:
        create_index(config.QDRANT_COLLECTION, field, field_schema=schema)


def semantic_search_core(
    query: str,
    space_id: str | None = None,
    types: list[str] | None = None,
    ingested_after: str | None = None,
    ingested_before: str | None = None,
    source_type: list[str] | None = None,
    domain_tags: list[str] | None = None,
    limit: int = 10,
) -> list[dict]:
    """Search Anytype object chunks by semantic similarity (shared core).

    Extracted from the v0.1 ``semantic_search`` MCP tool so both that tool and
    ``wiki/query.py`` Tier-2 retrieval share one implementation.

    Filter construction (Decision 2 — nested AND-of-OR):
      - ``space_id`` (when given) is a top-level ``must`` condition (unchanged
        single-condition behaviour).
      - a ``types`` list becomes a NESTED ``should``-group appended to ``must``.
        A nested filter inside ``must`` is a hard requirement that >=1 of its
        conditions match, i.e. "space AND (type in list)". ``min_should`` is NOT
        used (it is typed ``Optional[MinShould]`` and would raise a Pydantic
        ValidationError if set to an int).

    Returns a list of result dicts built by ``build_search_hit``: object_name,
    object_id, type, heading, text, score, plus ``wiki_url`` only on hits from
    sources ingested from a URL (absent otherwise). The Qdrant client is built
    via the module-level ``_qdrant()`` factory and the collection name is read
    from ``config.QDRANT_COLLECTION`` so tests can monkeypatch both.
    """
    from qdrant_client.models import DatetimeRange, MatchAny

    vector = embed_query(query)
    client = _qdrant()

    must: list = []
    if space_id:
        must.append(FieldCondition(key="space_id", match=MatchValue(value=space_id)))
    if types:
        must.append(
            Filter(
                should=[
                    FieldCondition(key="type_key", match=MatchValue(value=t))
                    for t in types
                ]
            )
        )
    if ingested_after or ingested_before:
        must.append(
            FieldCondition(
                key="last_modified_date",
                range=DatetimeRange(
                    gte=ingested_after or None,
                    lte=ingested_before or None,
                ),
            )
        )
    if source_type:
        must.append(
            FieldCondition(key="source_type", match=MatchAny(any=source_type))
        )
    if domain_tags:
        must.append(
            FieldCondition(key="domain_tags", match=MatchAny(any=domain_tags))
        )
    search_filter = Filter(must=must) if must else None

    results = client.query_points(
        collection_name=config.QDRANT_COLLECTION,
        query=vector,
        query_filter=search_filter,
        limit=limit,
        with_payload=True,
    )

    return [build_search_hit(r.payload, r.score) for r in results.points]


def _ensure_collection(client: QdrantClient) -> None:
    collections = [c.name for c in client.get_collections().collections]
    if config.QDRANT_COLLECTION not in collections:
        client.create_collection(
            collection_name=config.QDRANT_COLLECTION,
            vectors_config=VectorParams(size=config.EMBED_DIMS, distance=Distance.COSINE),
        )


def _load_state() -> dict:
    if config.INDEX_STATE_FILE.exists():
        return json.loads(config.INDEX_STATE_FILE.read_text())
    return {}


def _save_state(state: dict) -> None:
    config.INDEX_STATE_DIR.mkdir(parents=True, exist_ok=True)
    # Atomic write: serialize to a temp file in the same directory, fsync, then
    # os.replace() (atomic rename on POSIX). A crash mid-write can no longer leave
    # a truncated/corrupt state.json that would make every future _load_state raise
    # on json.loads and block all reindexing until the file is deleted by hand.
    fd, tmp_path = tempfile.mkstemp(
        dir=str(config.INDEX_STATE_DIR), prefix=".state-", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w") as f:
            f.write(json.dumps(state, indent=2))
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, config.INDEX_STATE_FILE)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _get_last_modified(obj: dict) -> str | None:
    """Extract last_modified_date from object properties."""
    for prop in obj.get("properties", []):
        if prop.get("key") == "last_modified_date":
            return prop.get("date")
    return None


@contextmanager
def _reindex_lock():
    """Non-blocking advisory lock serializing reindex runs on this host.

    Every reindex path — the scoped auto-reindex fired after each
    wiki_ingest/wiki_remember and the full unscoped cron reindex — reads and
    rewrites the shared state.json, so two concurrent runs can race that write
    (lost update). The lock file lives beside the state file. Yields True when
    acquired, False when another reindex already holds it (the caller skips; the
    in-flight or next reindex re-scans and self-heals, so nothing is permanently
    missed).
    """
    config.INDEX_STATE_DIR.mkdir(parents=True, exist_ok=True)
    lock_path = config.INDEX_STATE_DIR / "reindex.lock"
    fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        yield True
    finally:
        os.close(fd)


def reindex(space_id: str | None = None) -> dict:
    """Run an incremental reindex, serialized by a host-local advisory lock.

    Skips (returns zeroed stats with ``skipped=True``) when another reindex is
    already running rather than racing the shared state.json write.
    """
    with _reindex_lock() as acquired:
        if not acquired:
            return {
                "spaces": 0,
                "objects_checked": 0,
                "objects_indexed": 0,
                "objects_removed": 0,
                "chunks": 0,
                "payload_backfilled": 0,
                "payload_backfill_errors": 0,
                "skipped": True,
                "reason": "reindex_in_progress",
            }
        return _run_reindex(space_id)


def _run_reindex(space_id: str | None = None) -> dict:
    """Run incremental reindex. Returns stats."""
    client = _qdrant()
    _ensure_collection(client)
    _ensure_payload_indexes(client)
    state = _load_state()

    # Forced-backfill migration: when the code payload-schema version exceeds the
    # version stored in the state file, backfill the new payload field(s) once.
    # Stored <= 2 (before source_type/domain_tags) re-embeds every object.
    # Stored 3 needs only wiki_url (v4, Aldeia-IT/aldeia-box#1413), which is a
    # payload-only update: unchanged URL sources get set_payload, no re-embed.
    # The marker is stamped only after a successful unscoped run (see below).
    stored_schema = state.get("_payload_schema_version", 1)
    force_full = (
        stored_schema < _LAST_REEMBED_SCHEMA_VERSION
        and config.PAYLOAD_SCHEMA_VERSION > stored_schema
    )
    backfill_wiki_url = (
        stored_schema == _LAST_REEMBED_SCHEMA_VERSION
        and config.PAYLOAD_SCHEMA_VERSION > stored_schema
    )

    spaces = list_spaces() if not space_id else [{"id": space_id}]
    stats = {
        "spaces": 0, "objects_checked": 0, "objects_indexed": 0,
        "objects_removed": 0, "chunks": 0, "payload_backfilled": 0,
        "payload_backfill_errors": 0,
    }

    for space in spaces:
        sid = space["id"]
        stats["spaces"] += 1
        space_state = state.get(sid, {})
        objects = list_objects(sid)
        current_ids = set()

        for obj_summary in objects:
            oid = obj_summary["id"]
            current_ids.add(oid)
            stats["objects_checked"] += 1

            last_mod = _get_last_modified(obj_summary) or "unknown"
            if not force_full and space_state.get(oid) == last_mod:
                # unchanged
                if backfill_wiki_url:
                    try:
                        if _backfill_wiki_url(client, sid, obj_summary):
                            stats["payload_backfilled"] += 1
                    except (httpx.HTTPError, LookupError):
                        # One failed fetch (object deleted since the list, a
                        # transient 5xx) must not abort the reindex. Count it;
                        # the marker stays unstamped so the next run retries.
                        stats["payload_backfill_errors"] += 1
                continue

            # Fetch full object with markdown
            obj = get_object(sid, oid)
            chunks = chunk_object(obj)

            if not chunks:
                continue

            # Delete old vectors for this object
            _delete_object_vectors(client, oid)

            # Embed and upsert
            texts = [c["text"] for c in chunks]
            vectors = embed(texts)

            points = [
                PointStruct(
                    id=str(
                        uuid.uuid5(
                            uuid.NAMESPACE_URL,
                            f"{chunk['object_id']}:{i}:{chunk['heading']}",
                        )
                    ),
                    vector=vec,
                    payload=_chunk_to_payload(chunk),
                )
                for i, (chunk, vec) in enumerate(zip(chunks, vectors))
            ]

            client.upsert(collection_name=config.QDRANT_COLLECTION, points=points)
            space_state[oid] = last_mod
            stats["objects_indexed"] += 1
            stats["chunks"] += len(points)

        # Remove vectors for deleted objects
        removed_ids = set(space_state.keys()) - current_ids
        for oid in removed_ids:
            _delete_object_vectors(client, oid)
            del space_state[oid]
            stats["objects_removed"] += 1

        state[sid] = space_state

    # Advance the global payload-schema marker only after a full-corpus
    # (unscoped) reindex. A single-space reindex auto-fires after every
    # wiki_ingest/wiki_remember (WIKI_AUTO_REINDEX); advancing the marker on a
    # scoped run would backfill only that one space then permanently strand
    # every other space on the old payload (force_full would never trigger
    # for them again). A scoped reindex still backfills its named space.
    # A run whose wiki_url backfill hit fetch errors leaves the marker too, so
    # the next unscoped run retries the backfill.
    if space_id is None and stats["payload_backfill_errors"] == 0:
        state["_payload_schema_version"] = config.PAYLOAD_SCHEMA_VERSION
    _save_state(state)
    return stats


def _backfill_wiki_url(client: QdrantClient, space_id: str, obj_summary: dict) -> bool:
    """Set ``wiki_url`` on an unchanged wiki_source's points, payload only (v3 -> v4).

    Only ``wiki_source`` objects are fetched: the list summary's type (a
    ``type.key`` dict or a plain string) decides when present; otherwise the
    full object is fetched and its type checked. The url is read with the
    chunker's ``extract_payload_metadata`` (``scrub_url_secrets``), and written with ``set_payload`` filtered on
    ``object_id``: no embed, upsert or delete, and the index state is untouched.

    Args:
        client: Qdrant client.
        space_id: space of the object.
        obj_summary: the object's ``list_objects`` summary.

    Returns:
        True when a payload was set, False when the object is not a wiki_source
        or carries no ``wiki_url``.
    """
    summary_type = object_type_key(obj_summary)
    if summary_type and summary_type != _WIKI_SOURCE_TYPE:
        return False
    obj = get_object(space_id, obj_summary["id"])
    if object_type_key(obj) != _WIKI_SOURCE_TYPE:
        return False
    wiki_url = extract_payload_metadata(obj).get("wiki_url")
    if not wiki_url:
        return False
    client.set_payload(
        collection_name=config.QDRANT_COLLECTION,
        payload={"wiki_url": wiki_url},
        points=_object_id_filter(obj_summary["id"]),
    )
    return True


def reembed_object(space_id: str, object_id: str, obj: dict) -> dict:
    """Force a re-embed of a single object (V2-fail bypass / update path).

    Object-scoped: delete the object's existing Qdrant points by object_id,
    then re-chunk + embed + upsert. O(1) in corpus size.
    """
    client = _qdrant()
    _ensure_collection(client)

    chunks = chunk_object(obj)
    _delete_object_vectors(client, object_id)

    if not chunks:
        return {"object_id": object_id, "chunks": 0}

    texts = [c["text"] for c in chunks]
    vectors = embed(texts)

    points = [
        PointStruct(
            id=str(
                uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"{chunk['object_id']}:{i}:{chunk['heading']}",
                )
            ),
            vector=vec,
            payload=_chunk_to_payload(chunk),
        )
        for i, (chunk, vec) in enumerate(zip(chunks, vectors))
    ]

    client.upsert(collection_name=config.QDRANT_COLLECTION, points=points)
    return {"object_id": object_id, "chunks": len(points)}


def _object_id_filter(object_id: str) -> Filter:
    """Return the Qdrant filter that selects every point of one object.

    Args:
        object_id: the Anytype object id stored in the ``object_id`` payload.

    Returns:
        ``Filter(must=[FieldCondition(object_id == object_id)])``.
    """
    return Filter(must=[FieldCondition(key="object_id", match=MatchValue(value=object_id))])


def _delete_object_vectors(client: QdrantClient, object_id: str) -> None:
    """Delete all vectors belonging to an object."""
    client.delete(
        collection_name=config.QDRANT_COLLECTION,
        points_selector=_object_id_filter(object_id),
    )
