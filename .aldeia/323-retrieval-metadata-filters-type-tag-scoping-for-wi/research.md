# Research: Qdrant Filter + Payload-Index + Property-Extraction Contract

**Date:** 2026-06-12
**Researcher:** technical-research worker (claude-sonnet-4-6)
**Questions investigated:** 7 (Qdrant filter wire contract; payload indexing; property extraction; "source" filter interpretation; validation approach; test-fake pattern; no-filter regression)

---

## Research Questions

1. Qdrant filter wire contract for `MatchAny`, `Range`/`DatetimeRange`, conjunctive AND shape
2. Payload indexing: `create_payload_index` signature, `PayloadSchemaType`, idempotency
3. Property extraction contract: what `get_object` returns for `multi_select`, `select`, `date`
4. What "source" means as a filter — candidate interpretations and v1 recommendation
5. Validation approach for invalid filter values
6. Test-fake pattern to mirror (based on `tests/test_indexer.py`)
7. No-filter regression guarantee

---

## Findings

### Q1 — Qdrant Filter Wire Contract (qdrant-client 1.18.0)

**Installed version confirmed:** 1.18.0 (pinned in `uv.lock`, bounded `>=1.18.0,<2.0.0` in `pyproject.toml`)

#### Exact model imports

```python
from qdrant_client.models import (
    FieldCondition, Filter,
    MatchValue,    # single-value equality
    MatchAny,      # one-of match (IN operator)
    DatetimeRange, # range over datetime payload fields
    Range,         # range over numeric payload fields (NOT for ISO date strings)
)
```

All live in `qdrant_client.http.models.models`, re-exported from `qdrant_client.models`.

#### Constructors (verified via `inspect.signature` + runtime test)

```python
MatchValue(value=<str|int|bool>)
# e.g. MatchValue(value="wiki_entity")

MatchAny(any=<list[str|int]>)
# e.g. MatchAny(any=["wiki_entity", "wiki_concept"])

DatetimeRange(
    gt=None,  # Union[datetime, date, None]
    gte=None, # Union[datetime, date, None]
    lt=None,  # Union[datetime, date, None]
    lte=None, # Union[datetime, date, None]
)
# Accepts both datetime objects AND ISO-8601 strings (Pydantic coerces them).
# e.g. DatetimeRange(gte="2026-01-01T00:00:00Z")
# e.g. DatetimeRange(gte=datetime(2026, 1, 1, tzinfo=timezone.utc))

Range(gt=None, gte=None, lt=None, lte=None)
# Accepts float/int. NOT suitable for ISO-8601 string dates.
```

**For ISO-8601 date strings stored in the payload (e.g. `wiki_ingested_at`), use `DatetimeRange`, NOT `Range`.** Pydantic on `DatetimeRange` parses ISO strings to `datetime` automatically. `Range` expects numeric values and will not parse date strings.

#### Conjunctive AND filter shape (type ∈ {a,b} AND domain_tags CONTAINS any-of {x,y} AND ingested_at >= D)

```python
Filter(
    must=[
        # type filter: AND(type in list)
        FieldCondition(
            key="type_key",
            match=MatchAny(any=["wiki_entity", "wiki_concept"]),
        ),
        # domain_tags filter: AND(any domain_tag in payload_list overlaps filter_set)
        FieldCondition(
            key="domain_tags",
            match=MatchAny(any=["wiki_ai-research", "wiki_engineering"]),
        ),
        # date range filter
        FieldCondition(
            key="ingested_at",
            range=DatetimeRange(gte="2026-01-01T00:00:00Z"),
        ),
    ]
)
```

Note: `FieldCondition` uses `match=` for equality/any matches and `range=` for range matches. These are mutually exclusive per field condition.

#### MatchAny against a list-valued payload field (multi_select)

**Verified experimentally with qdrant-client 1.18.0 in-memory mode:**

When the payload field is a list (e.g. `domain_tags: ["ai", "ml", "nlp"]`), `MatchAny(any=["ai", "other"])` matches if **ANY element of the payload list overlaps with ANY element of the filter list** — i.e., set intersection is non-empty. This is the Qdrant documented behavior: "When we apply a filter to an array, it will succeed if at least one of the values inside the array meets the condition." Source: Qdrant [Filtering docs](https://qdrant.tech/documentation/manage-data/payload/) + [payload_filters source](https://python-client.qdrant.tech/qdrant_client.local.payload_filters).

This is the correct semantic for domain_tags filtering: a query `domain_tags=["wiki_ai-research"]` will match any chunk whose payload `domain_tags` list contains `"wiki_ai-research"` as one of its elements.

#### Type filter: MatchAny vs nested Filter(should=[...])

The existing `semantic_search_core` (`indexer.py:54-60`) uses a nested `Filter(should=[FieldCondition(key="type_key", match=MatchValue(value=t)) for t in types])` appended to `must`. For new filter fields, the simpler `MatchAny` on `type_key` is equivalent and cleaner:

```python
# Current pattern (correct, but verbose)
Filter(should=[FieldCondition(key="type_key", match=MatchValue(value=t)) for t in types])

# Simpler equivalent (MatchAny)
FieldCondition(key="type_key", match=MatchAny(any=list(types)))
```

Both are valid. The spec should decide which to use for consistency; `MatchAny` is more concise.

---

### Q2 — Payload Indexing

#### `create_payload_index` signature (pinned from `inspect.signature`)

```python
client.create_payload_index(
    collection_name: str,
    field_name: str,
    field_schema: PayloadSchemaType | KeywordIndexParams | DatetimeIndexParams | ... | None = None,
    field_type: ... = None,  # legacy alias for field_schema, prefer field_schema
    wait: bool = True,
    ordering: WriteOrdering | None = None,
    timeout: int | None = None,
) -> UpdateResult
```

Use `field_schema=` (not `field_type=`). Returns `UpdateResult(operation_id=..., status=UpdateStatus.COMPLETED)`.

#### `PayloadSchemaType` enum values (relevant)

```python
from qdrant_client.models import PayloadSchemaType

PayloadSchemaType.KEYWORD   # for string fields: type_key, domain_tags, source_type
PayloadSchemaType.DATETIME  # for ISO-8601 date fields: ingested_at, last_reviewed
PayloadSchemaType.INTEGER   # (not needed here)
PayloadSchemaType.FLOAT     # (not needed here)
```

#### Idempotency

**Confirmed experimentally:** calling `create_payload_index` twice on the same field with the same schema type **does not raise**. It returns `UpdateStatus.COMPLETED` both times. Safe to call unconditionally in `_ensure_collection` without checking first.

**Note:** the in-memory Qdrant client (`':memory:'`) does NOT reflect payload indexes in `get_collection().payload_schema` (it returns `{}`). This is expected — in-memory Qdrant ignores payload indexes with a `UserWarning`. The real Qdrant server returns the schema in `payload_schema: Dict[str, PayloadIndexInfo]` where `PayloadIndexInfo.data_type` is the `PayloadSchemaType`. Checking `get_collection().payload_schema` is NOT needed before calling `create_payload_index` since the call is idempotent.

#### Where to place index creation

**Recommendation: extend `_ensure_collection` in `indexer.py:85-91`.** The function is called at the top of both `reindex` (`indexer.py:116`) and `reembed_object` (`indexer.py:198`) before any data operations. It is also used by the live tests in `TestEnsureCollection`. Extending it with `create_payload_index` calls ensures indexes exist whenever data is written.

Proposed extension:
```python
def _ensure_collection(client: QdrantClient) -> None:
    from qdrant_client.models import PayloadSchemaType
    collections = [c.name for c in client.get_collections().collections]
    if config.QDRANT_COLLECTION not in collections:
        client.create_collection(
            collection_name=config.QDRANT_COLLECTION,
            vectors_config=VectorParams(size=config.EMBED_DIMS, distance=Distance.COSINE),
        )
    # Ensure payload indexes exist (idempotent — safe to call even if already present)
    for field, schema in [
        ("type_key",    PayloadSchemaType.KEYWORD),
        ("space_id",    PayloadSchemaType.KEYWORD),
        ("domain_tags", PayloadSchemaType.KEYWORD),
        ("source_type", PayloadSchemaType.KEYWORD),
        ("ingested_at", PayloadSchemaType.DATETIME),
    ]:
        client.create_payload_index(config.QDRANT_COLLECTION, field, field_schema=schema)
```

**Cost on an existing populated collection:** Qdrant builds the index over existing points. For a KEYWORD index on a small-to-medium collection (hundreds to low thousands of wiki objects, each with a few chunks), this is fast (sub-second). For DATETIME indexes it is similarly cheap. The operation is synchronous when `wait=True` (default).

---

### Q3 — Property Extraction Contract from `get_object`

#### Known shape (from codebase evidence)

The `get_object` response returns `{"object": {...}}` where the inner object has a `"properties"` key that is a **list of dicts**, each dict being a `PropertyLinkWithValue`. The code in `indexer.py:106-110` demonstrates the date read pattern:

```python
# indexer.py:105-110
def _get_last_modified(obj: dict) -> str | None:
    for prop in obj.get("properties", []):
        if prop.get("key") == "last_modified_date":
            return prop.get("date")
    return None
```

This confirms: date properties are `{"key": "...", "date": "<ISO-8601 string>"}`.

The write pattern in `ingest.py:937` is:
```python
{"key": "wiki_ingested_at", "date": datetime.now(timezone.utc).isoformat()}
```
And `lint.py:372` reads back: `ingested.get("date")` — same field name. Confirmed symmetry.

#### `select` property shape in GET response

**Confirmed from `lint.py:388-389`:**
```python
if action_prop and isinstance(action_prop.get("select"), dict):
    action_name = action_prop["select"].get("name", "")
```
And `lint.py:519-526`:
```python
if status_prop and isinstance(status_prop.get("select"), dict):
    sel = status_prop["select"]
    sel_id = sel.get("id")
    sel_name = sel.get("name")
```

The GET response for a `select` property is:
```json
{"key": "wiki_action", "select": {"id": "tag-xxx", "name": "ingest", "color": "grey"}}
```
NOT just a tag ID string. The `select` value is a tag **object** (dict with `id`, `name`, `color`).

The write path uses a bare tag ID string: `{"key": "wiki_action", "select": "tag-xxx"}` (`ingest.py:353`). The API accepts the ID on write but returns a full tag object on read.

#### `multi_select` property shape in GET response

**No direct codebase evidence.** The codebase never reads `multi_select` properties back from `get_object` responses. The external third-party client [anytype-client](https://charlesneimog.github.io/anytype-client/api/property/) shows `"multi_select": ["tag_id_1", "tag_id_2"]` (a list of tag ID strings). However, given that `select` returns a full tag object (not just an ID), **the analogous GET response for multi_select is likely a list of tag objects**:
```json
{"key": "wiki_domain_tags", "multi_select": [
    {"id": "tag-xxx", "name": "wiki_ai-research", "color": "blue"},
    {"id": "tag-yyy", "name": "wiki_engineering", "color": "teal"}
]}
```
But this is an **unverified assumption**. The third-party client uses IDs, the Anytype API may return objects. **This must be verified against a live space before indexing multi_select values.**

#### Critical gap: `wiki_domain_tags` is NEVER written to objects in the current pipeline

After searching all source files, `wiki_domain_tags` is:
- Defined in `types_schema.py` as a `multi_select` property on `wiki_source`, `wiki_entity`, `wiki_concept`
- Validated in `ingest.py` (`domain_hint`) and `remember.py` (`domain_tags`) but **NEVER WRITTEN** to any object property

The current ingest pipeline validates the domain hint against the taxonomy but does NOT attach it to the created Source, Entity, or Concept objects. `remember.py` similarly validates `domain_tags` but does not write them to any object property.

**Implication:** `domain_tags` cannot be filtered via Qdrant payload until:
1. The ingest/remember pipelines are extended to write `wiki_domain_tags` as a `multi_select` property on created objects (using resolved tag IDs)
2. The chunker is extended to read `wiki_domain_tags` from `get_object` properties and include it in the chunk payload

**This is a prerequisite for domain_tags filtering that is NOT in the current scope of #323 as described in the ticket non-goals.** The ticket says "Any indexing / payload-schema change (filter only over already-indexed fields)" is out of scope. However, the ticket also lists `domain_tags` as a required filter, which is contradictory — `domain_tags` is NOT in the current payload. The spec writer must resolve this contradiction: either (a) include payload schema extension in scope or (b) defer domain_tags filtering to a follow-on ticket.

#### `date` property in GET response

Confirmed symmetrical:
- Write: `{"key": "wiki_ingested_at", "date": "2026-06-12T10:00:00+00:00"}`
- Read: `prop.get("date")` returns the ISO-8601 string

For payload storage, the chunker should store the date as an ISO-8601 string. Qdrant's `DatetimeRange` filter will parse it correctly.

#### Summary table

| Property Type | Anytype format | GET response shape | Payload storage recommendation |
|---|---|---|---|
| `date` | `"date"` | `{"key": "k", "date": "ISO-8601 str"}` | Store as ISO-8601 string; `DatetimeRange` filter |
| `select` | `"select"` | `{"key": "k", "select": {"id":"..","name":"..","color":".."}}` | Store tag name string; `MatchValue` / `MatchAny` filter |
| `multi_select` | `"multi_select"` | UNVERIFIED — likely `{"key": "k", "multi_select": [{"id":..,"name":..}]}` or list of IDs | Store list of tag name strings; `MatchAny` filter (ANY-overlap) |

**Recommendation for multi_select payload storage:** Store tag **names** (not IDs) in the chunk payload. Names are stable and human-meaningful for filter input from callers. IDs are opaque and space-specific. This requires resolving `{"id": "...", "name": "wiki_ai-research"}` → `"wiki_ai-research"` during chunking.

---

### Q4 — What "Source" Means as a Filter

**Candidate interpretations:**

(a) **`wiki_source_type` select on `wiki_source` objects** — values are: `"agent"`, `"conversation"`, `"url"` (from bootstrap's `_ensure_wiki_source_type_tags`). This is the ingestion mechanism/channel.

(b) **`wiki_url` / `wiki_file_path` provenance** — the actual source URL or file path. Useful for "only chunks from this specific URL" queries but too granular and space-specific for a general filter.

(c) **Filtering by the Source OBJECT a chunk derives from** — chunks today are per-object (one `wiki_source`, `wiki_entity`, or `wiki_concept` object → N chunks). A `wiki_source` object's own chunks are its excerpt/URL; chunks from `wiki_entity`/`wiki_concept` objects that *cite* a source are separate objects.

**Recommendation for v1:** interpretation (a) — `wiki_source_type` as `source_type` filter.

Rationale:
- `wiki_source_type` is already a `select` property on `wiki_source` objects
- It maps to a small, well-known taxonomy ("agent", "conversation", "url") — easy to validate
- Chunks from `wiki_source` objects carry a `wiki_source_type`; chunks from `wiki_entity`/`wiki_concept` do NOT (they don't have this property)
- A payload field `source_type` in the chunk can be populated for `wiki_source` objects by reading the `wiki_source_type` select property during chunking, and left `None` for entity/concept chunks

**Payload field name:** `source_type` (stores the tag name string, e.g. `"url"`, `"agent"`, `"conversation"`).

**Note:** interpretation (b) and (c) are out of scope for v1. Filtering by exact URL would require an additional payload field `source_url` and a `MatchValue` condition — deferred.

---

### Q5 — Validation Approach

#### FastMCP exception surfacing (confirmed from source inspection)

FastMCP 3.4.2 (`server.py:1282-1311`):
- A `FastMCPError` raised inside a tool is caught and re-raised (propagates to MCP protocol)
- Any other `Exception` is caught and wrapped in a `ToolError(f"Error calling tool {name!r}: {e}")` unless `_mask_error_details` is set

The MCP SDK (`mcp.server.lowlevel.server:446-447`) catches all exceptions and converts them to `CallToolResult(isError=True, content=[TextContent(text=str(e))])`. **A `ValueError` raised from a tool function WILL surface to the LLM as a structured MCP error result** — the message is included in the content.

#### Existing error patterns

`wiki_query` returns **error dicts** (`{"status": "error", "error": "...", "error_category": "..."}`) — it never raises. `semantic_search` currently raises nothing (it delegates to `semantic_search_core` which raises raw `httpx.HTTPError` on network failure but has no input validation).

#### Recommended validation approach for #323

**Raise `ValueError` at the MCP tool boundary** for invalid filter inputs. Do NOT return error dicts from `semantic_search` (it currently returns `list[dict]`; changing to an error dict would break callers). For `wiki_query`, fit validation into the existing error-dict pattern.

Specifically:

- **`semantic_search` tool:** raise `ValueError` for invalid filter params before calling `semantic_search_core`. Example: `raise ValueError(f"Invalid type_key: {v!r}. Known wiki types: {KNOWN_TYPES}")`.

- **`semantic_search_core`:** validate at the tool layer, not in core. Core should trust its callers (test isolation).

- **Invalid `type_key`:** reject if not in the known wiki type key set. But note: `semantic_search` is a general-purpose tool (not wiki-only), so type key validation should be optional/configurable or only applied when a `wiki_*` prefix is required.

- **Invalid `domain_tag`:** requires a live taxonomy lookup via `_domain_taxonomy(client, space_id)` — same pattern as `ingest.py:661-666`. This adds a network round-trip. For v1, validation of domain tags at the tool boundary is expensive; consider accepting unknown tags silently (they'll just return 0 results) or making validation opt-in.

- **Malformed date string:** `DatetimeRange` Pydantic model will raise a `ValidationError` on bad ISO strings. Catch this and re-raise as `ValueError` with a clear message: `"Invalid date format for ingested_after: {v!r}. Expected ISO-8601, e.g. 2026-01-01T00:00:00Z"`.

- **`wiki_query` validation:** use existing `_error_result("config_error", ...)` pattern (`query.py:392-409` shows the shape). Pass filter params through to `semantic_search_core` without live-taxonomy validation (too expensive in the query path).

#### Validation placement summary

| Check | Location | Method |
|---|---|---|
| Malformed date | MCP tool layer (`server.py`) or `semantic_search_core` | Catch `pydantic.ValidationError`, raise `ValueError` |
| Unknown type_key | MCP tool layer, optional | Raise `ValueError` |
| Unknown domain_tag | DEFER to v1.1 or warn-only | Live taxonomy lookup is expensive |

---

### Q6 — Test-Fake Pattern to Mirror

#### Existing `FakeQdrantClient` in `tests/test_indexer.py:172-195`

```python
class FakeQdrantClient:
    def __init__(self):
        self.upserted_points = []       # List[PointStruct]
        self.collections_called = False
        self.created_collection = False
        self.deleted = []               # List[Filter] (points_selector)

    def get_collections(self):
        self.collections_called = True
        class _Col:
            name = config.QDRANT_COLLECTION
        class _Result:
            collections = [_Col()]
        return _Result()

    def create_collection(self, **kwargs):
        self.created_collection = True

    def upsert(self, collection_name, points):
        self.upserted_points.extend(points)

    def delete(self, collection_name, points_selector):
        self.deleted.append(points_selector)
```

Monkeypatched via: `monkeypatch.setattr(_indexer, "_qdrant", lambda: fake_client)` (test_indexer.py:203).

**What is missing:** the fake does NOT implement `query_points`. For filter tests on `semantic_search_core`, a new fake (or extension) must add `query_points` and capture the `query_filter` argument.

#### Extended fake for filter tests

```python
class FakeQdrantClientWithSearch:
    def __init__(self, mock_results=None):
        self.upserted_points = []
        self.deleted = []
        self.query_calls = []           # List[dict] of captured call kwargs
        self.query_filter = None        # Last query_filter passed to query_points
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
        pass  # no-op for tests

    def upsert(self, collection_name, points):
        self.upserted_points.extend(points)

    def delete(self, collection_name, points_selector):
        self.deleted.append(points_selector)

    def query_points(self, collection_name, query, query_filter=None, limit=10, with_payload=True):
        self.query_filter = query_filter
        self.query_calls.append({
            "collection_name": collection_name,
            "query_filter": query_filter,
            "limit": limit,
        })
        class _Result:
            points = self._mock_results
        return _Result()
```

**How to assert on `query_filter` shape:**

```python
# Assert type filter was applied
from qdrant_client.models import FieldCondition, Filter, MatchAny
assert fake_client.query_filter is not None
must = fake_client.query_filter.must
type_cond = next((c for c in must if isinstance(c, FieldCondition) and c.key == "type_key"), None)
assert type_cond is not None
assert isinstance(type_cond.match, MatchAny)
assert "wiki_entity" in type_cond.match.any

# Assert no-filter regression: query_filter is None
assert fake_client.query_filter is None
```

The test file location should be `tests/test_indexer.py` (same as existing fake), because `indexer._qdrant` is monkeypatchable there.

---

### Q7 — No-Filter Regression Guarantee

#### Current code path (`indexer.py:50-62`)

```python
must: list = []
if space_id:
    must.append(FieldCondition(key="space_id", match=MatchValue(value=space_id)))
if types:
    must.append(Filter(should=[...]))
search_filter = Filter(must=must) if must else None
```

**When no filter params are passed** (`space_id=None`, `types=None`): `must` stays empty, so `Filter(must=[])` is NOT constructed — `search_filter` is `None`.

The `query_points` call at `indexer.py:64-70`:
```python
results = client.query_points(
    collection_name=config.QDRANT_COLLECTION,
    query=vector,
    query_filter=search_filter,   # ← None when no filters
    limit=limit,
    with_payload=True,
)
```

When `query_filter=None`, Qdrant performs an unfiltered vector search — byte-identical to the pre-filter behavior.

#### Extension contract for new filter params

The new `domain_tags`, `source_type`, `ingested_after` params must follow the same pattern: each must be guarded by `if param:` so that `None` / empty list does NOT append to `must`. If all params are `None`, `must` stays empty and `search_filter` stays `None`. This is the exact assertion the regression test must enforce.

#### Regression test assertion (precise)

```python
def test_no_filter_regression(monkeypatch):
    """When NO filter params passed, query_filter must be None (same as today)."""
    import anytype_llm_wiki.indexer as _indexer
    fake = FakeQdrantClientWithSearch()
    monkeypatch.setattr(_indexer, "_qdrant", lambda: fake)
    monkeypatch.setattr(_indexer, "embed_query", lambda q: [0.1] * config.EMBED_DIMS)

    _indexer.semantic_search_core(query="test")

    assert fake.query_filter is None, (
        "No-filter regression: query_filter must be None when no filter params passed; "
        f"got: {fake.query_filter}"
    )
```

---

## Alternatives Considered

| Option | Pros | Cons | Verdict |
|--------|------|------|---------|
| Use `Range` for date filtering | Simple | Does not accept ISO-8601 strings; requires Unix timestamps | Rejected — use `DatetimeRange` |
| Use `MatchValue` in a `Filter(should=[])` for type filter | Consistent with existing code | More verbose than `MatchAny` | Acceptable — both work; `MatchAny` is cleaner |
| Validate domain_tags against live taxonomy at tool boundary | Strongest UX | Extra network round-trip; slows every filtered query | Deferred — warn-only or skip for v1 |
| Store domain_tags as tag IDs in payload | Compact | ID-to-name mapping needed for human-readable filter input | Rejected — store tag names |
| Place payload indexes in a separate `_ensure_indexes` function | Separation of concerns | One more call site to maintain | Optional — embedding in `_ensure_collection` is simpler |

---

## Key Findings

1. **`DatetimeRange` is the correct model for ISO-8601 date strings.** `Range` is for numeric values only. `DatetimeRange` accepts ISO strings via Pydantic coercion.

2. **`MatchAny` against a list payload field does ANY-overlap matching.** Confirmed experimentally: if the payload list contains `["ai", "ml"]` and the filter is `MatchAny(any=["ai", "other"])`, the point matches. This is the correct semantic for domain_tags filtering.

3. **`create_payload_index` is idempotent.** Calling it twice with the same schema type returns `COMPLETED` both times without error. Safe to call unconditionally in `_ensure_collection` without checking `get_collection().payload_schema` first.

4. **`domain_tags` is NOT in the current chunk payload.** The chunker only writes 6 fields: `object_id, space_id, object_name, type_key, heading, text`. Adding `domain_tags` requires (a) chunker extension to read the `wiki_domain_tags` multi_select from `get_object` properties, and (b) ingest/remember pipeline extension to write `wiki_domain_tags` to objects. This is a payload schema change and may conflict with ticket non-goal "no indexing/payload-schema change."

5. **`select` GET response is a tag object dict, not a string.** `{"key": "wiki_action", "select": {"id": "...", "name": "ingest", "color": "grey"}}`. Store the `name` field for payload storage.

6. **`multi_select` GET response shape is unverified.** Based on analogy with `select`, it is likely a list of tag objects. Store tag `name` values (not IDs) in the payload.

7. **`wiki_domain_tags` is never written to object properties in the current pipeline.** This is a prerequisite for domain_tags filtering. The spec must decide whether to include this write path in scope.

8. **FastMCP surfaces `ValueError` as a structured MCP error result with `isError=True`.** The error message is included. Raising `ValueError` from a tool function is the clean way to reject invalid filter params.

9. **No `query_points` capture in any existing test fake.** The new filter tests need a new fake class that captures `query_filter` as an attribute. The pattern to extend is the `FakeQdrantClient` in `tests/test_indexer.py:172-195`.

10. **`semantic_search_core` already builds `search_filter = None` when all filter params are `None`** (`indexer.py:62`). The regression guarantee is preserved as long as new filter params are guarded by `if param:`.

---

## Open Assumptions to Verify

1. **`multi_select` GET response shape.** Is `wiki_domain_tags` returned as `{"multi_select": [{"id": "...", "name": "..."}]}` (list of tag objects) or `{"multi_select": ["tag_id_1", "tag_id_2"]}` (list of IDs)? **Must verify against a live space before implementing the chunker extraction logic.** The third-party client suggests IDs; the in-codebase pattern for `select` returns a full tag object.

2. **`wiki_domain_tags` write path scoping.** The ticket says "no indexing/payload-schema change" in non-goals, but also lists `domain_tags` as a required filter field. The spec writer must decide: (a) include `domain_tags` payload field in scope (requires chunker + ingest/remember write path changes), or (b) defer `domain_tags` filtering to a follow-on ticket and only implement `type_key` + date/source_type filters in v1.

3. **`create_payload_index` on the real Qdrant server.** Confirmed idempotent in in-memory mode. Server behavior documented as returning `COMPLETED` or `acknowledged`. The in-memory client emits a `UserWarning` that payload indexes have no effect — tests should monkeypatch `create_payload_index` or suppress the warning.

4. **`source_type` data availability.** `wiki_source_type` is only written to `wiki_source` objects (via `remember.py:192` and the bootstrap tags). Chunks from `wiki_entity`/`wiki_concept` objects do not have a `source_type`. The payload field `source_type` will be `None` for most chunks. A filter `source_type="url"` will match only `wiki_source` object chunks.

---

## Sources

- `src/anytype_llm_wiki/indexer.py` — `semantic_search_core` (lines 20-82), `_ensure_collection` (lines 85-91), `reindex` (lines 113-188), `reembed_object` (lines 191-231), `_get_last_modified` (lines 105-110)
- `src/anytype_llm_wiki/chunker.py` — `chunk_object`, `_chunk_body`, `_chunk_properties` (payload fields: 6 fields only)
- `src/anytype_llm_wiki/server.py` — `semantic_search` (lines 22-39), `wiki_query` (lines 146-173)
- `src/anytype_llm_wiki/wiki/types_schema.py` — `WIKI_TYPES`, `DEFAULT_DOMAIN_TAGS`, property formats
- `src/anytype_llm_wiki/wiki/ingest.py` — date write pattern (line 937), domain_hint validation (lines 659-666), select write pattern (line 353)
- `src/anytype_llm_wiki/wiki/remember.py` — domain_tag validation (lines 301-307), select write pattern (line 192)
- `src/anytype_llm_wiki/wiki/lint.py` — select GET response shape (lines 388-389, 519-526), date GET response shape (line 372)
- `tests/test_indexer.py` — `FakeQdrantClient` pattern (lines 172-195), monkeypatch pattern (lines 203, 307)
- `tests/test_server.py` — existing `semantic_search` type filter test (line 66-70) — live only, no CI fake
- qdrant-client 1.18.0 models (inspected locally): `MatchAny`, `MatchValue`, `DatetimeRange`, `Range`, `PayloadSchemaType`, `create_payload_index`
- [Qdrant Payload Docs](https://qdrant.tech/documentation/manage-data/payload/) — MatchAny vs array: "succeed if at least one value meets the condition"
- [Qdrant Filtering Docs](https://qdrant.tech/documentation/search/filtering/) — filter shapes
- [Qdrant API: create-field-index](https://api.qdrant.tech/api-reference/indexes/create-field-index) — request/response schema
- [fastmcp server.py](https://github.com/qdrant/qdrant) — tool exception handling (lines 1282-1311)
- [MCP SDK server.py lowlevel](https://github.com/modelcontextprotocol/python-sdk) — `isError=True` on exception (line 447)
- [Anytype API docs (2025-11-08)](https://developers.anytype.io/docs/reference/2025-11-08/list-objects/)
- [anytype-client third-party](https://charlesneimog.github.io/anytype-client/api/property/) — multi_select as list of IDs (unverified against official API)
