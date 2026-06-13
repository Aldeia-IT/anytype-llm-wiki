---
name: retrieval-metadata-filters-type-tag-scoping
status: SPEC
issue: 323
repo: anytype-llm-wiki
target_repo: anytype-llm-wiki
date: 2026-06-12
author: spec-writer agent
parent_spec: 285-anytype-llm-wiki-v0-4-0-wiki-query-tiered-retrieva
---

# Retrieval: Metadata Filters + Type/Tag Scoping for `wiki_query` / `semantic_search`

**Status:** SPEC
**Date:** 2026-06-12
**Author:** spec-writer agent
**Review rounds:** 1
**Epic:** aldeia-box#140 | **Sibling (deferred fusion half):** aldeia-box#327

---

## 1. Problem Statement

### 1.1 The Payload Gap (Verified Reality)

The ticket (aldeia-box#323) is premised on the belief that Qdrant already stores metadata
(domain tags, source type, dates) in the chunk payload and just needs filter parameters wired
to it. **This premise is only partially correct.**

Verified from `chunker.py:25-94` and `indexer.py:161-168, 218-225`: the Qdrant chunk payload
written today contains **exactly six fields**:

```
object_id | space_id | object_name | type_key | heading | text
```

`domain_tags`, `source_type`, and any date field are **not in the payload**. They exist only as
Anytype object properties and are never read by the indexer or written to Qdrant.

Two filter dimensions the ticket asks for are inert against the real corpus and are **deferred**
to a single follow-up ticket (see §3 D4/D5 and §4):

- **`source_type`** — `wiki_source` objects are created body-less (properties only) and
  `wiki_excerpt` is not in the chunker's text allowlist, so sources produce **zero chunks** and
  never reach Qdrant. A `source_type` filter would return zero for all inputs.
- **`domain_tags`** — `wiki_domain_tags` is never written onto any Anytype object by the
  ingest/remember pipelines (validate-only), so the field never exists to filter on.

Both are the same footgun: an accepted-but-inert parameter that silently returns nothing. v1
ships only the two dimensions that work against the real corpus: **`type`** and **`date`**.

### 1.2 What Works Today

`semantic_search_core` (`indexer.py:20-82`) already builds a conjunctive Qdrant `Filter` for
`space_id` and `types`. `semantic_search` already exposes `types`/`space_id` as MCP params. The
`type` scoping half of this ticket is therefore largely built. The gaps for v1 are: exposing
type scoping on `wiki_query`, adding the `last_modified_date` payload field + a date filter,
payload indexes, input validation, a forced-backfill migration, and tests.

### 1.3 Compliance / Egress Check

Metadata filters are evaluated entirely within Qdrant (local Docker container). No new data
leaves the machine. No new network calls to any external service are introduced. The local-first
posture of `.aldeia/context/compliance.md` is preserved.

---

## 2. Scope

### In Scope

| File | Nature |
|------|--------|
| `src/anytype_llm_wiki/indexer.py` | `semantic_search_core` date filter param; `reindex` payload-schema-version backfill; shared `_chunk_to_payload`; `_ensure_payload_indexes` on the reindex path only |
| `src/anytype_llm_wiki/chunker.py` | Extract `last_modified_date` in `chunk_object`, inject into every chunk |
| `src/anytype_llm_wiki/server.py` | Add `ingested_after`/`ingested_before` to `semantic_search`; add `types`, `ingested_after`, `ingested_before` to `wiki_query` |
| `src/anytype_llm_wiki/wiki/query.py` | Thread filter params into Tier-2 core; module-level Tier-1 predicates (`_passes_type_filter`, `_passes_date_filter`) |
| `src/anytype_llm_wiki/config.py` | `PAYLOAD_SCHEMA_VERSION` constant |
| `tests/test_indexer.py` / `tests/test_chunker.py` / `tests/wiki/test_query.py` | Filter, regression, validation, payload-index, Tier-1 predicate, and migration-backfill tests |

### Out of Scope (v1)

- `source_type` filter — **deferred** (see D4 and Open Decisions for Jan)
- `domain_tags` filter — **deferred** (see D5 and Open Decisions for Jan)
- Filtering by exact source URL or file path
- Filtering by `wiki_last_reviewed` / `wiki_asked_at` dates (trivial follow-on once the pattern
  is established)

---

## 3. Design Decisions

### D1 — `type` Filter: Full, Ship in v1

**Decision:** Expose type scoping on `wiki_query` (it already exists on `semantic_search`). Use
the existing `semantic_search_core` `types` parameter. No payload schema change needed; `type_key`
is already in the payload. Add a `PayloadSchemaType.KEYWORD` index for `type_key` (and `space_id`)
on the reindex path for query performance.

**Rationale:** The filter wire is already built. The only gap is the `wiki_query` tool surface.

**Caller semantics for `wiki_query`:** `types` specifies which wiki type keys the caller wants
included. It intersects with (does NOT replace) the hardcoded `_WIKI_TYPE_KEYS` tuple
`("wiki_entity", "wiki_concept", "wiki_comparison", "wiki_query")`. `types=["wiki_entity"]` gets
only entities; `types=["wiki_entity", "wiki_source"]` is silently narrowed to `["wiki_entity"]`
(non-wiki types dropped). An empty intersection is an error (see §9.2). When `types` is omitted,
`wiki_query` passes the full `_WIKI_TYPE_KEYS` to the core (unchanged default behavior).

### D2 — Date Filter: Ship in v1 via Additive Payload Extension

**Decision:** Add a `last_modified_date` payload field (ISO-8601 string) and expose
`ingested_after` / `ingested_before` MCP params that translate to a `DatetimeRange` condition on
`last_modified_date`.

**Date field selection — `last_modified_date`:** It is universal (all object types), already read
by `indexer._get_last_modified` (`indexer.py:105-110`), and system-managed. The alternative
`wiki_ingested_at` exists only on `wiki_source` objects and would be `None` on most chunks —
producing confusing null results. `last_modified_date` gives uniform date filtering across every
chunked type.

**Implementation:** The chunker extracts `last_modified_date` from object properties (same read
shape as `_get_last_modified`, see §7.2) and injects it into every chunk. The shared
`_chunk_to_payload` helper (§7.4) writes it into the `PointStruct` payload in BOTH `reindex` and
`reembed_object`.

**Consequence:** Additive, backward-compatible payload extension. Existing chunks lack the field;
the date filter safely returns zero matches for them (Qdrant treats a missing field as
non-matching). A one-time **forced** reindex backfills the field for the whole corpus — see D3.
This is a payload schema change; the lead has adjudicated it as necessary. See Open Decisions (§4).

### D3 — Forced Backfill via Payload-Schema-Version Marker (Migration)

**Problem:** `reindex` skips any object whose `last_modified_date` is unchanged
(`indexer.py:134-136`). After upgrade, almost every object is unchanged, so its chunks would keep
the old 6-field payload **indefinitely** — the new field would only land for objects edited
post-upgrade. The launchd cron (`docs/samples/com.aldeia.anytype-llm-wiki-reindex.plist`) runs
plain `reindex()` and would never backfill either. The date filter would silently under-return
against the historical corpus.

**Decision:** Store a **payload-schema-version marker** in the index state file
(`config.INDEX_STATE_FILE`, a JSON dict currently keyed by `space_id`). Define:

- **Code constant:** `config.PAYLOAD_SCHEMA_VERSION = 2` (was implicitly `1` = the 6-field
  payload; `2` = adds `last_modified_date`).
- **State key:** top-level `"_payload_schema_version"` in the state dict (leading underscore
  avoids collision with `space_id` keys, which are Anytype object-space IDs).

**Behavior in `reindex`:** Read `stored = state.get("_payload_schema_version", 1)`. If
`config.PAYLOAD_SCHEMA_VERSION > stored`, set a `force_full = True` flag for this run. When
`force_full`, the unchanged-skip at `indexer.py:134-136` is bypassed (every object is re-fetched,
re-chunked, re-embedded, re-upserted). After the loop completes successfully, stamp
`state["_payload_schema_version"] = config.PAYLOAD_SCHEMA_VERSION` before `_save_state`. Subsequent
runs see `stored == code version`, `force_full` is `False`, and normal incremental behavior
resumes.

This auto-heals **both** the manual `reindex` and the launchd cron — neither needs a flag or a
human step. The force is one-time per version bump.

```python
# In reindex(), after _load_state():
stored_schema = state.get("_payload_schema_version", 1)
force_full = config.PAYLOAD_SCHEMA_VERSION > stored_schema

# In the per-object loop, replace the unchanged-skip guard:
last_mod = _get_last_modified(obj_summary) or "unknown"
if not force_full and space_state.get(oid) == last_mod:
    continue  # unchanged

# After all spaces processed, before _save_state(state):
state["_payload_schema_version"] = config.PAYLOAD_SCHEMA_VERSION
```

**Note:** `_load_state`/`_save_state` already round-trip the whole dict, so the new top-level key
persists with no serialization change. The space-iteration code reads `state.get(sid, {})` per
space, so the `"_payload_schema_version"` key is never mistaken for a space.

**Marker advance is gated to full (unscoped) reindex:** the `_payload_schema_version` marker is
stamped only after a full (unscoped) `reindex()` — i.e. gated by `if space_id is None`. An
auto-fired single-space reindex (post-`wiki_ingest`/`wiki_remember` under `WIKI_AUTO_REINDEX`)
still backfills its named space but does NOT advance the marker, so it cannot prematurely stamp the
new version and strand every other space on the old payload.

### D4 — `source_type` Filter: DEFER (root cause verified)

**Decision:** Do NOT add `source_type` as an MCP filter parameter in v1. Removed from the API
surface, filter build, chunker, payload writes, payload indexes, and tests.

**Root cause (Lead-verified):** `wiki_source` objects are created **body-less** — `_create_source`
(`src/anytype_llm_wiki/wiki/ingest.py:924-971`) and `remember.py:172-195` write properties only
(`wiki_excerpt`, `wiki_ingested_at`, `wiki_url`/`wiki_file_path`), never a markdown body (AC-L1:
"NEVER a body/markdown key"). The chunker emits property chunks only for keys in
`WIKI_TEXT_PROPERTY_KEYS`
(`chunker.py:13-16`), which does **not** include `wiki_excerpt`. Therefore `chunk_object` returns
**zero chunks** for every `wiki_source` object → sources never reach Qdrant → no payload ever
carries `source_type`. A `source_type` filter returns zero for ALL inputs on both tools. (On
`wiki_query` this is doubly inert: `wiki_source ∉ _WIKI_TYPE_KEYS`.)

**Optional enable-path (Open Decision, NOT v1 default):** To make sources filterable, add
`wiki_excerpt` to `WIKI_TEXT_PROPERTY_KEYS` so sources get chunked and `source_type` can be read
and indexed. **This changes `semantic_search` retrieval semantics** — source excerpts would start
appearing in semantic results that today only contain entity/concept/comparison/query content.
That is a product-facing behavior change requiring Jan/product sign-off (OD-2), not a silent v1
inclusion.

### D5 — `domain_tags` Filter: DEFER (root cause verified)

**Decision:** Do NOT add `domain_tags` as an MCP filter parameter in v1.

**Root cause:** `wiki_domain_tags` is never written onto Anytype objects by the current ingest or
remember pipelines. `extraction.py` produces domain tags and `ingest.py`/`remember.py` validate
the `domain_hint`/`domain_tags` input against the taxonomy, but neither pipeline persists
`wiki_domain_tags` as a `multi_select` property on the created objects (tag IDs are never resolved
or stored). A `domain_tags` filter cannot match anything against the current corpus.

### D6 — Single Follow-Up Ticket (#336: source_type + domain_tags)

D4 and D5 are blocked by the same class of upstream gap (metadata not persisted/indexed onto
chunks) and fold into **one** follow-up ticket — **#336**: **"Persist `wiki_domain_tags` onto
objects AND index source excerpts, then expose both filters."** Scope:

1. Extend ingest/remember to persist `wiki_domain_tags` as a `multi_select` property (resolve tag
   names → IDs via the space tag registry).
2. Add `wiki_excerpt` to `WIKI_TEXT_PROPERTY_KEYS` so `wiki_source` objects are chunked (with
   product sign-off on the retrieval-semantics change).
3. Extend the chunker to read `wiki_source_type` (select) and `wiki_domain_tags` (multi_select)
   into chunk payload (`source_type: str`, `domain_tags: list[str]` of tag names).
4. Add `PayloadSchemaType.KEYWORD` indexes for `source_type` and `domain_tags`; bump
   `PAYLOAD_SCHEMA_VERSION` (the D3 marker auto-backfills).
5. Expose `source_type` and `domain_tags` filter params on both tools. `domain_tags` filters via
   `FieldCondition(key="domain_tags", match=MatchAny(any=[...]))` (ANY-overlap on list-valued
   fields).

**Prerequisite verification for the follow-up:** the `multi_select` GET response shape is
UNVERIFIED in the codebase (the code never reads `multi_select` values back). `select` returns
`{"select": {"id","name","color"}}`; by analogy `multi_select` likely returns
`{"multi_select": [{"id","name"}, ...]}`. Verify against a live space before implementing chunker
extraction.

---

## 4. Open Decisions for Jan (Decide Gate)

These deviate from the ticket's stated non-goal and require ratification before implementation.

### OD-1: Date payload field + forced one-time re-embed (D2 + D3)

**Question:** Accept `last_modified_date` as an additive payload field plus a **forced one-time
full re-embed** (auto-healed via the payload-schema-version marker) as part of this ticket?

**Recommendation:** Yes. The field is additive and backward-compatible; the forced re-embed is a
complete Ollama pass over a small corpus (seconds — see §13), auto-triggered by the version bump
on the next manual or cron `reindex`. This is the only way to make the date filter work against
the historical corpus rather than only objects edited post-upgrade.

**Fallback (Option A):** Ship `type` + `space` scoping only (no payload change, no migration).
Delivers the type half; misses date filtering entirely.

### OD-2: Defer both `source_type` and `domain_tags` to one follow-up (D4 + D5 + D6)

**Question:** Accept deferring **both** `source_type` and `domain_tags` to a single follow-up
ticket (persist `wiki_domain_tags` onto objects AND index source excerpts, then expose both
filters)?

**Recommendation:** Yes. Each is blocked by a verified upstream indexing gap and cannot be made to
work by a Qdrant-only change. Shipping either param now is a footgun (silently returns nothing).
The ticket is titled "type/**tag** scoping" and lists these as ACs, so this deferral needs Jan's
explicit acceptance and a linked follow-up ticket created at the Decide gate.

**Alternative to weigh:** Opt into indexing `wiki_excerpt` now to enable `source_type` on
`semantic_search` — but note this **changes `semantic_search` retrieval semantics** (source
excerpts enter semantic results). Not recommended for v1 without product agreement.

---

## 5. API Surface

### 5.1 `semantic_search` (extended)

```python
@mcp.tool()
def semantic_search(
    query: str,
    space_id: str | None = None,
    types: list[str] | None = None,       # existing
    ingested_after: str | None = None,    # NEW: ISO-8601 datetime (inclusive lower bound)
    ingested_before: str | None = None,   # NEW: ISO-8601 datetime (inclusive upper bound)
    limit: int = 10,
) -> list[dict]:
```

All new params optional, default `None`. Return type `list[dict]` unchanged. Validation errors
raise `ValueError` (surfaced as `CallToolResult(isError=True)` by FastMCP).

**Docstring additions:**
```
    ingested_after: Optional ISO-8601 datetime lower bound on last_modified_date, inclusive.
        Example: "2026-01-01T00:00:00Z".
    ingested_before: Optional ISO-8601 datetime upper bound on last_modified_date, inclusive.
        Example: "2026-06-30T23:59:59Z".
```

### 5.2 `wiki_query` (extended)

```python
@mcp.tool()
def wiki_query(
    question: str,
    space_id: str,
    file_back: bool | None = None,
    types: list[str] | None = None,       # NEW: subset of wiki type keys
    ingested_after: str | None = None,    # NEW: same semantics as semantic_search
    ingested_before: str | None = None,   # NEW: same semantics as semantic_search
) -> dict:
```

All new params optional, default `None`. Return type `dict` (QueryResult) unchanged. Validation
errors fit the existing error-dict pattern `{"status": "error", "error": "...",
"error_category": "config_error"}` (NOT raised — consistent with `wiki_query`'s never-raise
contract).

### 5.3 `semantic_search_core` (extended)

```python
def semantic_search_core(
    query: str,
    space_id: str | None = None,
    types: list[str] | None = None,       # existing
    ingested_after: str | None = None,    # NEW
    ingested_before: str | None = None,   # NEW
    limit: int = 10,
) -> list[dict]:
```

The core does not validate inputs; validation is the caller's responsibility (test isolation).

---

## 6. Qdrant Filter-Translation Design

### 6.1 Pinned Wire Contract

```python
from qdrant_client.models import (
    FieldCondition,
    Filter,
    MatchValue,      # single-value equality (existing use)
    DatetimeRange,   # range over ISO-8601 datetime payload fields (NOT Range)
    PayloadSchemaType,
)
```

All imports are from `qdrant_client.models` (re-exported from `qdrant_client.http.models.models`),
confirmed in qdrant-client 1.18.0 (pinned `>=1.18.0,<2.0.0`).

**`MatchAny` is intentionally NOT imported.** The type filter uses the nested
`Filter(should=[FieldCondition(... MatchValue ...)])` form (see §6.2) — this matches the existing
code (`indexer.py:53-61`) and AC-F2. Do not "simplify" to `MatchAny`: the regression and AC-F2
both depend on the nested-`should` shape, and a contradictory shape makes the test suite
unsatisfiable.

### 6.2 Filter Construction in `semantic_search_core`

The extended `must`-list build (replacing `indexer.py:50-62`):

```python
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
                gte=ingested_after if ingested_after else None,
                lte=ingested_before if ingested_before else None,
            ),
        )
    )

search_filter = Filter(must=must) if must else None
```

**Critical:** `DatetimeRange` (not `Range`). `Range` accepts floats/ints only; `DatetimeRange`
accepts ISO-8601 strings via Pydantic coercion. Using `Range` on ISO strings silently fails.

**No-filter guarantee:** When all filter params are `None`/empty, `must` stays empty and
`search_filter` is `None` — byte-identical to current behavior. An empty-list `types=[]` is falsy,
so it also yields no filter (no-op, by design).

### 6.3 Payload Index Creation (reindex path only)

Index creation moves OUT of `_ensure_collection` (which runs on every `reembed_object` hot-path
call, `indexer.py:198`) into a dedicated `_ensure_payload_indexes` called **only** from `reindex`:

```python
def _ensure_payload_indexes(client: QdrantClient) -> None:
    from qdrant_client.models import PayloadSchemaType
    # Idempotent; called once per full reindex, not on the per-object reembed path.
    for field, schema in [
        ("type_key",           PayloadSchemaType.KEYWORD),
        ("space_id",           PayloadSchemaType.KEYWORD),
        ("last_modified_date", PayloadSchemaType.DATETIME),
    ]:
        client.create_payload_index(config.QDRANT_COLLECTION, field, field_schema=schema)
```

`reindex` calls `_ensure_collection(client)` then `_ensure_payload_indexes(client)`.
`reembed_object` calls only `_ensure_collection(client)` (no index calls). Indexes are:
`type_key`, `space_id`, `last_modified_date` (no `source_type`).

`create_payload_index` signature (verified): `(collection_name, field_name, field_schema=None,
wait=True) -> UpdateResult`. Use `field_schema=` (not legacy `field_type=`). Idempotent: repeat
calls return `UpdateStatus.COMPLETED` without raising.

**In-memory Qdrant `UserWarning`:** the in-memory client emits a `UserWarning` that
`create_payload_index` has no effect. To keep a warnings-as-errors CI run green, the migration
test (and any test exercising `_ensure_payload_indexes` against a real in-memory client) must
register an explicit filter:

```python
@pytest.mark.filterwarnings("ignore::UserWarning")
```

or, narrower, `warnings.filterwarnings("ignore", message=".*payload.*index.*", category=UserWarning)`
in the test. The fakes in §10 are no-ops and never emit the warning; this guard is for any test
using a genuine in-memory `QdrantClient`.

---

## 7. Chunker / Indexer Payload Extension

### 7.1 New Chunk Field

The chunk dict produced by `chunk_object` gains one optional field:

| Field | Type | Source | Objects present on |
|---|---|---|---|
| `last_modified_date` | `str \| None` | `last_modified_date` date property → `date` | All object types (when the property is present) |

(No `source_type` field — deferred per D4.)

### 7.2 Property Extraction Pattern (Verified)

The chunker reads `last_modified_date` with the **same shape** as `indexer._get_last_modified`
(`indexer.py:105-110`) and `lint.py` date readers — `prop.get("date")` — so chunker and Tier-1
predicate agree on the read shape:

```python
# GET response shape (confirmed indexer.py:105-110, ingest.py:937):
{"key": "last_modified_date", "date": "2026-06-12T10:00:00+00:00"}

for prop in obj.get("properties", []):
    if isinstance(prop, dict) and prop.get("key") == "last_modified_date":
        last_modified_date = prop.get("date")
```

### 7.3 `chunk_object` Extension

`chunk_object` extracts `last_modified_date` before dispatch, then injects it into every chunk:

```python
def chunk_object(obj: dict) -> list[dict]:
    object_id = obj.get("id", "")
    space_id = obj.get("space_id", "")
    object_name = obj.get("name", "")
    type_key = obj.get("type", {}).get("key", "unknown")

    # NEW: extract date payload field
    last_modified_date = None
    for prop in obj.get("properties", []):
        if isinstance(prop, dict) and prop.get("key") == "last_modified_date":
            last_modified_date = prop.get("date")
            break

    markdown = obj.get("markdown", "") or ""
    chunks = (
        _chunk_body(markdown, object_id, space_id, object_name, type_key)
        if markdown.strip()
        else _chunk_properties(obj, object_id, space_id, object_name, type_key)
    )

    # Inject into every chunk (None omitted from payload by _chunk_to_payload)
    if last_modified_date is not None:
        for chunk in chunks:
            chunk["last_modified_date"] = last_modified_date

    return chunks
```

### 7.4 Shared Payload Helper

Both `reindex` and `reembed_object` currently hand-duplicate the `PointStruct` payload dict
(`indexer.py:161-168, 218-225`), which drifts. Extract a single helper used by both:

```python
def _chunk_to_payload(chunk: dict) -> dict:
    payload = {
        "object_id": chunk["object_id"],
        "space_id": chunk["space_id"],
        "object_name": chunk["object_name"],
        "type_key": chunk["type_key"],
        "heading": chunk["heading"],
        "text": chunk["text"],
    }
    # Optional metadata written only when present (missing key is cleaner than
    # null for Qdrant filtering).
    if "last_modified_date" in chunk:
        payload["last_modified_date"] = chunk["last_modified_date"]
    return payload
```

Both `reindex` and `reembed_object` build `PointStruct(..., payload=_chunk_to_payload(chunk))`.

---

## 8. `wiki_query` Two-Tier Filter Semantics

`wiki_query` has two retrieval tiers selected by `config.index_threshold()` (where `config` is
**`anytype_llm_wiki.wiki.config`**, not the root `config` module — patch/seam tests against
`anytype_llm_wiki.wiki.config.index_threshold`):
- **Tier 1 (index_navigation):** below threshold — enumerates wiki objects directly, no Qdrant
  call (`query.py:478-485`).
- **Tier 2 (vector_augmented):** at/above threshold — calls `semantic_search_core`
  (`query.py:443-463`).

Filters must behave consistently across both tiers. Tier-1 predicates are **module-level pure
functions** in `query.py` (testable seam — see §10 AC-F10):

```python
def _passes_type_filter(obj: dict, effective_types: set[str]) -> bool:
    """True if the object's type key is in the effective type set."""
    return _type_of(obj) in effective_types


def _passes_date_filter(
    obj: dict, after_dt: datetime | None, before_dt: datetime | None
) -> bool:
    """True if the object's last_modified_date falls within [after, before].

    No date property → does NOT pass when any bound is set (mirrors Qdrant:
    a missing field never matches a range condition). When both bounds are
    None this is never called.
    """
    obj_dt = None
    for prop in obj.get("properties", []):
        if isinstance(prop, dict) and prop.get("key") == "last_modified_date":
            obj_dt = _parse_iso(prop.get("date") or "")
            break
    if obj_dt is None:
        return False
    if after_dt and obj_dt < after_dt:
        return False
    if before_dt and obj_dt > before_dt:
        return False
    return True


def _parse_iso(s: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None
```

### 8.1 `types` in `wiki_query`

Compute `effective_types` once, before tier dispatch:

```python
_WIKI_TYPE_KEYS_SET = set(_WIKI_TYPE_KEYS)
effective_types_set = _WIKI_TYPE_KEYS_SET
if types:
    intersection = [t for t in types if t in _WIKI_TYPE_KEYS_SET]
    if not intersection:
        return {**_empty_result(), "status": "error",
                "error": f"[CONFIG ERROR] type_filter_empty: none of {types!r} are "
                         f"valid wiki type keys {list(_WIKI_TYPE_KEYS)}",
                "error_category": "config_error"}
    effective_types_set = set(intersection)
```

- **Tier 2:** pass `types=sorted(effective_types_set)` to `semantic_search_core` (replaces the
  current hardcoded `types=list(_WIKI_TYPE_KEYS)`; default = full set when `types` omitted).
- **Tier 1:** `wiki_objects = [o for o in wiki_objects if _passes_type_filter(o, effective_types_set)]`.

### 8.2 Date Filter in `wiki_query`

- **Tier 2:** pass `ingested_after`/`ingested_before` straight through to `semantic_search_core`.
- **Tier 1:** parse bounds once, then filter:

```python
if ingested_after or ingested_before:
    after_dt = _parse_iso(ingested_after) if ingested_after else None
    before_dt = _parse_iso(ingested_before) if ingested_before else None
    wiki_objects = [o for o in wiki_objects if _passes_date_filter(o, after_dt, before_dt)]
```

Tier-1 operates on the object's `last_modified_date` — the same field as the Qdrant payload, so
the two tiers are consistent.

### 8.3 Tier-1 Filter Ordering

Apply cheapest-to-most-expensive: (1) type filter, (2) date filter.

---

## 9. Validation Rules

### 9.1 `semantic_search` Validation (raises `ValueError`)

| Param | Check | Error |
|---|---|---|
| `ingested_after` | Probe via `DatetimeRange(gte=...)`; on `pydantic.ValidationError` re-raise `ValueError` | `"Invalid date format for ingested_after: {v!r}. Expected ISO-8601, e.g. 2026-01-01T00:00:00Z"` |
| `ingested_before` | Same | `"Invalid date format for ingested_before: {v!r}. ..."` |
| `types` | Accept any non-empty list of strings. `semantic_search` is a general tool — do NOT validate against `_WIKI_TYPE_KEYS`. | N/A |

```python
from pydantic import ValidationError as _PydanticValidationError
from qdrant_client.models import DatetimeRange as _DatetimeRange

for name, val in [("ingested_after", ingested_after), ("ingested_before", ingested_before)]:
    if val is not None:
        try:
            _DatetimeRange(gte=val)  # probe only; not stored
        except _PydanticValidationError:
            raise ValueError(
                f"Invalid date format for {name}: {val!r}. "
                f"Expected ISO-8601, e.g. 2026-01-01T00:00:00Z"
            )
```

### 9.2 `wiki_query` Validation (returns error dict, never raises)

Fits the existing `{"status": "error", "error": "...", "error_category": "config_error"}` pattern.

| Param | Check | Error key |
|---|---|---|
| `ingested_after` / `ingested_before` | Same probe; on `ValidationError` return error dict | `config_error` |
| `types` (intersection empty) | All supplied types outside `_WIKI_TYPE_KEYS` | `config_error` |

Validation occurs before the `AnytypeReadClient` / `WikiClient` are constructed (early return, no
WikiLog written — same pattern as schema-check failures in `query.py:390-410`).

---

## 10. Test Plan

Tests live in `tests/test_indexer.py` (Qdrant filter + payload-index + migration tests),
`tests/test_chunker.py` (chunker date extraction), and `tests/wiki/test_query.py` (Tier-1
predicate tests).

### 10.1 Extended Fake Qdrant Client

Add `FakeQdrantClientWithSearch` to `tests/test_indexer.py`:

```python
class FakeQdrantClientWithSearch:
    def __init__(self, mock_results=None):
        self.upserted_points = []
        self.deleted = []
        self.query_calls = []
        self.query_filter = None
        self.created_indexes = []
        self._mock_results = mock_results or []

    def get_collections(self):
        class _Col: name = config.QDRANT_COLLECTION
        class _Result: collections = [_Col()]
        return _Result()

    def create_collection(self, **kwargs): pass

    def create_payload_index(self, collection_name, field_name, field_schema=None, **kwargs):
        self.created_indexes.append(field_name)  # no-op; never emits a warning

    def upsert(self, collection_name, points):
        self.upserted_points.extend(points)

    def delete(self, collection_name, points_selector):
        self.deleted.append(points_selector)

    def query_points(self, collection_name, query, query_filter=None, limit=10, with_payload=True):
        self.query_filter = query_filter
        self.query_calls.append({"collection_name": collection_name, "query_filter": query_filter,
                                 "limit": limit, "with_payload": with_payload})
        class _Result: points = self._mock_results
        return _Result()
```

### 10.2 Acceptance Criteria Tests

**AC-F1 — No-filter regression (byte-identical Qdrant call)**
```python
def test_no_filter_regression(monkeypatch):
    fake = FakeQdrantClientWithSearch()
    monkeypatch.setattr(_indexer, "_qdrant", lambda: fake)
    monkeypatch.setattr(_indexer, "embed_query", lambda q: [0.1] * config.EMBED_DIMS)
    _indexer.semantic_search_core(query="test")
    call = fake.query_calls[-1]
    assert call["query_filter"] is None
    assert call["collection_name"] == config.QDRANT_COLLECTION
    assert call["limit"] == 10
    assert call["with_payload"] is True
```

**AC-F1b — Default `wiki_query` passes the full `_WIKI_TYPE_KEYS` (not `None`) to the core**

Tier-2 seam (all three are real, existing module attributes — anchor the test to them):
- `index_threshold` lives on **`anytype_llm_wiki.wiki.config`** (NOT root `config`); monkeypatch
  `query_mod.config.index_threshold` to return `1` (or set env `WIKI_INDEX_THRESHOLD=1`) so any
  non-empty wiki enumeration takes the `vector_augmented` branch (`query.py:436` `tier2 = count >= threshold`).
- `query_mod.write_client`/`WikiClient.list_objects` supplies the enumeration; provide ≥1 wiki-typed
  object so `count >= threshold` and the schema pre-check passes (include the bootstrap schema-version
  marker object so `_schema_version_from_objects` returns a current version — reuse the
  `test_query.py` enumeration fixture / respx `/search` mock).
- `query_mod.indexer.semantic_search_core` is the Tier-2 call site; monkeypatch it to capture kwargs.
- `query_mod.synthesize` → monkeypatch to a sentinel string to avoid any Ollama call.

```python
def test_wiki_query_default_passes_full_type_keys(monkeypatch, anytype_enum_fixture):
    # anytype_enum_fixture: the existing test_query.py harness that mocks WikiClient.list_objects
    # (>=1 wiki object + schema marker) and AnytypeReadClient.get_object.
    captured = {}
    def _fake_core(query, space_id=None, types=None, ingested_after=None,
                   ingested_before=None, limit=10):
        captured["types"] = types
        return []
    monkeypatch.setattr(query_mod.config, "index_threshold", lambda: 1)
    monkeypatch.setattr(query_mod.indexer, "semantic_search_core", _fake_core)
    monkeypatch.setattr(query_mod, "synthesize", lambda q, ctx: "SENTINEL ANSWER")

    query_mod.wiki_query(question="q", space_id=FAKE_SPACE_ID)  # no `types` arg

    assert captured["types"] is not None
    assert set(captured["types"]) == set(query_mod._WIKI_TYPE_KEYS)
```

**AC-F2 — Type filter applied (nested `should` shape)**
```python
def test_type_filter_applied(monkeypatch):
    fake = FakeQdrantClientWithSearch()
    monkeypatch.setattr(_indexer, "_qdrant", lambda: fake)
    monkeypatch.setattr(_indexer, "embed_query", lambda q: [0.1] * config.EMBED_DIMS)
    _indexer.semantic_search_core(query="test", types=["wiki_entity", "wiki_concept"])
    must = fake.query_filter.must
    type_cond = next((c for c in must if hasattr(c, "should") and c.should), None)
    assert type_cond is not None, f"No nested type Filter in must: {must}"
    keys = {c.match.value for c in type_cond.should if hasattr(c, "match")}
    assert {"wiki_entity", "wiki_concept"} <= keys
```

**AC-F4 — Date range filter applied (`DatetimeRange`, both bounds)**
```python
def test_date_range_filter_applied(monkeypatch):
    from qdrant_client.models import DatetimeRange, FieldCondition
    fake = FakeQdrantClientWithSearch()
    monkeypatch.setattr(_indexer, "_qdrant", lambda: fake)
    monkeypatch.setattr(_indexer, "embed_query", lambda q: [0.1] * config.EMBED_DIMS)
    _indexer.semantic_search_core(
        query="test",
        ingested_after="2026-01-01T00:00:00Z",
        ingested_before="2026-06-30T23:59:59Z",
    )
    must = fake.query_filter.must
    date_cond = next(
        (c for c in must if isinstance(c, FieldCondition) and c.key == "last_modified_date"), None)
    assert date_cond is not None
    assert isinstance(date_cond.range, DatetimeRange)
    assert date_cond.range.gte is not None and date_cond.range.lte is not None
```

**AC-F5 — Combined AND filter (type + date)**
```python
def test_combined_filter_and(monkeypatch):
    from qdrant_client.models import FieldCondition
    fake = FakeQdrantClientWithSearch()
    monkeypatch.setattr(_indexer, "_qdrant", lambda: fake)
    monkeypatch.setattr(_indexer, "embed_query", lambda q: [0.1] * config.EMBED_DIMS)
    _indexer.semantic_search_core(
        query="test", types=["wiki_entity"], ingested_after="2026-01-01T00:00:00Z")
    must = fake.query_filter.must
    assert any(hasattr(c, "should") and c.should for c in must)            # type group
    assert any(isinstance(c, FieldCondition) and c.key == "last_modified_date" for c in must)
```

**AC-F5b — Empty-list filter param == no filter**
```python
def test_empty_list_types_is_no_filter(monkeypatch):
    fake = FakeQdrantClientWithSearch()
    monkeypatch.setattr(_indexer, "_qdrant", lambda: fake)
    monkeypatch.setattr(_indexer, "embed_query", lambda q: [0.1] * config.EMBED_DIMS)
    _indexer.semantic_search_core(query="test", types=[])
    assert fake.query_filter is None
```

**AC-F5c — Zero-result filter returns empty list (no error)**
```python
def test_zero_result_filter(monkeypatch):
    fake = FakeQdrantClientWithSearch(mock_results=[])  # query matches nothing
    monkeypatch.setattr(_indexer, "_qdrant", lambda: fake)
    monkeypatch.setattr(_indexer, "embed_query", lambda q: [0.1] * config.EMBED_DIMS)
    out = _indexer.semantic_search_core(query="test", types=["wiki_entity"])
    assert out == []
```

**AC-F6 — Invalid date raises `ValueError` from `semantic_search`**
```python
def test_invalid_date_raises_value_error():
    import pytest
    from anytype_llm_wiki.server import semantic_search
    with pytest.raises(ValueError, match="ingested_after"):
        semantic_search(query="test", ingested_after="not-a-date")
```

**AC-F6b — Bad date on `wiki_query` returns error dict (never raises)**
```python
def test_wiki_query_bad_date_returns_error_dict():
    out = wiki_query(question="q", space_id="sp-1", ingested_after="not-a-date")
    assert out["status"] == "error"
    assert out["error_category"] == "config_error"
    # never raised
```

**AC-F6c — Empty type intersection on `wiki_query` returns error dict**
```python
def test_wiki_query_empty_type_intersection_error():
    out = wiki_query(question="q", space_id="sp-1", types=["not_a_wiki_type"])
    assert out["status"] == "error"
    assert out["error_category"] == "config_error"
```

**AC-F7 — Payload indexes created on the reindex path (not the reembed hot path)**
```python
def test_reindex_creates_payload_indexes(monkeypatch):
    fake = FakeQdrantClientWithSearch()
    monkeypatch.setattr(_indexer, "_qdrant", lambda: fake)
    monkeypatch.setattr(_indexer, "list_spaces", lambda: [])
    _indexer.reindex()
    assert set(fake.created_indexes) >= {"type_key", "space_id", "last_modified_date"}
    assert "source_type" not in fake.created_indexes

def test_reembed_does_not_create_payload_indexes(monkeypatch):
    fake = FakeQdrantClientWithSearch()
    monkeypatch.setattr(_indexer, "_qdrant", lambda: fake)
    monkeypatch.setattr(_indexer, "embed", lambda texts: [[0.1]*config.EMBED_DIMS for _ in texts])
    _indexer.reembed_object("sp-1", "obj-1", {
        "id": "obj-1", "space_id": "sp-1", "name": "X",
        "type": {"key": "wiki_entity"}, "markdown": "# H\nbody",
        "properties": [],
    })
    assert fake.created_indexes == []  # index creation gated out of the hot path
```

**AC-F8 — Chunker writes `last_modified_date` (entity with body)**
```python
def test_chunker_writes_last_modified_date():
    from anytype_llm_wiki.chunker import chunk_object
    obj = {
        "id": "ent-1", "space_id": "sp-1", "name": "Neural Networks",
        "type": {"key": "wiki_entity"}, "markdown": "# Overview\nTransformers use attention.",
        "properties": [{"key": "last_modified_date", "date": "2026-05-01T00:00:00+00:00"}],
    }
    chunks = chunk_object(obj)
    assert chunks
    assert all(c.get("last_modified_date") == "2026-05-01T00:00:00+00:00" for c in chunks)
```

**AC-F9 — Chunker on property-only concept also carries the date; omits field when absent**
```python
def test_chunker_property_concept_date_and_absence():
    from anytype_llm_wiki.chunker import chunk_object
    obj = {
        "id": "con-1", "space_id": "sp-1", "name": "Attention",
        "type": {"key": "wiki_concept"}, "markdown": "",
        "properties": [
            {"key": "wiki_definition", "text": "A mechanism for weighting inputs."},
            {"key": "last_modified_date", "date": "2026-05-02T00:00:00+00:00"},
        ],
    }
    chunks = chunk_object(obj)
    assert chunks
    assert all(c.get("last_modified_date") == "2026-05-02T00:00:00+00:00" for c in chunks)

    obj_nodate = {**obj, "properties": [{"key": "wiki_definition", "text": "A mechanism."}]}
    chunks2 = chunk_object(obj_nodate)
    assert chunks2 and all("last_modified_date" not in c for c in chunks2)
```

**AC-F10 — Tier-1 predicates (runnable, both filters)**
```python
def test_tier1_type_predicate():
    from anytype_llm_wiki.wiki.query import _passes_type_filter
    ent = {"type": {"key": "wiki_entity"}}
    con = {"type": {"key": "wiki_concept"}}
    assert _passes_type_filter(ent, {"wiki_entity"})
    assert not _passes_type_filter(con, {"wiki_entity"})

def test_tier1_date_predicate():
    from datetime import datetime, timezone
    from anytype_llm_wiki.wiki.query import _passes_date_filter
    after = datetime(2026, 1, 1, tzinfo=timezone.utc)
    before = datetime(2026, 12, 31, tzinfo=timezone.utc)
    in_range = {"properties": [{"key": "last_modified_date", "date": "2026-06-01T00:00:00Z"}]}
    too_old  = {"properties": [{"key": "last_modified_date", "date": "2025-06-01T00:00:00Z"}]}
    no_date  = {"properties": []}
    assert _passes_date_filter(in_range, after, before)
    assert not _passes_date_filter(too_old, after, before)
    assert not _passes_date_filter(no_date, after, before)  # missing field never matches
```

**AC-F10b — Mixed valid+invalid `types` silently narrowed (Tier-2 threading)**

Uses the same Tier-2 seam as AC-F1b (`query_mod.config.index_threshold` → 1, the `anytype_enum_fixture`
enumeration, `query_mod.synthesize` sentinel, capture on `query_mod.indexer.semantic_search_core`).
```python
def test_wiki_query_mixed_types_silently_narrowed(monkeypatch, anytype_enum_fixture):
    captured = {}
    def _fake_core(query, space_id=None, types=None, ingested_after=None,
                   ingested_before=None, limit=10):
        captured["types"] = types
        return []
    monkeypatch.setattr(query_mod.config, "index_threshold", lambda: 1)
    monkeypatch.setattr(query_mod.indexer, "semantic_search_core", _fake_core)
    monkeypatch.setattr(query_mod, "synthesize", lambda q, ctx: "SENTINEL ANSWER")

    # "wiki_source" ∉ _WIKI_TYPE_KEYS → silently dropped; "wiki_entity" survives.
    query_mod.wiki_query(question="q", space_id=FAKE_SPACE_ID,
                         types=["wiki_entity", "wiki_source"])

    assert set(captured["types"]) == {"wiki_entity"}  # non-wiki type dropped
```

**AC-F11 — Migration: schema-version bump forces a full re-embed**
```python
def test_schema_version_bump_forces_full_reembed(monkeypatch, tmp_path):
    # Pre-seed state with an OLD schema version and an unchanged object.
    state = {"_payload_schema_version": 1, "sp-1": {"obj-1": "2026-01-01T00:00:00Z"}}
    state_file = tmp_path / "state.json"
    state_file.write_text(json.dumps(state))
    monkeypatch.setattr(config, "INDEX_STATE_FILE", state_file)
    monkeypatch.setattr(config, "INDEX_STATE_DIR", tmp_path)
    monkeypatch.setattr(config, "PAYLOAD_SCHEMA_VERSION", 2)

    fake = FakeQdrantClientWithSearch()
    monkeypatch.setattr(_indexer, "_qdrant", lambda: fake)
    monkeypatch.setattr(_indexer, "list_spaces", lambda: [{"id": "sp-1"}])
    monkeypatch.setattr(_indexer, "list_objects",
                        lambda sid: [{"id": "obj-1", "properties":
                            [{"key": "last_modified_date", "date": "2026-01-01T00:00:00Z"}]}])
    monkeypatch.setattr(_indexer, "get_object", lambda sid, oid: {
        "id": "obj-1", "space_id": "sp-1", "name": "X", "type": {"key": "wiki_entity"},
        "markdown": "# H\nbody",
        "properties": [{"key": "last_modified_date", "date": "2026-01-01T00:00:00Z"}]})
    monkeypatch.setattr(_indexer, "embed",
                        lambda texts: [[0.1]*config.EMBED_DIMS for _ in texts])

    stats = _indexer.reindex()
    assert stats["objects_indexed"] == 1            # unchanged object STILL re-embedded
    assert fake.upserted_points                     # payload re-written
    new_state = json.loads(state_file.read_text())
    assert new_state["_payload_schema_version"] == 2  # version stamped

def test_no_bump_keeps_incremental_skip(monkeypatch, tmp_path):
    # Same setup but stored version already == code version → unchanged object skipped.
    state = {"_payload_schema_version": 2, "sp-1": {"obj-1": "2026-01-01T00:00:00Z"}}
    # ... identical harness ...
    monkeypatch.setattr(config, "PAYLOAD_SCHEMA_VERSION", 2)
    stats = _indexer.reindex()
    assert stats["objects_indexed"] == 0            # skip preserved when no bump
```

**AC-F12 — `reembed_object` writes `last_modified_date`**
```python
def test_reembed_writes_last_modified_date(monkeypatch):
    fake = FakeQdrantClientWithSearch()
    monkeypatch.setattr(_indexer, "_qdrant", lambda: fake)
    monkeypatch.setattr(_indexer, "embed", lambda texts: [[0.1]*config.EMBED_DIMS for _ in texts])
    _indexer.reembed_object("sp-1", "obj-1", {
        "id": "obj-1", "space_id": "sp-1", "name": "X", "type": {"key": "wiki_entity"},
        "markdown": "# H\nbody",
        "properties": [{"key": "last_modified_date", "date": "2026-05-01T00:00:00Z"}]})
    assert fake.upserted_points
    assert all(p.payload.get("last_modified_date") == "2026-05-01T00:00:00Z"
               for p in fake.upserted_points)
```

### 10.3 Test File Location

- `FakeQdrantClientWithSearch`, AC-F1/F2/F4/F5(+b/c)/F7/F11/F12: `tests/test_indexer.py`
- AC-F6, AC-F6b/c: `tests/test_indexer.py` (server import) / `tests/wiki/test_query.py`
- AC-F8, AC-F9: `tests/test_chunker.py`
- AC-F1b, AC-F10/F10b: `tests/wiki/test_query.py`

---

## 11. Implementation Plan

Steps ordered by dependency. Steps 1–4 are independent; step 5 depends on 1+3; step 6 depends on 5.

**Step 1 — `config.PAYLOAD_SCHEMA_VERSION = 2`** (config.py). One constant.

**Step 2 — Extend `chunk_object`** (chunker.py): read `last_modified_date` from
`obj.properties`, inject into every chunk (§7.3). No change to `_chunk_body`/`_chunk_properties`.

**Step 3 — Shared `_chunk_to_payload` + payload writes** (indexer.py): add the helper (§7.4),
use it in both `reindex` and `reembed_object`.

**Step 4 — Payload indexes off the hot path** (indexer.py): add `_ensure_payload_indexes`
(§6.3); call it from `reindex` only; leave `_ensure_collection` to collection creation.

**Step 5 — Migration + filter build** (indexer.py): in `reindex`, read/stamp the
`_payload_schema_version` marker and force-full on bump (§3 D3); extend `semantic_search_core`
with `ingested_after`/`ingested_before` and the date `must` clause (§6.2). Import `DatetimeRange`
inside the function.

**Step 6 — MCP surfaces + Tier-1 predicates** (server.py, wiki/query.py):
- `server.py`: add `ingested_after`/`ingested_before` to `semantic_search` + date validation
  (§9.1); add `types`, `ingested_after`, `ingested_before` to `wiki_query`; thread through.
- `wiki/query.py`: add module-level `_passes_type_filter`, `_passes_date_filter`, `_parse_iso`
  (§8); add `wiki_query` params + validation (§9.2, error-dict); compute `effective_types_set`
  (§8.1); thread into Tier-2 core; apply Tier-1 predicates (§8.1, §8.2).

**Step 7 — Tests** (tests/test_indexer.py, tests/test_chunker.py, tests/wiki/test_query.py): add
`FakeQdrantClientWithSearch` and AC-F1 … AC-F12. Run the suite to confirm no regressions.

**Step 8 — Docs:** update `.aldeia/context/technical.md` payload-schema section to the 7-field
payload (`+ last_modified_date`); update README tool docs for the new params; add release note
(see §15).

---

## 12. Acceptance Criteria Checklist

Mapped to ticket ACs, adjusted for the type+date scope (source_type and domain_tags deferred).

- [ ] **AC-F1** No filter params → byte-identical Qdrant call (`query_filter=None`; collection,
  limit, with_payload unchanged). Test: `test_no_filter_regression`.
- [ ] **AC-F1b** Default `wiki_query` (no `types`) passes the full `_WIKI_TYPE_KEYS` to the core
  (not `None`). Test: `test_wiki_query_default_passes_full_type_keys`.
- [ ] **AC-F2** `types` narrows retrieval via a nested `Filter(should=[FieldCondition(MatchValue)])`;
  consistent across tiers. Test: `test_type_filter_applied`.
- [ ] **AC-F4** `ingested_after`/`ingested_before` produce
  `FieldCondition(key="last_modified_date", range=DatetimeRange(...))` (`DatetimeRange`, not
  `Range`). Test: `test_date_range_filter_applied`.
- [ ] **AC-F5** Filters compose as AND (all in `must`). Empty-list param == no filter; zero-result
  filter returns `[]`. Tests: `test_combined_filter_and`, `test_empty_list_types_is_no_filter`,
  `test_zero_result_filter`.
- [ ] **AC-F6** Malformed date raises `ValueError` from `semantic_search`; returns error dict
  (`config_error`) from `wiki_query`. Empty type intersection returns error dict from `wiki_query`.
  Tests: `test_invalid_date_raises_value_error`, `test_wiki_query_bad_date_returns_error_dict`,
  `test_wiki_query_empty_type_intersection_error`.
- [ ] **AC-F7** Payload indexes (`type_key`, `space_id`, `last_modified_date`) created on the
  `reindex` path only — NOT on `reembed_object`. Tests: `test_reindex_creates_payload_indexes`,
  `test_reembed_does_not_create_payload_indexes`.
- [ ] **AC-F8/F9** Chunker writes `last_modified_date` to chunks for all object types when the
  property is present; omits the key when absent. Tests: `test_chunker_writes_last_modified_date`,
  `test_chunker_property_concept_date_and_absence`.
- [ ] **AC-F10** Tier-1 module-level predicates (`_passes_type_filter`, `_passes_date_filter`)
  match Tier-2 semantics; mixed valid+invalid `types` silently narrowed. Tests:
  `test_tier1_type_predicate`, `test_tier1_date_predicate`,
  `test_wiki_query_mixed_types_silently_narrowed`.
- [ ] **AC-F11** Schema-version bump forces a full re-embed (unchanged objects re-indexed) and
  stamps the new version; no bump preserves the incremental skip. Tests:
  `test_schema_version_bump_forces_full_reembed`, `test_no_bump_keeps_incremental_skip`.
- [ ] **AC-F12** `reembed_object` writes `last_modified_date`. Test:
  `test_reembed_writes_last_modified_date`.
- [ ] **DEFERRED — source_type:** not implemented (D4). `wiki_source` objects are body-less and
  not chunked → inert. Single follow-up ticket (D6 → #336).
- [ ] **DEFERRED — domain_tags:** not implemented (D5). `wiki_domain_tags` never persisted onto
  objects → inert. Same follow-up ticket (D6 → #336).

---

## 13. Resource Impact

**One-time forced re-embed (migration):** the D3 schema-version bump forces a **full** re-embed
pass through Ollama on the next `reindex` (manual or cron) — not an incremental delta. On this
corpus (~500 chunks on the 32GB Mac Mini) the full pass is on the order of seconds (bge-m3 embed
throughput per `.aldeia/context/technical.md`). It runs once per version bump; subsequent reindexes
return to incremental.

**Payload index build:** `create_payload_index` on a small collection is sub-second for KEYWORD
and DATETIME indexes (synchronous, `wait=True`), and now runs only on the full `reindex` path —
off the per-object `reembed_object` hot path. No query-latency impact after build.

**Memory / CPU:** No change to embedding dimensions. No extra Anytype API calls during query
(filters applied in Qdrant). Tier-1 predicates add negligible cost to an already-full enumeration.

---

## 14. Security Considerations

**No egress:** all filter evaluation is local (Qdrant container); no new network calls.

**Input validation:** date strings pass `DatetimeRange` Pydantic validation at the MCP boundary
before reaching Qdrant; malformed dates raise `ValueError` (semantic_search) / return an error
dict (wiki_query) before any Qdrant call.

**`types` input:** arbitrary strings passed to `MatchValue` equality matching — no injection
vector; unknown values return zero results (correct, not a security issue).

**Trust model unchanged:** local stdio MCP server; callers are the local AI assistant. No new
authentication surface.

**Migration data integrity (CSO-6):** the D3 forced re-embed is the only state-mutating
operation introduced here — see the §3 D3 / §15 migration analysis for the version-marker
behavior, idempotency on interruption, and the no-concurrent-run sequencing requirement.

---

## 15. Operational Considerations

**Rollback story (trivial):** the added payload field (`last_modified_date`) and payload indexes
are **inert under the prior code version** — old code never reads them and never sets the new
filter params. Downgrading the package needs no data migration; the extra payload key and indexes
are simply ignored. (The `_payload_schema_version` state key is likewise ignored by old code.)

**Deployment steps for v1:**
1. Install the new version (`uv tool install --upgrade .`).
2. Run `reindex` (manual MCP tool / CLI, OR just let the launchd cron fire). Because
   `PAYLOAD_SCHEMA_VERSION` (2) exceeds the stored marker (1, or absent), the first post-upgrade
   `reindex` **auto-forces a full re-embed** that backfills `last_modified_date` on every chunk,
   creates the payload indexes, and stamps the new marker. No manual flag or extra step.
3. Subsequent reindexes return to incremental behavior automatically.

**Deployment sequencing (Infra-7 / Infra-9):** do NOT run a manual `reindex` and the launchd
cron reindex concurrently for the migration. The state file has no atomic write / lock and the
cron plist has no overlap guard, so an overlapping run can race the version-marker stamp / state
write. Either (a) unload the launchd cron, run the manual `reindex`, then reload the cron, OR
(b) simply let the cron perform the migration on its next run and do not run a manual reindex in
the same window.

**Post-deploy verification (Infra-7 / Infra-9):** after the first reindex completes, confirm the
migration landed:
1. The index state file (`config.INDEX_STATE_FILE`) contains `"_payload_schema_version": 2` at
   the top level.
2. Spot-check that a dated chunk's Qdrant payload carries `last_modified_date` (e.g. retrieve a
   point for an object known to have the property and confirm the field is present).

**Release note required:** "v1 extends the Qdrant payload with `last_modified_date`. The first
`reindex` after upgrade auto-runs a one-time full re-embed (seconds on this corpus) to backfill
the field — no manual action needed; the launchd cron triggers it on its next run. Until that
reindex completes, the date filter under-returns against the historical corpus."

**Failure modes:**
- Qdrant unavailable: `semantic_search_core` raises `httpx.HTTPError` (unchanged); `wiki_query`
  catches it → `error_category: "api_error"` (existing).
- Bad date string: caught at validation, not silently ignored (§9).
- Interrupted forced reindex: the marker is stamped only after the loop completes, so an aborted
  run leaves the old marker and the next `reindex` re-attempts the full backfill (safe, idempotent).

---

## 16. Open Questions

*(After Jan adjudicates OD-1 and OD-2 at Decide, these should all close.)*

1. **OD-1 ratified?** Accept the `last_modified_date` payload field + forced one-time re-embed
   (auto-healed via the schema-version marker)? If not, scope reverts to type-filter-only.
2. **OD-2 ratified?** Defer **both** `source_type` and `domain_tags` to one follow-up ticket (D6)?
   Or opt into indexing `wiki_excerpt` now to enable `source_type` (changes `semantic_search`
   retrieval semantics)?
3. **`types` intersection behavior in `wiki_query`:** silent narrowing of non-wiki types
   acceptable, or should any non-wiki type key always error? Recommendation: error only on empty
   intersection; mixed lists silently narrowed.

---

## 17. Deferred Items

- **`source_type` filter** (D4): `wiki_source` objects are body-less and `wiki_excerpt` is not in
  `WIKI_TEXT_PROPERTY_KEYS`, so sources produce zero chunks. Enabling it requires chunking source
  excerpts (a retrieval-semantics change needing product sign-off). Folded into the D6 follow-up.
- **`domain_tags` filter** (D5): `wiki_domain_tags` is never persisted onto objects by
  ingest/remember. Folded into the D6 follow-up (persist tags onto objects, then index + filter).
- **`wiki_last_reviewed` / `wiki_asked_at` date filters:** trivially addable as second date
  filters once the `last_modified_date` pattern is established. Deferred to keep v1 focused.
