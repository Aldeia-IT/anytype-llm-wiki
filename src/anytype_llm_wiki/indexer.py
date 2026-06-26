"""Incremental indexer: Anytype → chunks → embeddings → Qdrant."""

import dataclasses
import fcntl
import json
import logging
import os
import tempfile
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from . import config
from .anytype_client import get_object, list_objects, list_spaces
from .chunker import chunk_object
from .embedder import embed, embed_query

logger = logging.getLogger(__name__)

# --- #327 hybrid retrieval: in-memory BM25 index + cross-process staleness ---
# The MCP server is a long-lived single-process stdio service; the launchd cron
# runs reindex() in a separate short-lived interpreter. Module-level BM25 state
# therefore never crosses the process boundary, so the index is built lazily on
# first use and invalidated across processes via a monotonic bm25_corpus_version
# stamp in state.json (see spec §4 D3). Single-process / no concurrent request
# handling, so the module state needs no lock.
_bm25_index: "_BM25Index | None" = None
_bm25_built_version: int = -1  # corpus version this process's index was built against


@dataclasses.dataclass
class _BM25Index:
    """In-memory BM25 index over all Qdrant chunks.

    Stores only the fields used downstream (the fusion key, the six output
    fields, and the three post-fusion filter fields), not the whole payload
    (spec §4 D3 / SG-1). All lists are parallel to the BM25 corpus rows.
    """

    bm25: object  # rank_bm25.BM25Okapi instance
    point_ids: list[str]  # str(point.id) — the RRF fusion key
    object_ids: list[str]
    object_names: list[str]
    type_keys: list[str]
    headings: list[str]
    texts: list[str]  # payload["text"][:500]
    space_ids: list[str]
    source_types: list[str]  # "" if absent
    domain_tags: list[list[str]]  # [] if absent


def _qdrant() -> QdrantClient:
    return QdrantClient(url=config.QDRANT_URL, api_key=config.QDRANT_API_KEY or None)


def _bump_bm25_corpus_version(state: dict) -> int:
    """Increment the monotonic corpus version inside an already-loaded state dict."""
    state["bm25_corpus_version"] = int(state.get("bm25_corpus_version", 0)) + 1
    return state["bm25_corpus_version"]


def _read_bm25_corpus_version() -> int:
    """Cheap on-disk read of the corpus version (0 if absent / unreadable)."""
    try:
        return int(_load_state().get("bm25_corpus_version", 0))
    except Exception:  # noqa: BLE001 — never let a state read break a query
        return 0


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
    return payload


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

    Returns a list of result dicts (object_name, object_id, type, heading, text,
    score). The Qdrant client is built via the module-level ``_qdrant()`` factory
    and the collection name is read from ``config.QDRANT_COLLECTION`` so tests can
    monkeypatch both.
    """
    vector = embed_query(query)
    client = _qdrant()

    search_filter = _build_search_filter(
        space_id=space_id,
        types=types,
        ingested_after=ingested_after,
        ingested_before=ingested_before,
        source_type=source_type,
        domain_tags=domain_tags,
    )

    results = client.query_points(
        collection_name=config.QDRANT_COLLECTION,
        query=vector,
        query_filter=search_filter,
        limit=limit,
        with_payload=True,
    )

    return [
        {
            "object_name": r.payload.get("object_name", ""),
            "object_id": r.payload.get("object_id", ""),
            "type": r.payload.get("type_key", ""),
            "heading": r.payload.get("heading", ""),
            "text": r.payload.get("text", "")[:500],
            "score": round(r.score, 4),
        }
        for r in results.points
    ]


def _build_search_filter(
    space_id: str | None = None,
    types: list[str] | None = None,
    ingested_after: str | None = None,
    ingested_before: str | None = None,
    source_type: list[str] | None = None,
    domain_tags: list[str] | None = None,
):
    """Construct the Qdrant ``query_filter`` (``Filter | None``) for the dense paths.

    Extracted VERBATIM from ``semantic_search_core`` so ``semantic_search_core``
    and ``_dense_search_with_ids`` share one filter implementation and can never
    drift (spec §5.4). Returns ``None`` for a bare call exactly as the inline code
    did, preserving the AC-H-REG1 ``query_filter is None`` contract.
    """
    from qdrant_client.models import (
        DatetimeRange,
        FieldCondition,
        Filter,
        MatchAny,
        MatchValue,
    )

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
    return Filter(must=must) if must else None


def _dense_search_with_ids(
    query: str,
    space_id: str | None = None,
    types: list[str] | None = None,
    ingested_after: str | None = None,
    ingested_before: str | None = None,
    source_type: list[str] | None = None,
    domain_tags: list[str] | None = None,
    limit: int = 10,
) -> list[dict]:
    """Like ``semantic_search_core`` but each dict also carries ``_point_id``.

    The Qdrant ``point.id`` is the RRF fusion key (spec §4 D3 / BL-1); the public
    ``semantic_search_core`` deliberately omits it, so this thin sibling reproduces
    the same query/filter via the shared ``_build_search_filter`` helper and adds
    ``_point_id = str(r.id)`` to each result dict.
    """
    vector = embed_query(query)
    client = _qdrant()

    search_filter = _build_search_filter(
        space_id=space_id,
        types=types,
        ingested_after=ingested_after,
        ingested_before=ingested_before,
        source_type=source_type,
        domain_tags=domain_tags,
    )

    results = client.query_points(
        collection_name=config.QDRANT_COLLECTION,
        query=vector,
        query_filter=search_filter,
        limit=limit,
        with_payload=True,
    )

    return [
        {
            "_point_id": str(r.id),
            "object_name": r.payload.get("object_name", ""),
            "object_id": r.payload.get("object_id", ""),
            "type": r.payload.get("type_key", ""),
            "heading": r.payload.get("heading", ""),
            "text": r.payload.get("text", "")[:500],
            "score": round(r.score, 4),
        }
        for r in results.points
    ]


def _build_bm25_index(client: QdrantClient) -> None:
    """Scroll all Qdrant chunks and (re)build the in-memory BM25 index.

    Replaces the prior index only when the new corpus is non-empty; on a
    transient empty scroll it leaves the prior index intact and logs a warning
    (SF-3). Silently no-ops if rank_bm25 is not importable (graceful degradation).
    """
    global _bm25_index

    try:
        from rank_bm25 import BM25Okapi
    except ImportError:
        logger.warning("bm25_fallback: rank_bm25 not importable")
        return

    t0 = time.monotonic()
    point_ids, object_ids, object_names, type_keys = [], [], [], []
    headings, texts, space_ids, source_types, domain_tags = [], [], [], [], []
    corpus: list[list[str]] = []

    offset = None
    while True:
        results, next_offset = client.scroll(
            collection_name=config.QDRANT_COLLECTION,
            limit=1000,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        for point in results:
            p = point.payload or {}
            point_ids.append(str(point.id))
            object_ids.append(p.get("object_id", ""))
            object_names.append(p.get("object_name", ""))
            type_keys.append(p.get("type_key", ""))
            headings.append(p.get("heading", ""))
            texts.append((p.get("text", "") or "")[:500])
            space_ids.append(p.get("space_id", ""))
            source_types.append(p.get("source_type", "") or "")
            domain_tags.append(p.get("domain_tags", []) or [])
            corpus.append((p.get("text", "") or "").lower().split())
        if next_offset is None:
            break
        offset = next_offset

    if not corpus:
        # Distinguish transient-empty from genuinely-empty: never null a good
        # index on an empty scroll. If we have never built one, stay None.
        if _bm25_index is not None:
            logger.warning(
                "bm25_build: empty scroll; keeping prior index (%d chunks)",
                len(_bm25_index.point_ids),
            )
        return

    _bm25_index = _BM25Index(
        bm25=BM25Okapi(corpus),
        point_ids=point_ids,
        object_ids=object_ids,
        object_names=object_names,
        type_keys=type_keys,
        headings=headings,
        texts=texts,
        space_ids=space_ids,
        source_types=source_types,
        domain_tags=domain_tags,
    )
    logger.info(
        "bm25_index_built chunks=%d ms=%d",
        len(corpus),
        int((time.monotonic() - t0) * 1000),
    )


def _ensure_bm25_fresh() -> None:
    """Build or rebuild the module-level BM25 index iff it is missing or stale.

    Stale = the on-disk bm25_corpus_version differs from the version this process
    last built against. Cheap (one small JSON read) on the hot path; the actual
    scroll+build runs only on a version change or cold start.
    """
    global _bm25_built_version
    on_disk = _read_bm25_corpus_version()
    if _bm25_index is not None and _bm25_built_version == on_disk:
        return
    _build_bm25_index(_qdrant())  # may raise; caller wraps in try/except
    _bm25_built_version = on_disk  # only advance after a successful build


def _bm25_search(
    query: str, space_id: str | None = None, limit: int = 20
) -> list[dict]:
    """Top-``limit`` BM25-scored chunks as result dicts.

    Each dict carries ``_point_id`` (the RRF fusion key) and the payload fields
    the post-fusion filter gate needs (``source_type`` / ``domain_tags``, BL-2).
    Applies only the ``space_id`` filter in-memory (the primary safety filter).
    Raises ``RuntimeError`` if no index has been built.
    """
    idx = _bm25_index
    if idx is None:
        raise RuntimeError("BM25 index not built")
    tokens = query.lower().split()
    scores = idx.bm25.get_scores(tokens)  # ndarray, len == corpus
    pairs = [
        (scores[i], i)
        for i in range(len(scores))
        if (space_id is None or idx.space_ids[i] == space_id)
    ]
    pairs.sort(key=lambda x: x[0], reverse=True)
    out = []
    for score, i in pairs[:limit]:
        if score <= 0.0:
            break  # 0 == no token match; ranked list ends here
        out.append(
            {
                "_point_id": idx.point_ids[i],
                "object_name": idx.object_names[i],
                "object_id": idx.object_ids[i],
                "type": idx.type_keys[i],
                "heading": idx.headings[i],
                "text": idx.texts[i],
                "score": round(float(score), 4),  # raw BM25; overwritten by RRF
                "source_type": idx.source_types[i],  # BL-2: for the filter gate
                "domain_tags": idx.domain_tags[i],  # BL-2: for the filter gate
            }
        )
    return out


def _rrf_fuse(
    dense_results: list[dict],
    bm25_results: list[dict],
    k: int = 60,
) -> list[tuple[float, dict]]:
    """RRF (Cormack et al. 2009) over two ranked lists, keyed on ``_point_id``.

    Returns ``(rrf_score, chunk)`` pairs ordered by descending RRF score so the
    caller can stamp ``score = rrf_score`` (D8). Dedups by ``_point_id`` (D10).
    """
    scores: dict[str, float] = {}
    chunks: dict[str, dict] = {}
    for rank, r in enumerate(dense_results):
        cid = r["_point_id"]
        scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank + 1)
        chunks.setdefault(cid, r)
    for rank, r in enumerate(bm25_results):
        cid = r["_point_id"]
        scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank + 1)
        chunks.setdefault(cid, r)
    ordered = sorted(scores, key=lambda cid: scores[cid], reverse=True)
    return [(scores[cid], chunks[cid]) for cid in ordered]


def _passes_inline_filters(r, types, source_type, domain_tags) -> bool:
    """Post-fusion filter gate for BM25-only chunks (spec §7.3).

    Dense chunks are exempt (Qdrant already filtered them). Date filters are
    handled separately in ``hybrid_search_core`` (D5).
    """
    if types and r.get("type") not in types:
        return False
    if source_type and r.get("source_type") not in source_type:
        return False
    if domain_tags:
        obj_tags = r.get("domain_tags") or []
        if not any(t in obj_tags for t in domain_tags):
            return False
    return True


def hybrid_search_core(
    query: str,
    space_id: str | None = None,
    types: list[str] | None = None,
    ingested_after: str | None = None,
    ingested_before: str | None = None,
    source_type: list[str] | None = None,
    domain_tags: list[str] | None = None,
    limit: int = 10,
) -> list[dict]:
    """Hybrid dense+sparse retrieval with app-level RRF fusion (spec §6.7).

    Identical signature to ``semantic_search_core``. Calls the dense path FIRST
    and OUTSIDE the try so a Qdrant outage propagates (D9, AC-H13); the BM25 path
    is wrapped so any failure degrades gracefully to dense-only with the original
    cosine score preserved (D8). The output ``score`` is the RRF score in the
    fused path; internal ``_point_id`` keys are stripped.
    """
    if limit <= 0:
        return []
    fetch_limit = limit * 2

    # Dense FIRST and OUTSIDE the try: Qdrant outage must propagate (D9).
    dense_results = _dense_search_with_ids(
        query=query,
        space_id=space_id,
        types=types,
        ingested_after=ingested_after,
        ingested_before=ingested_before,
        source_type=source_type,
        domain_tags=domain_tags,
        limit=fetch_limit,
    )

    try:
        _ensure_bm25_fresh()
        bm25_results = _bm25_search(query, space_id=space_id, limit=fetch_limit)
    except Exception as e:  # noqa: BLE001
        logger.warning("bm25_fallback: %s", e)
        bm25_results = []

    if not bm25_results:
        for r in dense_results:
            r.pop("_point_id", None)
        return dense_results[:limit]  # dense-only: original cosine scores kept (D8)

    fused = _rrf_fuse(dense_results, bm25_results, k=60)  # [(rrf_score, chunk)]

    dense_ids = {r["_point_id"] for r in dense_results}
    date_active = bool(ingested_after or ingested_before)
    meta_active = bool(types or source_type or domain_tags)

    out = []
    for rrf_score, r in fused:
        bm25_only = r["_point_id"] not in dense_ids
        if bm25_only and date_active:
            continue  # D5: drop BM25-only under date filter
        if (
            bm25_only
            and meta_active
            and not _passes_inline_filters(
                r, types=types, source_type=source_type, domain_tags=domain_tags
            )
        ):
            continue
        r["score"] = round(rrf_score, 6)  # D8: RRF score IS the output score
        r.pop("_point_id", None)
        out.append(r)
        if len(out) >= limit:
            break
    return out


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
    # version stored in the state file, re-embed every object once to backfill the
    # new payload field(s). The marker is stamped only after a successful run.
    stored_schema = state.get("_payload_schema_version", 1)
    force_full = config.PAYLOAD_SCHEMA_VERSION > stored_schema

    spaces = list_spaces() if not space_id else [{"id": space_id}]
    stats = {"spaces": 0, "objects_checked": 0, "objects_indexed": 0, "objects_removed": 0, "chunks": 0}

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
                continue  # unchanged

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
    if space_id is None:
        state["_payload_schema_version"] = config.PAYLOAD_SCHEMA_VERSION
    # Bump the cross-process BM25 staleness stamp once per reindex run (incl.
    # deletions and scoped runs), in the SAME state write (spec §6.2). The
    # server's _ensure_bm25_fresh reads this to invalidate its in-memory index.
    _bump_bm25_corpus_version(state)
    _save_state(state)
    return stats


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

    # Bump the cross-process BM25 staleness stamp (spec §6.2). The
    # _load_state/_bump/_save_state cycle races the cron _run_reindex's state
    # write, so guard it with a fresh _reindex_lock() (addendum item 1 /
    # CTO-1/INFRA-1): if the lock is NOT acquired, SKIP the bump — a lost bump is
    # self-healing (the concurrent reindex bumps the version itself), whereas a
    # clobbered _payload_schema_version / per-space map would not be. Keeps
    # reembed O(1): no scroll, only a single small state write.
    with _reindex_lock() as acquired:
        if acquired:
            state = _load_state()
            _bump_bm25_corpus_version(state)
            _save_state(state)
    return {"object_id": object_id, "chunks": len(points)}


def _delete_object_vectors(client: QdrantClient, object_id: str) -> None:
    """Delete all vectors belonging to an object."""
    from qdrant_client.models import FieldCondition, Filter, MatchValue

    client.delete(
        collection_name=config.QDRANT_COLLECTION,
        points_selector=Filter(
            must=[FieldCondition(key="object_id", match=MatchValue(value=object_id))]
        ),
    )
