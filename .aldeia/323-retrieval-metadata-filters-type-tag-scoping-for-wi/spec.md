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
**Review rounds:** 0
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
Anytype object properties (`wiki_domain_tags` multi_select, `wiki_ingested_at` date,
`wiki_source_type` select — defined in `wiki/types_schema.py:69-154`) and are never read by the
indexer or written to Qdrant.

A second gap compounds the first: `wiki_domain_tags` is **never written onto Anytype objects**
by the current ingest/remember pipeline. `ingest.py` and `remember.py` both validate the
`domain_hint`/`domain_tags` parameter against the taxonomy but never persist it onto the created
Source, Entity, or Concept objects. Any domain_tags filter against the current corpus would
silently return zero results.

This creates a direct contradiction between the ticket's own **non-goal** ("no indexing /
payload-schema change") and its **acceptance criteria** (domain_tags + source + date filters;
"create payload index if missing"). The non-goal reflects a mistaken belief about the current
payload. The acceptance criteria reflect the ticket's actual intent.

**This spec resolves the contradiction.** It does NOT paper over it.

### 1.2 What Works Today

`semantic_search_core` (`indexer.py:50-62`) already builds a conjunctive Qdrant `Filter` for
`space_id` and `types`. `semantic_search` (`server.py:22-39`) already exposes `types`/`space_id`
as MCP params. The `type` scoping half of this ticket is therefore largely built. The gaps are:
exposing type scoping on `wiki_query`, adding payload indexes, input validation, tests, and the
two new payload fields (`source_type`, `last_modified_date`).

### 1.3 Compliance / Egress Check

Metadata filters are evaluated entirely within Qdrant (local Docker container). No new data
leaves the machine. No new network calls to any external service are introduced by this feature.
The local-first posture of `.aldeia/context/compliance.md` is preserved.

---

## 2. Scope

### In Scope

| File | Nature |
|------|--------|
| `src/anytype_llm_wiki/indexer.py` | Extend `semantic_search_core` (new filter params); extend `_ensure_collection` (payload indexes); extend `reindex`/`reembed_object` payload writes |
| `src/anytype_llm_wiki/chunker.py` | Extend `chunk_object` / `_chunk_body` / `_chunk_properties` to extract and return `source_type` and `last_modified_date` |
| `src/anytype_llm_wiki/server.py` | Add `source_type`, `ingested_after`, `ingested_before` params to `semantic_search`; add `types`, `source_type`, `ingested_after`, `ingested_before` to `wiki_query` |
| `src/anytype_llm_wiki/wiki/query.py` | Thread new filter params from `wiki_query` into `semantic_search_core` (Tier 2) and apply equivalent in-memory predicates (Tier 1) |
| `tests/test_indexer.py` | Add `FakeQdrantClientWithSearch`; add filter unit tests, regression test, validation tests |

### Out of Scope (v1)

- `domain_tags` filter — deferred (see D4 and Open Decisions for Jan)
- Filtering by exact source URL or file path
- Filtering by `wiki_last_reviewed` date (can be added as a trivial follow-on once the pattern is established)
- Filtering by `wiki_asked_at` on `wiki_query` objects

---

## 3. Design Decisions

### D1 — `type` Filter: Full, Ship in v1

**Decision:** Expose type scoping on `wiki_query` (it already exists on `semantic_search`).
Use the existing `semantic_search_core` `types` parameter. No payload schema change needed;
`type_key` is already in the payload. Add a `PayloadSchemaType.KEYWORD` index for `type_key`
(and `space_id`) in `_ensure_collection` for query performance.

**Rationale:** The filter wire is already built. The only gap is the `wiki_query` tool surface.

**Caller semantics for `wiki_query`:** The `types` parameter specifies which wiki type keys the
caller wants included. It intersects with (does NOT replace) the hardcoded `_WIKI_TYPE_KEYS`
tuple `("wiki_entity", "wiki_concept", "wiki_comparison", "wiki_query")`. A caller passing
`types=["wiki_entity"]` gets only entities; `types=["wiki_entity", "wiki_source"]` is silently
narrowed to `["wiki_entity"]` (non-wiki types are filtered out). An empty intersection is an
error (see §6.3).

### D2 — `source_type` Filter: Ship in v1 via Additive Payload Extension

**Decision:** Add a `source_type` payload field. During chunking, read the `wiki_source_type`
select property from the object's `get_object` response properties and store the tag `name`
string (e.g. `"url"`, `"agent"`, `"conversation"`). For objects without this property (all
`wiki_entity`, `wiki_concept`, `wiki_comparison`, `wiki_query` objects), the field is `None`
and is not written to the payload (absent key, not `null`). A `source_type` filter therefore
matches only `wiki_source` chunks.

**Consequence:** This is an additive, backward-compatible payload extension. Existing chunks
lack `source_type`. A one-time reindex is required to populate the field for existing objects.
New chunks from objects indexed after this change will carry the field. The filter safely
returns zero matches on unindexed chunks (Qdrant treats missing field as non-matching for
equality conditions — correct behavior).

**Deviation from non-goal:** This is a payload schema change. The lead has adjudicated this
as necessary to deliver the ticket's stated intent. See Open Decisions for Jan (§4).

### D3 — Date Filter: Ship in v1 via Additive Payload Extension

**Decision:** Add a `last_modified_date` payload field (ISO-8601 string) and expose
`ingested_after` / `ingested_before` MCP params that translate to a `DatetimeRange` condition
on `last_modified_date`.

**Date field selection — `last_modified_date` (recommended) vs `wiki_ingested_at`:**

| Candidate | Coverage | Availability |
|---|---|---|
| `last_modified_date` | ALL object types (`wiki_entity`, `wiki_concept`, `wiki_source`, etc.) | Already read by `indexer._get_last_modified`; universal system-managed field |
| `wiki_ingested_at` | `wiki_source` objects only; `None` for entity/concept | Set by the ingest pipeline on source creation; not on all object types |

**Recommendation: `last_modified_date`.** It provides uniform date filtering across all chunk
types. A caller wanting "sources since January 2026" gets exactly that (because `wiki_source`
objects are modified at ingest time). A caller wanting "entities modified since last week"
also works. `wiki_ingested_at` would only be meaningful for one type and produce confusing
null results on most chunks.

**Implementation:** `indexer._get_last_modified` already reads `last_modified_date` from
object properties. The payload write in `reindex` and `reembed_object` must include
`"last_modified_date": chunk["last_modified_date"]` where chunks will carry this field from
the chunker.

**Consequence:** Same as D2 — additive payload extension, one-time reindex required.

### D4 — `domain_tags` Filter: Defer, Do NOT Ship a Non-Functional Param in v1

**Decision:** Do NOT add `domain_tags` as an MCP filter parameter in v1.

**Rationale:** `wiki_domain_tags` is never written onto Anytype objects by the current ingest
or remember pipelines. A `domain_tags` filter cannot work against the current corpus. Shipping
an accepted-but-inert parameter is a footgun: it silently returns nothing, misleads callers,
and is harder to revoke later than to defer now.

**Root cause (documented for the follow-up ticket):** The extraction prompt in `extraction.py`
does produce domain tags per entity/concept, and `ingest.py`/`remember.py` validate the
`domain_hint`/`domain_tags` input against the taxonomy, but neither pipeline writes
`wiki_domain_tags` as a `multi_select` property onto the created `wiki_source`, `wiki_entity`,
or `wiki_concept` objects. The tag IDs are never resolved and never persisted.

**Follow-up ticket scope (recommended):**
1. Extend the ingest and remember pipelines to persist `wiki_domain_tags` as a multi_select
   property on created/updated objects (resolve tag names to IDs via the space tag registry).
2. Extend the chunker to read `wiki_domain_tags` from the `get_object` property response
   and include a `domain_tags: list[str]` field in the chunk payload (storing tag names,
   not IDs — names are stable and human-meaningful).
3. Add `PayloadSchemaType.KEYWORD` index for `domain_tags` in `_ensure_collection`.
4. Expose `domain_tags: list[str] | None` filter param on `semantic_search` and `wiki_query`.
5. Filter via `FieldCondition(key="domain_tags", match=MatchAny(any=[...]))` — confirmed by
   research to perform ANY-overlap matching against list-valued payload fields.

**Prerequisite verification for the follow-up:** The `multi_select` GET response shape from
`get_object` is UNVERIFIED in the codebase. The codebase never reads `multi_select` values
back. The `select` property returns `{"select": {"id": "...", "name": "...", "color": "..."}}`.
By analogy, `multi_select` likely returns `{"multi_select": [{"id": "...", "name": "..."}]}`.
This must be verified against a live space before the follow-up implements chunker extraction.

**If Jan overrides at Decide to include domain_tags now:** The filter-translation design
in §5 already accommodates a `domain_tags` list payload field via
`FieldCondition(key="domain_tags", match=MatchAny(any=[...]))`. The blocker is not the filter
mechanism but the absent write path. Including domain_tags now requires also including the
ingest/remember write path in scope, which expands the ticket to a different complexity class.

---

## 4. Open Decisions for Jan (Decide Gate)

These items deviate from the ticket's stated non-goal and require ratification before
implementation begins.

### OD-1: Payload Extension (D2 + D3)

**Question:** Do you accept `source_type` and `last_modified_date` as additive payload
fields (requiring a one-time reindex) as part of this ticket?

**Recommendation:** Yes. The extension is additive and backward-compatible. Old chunks
without the new fields return no results for the new filters (correct behavior, not an error).
The reindex is cheap (small corpus, 32GB box, ~7s projected). This is the only way to deliver
the ticket's stated intent; the literal non-goal reflects a mistaken belief about the payload.

**Option B (rejected larger scope):** Include `domain_tags` in the same reindex pass. Blocked
by the absent write path in ingest/remember. Expands scope significantly. Deferred to follow-up.

**Option A (fallback):** Ship only `type` + `space` scoping (no payload change). Delivers
~30% of the ticket's value. Misses the date and source filters entirely.

### OD-2: `domain_tags` Deferral (D4)

**Question:** Do you accept deferring domain_tags filtering to a follow-up ticket?

**Recommendation:** Yes. The prerequisite (writing `wiki_domain_tags` onto objects) is absent
from the codebase and cannot be remedied by a Qdrant-only change. Shipping the param now would
be a footgun (silently returns nothing). The follow-up ticket has a clear, bounded scope (see D4).

---

## 5. API Surface

### 5.1 `semantic_search` (extended)

```python
@mcp.tool()
def semantic_search(
    query: str,
    space_id: str | None = None,
    types: list[str] | None = None,       # existing
    source_type: str | None = None,       # NEW: "url" | "agent" | "conversation"
    ingested_after: str | None = None,    # NEW: ISO-8601 datetime string (inclusive lower bound)
    ingested_before: str | None = None,   # NEW: ISO-8601 datetime string (inclusive upper bound)
    limit: int = 10,
) -> list[dict]:
```

All new params are optional, default `None`. The existing return type `list[dict]` is unchanged.
Validation errors raise `ValueError` (surfaced as `CallToolResult(isError=True)` by FastMCP).

**Docstring additions:**
```
    source_type: Optional filter by ingestion channel — "url", "agent", or "conversation".
        Only chunks from wiki_source objects carry this field; entity/concept chunks will
        not match.
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
    source_type: str | None = None,       # NEW: same semantics as semantic_search
    ingested_after: str | None = None,    # NEW: same semantics as semantic_search
    ingested_before: str | None = None,   # NEW: same semantics as semantic_search
) -> dict:
```

All new params are optional, default `None`. The existing return type `dict` (QueryResult) is
unchanged. Validation errors fit into the existing error-dict pattern
`{"status": "error", "error": "...", "error_category": "config_error"}` (NOT raised as
exceptions, consistent with `wiki_query`'s current never-raise contract).

### 5.3 `semantic_search_core` (extended)

```python
def semantic_search_core(
    query: str,
    space_id: str | None = None,
    types: list[str] | None = None,       # existing
    source_type: str | None = None,       # NEW
    ingested_after: str | None = None,    # NEW
    ingested_before: str | None = None,   # NEW
    limit: int = 10,
) -> list[dict]:
```

The core does not validate inputs; validation is the caller's responsibility. The core trusts
its callers (test isolation).

---

## 6. Qdrant Filter-Translation Design

### 6.1 Pinned Wire Contract

```python
from qdrant_client.models import (
    FieldCondition,
    Filter,
    MatchValue,      # single-value equality (existing use)
    MatchAny,        # IN operator — used for type_key and source_type
    DatetimeRange,   # range over ISO-8601 datetime payload fields (NOT Range)
    PayloadSchemaType,
)
```

All imports are from `qdrant_client.models` (re-exported from `qdrant_client.http.models.models`).
Confirmed in qdrant-client 1.18.0 (pinned `>=1.18.0,<2.0.0` in `pyproject.toml`).

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

if source_type:
    must.append(FieldCondition(key="source_type", match=MatchValue(value=source_type)))

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

**Critical:** `DatetimeRange` is used, not `Range`. `Range` accepts floats/ints only;
`DatetimeRange` accepts ISO-8601 strings via Pydantic coercion. Using `Range` on ISO strings
is a silent failure (wrong type, no match).

**No-filter guarantee:** When all filter params are `None`/empty, `must` stays empty and
`search_filter` is `None` — byte-identical to the current behavior.

### 6.3 Payload Index Creation in `_ensure_collection`

The extended `_ensure_collection` (`indexer.py:85-91`):

```python
def _ensure_collection(client: QdrantClient) -> None:
    from qdrant_client.models import PayloadSchemaType

    collections = [c.name for c in client.get_collections().collections]
    if config.QDRANT_COLLECTION not in collections:
        client.create_collection(
            collection_name=config.QDRANT_COLLECTION,
            vectors_config=VectorParams(size=config.EMBED_DIMS, distance=Distance.COSINE),
        )
    # Payload indexes — idempotent, safe to call unconditionally.
    # In-memory Qdrant emits a UserWarning that indexes have no effect — expected in tests.
    for field, schema in [
        ("type_key",          PayloadSchemaType.KEYWORD),
        ("space_id",          PayloadSchemaType.KEYWORD),
        ("source_type",       PayloadSchemaType.KEYWORD),
        ("last_modified_date", PayloadSchemaType.DATETIME),
    ]:
        client.create_payload_index(
            config.QDRANT_COLLECTION,
            field,
            field_schema=schema,
        )
```

`create_payload_index` signature (verified via `inspect.signature`):
```python
client.create_payload_index(
    collection_name: str,
    field_name: str,
    field_schema: PayloadSchemaType | ... | None = None,
    wait: bool = True,
) -> UpdateResult
```

Use `field_schema=` (not the legacy `field_type=`). Confirmed idempotent: calling twice with
the same schema type returns `UpdateStatus.COMPLETED` without raising. Safe to call
unconditionally every time `_ensure_collection` runs (called at the top of `reindex` at
`indexer.py:116` and `reembed_object` at `indexer.py:197`).

---

## 7. Chunker / Indexer Payload Extension

### 7.1 New Chunk Fields

The chunk dict produced by `chunk_object` / `_chunk_body` / `_chunk_properties` gains two
optional fields:

| Field | Type | Source | Objects present on |
|---|---|---|---|
| `source_type` | `str \| None` | `wiki_source_type` select property → `select.name` | `wiki_source` only |
| `last_modified_date` | `str \| None` | `last_modified_date` date property → `date` | All object types |

### 7.2 Property Extraction Patterns (Verified)

**`select` property GET response** (confirmed from `lint.py:388-389, 519-526`):
```python
# GET response shape:
{"key": "wiki_source_type", "select": {"id": "tag-xxx", "name": "url", "color": "grey"}}

# Extraction:
for prop in obj.get("properties", []):
    if prop.get("key") == "wiki_source_type":
        sel = prop.get("select")
        source_type = sel.get("name") if isinstance(sel, dict) else None
```

**`date` property GET response** (confirmed from `indexer.py:105-110`, `lint.py:372`,
`ingest.py:937`):
```python
# GET response shape:
{"key": "last_modified_date", "date": "2026-06-12T10:00:00+00:00"}

# Extraction (mirrors existing _get_last_modified):
for prop in obj.get("properties", []):
    if prop.get("key") == "last_modified_date":
        last_modified_date = prop.get("date")
```

### 7.3 `chunk_object` Signature Extension

`chunk_object` receives the full `obj` dict (already the case). It must extract `source_type`
and `last_modified_date` before delegating to `_chunk_body` / `_chunk_properties`, then inject
them into every chunk dict returned.

```python
def chunk_object(obj: dict) -> list[dict]:
    object_id = obj.get("id", "")
    space_id = obj.get("space_id", "")
    object_name = obj.get("name", "")
    type_key = obj.get("type", {}).get("key", "unknown")

    # NEW: extract metadata payload fields
    source_type = None
    last_modified_date = None
    for prop in obj.get("properties", []):
        if not isinstance(prop, dict):
            continue
        key = prop.get("key")
        if key == "wiki_source_type":
            sel = prop.get("select")
            if isinstance(sel, dict):
                source_type = sel.get("name")
        elif key == "last_modified_date":
            last_modified_date = prop.get("date")

    # ... existing markdown / property-only dispatch ...
    chunks = (
        _chunk_body(markdown, object_id, space_id, object_name, type_key)
        if markdown.strip()
        else _chunk_properties(obj, object_id, space_id, object_name, type_key)
    )

    # Inject new metadata fields into every chunk (None values omitted from payload)
    for chunk in chunks:
        if source_type is not None:
            chunk["source_type"] = source_type
        if last_modified_date is not None:
            chunk["last_modified_date"] = last_modified_date

    return chunks
```

### 7.4 Indexer Payload Write Extension

In both `reindex` (`indexer.py:162-168`) and `reembed_object` (`indexer.py:218-225`), the
`PointStruct` payload must include the new fields when present in the chunk:

```python
payload = {
    "object_id": chunk["object_id"],
    "space_id": chunk["space_id"],
    "object_name": chunk["object_name"],
    "type_key": chunk["type_key"],
    "heading": chunk["heading"],
    "text": chunk["text"],
}
# NEW: write optional metadata fields only when present (avoids polluting payload
# with explicit null values — missing key is cleaner than null for Qdrant filtering)
if "source_type" in chunk:
    payload["source_type"] = chunk["source_type"]
if "last_modified_date" in chunk:
    payload["last_modified_date"] = chunk["last_modified_date"]
```

---

## 8. `wiki_query` Two-Tier Filter Semantics

`wiki_query` has two retrieval tiers selected by `config.index_threshold()`:
- **Tier 1 (index_navigation):** below threshold — enumerates all wiki objects directly, no
  Qdrant call (`query.py:479-485`)
- **Tier 2 (vector_augmented):** at/above threshold — calls `semantic_search_core`
  (`query.py:444-462`)

Filters must behave consistently across both tiers.

### 8.1 `types` Parameter in `wiki_query`

The caller-supplied `types` is **intersected** with `_WIKI_TYPE_KEYS` before use:

```python
# In wiki_query, before tier dispatch:
_WIKI_TYPE_KEYS_SET = set(_WIKI_TYPE_KEYS)
effective_types: list[str] | None = None
if types:
    intersection = [t for t in types if t in _WIKI_TYPE_KEYS_SET]
    if not intersection:
        return {**_empty_result(), "status": "error",
                "error": f"[CONFIG ERROR] type_filter_empty: none of {types!r} are "
                         f"valid wiki type keys {list(_WIKI_TYPE_KEYS)}",
                "error_category": "config_error"}
    effective_types = intersection
```

- **Tier 2:** pass `types=effective_types` to `semantic_search_core` (replaces the current
  hardcoded `types=list(_WIKI_TYPE_KEYS)`).
- **Tier 1:** filter `wiki_objects` by `_type_of(o) in set(effective_types or _WIKI_TYPE_KEYS)`.

### 8.2 `source_type` in `wiki_query`

- **Tier 2:** pass `source_type=source_type` to `semantic_search_core`.
- **Tier 1:** filter `wiki_objects` by reading the `wiki_source_type` select property from
  each object's property list and matching against the requested `source_type` name. An object
  without `wiki_source_type` does not match when `source_type` is specified.

```python
# Tier-1 source_type predicate (applied after type filter):
if source_type:
    def _has_source_type(obj: dict, target: str) -> bool:
        for prop in obj.get("properties", []):
            if not isinstance(prop, dict):
                continue
            if prop.get("key") == "wiki_source_type":
                sel = prop.get("select")
                return isinstance(sel, dict) and sel.get("name") == target
        return False
    wiki_objects = [o for o in wiki_objects if _has_source_type(o, source_type)]
```

### 8.3 Date Filter (`ingested_after` / `ingested_before`) in `wiki_query`

- **Tier 2:** pass `ingested_after=ingested_after, ingested_before=ingested_before` to
  `semantic_search_core`.
- **Tier 1:** apply in-memory date filter over `last_modified_date` property values.

```python
# Tier-1 date predicate:
from datetime import datetime, timezone

def _parse_iso(s: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None

if ingested_after or ingested_before:
    after_dt = _parse_iso(ingested_after) if ingested_after else None
    before_dt = _parse_iso(ingested_before) if ingested_before else None

    def _in_date_range(obj: dict) -> bool:
        for prop in obj.get("properties", []):
            if isinstance(prop, dict) and prop.get("key") == "last_modified_date":
                obj_dt = _parse_iso(prop.get("date") or "")
                if obj_dt is None:
                    return False
                if after_dt and obj_dt < after_dt:
                    return False
                if before_dt and obj_dt > before_dt:
                    return False
                return True
        return False  # no date property → does not match date filter

    wiki_objects = [o for o in wiki_objects if _in_date_range(o)]
```

Note: Tier-1 date filtering operates on the **object's** `last_modified_date` (same field as
the Qdrant payload). This is consistent.

### 8.4 Filter Ordering in `wiki_query`

Apply Tier-1 filters in this order (mirrors cheapest-to-most-expensive):
1. type filter (`_type_of(o) in effective_types`)
2. source_type filter
3. date range filter

---

## 9. Validation Rules

### 9.1 `semantic_search` Validation (raises `ValueError`)

| Param | Check | Error |
|---|---|---|
| `ingested_after` | Passes to `DatetimeRange(gte=...)` — catch `pydantic.ValidationError`, re-raise `ValueError` | `"Invalid date format for ingested_after: {v!r}. Expected ISO-8601, e.g. 2026-01-01T00:00:00Z"` |
| `ingested_before` | Same | `"Invalid date format for ingested_before: {v!r}. ..."` |
| `source_type` | Accept any non-empty string (lenient — callers may have custom source types). No allowlist. | N/A |
| `types` | Accept any non-empty list of strings. `semantic_search` is a general tool, not wiki-only; do NOT validate against `_WIKI_TYPE_KEYS`. | N/A |

Date validation in `server.py` `semantic_search`:
```python
from pydantic import ValidationError as _PydanticValidationError
from qdrant_client.models import DatetimeRange as _DatetimeRange

for param_name, param_val in [("ingested_after", ingested_after), ("ingested_before", ingested_before)]:
    if param_val is not None:
        try:
            _DatetimeRange(gte=param_val)  # probe only; not stored
        except _PydanticValidationError:
            raise ValueError(
                f"Invalid date format for {param_name}: {param_val!r}. "
                f"Expected ISO-8601, e.g. 2026-01-01T00:00:00Z"
            )
```

### 9.2 `wiki_query` Validation (returns error dict, does not raise)

Fits into the existing `{"status": "error", "error": "...", "error_category": "config_error"}`
pattern used throughout `query.py`.

| Param | Check | Error key |
|---|---|---|
| `ingested_after` / `ingested_before` | Same probe as above; on `ValidationError` return error dict | `config_error` |
| `types` (intersection empty) | All supplied types outside `_WIKI_TYPE_KEYS` → empty intersection | `config_error` |

Validation occurs before the `AnytypeReadClient` / `WikiClient` are constructed (early return,
no WikiLog written — same pattern as schema-check failures in `query.py:390-410`).

---

## 10. Test Plan

Tests live in `tests/test_indexer.py` (filter unit tests, using the extended fake) and
`tests/wiki/test_query.py` (Tier-1 filter predicate tests, if the file exists) or inline.

### 10.1 Extended Fake Qdrant Client

Add `FakeQdrantClientWithSearch` to `tests/test_indexer.py`:

```python
class FakeQdrantClientWithSearch:
    def __init__(self, mock_results=None):
        self.upserted_points = []
        self.deleted = []
        self.query_calls = []
        self.query_filter = None        # last query_filter passed to query_points
        self._mock_results = mock_results or []

    def get_collections(self):
        class _Col:
            name = config.QDRANT_COLLECTION
        class _Result:
            collections = [_Col()]
        return _Result()

    def create_collection(self, **kwargs):
        pass

    def create_payload_index(self, collection_name, field_name, field_schema=None, **kwargs):
        pass  # no-op; in-memory Qdrant emits a UserWarning — suppress or monkeypatch

    def upsert(self, collection_name, points):
        self.upserted_points.extend(points)

    def delete(self, collection_name, points_selector):
        self.deleted.append(points_selector)

    def query_points(self, collection_name, query, query_filter=None, limit=10, with_payload=True):
        self.query_filter = query_filter
        self.query_calls.append({"collection_name": collection_name,
                                  "query_filter": query_filter, "limit": limit})
        class _Result:
            points = self._mock_results
        return _Result()
```

### 10.2 Acceptance Criteria Tests

Each test maps to a ticket AC. All use `FakeQdrantClientWithSearch` + monkeypatch of
`_indexer._qdrant` and `_indexer.embed_query`.

**AC-F1 — No-filter regression (byte-identical behavior)**
```python
def test_no_filter_regression(monkeypatch):
    fake = FakeQdrantClientWithSearch()
    monkeypatch.setattr(_indexer, "_qdrant", lambda: fake)
    monkeypatch.setattr(_indexer, "embed_query", lambda q: [0.1] * config.EMBED_DIMS)
    _indexer.semantic_search_core(query="test")
    assert fake.query_filter is None, (
        f"No-filter regression: query_filter must be None; got {fake.query_filter}"
    )
```

**AC-F2 — Type filter applied**
```python
def test_type_filter_applied(monkeypatch):
    from qdrant_client.models import FieldCondition, MatchAny, MatchValue
    fake = FakeQdrantClientWithSearch()
    monkeypatch.setattr(_indexer, "_qdrant", lambda: fake)
    monkeypatch.setattr(_indexer, "embed_query", lambda q: [0.1] * config.EMBED_DIMS)
    _indexer.semantic_search_core(query="test", types=["wiki_entity", "wiki_concept"])
    assert fake.query_filter is not None
    must = fake.query_filter.must
    # types produce a nested Filter(should=[...]) — existing pattern preserved
    type_cond = next(
        (c for c in must if hasattr(c, "should") and c.should), None
    )
    assert type_cond is not None, f"No type condition in must: {must}"
    type_keys_in_filter = {c.match.value for c in type_cond.should if hasattr(c, "match")}
    assert "wiki_entity" in type_keys_in_filter
    assert "wiki_concept" in type_keys_in_filter
```

**AC-F3 — `source_type` filter applied**
```python
def test_source_type_filter_applied(monkeypatch):
    from qdrant_client.models import FieldCondition, MatchValue
    fake = FakeQdrantClientWithSearch()
    monkeypatch.setattr(_indexer, "_qdrant", lambda: fake)
    monkeypatch.setattr(_indexer, "embed_query", lambda q: [0.1] * config.EMBED_DIMS)
    _indexer.semantic_search_core(query="test", source_type="url")
    assert fake.query_filter is not None
    must = fake.query_filter.must
    st_cond = next((c for c in must if isinstance(c, FieldCondition) and c.key == "source_type"), None)
    assert st_cond is not None, f"No source_type condition in must: {must}"
    assert isinstance(st_cond.match, MatchValue)
    assert st_cond.match.value == "url"
```

**AC-F4 — Date range filter applied**
```python
def test_date_range_filter_applied(monkeypatch):
    from qdrant_client.models import DatetimeRange, FieldCondition
    fake = FakeQdrantClientWithSearch()
    monkeypatch.setattr(_indexer, "_qdrant", lambda: fake)
    monkeypatch.setattr(_indexer, "embed_query", lambda q: [0.1] * config.EMBED_DIMS)
    _indexer.semantic_search_core(query="test", ingested_after="2026-01-01T00:00:00Z")
    assert fake.query_filter is not None
    must = fake.query_filter.must
    date_cond = next(
        (c for c in must if isinstance(c, FieldCondition) and c.key == "last_modified_date"),
        None
    )
    assert date_cond is not None, f"No last_modified_date condition in must: {must}"
    assert isinstance(date_cond.range, DatetimeRange)
    assert date_cond.range.gte is not None
```

**AC-F5 — Combined AND filter (type + source_type + date)**
```python
def test_combined_filter_and(monkeypatch):
    from qdrant_client.models import DatetimeRange, FieldCondition, MatchValue
    fake = FakeQdrantClientWithSearch()
    monkeypatch.setattr(_indexer, "_qdrant", lambda: fake)
    monkeypatch.setattr(_indexer, "embed_query", lambda q: [0.1] * config.EMBED_DIMS)
    _indexer.semantic_search_core(
        query="test",
        types=["wiki_entity"],
        source_type="agent",
        ingested_after="2026-01-01T00:00:00Z",
        ingested_before="2026-12-31T23:59:59Z",
    )
    assert fake.query_filter is not None
    must = fake.query_filter.must
    assert len(must) >= 3  # type Filter, source_type FieldCondition, date FieldCondition
    keys = {getattr(c, "key", None) for c in must}
    assert "source_type" in keys
    assert "last_modified_date" in keys
```

**AC-F6 — Invalid date raises `ValueError` from `semantic_search`**
```python
def test_invalid_date_raises_value_error():
    import pytest
    from anytype_llm_wiki.server import semantic_search
    with pytest.raises(ValueError, match="ingested_after"):
        semantic_search(query="test", ingested_after="not-a-date")
```

**AC-F7 — Payload indexes created by `_ensure_collection`**
```python
def test_ensure_collection_creates_payload_indexes(monkeypatch):
    from anytype_llm_wiki.indexer import _ensure_collection
    created_indexes = []
    class _FakeClient:
        def get_collections(self):
            class _Col:
                name = config.QDRANT_COLLECTION
            class _R:
                collections = [_Col()]
            return _R()
        def create_collection(self, **kwargs): pass
        def create_payload_index(self, collection_name, field_name, field_schema=None, **kwargs):
            created_indexes.append(field_name)
    _ensure_collection(_FakeClient())
    assert "type_key" in created_indexes
    assert "source_type" in created_indexes
    assert "last_modified_date" in created_indexes
```

**AC-F8 — Chunker writes `source_type` for `wiki_source` objects**
```python
def test_chunker_writes_source_type():
    from anytype_llm_wiki.chunker import chunk_object
    obj = {
        "id": "src-1", "space_id": "sp-1", "name": "My Source",
        "type": {"key": "wiki_source"}, "markdown": "# Body\nContent here.",
        "properties": [
            {"key": "wiki_source_type", "select": {"id": "t1", "name": "url", "color": "blue"}},
            {"key": "last_modified_date", "date": "2026-06-01T10:00:00Z"},
        ],
    }
    chunks = chunk_object(obj)
    assert chunks, "Expected at least one chunk"
    assert all(c.get("source_type") == "url" for c in chunks)
    assert all(c.get("last_modified_date") == "2026-06-01T10:00:00Z" for c in chunks)
```

**AC-F9 — Chunker omits `source_type` for non-source objects**
```python
def test_chunker_omits_source_type_for_entity():
    from anytype_llm_wiki.chunker import chunk_object
    obj = {
        "id": "ent-1", "space_id": "sp-1", "name": "Neural Networks",
        "type": {"key": "wiki_entity"}, "markdown": "",
        "properties": [
            {"key": "wiki_facts", "text": "Transformers use attention."},
            {"key": "last_modified_date", "date": "2026-05-01T00:00:00Z"},
        ],
    }
    chunks = chunk_object(obj)
    assert chunks
    assert all("source_type" not in c for c in chunks)
    assert all(c.get("last_modified_date") == "2026-05-01T00:00:00Z" for c in chunks)
```

**AC-F10 — `wiki_query` Tier-1 type filter (in-memory predicate)**

Unit test against `wiki_query`'s internal filter logic (test against the Tier-1 path by
forcing `count < threshold` via monkeypatching `config.index_threshold` to return a large
value, and pre-populating wiki objects with both entity and concept types):
```python
# Asserts that wiki_objects list is narrowed to only the requested type before synthesis.
# Full test setup omitted here; test must monkeypatch synthesize to return a sentinel,
# and verify sources_consulted contains only objects of the requested type.
```

See `tests/wiki/test_query.py` for the full Tier-1 filter test (or add to
`tests/test_indexer.py` alongside the Qdrant filter tests).

### 10.3 Test File Location

- `FakeQdrantClientWithSearch` and AC-F1 through AC-F7: `tests/test_indexer.py`
  (mirrors the monkeypatch pattern at `test_indexer.py:203`)
- AC-F8, AC-F9 (chunker): `tests/test_chunker.py` (or `tests/test_indexer.py`)
- AC-F10 (Tier-1 predicate): `tests/wiki/test_query.py`

---

## 11. Implementation Plan

Steps are ordered by dependency. Steps 1–3 have no dependencies on each other and can be
done in any order; step 4 depends on 1 and 2; step 5 depends on 3 and 4.

**Step 1 — Extend `chunk_object` (chunker.py)**
Read `wiki_source_type` (select) and `last_modified_date` (date) from `obj.properties`.
Inject `source_type` (if non-None) and `last_modified_date` (if non-None) into every chunk dict.
No change to `_chunk_body` or `_chunk_properties` signatures needed — inject after the dispatch.

**Step 2 — Extend `_ensure_collection` (indexer.py)**
Add `create_payload_index` calls for `type_key`, `space_id`, `source_type`,
`last_modified_date` as shown in §6.3. Import `PayloadSchemaType` inside the function.

**Step 3 — Extend `semantic_search_core` signature and filter build (indexer.py)**
Add `source_type`, `ingested_after`, `ingested_before` params. Extend the `must`-list build
as shown in §6.2. Import `DatetimeRange` inside the function alongside existing imports.

**Step 4 — Extend payload writes in `reindex` and `reembed_object` (indexer.py)**
Add `source_type` and `last_modified_date` to the `PointStruct` payload dict in both
functions as shown in §7.4. Conditional on the key being present in the chunk (absent for
entity/concept objects that lack `wiki_source_type`).

**Step 5 — Extend MCP tool surfaces (server.py, wiki/query.py)**
- `server.py`: Add `source_type`, `ingested_after`, `ingested_before` to `semantic_search`.
  Add date validation (§9.1). Thread new params to `semantic_search_core`.
- `server.py`: Add `types`, `source_type`, `ingested_after`, `ingested_before` to `wiki_query`.
  Thread to the internal `_wiki_query` call.
- `wiki/query.py`: Add params to `wiki_query` function. Add validation (§9.2 — error dict
  return, not raise). Compute `effective_types` intersection (§8.1). Thread params into the
  Tier-2 `semantic_search_core` call. Apply Tier-1 in-memory predicates (§8.2, §8.3).

**Step 6 — Tests (tests/test_indexer.py, tests/test_chunker.py)**
Add `FakeQdrantClientWithSearch`. Add AC-F1 through AC-F9. Run `pytest tests/test_indexer.py`
to confirm no regressions on existing seam tests.

**Step 7 — Documentation updates**
- Update `.aldeia/context/technical.md` payload-schema section to reflect the 8-field payload.
- Update README tool documentation for `semantic_search` and `wiki_query` new params.
- Add release note: "v1 reindex required — payload schema extended with `source_type` and
  `last_modified_date` fields."

---

## 12. Acceptance Criteria Checklist

Mapped to ticket ACs, adjusted for D4 deferral.

- [ ] **AC-F1** `semantic_search` and `wiki_query` with no filter params produce
  byte-identical Qdrant calls to today (`query_filter=None`). Test: `test_no_filter_regression`.

- [ ] **AC-F2** `types` filter on `wiki_query` narrows retrieval to requested wiki type keys
  (intersected with `_WIKI_TYPE_KEYS`); consistent across Tier 1 and Tier 2.

- [ ] **AC-F3** `source_type` filter on `semantic_search` and `wiki_query` produces a
  `FieldCondition(key="source_type", match=MatchValue(value=...))` in `must`.
  Test: `test_source_type_filter_applied`.

- [ ] **AC-F4** `ingested_after` / `ingested_before` produce a
  `FieldCondition(key="last_modified_date", range=DatetimeRange(gte=..., lte=...))` in `must`.
  `DatetimeRange` used (not `Range`). Test: `test_date_range_filter_applied`.

- [ ] **AC-F5** Multiple filters compose as AND (all conditions in `must`).
  Test: `test_combined_filter_and`.

- [ ] **AC-F6** Malformed date string raises `ValueError` from `semantic_search`
  (surfaces as `isError=True` via FastMCP) and returns error dict from `wiki_query`.
  Test: `test_invalid_date_raises_value_error`.

- [ ] **AC-F7** `_ensure_collection` calls `create_payload_index` for `type_key`,
  `space_id`, `source_type`, `last_modified_date` (idempotent, `wait=True`).
  Test: `test_ensure_collection_creates_payload_indexes`.

- [ ] **AC-F8** Chunker writes `source_type` field to chunks from `wiki_source` objects;
  omits it for `wiki_entity` / `wiki_concept` / other types.
  Test: `test_chunker_writes_source_type`, `test_chunker_omits_source_type_for_entity`.

- [ ] **AC-F9** Chunker writes `last_modified_date` to chunks for all object types
  (when the property is present). Test: AC-F8/F9 tests above.

- [ ] **AC-F10** `wiki_query` Tier-1 in-memory filter predicates consistent with Tier-2
  Qdrant filter semantics for `types`, `source_type`, and date range.

- [ ] **DEFERRED — domain_tags:** `domain_tags` filter is NOT implemented in v1.
  Rationale: `wiki_domain_tags` is never written onto Anytype objects by the current
  ingest/remember pipeline. A non-functional param would silently return nothing.
  Follow-up ticket required (see D4).

---

## 13. Resource Impact

**Reindex cost:** Additive payload fields (`source_type`, `last_modified_date`) require a
one-time full reindex to populate existing chunks. Projected reindex time: ~7s for 500 chunks
(benchmarked in `.aldeia/context/technical.md`). Negligible on the 32GB Mac Mini.

**Payload index build:** `create_payload_index` on a small-to-medium collection is sub-second
for KEYWORD and DATETIME indexes. Synchronous with `wait=True`. No impact on query latency
after index build.

**Memory / CPU:** No change to embedding or vector dimensions. No additional Anytype API calls
during query (filters are applied in Qdrant, not by fetching extra objects). The Tier-1
in-memory predicate adds negligible cost to what is already a full-enumeration path.

---

## 14. Security Considerations

**No egress:** All filter evaluation is local (Qdrant container). No new network calls.

**Input validation:** Date strings pass through `DatetimeRange` Pydantic validation before
reaching Qdrant. Malformed dates raise `ValueError` at the MCP boundary before any Qdrant
call. This prevents malformed input from reaching the Qdrant client.

**`source_type` and `types` inputs:** Accepted as arbitrary strings and passed to Qdrant
`MatchValue`/`MatchAny`. Qdrant performs equality matching; no SQL injection or query injection
vector. Unknown values return zero results (correct, not a security issue).

**Existing trust model unchanged:** The MCP server is a local stdio tool; callers are the local
AI assistant (Claude Code). No authentication surface added.

---

## 15. Operational Considerations

**Deployment steps for v1:**
1. Install the new package version (`uv tool install --upgrade .`).
2. Run `reindex_anytype` (via MCP tool or `anytype-llm-wiki reindex`) to populate
   `source_type` and `last_modified_date` on all existing chunks.
3. Payload indexes for `type_key`, `space_id`, `source_type`, `last_modified_date` are
   created idempotently by `_ensure_collection` on the next reindex call.

**Release note required:** "Payload schema extended in v1. A one-time full reindex is required
after upgrading. Existing chunks without `source_type` / `last_modified_date` will not match
those filters until reindexed."

**Failure modes:**
- Qdrant unavailable: `semantic_search_core` raises `httpx.HTTPError` (existing behavior,
  unchanged). `wiki_query` catches this and returns `error_category: "api_error"` (existing).
- Bad date string: caught at validation, not silently ignored (see §9).
- `create_payload_index` on a missing collection: `_ensure_collection` creates the collection
  first; index calls follow. No ordering risk.

---

## 16. Open Questions

*(After Jan adjudicates OD-1 and OD-2 at Decide, these should all be closed.)*

1. **OD-1 ratified?** Does Jan accept the additive payload extension (D2 + D3) requiring a
   one-time reindex? If not, scope reverts to type-filter-only (no `source_type` or date params).

2. **OD-2 ratified?** Does Jan accept deferring `domain_tags` to a follow-up ticket? If not,
   the spec must be expanded to include the ingest/remember write path.

3. **`types` intersection behavior in `wiki_query`:** Is a silent narrowing acceptable
   (non-wiki types silently dropped), or should passing a non-wiki type key always error?
   Current recommendation: error only on empty intersection (all supplied types are non-wiki);
   mixed lists are silently narrowed.

---

## 17. Deferred Items

- **domain_tags filter** (D4): Blocked by absent write path in ingest/remember pipelines.
  See D4 for complete follow-up scope.
- **`wiki_last_reviewed` date filter:** Trivially addable as a second `date` filter once the
  pattern is established. Deferred to keep this ticket focused.
- **`source_type` from non-wiki objects:** The current impl sets `source_type` only from
  `wiki_source_type`. Other (non-wiki) Anytype object types with `source_type`-like select
  properties are not considered. Out of scope.
- **Multi-value `source_type` filter:** Currently a single-value `MatchValue`. If callers
  need `source_type IN ["url", "agent"]`, extend to `MatchAny`. Deferred; single-value
  covers the primary use case.
