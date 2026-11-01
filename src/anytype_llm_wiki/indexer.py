"""Incremental indexer: Anytype → chunks → embeddings → Qdrant."""

import dataclasses
import fcntl
import json
import logging
import os
import re
import tempfile
import threading
import time
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
from .textfold import fold
from .wiki.util import object_type_key

# The newest payload-schema version whose migration needed a full re-embed
# (v3: source_type/domain_tags). Later versions add payload-only fields that
# _run_reindex backfills with set_payload (v4: wiki_url).
_LAST_REEMBED_SCHEMA_VERSION = 3
_WIKI_SOURCE_TYPE = "wiki_source"

logger = logging.getLogger(__name__)

# --- Hybrid retrieval state (Aldeia-IT/aldeia-box#327 D3) ---
# The MCP server is long-lived; the launchd cron runs reindex() in its own
# interpreter. Each space's BM25 index is therefore built lazily on that space's
# first scoped query and invalidated across processes by a per-space version
# stamp in state.json (_bm25_corpus_versions). FastMCP runs sync tools in a
# thread pool, so builds are serialised by _bm25_build_lock; searches read the
# published _SpaceIndex unlocked (it is assigned only when fully built).
_bm25_indexes: "dict[str, _SpaceIndex]" = {}
_bm25_built_versions: dict[str, int] = {}
# Spaces whose last build scrolled zero chunks with no prior index, at that
# version: fresh without an index, so an empty or unknown space_id does not
# re-scroll under the build lock on every query (AC-H8 keeps the index absent).
_bm25_empty_versions: dict[str, int] = {}
_bm25_build_lock = threading.Lock()
_BM25_VERSIONS_KEY = "_bm25_corpus_versions"

_RRF_K = 60
_MIN_CANDIDATE_DEPTH = 50
# D8 score bands: exact name, all-words name, none; plus the first-chunk bonus.
_TIER_OFFSETS = {1: 2.0, 2: 1.0, 0: 0.0}
_FIRST_CHUNK_BONUS = 0.5

# D12 tokenizer: fold, tokens of [a-z0-9] joined by - _ . ', parts of joined
# tokens, stopwords dropped (English and Portuguese). No stemming. Words both
# languages share ("a", "as") are listed once, under English.
_TOKEN_RE = re.compile(r"[a-z0-9]+(?:[-_.'][a-z0-9]+)*")
_TOKEN_JOINER_RE = re.compile(r"[-_.']")
_STOPWORDS = frozenset((
    # English
    "a", "an", "and", "are", "as", "at", "be", "by", "can", "do", "does", "for",
    "from", "has", "have", "how", "in", "is", "it", "its", "of", "on", "or", "that",
    "the", "this", "to", "was", "what", "when", "where", "which", "who", "why",
    "with", "we", "you", "our", "about",
    # Portuguese
    "o", "os", "e", "de", "da", "do", "das", "dos", "em", "no", "na",
    "nos", "nas", "um", "uma", "uns", "umas", "para", "por", "com", "que", "se",
    "ao", "aos", "sua", "seu", "suas", "seus", "ou", "mais", "como", "foi", "era",
))

# D13 name tier: built-in leading title words (overridden by
# config.NAME_TIER_TITLE_WORDS), the non-alphanumeric runs norm() collapses and
# a trailing parenthetical context.
_BUILTIN_TITLE_WORDS = (
    "mestre", "mestra", "contramestre", "contramestra", "contra-mestre",
    "contra-mestra", "professor", "professora",
)
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
_TRAILING_PAREN_RE = re.compile(r"\(([^()]*)\)\s*$")


@dataclasses.dataclass(frozen=True)
class _NameEntry:
    """One object's row in a space's name table (D11, D13).

    ``base`` and ``paren`` are the normalised name without its trailing
    parenthetical and the normalised parenthetical; the leading title word is
    stripped at query time, because ``config.NAME_TIER_TITLE_WORDS`` is read at
    call time.
    """

    name: str
    type_key: str
    base: str
    paren: str  # "" when the name has no trailing parenthetical
    tokens: frozenset[str]  # _tokenize(name), parenthetical included
    positions: tuple[int, ...]  # the object's chunk rows in the index


@dataclasses.dataclass(frozen=True)
class _SpaceIndex:
    """In-memory BM25 index of one space (D3, D11).

    Rows are chunks; every list is parallel to the BM25 corpus rows. Only the
    fusion key, the stored hit payload and the post-fusion filter fields are
    kept, plus the per-object name table.
    """

    bm25: object  # rank_bm25.BM25Okapi
    point_ids: list[str]  # str(point.id), the fusion key
    object_ids: list[str]
    hits: list[dict]  # build_search_hit payloads: text[:500], wiki_url if present
    source_types: list[str]  # "" if absent
    domain_tags: list[list[str]]  # [] if absent
    names: dict[str, _NameEntry]  # object_id -> name table row


def _qdrant() -> QdrantClient:
    return QdrantClient(url=config.QDRANT_URL, api_key=config.QDRANT_API_KEY or None)


def _bump_bm25_corpus_versions(state: dict, space_ids) -> None:
    """Increment each named space's BM25 corpus version inside a loaded state dict.

    Args:
        state: the state dict, saved by the caller in its own write.
        space_ids: the spaces whose chunks changed; empty bumps nothing.
    """
    versions = state.get(_BM25_VERSIONS_KEY)
    if not isinstance(versions, dict):
        versions = {}
    for space_id in space_ids:
        versions[space_id] = int(versions.get(space_id, 0)) + 1
    if versions:
        state[_BM25_VERSIONS_KEY] = versions


def _read_bm25_corpus_version(space_id: str) -> int:
    """Return a space's on-disk BM25 corpus version (0 if absent or unreadable)."""
    try:
        return int(_load_state().get(_BM25_VERSIONS_KEY, {}).get(space_id, 0))
    except Exception:  # noqa: BLE001 - a state read never breaks a query
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
    if "wiki_url" in chunk:
        payload["wiki_url"] = chunk["wiki_url"]
    return payload


def build_search_hit(payload: dict | None, score: float) -> dict:
    """Build one search hit dict from a Qdrant point's payload and score.

    The single hit shape shared by every Qdrant search path (today
    ``semantic_search_core`` and ``hybrid_search_core``), so the hit keys
    never drift between callers.

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
    dense = _dense_search_with_ids(
        query=query,
        space_id=space_id,
        types=types,
        ingested_after=ingested_after,
        ingested_before=ingested_before,
        source_type=source_type,
        domain_tags=domain_tags,
        limit=limit,
    )
    return [build_search_hit(payload, score) for _, payload, score in dense]


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
    drift (Aldeia-IT/aldeia-box#327 D1). Returns ``None`` for a bare call exactly as the inline code
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
) -> list[tuple[str, dict, float]]:
    """Run the dense Qdrant query and keep each point's id (D1).

    ``semantic_search_core`` builds its hits from this list; ``hybrid_search_core``
    also needs the point id, the fusion key. The filter comes from the shared
    ``_build_search_filter``.

    Returns:
        ``(point_id, payload, score)`` per point, best first; ``point_id`` is
        ``str(point.id)`` and a missing payload is ``{}``.
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
    return [(str(r.id), r.payload or {}, r.score) for r in results.points]


def _tokenize(text: str) -> list[str]:
    """Tokenize text for BM25 and the name tier (D12).

    Folds the text (accents dropped, casefolded), takes runs of ``[a-z0-9]``
    joined by ``-``, ``_``, ``.`` or ``'``, adds the parts of each joined token
    ("sg-3" gives ``sg-3``, ``sg``, ``3``) and drops English and Portuguese
    stopwords, parts included. No stemming.

    Args:
        text: any string (``None``-safe: ``""``).

    Returns:
        The tokens in text order; empty for a stopword-only or empty text.
    """
    tokens: list[str] = []
    for token in _TOKEN_RE.findall(fold(text or "")):
        pieces = [token]
        if _TOKEN_JOINER_RE.search(token):
            pieces += _TOKEN_JOINER_RE.split(token)
        tokens.extend(piece for piece in pieces if piece not in _STOPWORDS)
    return tokens


def _norm(text: str) -> str:
    """Fold, collapse every run of non-``[a-z0-9]`` characters to one space, trim (D13)."""
    return _NON_ALNUM_RE.sub(" ", fold(text)).strip()


def _split_name(name: str) -> tuple[str, str]:
    """Return ``(base, paren)``: the normalised name without and the normalised trailing ``(...)``.

    A name that is only a parenthetical keeps its whole normalised text as ``base``.
    """
    match = _TRAILING_PAREN_RE.search(name)
    if not match:
        return _norm(name), ""
    base = _norm(name[: match.start()]) or _norm(name)
    return base, _norm(match.group(1))


def _title_words() -> tuple[str, ...]:
    """The normalised title words, longest first; read from config at call time (D13)."""
    configured = config.NAME_TIER_TITLE_WORDS
    words = _BUILTIN_TITLE_WORDS if configured is None else configured
    return tuple(sorted({w for w in map(_norm, words) if w}, key=len, reverse=True))


def _strip_title(normed: str, titles: tuple[str, ...]) -> str:
    """Remove one leading whole-word title; a text that is only a title stays as it is."""
    for title in titles:
        if normed.startswith(title + " "):
            return normed[len(title) + 1:]
    return normed


def strip_name(text: str) -> str:
    """Return the name-tier key of a name or query (D13).

    Folds, drops a trailing ``(...)`` context, normalises (non-alphanumeric runs
    become one space) and removes one leading title word from
    ``config.NAME_TIER_TITLE_WORDS`` (built-in list when ``None``). "Mestre
    Pastinha (Salvador)" gives ``pastinha``; "Mestre" alone keeps ``mestre``.

    Args:
        text: an object name or a search query.

    Returns:
        The key; ``""`` when the text has no letters or digits.
    """
    return _strip_title(_split_name(text)[0], _title_words())


def strip_display_title(name: str) -> str:
    """Remove one leading title word from a display name, keeping the rest as written.

    The display counterpart of ``strip_name`` (same title list, ``_title_words()``,
    so ``config.NAME_TIER_TITLE_WORDS`` applies): "Mestre Bimba" gives "Bimba",
    "Contra-Mestre Fulano" gives "Fulano", "Mestre Zé do Lenço" gives "Zé do
    Lenço". A name that is only a title ("Mestre", "Mestre (Salvador)"), a name
    without a leading title and a non-string stay as they are.

    Args:
        name: an object name as extracted or given by a caller.

    Returns:
        The name without its leading title word; the input when nothing applies.
    """
    if not isinstance(name, str):
        return name
    base = _split_name(name)[0]
    title = next((t for t in _title_words() if base.startswith(t + " ")), None)
    if title is None:
        return name
    tokens = list(re.finditer(r"[^\W_]+", name))
    needed = len(title.split())
    if len(tokens) <= needed:
        return name
    rest = name[tokens[needed - 1].end():].lstrip(" \t-_.,:;")
    return rest if rest.strip() else name


def _keys_of(base: str, paren: str, titles: tuple[str, ...]) -> set[str]:
    """The D13 keys of a split name: its stripped base and, if any, its stripped parenthetical."""
    keys = {_strip_title(base, titles)}
    if paren:
        keys.add(_strip_title(paren, titles))
    keys.discard("")
    return keys


def name_keys(name: str) -> set[str]:
    """Return the name-tier keys of an object name (D13).

    The key of the name without its trailing ``(...)`` context and, when the
    name has one, the key of the parenthetical itself; each with one leading
    title word removed (``config.NAME_TIER_TITLE_WORDS``, read at call time).
    A query whose ``strip_name`` key is in this set is a tier-1 match.
    "Cobra Mansa (FICA)" gives ``{"cobra mansa", "fica"}``.

    Args:
        name: an object name.

    Returns:
        The set of keys; empty when the name has no letters or digits.
    """
    return _keys_of(*_split_name(name), _title_words())


def _name_tier(entry: "_NameEntry", query_key: str, query_tokens: set[str],
               titles: tuple[str, ...]) -> int:
    """Return 1 (key equality), 2 (every query token in the name) or 0 (D13)."""
    if query_key and query_key in _keys_of(entry.base, entry.paren, titles):
        return 1
    if query_tokens and query_tokens <= entry.tokens:
        return 2
    return 0


def _space_filter(space_id: str) -> Filter:
    """The Qdrant filter selecting every point of one space."""
    return Filter(must=[FieldCondition(key="space_id", match=MatchValue(value=space_id))])


def _build_bm25_index(client: QdrantClient, space_id: str) -> None:
    """Scroll one space and publish its BM25 index and name table (D3, D11).

    A chunk's BM25 document is the D12 tokens of its object name (twice), its
    heading and its full text. An empty scroll keeps the space's prior index
    (WARN); a space never built stays absent. ``ImportError`` and Qdrant errors
    propagate to the caller's fallback (D9).
    """
    from rank_bm25 import BM25Okapi

    t0 = time.monotonic()
    point_ids: list[str] = []
    object_ids: list[str] = []
    hits: list[dict] = []
    source_types: list[str] = []
    domain_tags: list[list[str]] = []
    corpus: list[list[str]] = []
    positions: dict[str, list[int]] = {}
    first_payload: dict[str, dict] = {}

    offset = None
    while True:
        points, offset = client.scroll(
            collection_name=config.QDRANT_COLLECTION,
            scroll_filter=_space_filter(space_id),
            limit=1000,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        for point in points:
            p = point.payload or {}
            object_id = p.get("object_id", "")
            name = p.get("object_name", "") or ""
            text = p.get("text", "") or ""
            hit = {
                "object_name": name,
                "object_id": object_id,
                "type_key": p.get("type_key", ""),
                "heading": p.get("heading", ""),
                "text": text[:500],
            }
            if p.get("wiki_url"):
                hit["wiki_url"] = p["wiki_url"]
            positions.setdefault(object_id, []).append(len(point_ids))
            first_payload.setdefault(object_id, hit)
            point_ids.append(str(point.id))
            object_ids.append(object_id)
            hits.append(hit)
            source_types.append(p.get("source_type", "") or "")
            domain_tags.append(p.get("domain_tags", []) or [])
            name_tokens = _tokenize(name)
            corpus.append(
                name_tokens + name_tokens + _tokenize(p.get("heading", "") or "")
                + _tokenize(text)
            )
        if offset is None:
            break

    if not corpus:
        if space_id in _bm25_indexes:
            logger.warning(
                "bm25_build: empty scroll for space=%s; keeping prior index", space_id
            )
        return

    names = {}
    for object_id, rows in positions.items():
        hit = first_payload[object_id]
        base, paren = _split_name(hit["object_name"])
        names[object_id] = _NameEntry(
            name=hit["object_name"],
            type_key=hit["type_key"],
            base=base,
            paren=paren,
            tokens=frozenset(_tokenize(hit["object_name"])),
            positions=tuple(rows),
        )
    _bm25_indexes[space_id] = _SpaceIndex(
        bm25=BM25Okapi(corpus),
        point_ids=point_ids,
        object_ids=object_ids,
        hits=hits,
        source_types=source_types,
        domain_tags=domain_tags,
        names=names,
    )
    logger.info(
        "bm25_index_built space=%s chunks=%d ms=%d",
        space_id,
        len(corpus),
        int((time.monotonic() - t0) * 1000),
    )


def _ensure_bm25_fresh(space_id: str) -> None:
    """Build a space's index when it is absent or its built version is stale (D3).

    Stale = the space's on-disk version (``_bm25_corpus_versions``) differs from
    the version its index was built against. The check runs unlocked; a build
    takes ``_bm25_build_lock`` and re-checks inside, so concurrent first queries
    build once. The version is read before the scroll and recorded after the
    build, so a bump during a build triggers a rebuild on the next query. A
    space whose build scrolled nothing (and had no prior index) is recorded in
    ``_bm25_empty_versions`` and counts as fresh at that version, so it is not
    re-scrolled on every query.
    """

    def is_fresh(version: int) -> bool:
        if space_id in _bm25_indexes:
            return _bm25_built_versions.get(space_id) == version
        return _bm25_empty_versions.get(space_id) == version

    if is_fresh(_read_bm25_corpus_version(space_id)):
        return
    with _bm25_build_lock:
        version = _read_bm25_corpus_version(space_id)
        if is_fresh(version):
            return
        _build_bm25_index(_qdrant(), space_id)  # may raise; caller falls back (D9)
        _bm25_built_versions[space_id] = version
        if space_id in _bm25_indexes:
            _bm25_empty_versions.pop(space_id, None)
        else:
            _bm25_empty_versions[space_id] = version


def _bm25_search(idx: _SpaceIndex, query: str, depth: int) -> tuple[list[float], list[int]]:
    """Score a query against one space's index.

    Returns:
        ``(scores, ranked)``: the BM25 score of every row, and the rows with a
        score above 0, best first (ties: lowest row), at most ``depth`` of them.
    """
    tokens = _tokenize(query)
    if not tokens:
        return [0.0] * len(idx.point_ids), []
    scores = idx.bm25.get_scores(tokens).tolist()
    positive = [i for i, score in enumerate(scores) if score > 0.0]
    positive.sort(key=lambda i: -scores[i])  # stable: ties keep row order
    return scores, positive[:depth]


def _rrf_fuse(
    dense_results: list[dict],
    bm25_results: list[dict],
    k: int = _RRF_K,
) -> list[tuple[float, dict]]:
    """Reciprocal rank fusion of two ranked lists, keyed on ``_point_id`` (D6, D10).

    Each list contributes ``1 / (k + rank)`` with a 1-based ``rank``. A chunk in
    both lists appears once (its dense dict is kept) with the summed score.

    Returns:
        ``(rrf_score, chunk)`` pairs, best first; equal scores keep candidate
        order (dense rank, then BM25 rank).
    """
    scores: dict[str, float] = {}
    chunks: dict[str, dict] = {}
    for results in (dense_results, bm25_results):
        for rank, r in enumerate(results, start=1):
            cid = r["_point_id"]
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank)
            chunks.setdefault(cid, r)
    ordered = sorted(scores, key=lambda cid: scores[cid], reverse=True)
    return [(scores[cid], chunks[cid]) for cid in ordered]


def _passes_inline_filters(hit_fields: dict, types, source_type, domain_tags) -> bool:
    """Apply the metadata filters to a chunk Qdrant did not filter (D5).

    Args:
        hit_fields: the chunk's ``type_key``, ``source_type`` and ``domain_tags``.
        types: allowed ``type_key`` values; empty passes.
        source_type: allowed ``source_type`` values; empty passes.
        domain_tags: required tag overlap (any); empty passes.

    Returns:
        True when every non-empty filter matches. Date bounds are not checked
        here: ``hybrid_search_core`` drops every non-dense chunk under a date filter.
    """
    if types and hit_fields.get("type_key") not in types:
        return False
    if source_type and hit_fields.get("source_type") not in source_type:
        return False
    return not domain_tags or bool(set(domain_tags) & set(hit_fields.get("domain_tags") or []))


def _hybrid_rank(
    query: str,
    space_id: str,
    dense: list[tuple[str, dict, float]],
    depth: int,
    limit: int,
    filters: dict,
    date_active: bool,
) -> list[dict] | None:
    """Fuse, tier, gate and score one scoped query (D5 to D8, D10, D13, D14).

    Returns:
        The hits, or ``None`` when the space has no index (cold and empty), in
        which case the caller answers dense-only.
    """
    _ensure_bm25_fresh(space_id)
    idx = _bm25_indexes.get(space_id)
    if idx is None:
        return None
    scores, ranked = _bm25_search(idx, query, depth)

    dense_list = [
        {"_point_id": pid, "object_id": payload.get("object_id", ""), "payload": payload}
        for pid, payload, _ in dense
    ]
    bm25_list = [
        {"_point_id": idx.point_ids[i], "object_id": idx.object_ids[i], "row": i}
        for i in ranked
    ]
    fused = _rrf_fuse(dense_list, bm25_list)

    # D13: tier per object over the space's name table.
    titles = _title_words()
    query_key = strip_name(query)
    query_tokens = set(_tokenize(query_key))
    tiers = {
        object_id: tier
        for object_id, entry in idx.names.items()
        if (tier := _name_tier(entry, query_key, query_tokens, titles))
    }

    # D7: every tier-1 object without a candidate chunk enters with its best BM25 chunk.
    candidate_objects = {chunk["object_id"] for _, chunk in fused}
    entrants = [
        max(idx.names[object_id].positions, key=lambda i: (scores[i], -i))
        for object_id, tier in tiers.items()
        if tier == 1 and object_id not in candidate_objects
    ]
    entrants.sort(key=lambda i: (-scores[i], i))
    fused += [
        (0.0, {"_point_id": idx.point_ids[i], "object_id": idx.object_ids[i], "row": i})
        for i in entrants
    ]

    # D5: gate every non-dense chunk; D8: tier offset + first-chunk bonus + RRF.
    meta_active = any(filters.values())
    scored: list[tuple[float, dict]] = []
    bonused: set[str] = set()
    for rrf, chunk in fused:
        if "payload" in chunk:
            payload = chunk["payload"]
        else:
            row = chunk["row"]
            if date_active:
                continue
            fields = {
                "type_key": idx.hits[row]["type_key"],
                "source_type": idx.source_types[row],
                "domain_tags": idx.domain_tags[row],
            }
            if meta_active and not _passes_inline_filters(fields, **filters):
                continue
            payload = idx.hits[row]
        object_id = chunk["object_id"]
        tier = tiers.get(object_id, 0)
        score = _TIER_OFFSETS[tier] + rrf
        if tier and object_id not in bonused:
            bonused.add(object_id)
            score += _FIRST_CHUNK_BONUS
        scored.append((score, payload))
    scored.sort(key=lambda pair: -pair[0])  # stable: ties keep candidate order
    return [build_search_hit(payload, score) for score, payload in scored[:limit]]


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
    """Name-aware hybrid search: dense, per-space BM25, RRF, name tier (Aldeia-IT/aldeia-box#327).

    Same signature and hit shape as ``semantic_search_core``. The dense query
    runs first and outside any ``try``, so a Qdrant outage propagates (D9). For a
    scoped call, the space's BM25 list (depth ``max(limit * 2, 50)``) is fused
    with the dense list by RRF (k=60) on the point id; objects whose name matches
    the query rank first (tier 1: same name key, tier 2: every query word in the
    name), and a tier-1 object neither list returned still enters (D7). The
    output ``score`` follows the output order (D8): opaque, higher is better, not
    comparable across calls. Output is chunk-level (D10).

    An unscoped call (falsy ``space_id``), a space with no index, or any failure
    on the BM25 side (one WARN ``bm25_fallback``) answers dense-only with cosine
    scores.
    """
    if limit <= 0:
        return []
    depth = max(limit * 2, _MIN_CANDIDATE_DEPTH)
    filters = {"types": types, "source_type": source_type, "domain_tags": domain_tags}

    # Dense FIRST and OUTSIDE the try: a Qdrant outage propagates (D9, AC-H13).
    dense = _dense_search_with_ids(
        query=query,
        space_id=space_id,
        ingested_after=ingested_after,
        ingested_before=ingested_before,
        limit=depth,
        **filters,
    )
    hits = None
    if space_id:
        try:
            hits = _hybrid_rank(
                query, space_id, dense, depth, limit, filters,
                date_active=bool(ingested_after or ingested_before),
            )
        except Exception as e:  # noqa: BLE001 - any BM25-side failure degrades (D9)
            logger.warning("bm25_fallback: %s: %s", type(e).__name__, e)
    if hits is None:
        hits = [build_search_hit(payload, score) for _, payload, score in dense[:limit]]
    return hits


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

    changed_spaces: set[str] = set()  # spaces whose chunks changed (BM25 stamp, D3)
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
                            changed_spaces.add(sid)
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
            changed_spaces.add(sid)

        # Remove vectors for deleted objects
        removed_ids = set(space_state.keys()) - current_ids
        for oid in removed_ids:
            _delete_object_vectors(client, oid)
            del space_state[oid]
            stats["objects_removed"] += 1
            changed_spaces.add(sid)

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
    # Bump the BM25 corpus version of every space this run changed, in the same
    # state write (D3); a no-op run bumps nothing. The server's
    # _ensure_bm25_fresh rebuilds such a space on its next query.
    _bump_bm25_corpus_versions(state, changed_spaces)
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
    then re-chunk + embed + upsert. O(1) in corpus size. Either way (upsert or
    delete only) the space's BM25 corpus version is bumped afterwards.
    """
    client = _qdrant()
    _ensure_collection(client)

    chunks = chunk_object(obj)
    _delete_object_vectors(client, object_id)

    points = []
    if chunks:
        vectors = embed([c["text"] for c in chunks])
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

    # Bump this space's BM25 corpus version (D3). The load/bump/save cycle races
    # the cron _run_reindex's state write, so it runs under _reindex_lock(); when
    # the lock is not acquired the bump is skipped: a lost bump self-heals (the
    # concurrent reindex bumps the space itself), a clobbered state map would not.
    with _reindex_lock() as acquired:
        if acquired:
            state = _load_state()
            _bump_bm25_corpus_versions(state, [space_id])
            _save_state(state)
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
