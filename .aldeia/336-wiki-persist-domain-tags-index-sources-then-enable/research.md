---
name: technical-research-336-wiki-persist-domain-tags-index-sources
status: DONE
issue: 336
repo: anytype-llm-wiki
date: 2026-06-13
author: technical-researcher agent
---

# Technical Research: #336 — Persist domain_tags + Index Sources + Enable Filters

**Status:** DONE
**Date:** 2026-06-13
**Prerequisite verified:** `/Users/Shared/development/anytype-llm-wiki-worktrees/336-wiki-persist-domain-tags-index-sources-then-enable/.aldeia/336-wiki-persist-domain-tags-index-sources-then-enable/prereq-verification.md` (settled, do not re-verify)

---

## Dependency Context

**CRITICAL:** The worktree branch `aldeia/336-...` was cut from **main**, which does NOT
contain #323's code. The `#323` implementations referenced throughout this document are
read from `aldeia/323-retrieval-metadata-filters-type-tag-scoping-for-wi`. All #336 work
is a strict extension of #323.

Key verified facts from #323's implemented code (read via `git -C
/Users/Shared/development/anytype-llm-wiki show aldeia/323-...:src/...`):

- `config.py:PAYLOAD_SCHEMA_VERSION = 2` (was 1; #336 bumps to 3)
- `indexer.py`: `_chunk_to_payload` (shared helper, optional fields via `if "x" in
  chunk`), `_ensure_payload_indexes` (with `getattr(client, "create_payload_index",
  None)` guard), `semantic_search_core` (builds `must` list; `DatetimeRange`,
  `MatchValue` — **not** `MatchAny`; #336 adds `MatchAny`), `reindex` (version-marker
  migration with `force_full`)
- `chunker.py`: `chunk_object` extracts `last_modified_date` from properties, injects
  into every chunk
- `query.py`: `_WIKI_TYPE_KEYS = ("wiki_entity", "wiki_concept", "wiki_comparison",
  "wiki_query")` (hardcoded; `wiki_source` is NOT included); module-level
  `_passes_type_filter`, `_passes_date_filter`, `_parse_iso`
- `server.py` `wiki_query` tool: exposes `types`, `ingested_after`, `ingested_before`

The main-branch `indexer.py` is confirmed to lack `PAYLOAD_SCHEMA_VERSION`,
`_chunk_to_payload`, `_ensure_payload_indexes`, and date-filter params — confirming #336
must merge after #323.

---

## Q1 — domain_tags Persistence Design

### Where ingest.py should write wiki_domain_tags

`_run_ingest` is called at `ingest.py:689` from `wiki_ingest` (which validates
`domain_hint` before calling at line 689), and takes `domain_hint: str | None` as a
parameter (`ingest.py:715`). The key write points inside `_run_ingest` are:

**Entity/concept create** (`ingest.py:855`):
```python
created = client.create_object(
    space_id, type_key=type_key, name=clean_name, properties=props
)
```
`props` is built at lines 811-815 as a single-element list (`wiki_facts` or
`wiki_definition`). The `domain_tags` multi_select property should be appended to `props`
before this call.

**Entity/concept update** (`ingest.py:823-826`):
```python
updated = client.update_object(
    space_id, target["id"], {"properties": props}
)
```
Same `props` list — append `wiki_domain_tags` here too. Per the write verification, the
format is `{"key": "wiki_domain_tags", "multi_select": ["<tag_id>", ...]}`.

**Source object** (`_create_source`, `ingest.py:924`): See Q2 — source gets no
`wiki_domain_tags` (domain tags are a knowledge-domain classifier for entities/concepts,
not for the raw source document).

### Where remember.py should write wiki_domain_tags

The remember pipeline queues subjects via the work-log and processes them in
`_apply_batch` (`remember.py:510`). The write points are:

**Entity/concept create** (`remember.py:661-663`):
```python
created = client.create_object(
    space_id, type_key=type_key, name=clean_name, properties=create_props,
)
```
`create_props` is built at lines 658-660. Append `wiki_domain_tags` here.

**Entity/concept update** (`remember.py:649`):
```python
client.update_object(space_id, target_id, {"properties": patch_props})
```
`patch_props` is built at lines 639-648. Append `wiki_domain_tags` here.

The challenge: `domain_tags` is validated in `wiki_remember` (`remember.py:301`) but
is NOT passed into `meta` (`remember.py:336`) and therefore NOT available in `_apply_batch`
(which only receives `client`, `space_id`, `items`, `meta`, `result`). The `meta` dict
currently holds `relations`, `source`, `subject`. To thread `domain_tags` through the
queue:
1. Add `domain_tags` (the validated list of names) to `meta` in `wiki_remember:336`:
   `meta = {"relations": relations or [], "source": source, "subject": knowledge[:50],
   "domain_tags": domain_tags or []}`.
2. In `_apply_batch`, read `domain_tags_names = list(meta.get("domain_tags") or [])`.
3. If `domain_tags_names`: call `_resolve_multi_select_tags(...)` once per `_apply_batch`
   call (not per-object — it's a network call, cache the result at batch level).

### _resolve_multi_select_tags helper

Generalizes the existing `_resolve_select_tag` (`remember.py:124`) from a single name to
a list. Recommended signature and implementation:

```python
def _resolve_multi_select_tags(
    client: WikiClient,
    space_id: str,
    property_key: str,
    tag_names: list[str],
) -> tuple[list[str], bool]:
    """Resolve multiple multi_select tag names → tag IDs.

    Returns (resolved_ids, degraded). degraded=True when tag registry is
    unreachable; in that case resolved_ids may be a partial list. Any tag_name
    not found in the registry is silently skipped (missing tag → no-op, matching
    the existing _resolve_select_tag convention). Never aborts — degrade-not-abort.
    """
    if not tag_names:
        return [], False
    try:
        props = client.list_properties(space_id)
        prop_id = None
        for p in props:
            if isinstance(p, dict) and p.get("key") == property_key:
                prop_id = p.get("id")
                break
        # Attempt tags read even if prop_id is unresolved (mirrors SF12 symmetry).
        tags = client.list_tags(space_id, prop_id or property_key)
        name_to_id = {t["name"]: t["id"] for t in tags if t.get("name") and t.get("id")}
        resolved = [name_to_id[n] for n in tag_names if n in name_to_id]
        return resolved, False
    except httpx.HTTPError:
        return [], True
    except Exception:  # noqa: BLE001 — never abort
        return [], True
```

This function should live in `remember.py` (alongside the existing `_resolve_select_tag`
pattern) and be imported in `ingest.py`.

### Ingest: single domain_hint → multi_select

`ingest.py` takes a single `domain_hint: str | None`. The write is:
```python
if domain_hint:
    tag_ids, degraded = _resolve_multi_select_tags(
        client, space_id, "wiki_domain_tags", [domain_hint]
    )
    if degraded:
        result["warnings"].append("domain_tags_resolution_degraded")
    if tag_ids:
        domain_tag_prop = {"key": "wiki_domain_tags", "multi_select": tag_ids}
    else:
        domain_tag_prop = None
```
Then append `domain_tag_prop` to `props` at both the create and update call sites when
it is not None.

Recommendation: resolve once at the start of `_run_ingest` (not per-candidate) since all
entities from one source get the same domain tag, and the tag registry is stable per run.

### Remember: list[str] domain_tags → multi_select

`remember.py` takes `domain_tags: list[str] | None`, already validated. The resolution
call inside `_apply_batch`:
```python
domain_tag_ids: list[str] = []
domain_tags_names = list(meta.get("domain_tags") or [])
if domain_tags_names:
    domain_tag_ids, dt_degraded = _resolve_multi_select_tags(
        client, space_id, "wiki_domain_tags", domain_tags_names
    )
    if dt_degraded:
        result["warnings"].append("domain_tags_resolution_degraded")
```
Then for each create/update, if `domain_tag_ids`:
```python
create_props.append({"key": "wiki_domain_tags", "multi_select": domain_tag_ids})
```
Note: on UPDATE, `wiki_domain_tags` should be APPENDED to the existing value (not
replaced), or simply set (since the round-trip isn't read back here). Given there is no
current read of existing multi_select values before a patch, the simpler design is to SET
the multi_select to the caller-supplied values (the Anytype PATCH replaces, not merges).
This matches how other properties are patched (e.g. `wiki_facts` on update replaces the
whole text).

### Which objects get wiki_domain_tags

Both the **created/updated entity/concept objects** get `wiki_domain_tags`. The **source
object** does NOT get `wiki_domain_tags` (the source is the raw document; domain
classification belongs to the derived entities). The `_create_source` / `_create_remember_source`
signatures do not need to change for domain tags.

---

## Q2 — source_type Asymmetry

### Verification

Confirmed: `remember.py:192` writes `wiki_source_type` as a `select` property on
`wiki_source` objects created via `_create_remember_source`. The tag is resolved by
`_resolve_wiki_source_type_tag` which calls `_resolve_select_tag` for the
`"wiki_source_type"` property.

Confirmed: `ingest.py:_create_source` (`ingest.py:924-971`) does NOT write
`wiki_source_type`. The `props` list contains only `wiki_excerpt`, `wiki_ingested_at`,
and `wiki_url` or `wiki_file_path`.

### Seeded source_type values

`bootstrap.py:60`:
```python
_WIKI_SOURCE_TYPE_TAGS = ["document", "conversation", "agent"]
```
- `"document"` — the value to use for ingest-created sources (URL or file path)
- `"conversation"` — used by remember for conversation-type sources
- `"agent"` — used by remember for agent-type sources

### Recommendation

**Ingest sources should also write `wiki_source_type = "document"`.**

Rationale: A `wiki_source` object for an ingested URL/file is clearly a "document" source.
Leaving `source_type` absent means these sources never appear in `source_type` filter
results, even after #336's chunking change makes them reachable in Qdrant. The filter
would be silently incomplete: remember-produced sources (conversation/agent) filter
correctly; ingest-produced sources (document) never match a `source_type=document` filter.

Implementation in `_create_source`:
```python
# Resolve "document" source type tag (best-effort, degrade-not-abort)
source_type_tag_id, _ = _resolve_wiki_source_type_tag(client, space_id, "document")
if source_type_tag_id:
    props.append({"key": "wiki_source_type", "select": source_type_tag_id})
```
Place this after the `wiki_url`/`wiki_file_path` insert, before the `resolve_entity`
dedup check. Add `_resolve_wiki_source_type_tag` to the imports from `remember.py` in
`ingest.py` (or re-implement via `_resolve_select_tag` — the function is already in
`ingest.py` for `wiki_action`, so the pattern is available but the specific helper
`_resolve_wiki_source_type_tag` lives in `remember.py`).

**Alternative**: document in the spec that ingest sources are source_type-absent by
design (the filter always returns only remember-created sources when filtering by
`source_type`). This is a product decision, not a technical constraint. Given the ticket
title says "enable source_type filters", the "document" value being filterable is clearly
the intended behavior.

---

## Q3 — domain_tags Backfill "Where Derivable"

### Investigation

Searched for storage of original `domain_hint` across the codebase:

1. **WikiLog objects** (`wiki_log` type, written by `_write_wikilog`): The `wiki_log`
   schema writes `wiki_subject` (the source URL/path), `wiki_notes`, `wiki_action` (select
   tag), `wiki_timestamp`, `wiki_objects_created`, `wiki_objects_updated`,
   `wiki_schema_version`. There is NO `domain_hint` or `wiki_domain_tags` field in the
   WikiLog schema (`ingest.py:344-360`). The `domain_hint` is not stored in the WikiLog.

2. **Source objects** (`wiki_source` type): `_create_source` writes `wiki_url` /
   `wiki_file_path`, `wiki_excerpt`, `wiki_ingested_at`. No `domain_hint` stored.

3. **Entity/concept objects**: No `domain_hint` stored — the pipeline creates the entity
   with `wiki_facts` / `wiki_definition` only.

4. **Re-running extraction**: Re-extracting the original source would not recover the
   `domain_hint` since that was a caller-supplied parameter to `wiki_ingest`, not
   derivable from the content.

**Conclusion: There is no derivation source for the original `domain_hint` from existing
corpus objects. A one-time backfill of existing objects is NOT achievable from stored data.**

### What IS achievable

Two operations triggered by the version bump are different:

1. **Qdrant re-embed (automatic):** When `PAYLOAD_SCHEMA_VERSION` is bumped 2→3, the
   D3 migration in `reindex` forces a full re-embed of all objects. This picks up the
   NEW payload fields (`source_type`, `domain_tags`) for any objects that carry them
   after the upgrade. This is AUTOMATIC and requires no human action.

2. **Writing `wiki_domain_tags` onto existing Anytype objects (separate, not automatic):**
   This would require knowing what `domain_hint` was originally supplied for each object.
   Since that information was never stored, there is no derivation source. The backfill
   is limited to forward-only: objects created or updated AFTER the #336 deployment will
   carry `wiki_domain_tags`; existing objects will not.

### Recommendation

State plainly in the spec: **the backfill of `wiki_domain_tags` onto existing Anytype
objects is NOT achievable from stored data**. The only honest path is forward-only. The
Qdrant re-embed (auto-forced by version bump) will correctly pick up `domain_tags` for
any object that has `wiki_domain_tags` set at re-embed time, which means only
post-upgrade-created objects benefit.

The spec should explicitly distinguish:
- "Qdrant re-embed" (automatic, triggered by version bump) — picks up whatever
  `wiki_domain_tags` the Anytype objects carry at that moment
- "Anytype object backfill" (NOT achievable) — requires the original domain_hint, which
  was never stored

There is no "where derivable" shortcut available.

---

## Q4 — Product Decision: wiki_excerpt in WIKI_TEXT_PROPERTY_KEYS

### Current state

`chunker.py:WIKI_TEXT_PROPERTY_KEYS` (on `#323` branch, same as main):
```python
WIKI_TEXT_PROPERTY_KEYS = frozenset({
    "wiki_facts", "wiki_description", "wiki_definition", "wiki_open_questions",
    "wiki_dimensions", "wiki_verdict", "wiki_question", "wiki_answer",
})
```
`wiki_excerpt` is NOT in this set. `wiki_source` objects are body-less (confirmed by
the #323 spec §1.1) and produce zero chunks → never reach Qdrant.

### wiki_query's _WIKI_TYPE_KEYS — confirmed exclusion of wiki_source

From `#323` branch `query.py:50-51`:
```python
_WIKI_TYPE_KEYS = ("wiki_entity", "wiki_concept", "wiki_comparison", "wiki_query")
```
`wiki_source` is NOT in `_WIKI_TYPE_KEYS`. This is hardcoded and confirmed. Adding
`wiki_excerpt` to `WIKI_TEXT_PROPERTY_KEYS` has ZERO impact on `wiki_query` Tier-1
(which filters to `_WIKI_TYPE_KEYS` before the Qdrant call). The impact is solely on
`semantic_search` and `wiki_query` Tier-2 (vector search).

For `wiki_query` Tier-2: `wiki_query` passes `types=sorted(effective_types_set)` to
`semantic_search_core`, where `effective_types_set` is bounded by `_WIKI_TYPE_KEYS_SET`.
Since `wiki_source` is not in `_WIKI_TYPE_KEYS_SET`, `semantic_search_core` would
filter it out. So `wiki_query` Tier-2 also does NOT retrieve source chunks even if they
exist in Qdrant, AS LONG AS the `types` filter is passed (which it always is on the
`wiki_query` path). **This is a net positive: adding `wiki_excerpt` to
`WIKI_TEXT_PROPERTY_KEYS` does not change `wiki_query` behavior.**

### Options

**(a) Include sources by default (semantic_search returns all types including wiki_source)**

After adding `wiki_excerpt` to `WIKI_TEXT_PROPERTY_KEYS`, `semantic_search` (which does
NOT apply a `types` filter by default) will surface `wiki_source` chunks mixed with
entity/concept/comparison/query chunks. This changes retrieval semantics for all
`semantic_search` callers who have not passed a `types` filter.

**(b) Default-preserving: semantic_search returns sources, but callers scope via types**

Same code change (add `wiki_excerpt`) but document that callers can scope via
`types=["wiki_entity", "wiki_concept", ...]` to exclude sources, or
`types=["wiki_source"]` to get only sources. The default behavior (no types param)
changes. This is (a) plus documentation.

### Analysis

The retrieval semantics impact:
- `wiki_query`: NO impact (hardcoded `_WIKI_TYPE_KEYS` excludes `wiki_source` in both
  Tier-1 and Tier-2)
- `semantic_search` default (no types): CHANGES — source excerpts enter results
- `semantic_search` with `source_type` or `types` filter: allows precise scoping

Source excerpts are typically 1000-char truncated markdown snippets
(`ingest.py:934`: `(markdown or "")[:1000]`) or 500-char narration notes
(`remember.py:179`: `[:500]`). They are "raw material" text, not synthesized knowledge.
Including them in `semantic_search` results is potentially noisy but also potentially
useful (the source text may answer questions the derived entities don't).

### Recommendation

**Option (b) — add `wiki_excerpt` to `WIKI_TEXT_PROPERTY_KEYS`, document the semantic
change, and note that wiki_query is unaffected.**

Reasoning: The ticket (aldeia-box#336) explicitly states "Index source excerpts: add
`wiki_excerpt` to `WIKI_TEXT_PROPERTY_KEYS`" as item 2 of scope. This is the stated
intent. The `wiki_query` non-impact is a strong safety property: the primary wiki Q&A
tool doesn't change behavior. `semantic_search` is the general-purpose tool; callers who
want only entity/concept content can pass `types`. The change is reversible (remove
`wiki_excerpt` from the frozenset). The product decision point is: "does Jan/product
accept that `semantic_search` default results now include source excerpt chunks?" That is
OD-2 from the #323 spec, and this ticket is the acceptance of that decision.

---

## Q5 — Filter Build Specifics for semantic_search_core

### Slot into the must-list

The #323 branch's `semantic_search_core` builds a `must` list
(`indexer.py:83-108` on `#323`). The #336 additions append two new clauses:

```python
# source_type filter: caller supplies a list for MatchAny (symmetry with domain_tags)
if source_type:
    from qdrant_client.models import MatchAny
    must.append(
        FieldCondition(key="source_type", match=MatchAny(any=source_type))
    )

# domain_tags filter: ANY-overlap on the list-valued payload field
if domain_tags:
    from qdrant_client.models import MatchAny
    must.append(
        FieldCondition(key="domain_tags", match=MatchAny(any=domain_tags))
    )
```

### source_type: single value (MatchValue) vs list (MatchAny)

**Recommendation: list[str] + MatchAny for both `source_type` and `domain_tags`.**

Justification:
- `source_type` is a `select` property, so each chunk carries exactly one string value
  in the payload (e.g. `"document"`, `"conversation"`, `"agent"`). Filtering for a list
  of source types (`["document", "conversation"]`) is a natural use case ("give me
  sources from any document or conversation").
- Using `MatchAny` for both keeps the API symmetric and the filter build uniform. A
  single-element list `["document"]` is equivalent to `MatchValue(value="document")`.
- `MatchAny` is available in qdrant-client >=1.18.0 (verified: `uv run python -c "from
  qdrant_client.models import MatchAny; print('OK')"` returns OK on this repo's pinned
  `>=1.18.0,<2.0.0`).

### MatchAny import

The #323 spec explicitly notes `MatchAny` is NOT imported (it uses nested
`Filter(should=[FieldCondition(...)])` for the `types` filter). #336 introduces `MatchAny`
as a NEW import. Since the #323 `from qdrant_client.models import DatetimeRange,
FieldCondition, Filter, MatchValue` is inside `semantic_search_core`, the `MatchAny`
import should be added to the same import block:

```python
from qdrant_client.models import DatetimeRange, FieldCondition, Filter, MatchAny, MatchValue
```

### No-filter guarantee preservation

The `must` list remains empty when all filter params are `None`/empty (same as #323).
`source_type=[]` is falsy → no clause appended. `domain_tags=[]` is falsy → no clause
appended. `search_filter = Filter(must=must) if must else None` — unchanged. The
no-filter regression test (AC-F1 from #323) continues to pass.

### MatchAny on a scalar payload field (source_type)

Qdrant's `MatchAny` works on scalar string fields — it matches if the payload field
value equals ANY element in the list. This is correct for `source_type` (a string scalar).
For `domain_tags` (a list of strings in the payload), `MatchAny` matches if the payload
list-field contains ANY element from the filter list. Both semantics are correct and
confirmed by the Qdrant docs for KEYWORD-indexed fields.

---

## Q6 — Tier-1 Parity in wiki_query

### Context

`wiki_query` Tier-1 (index_navigation) applies Tier-1 predicates as pure functions on
enumerated objects. #323 added `_passes_type_filter` and `_passes_date_filter` in
`query.py`. #336 needs analogous predicates for `source_type` and `domain_tags`.

### Interaction with wiki_source exclusion

`wiki_query` enumerates ALL objects in `wiki_remember`/list then filters to
`_WIKI_TYPE_KEYS` (`query.py:511-514` on #323 branch):
```python
wiki_objects = [
    o for o in all_objects
    if isinstance(o, dict) and _type_of(o) in _WIKI_TYPE_KEYS
]
```
Since `wiki_source` is NOT in `_WIKI_TYPE_KEYS`, `wiki_objects` NEVER contains
`wiki_source` objects. Therefore:
- A `source_type` filter in `wiki_query` Tier-1 is **moot** — the objects being filtered
  never carry `wiki_source_type` (they are entities/concepts/comparisons/queries).
- A `domain_tags` filter in `wiki_query` Tier-1 IS meaningful — entities and concepts
  can carry `wiki_domain_tags` (that is the whole point of #336's persist step).

Both predicates should still be implemented for completeness and cross-tier consistency,
but the spec should note the `source_type` filter on `wiki_query` is effectively a no-op
in Tier-1 (no objects to filter) and in Tier-2 (types filter excludes `wiki_source`).

### Predicate sketches

```python
def _passes_source_type_filter(obj: dict, source_types: list[str]) -> bool:
    """True if the object's wiki_source_type tag name is in source_types.

    Reads the hydrated select property (format verified: {"format": "select",
    "select": {"name": ...}}). Objects lacking wiki_source_type do NOT pass
    when source_types is non-empty (mirrors Qdrant: missing field != match).
    """
    if not source_types:
        return True
    for prop in obj.get("properties", []):
        if not isinstance(prop, dict):
            continue
        if prop.get("key") == "wiki_source_type":
            select = prop.get("select")
            if isinstance(select, dict):
                return select.get("name") in source_types
            return False  # select present but None/malformed → no match
    return False  # property absent → no match


def _passes_domain_tags_filter(obj: dict, domain_tags: list[str]) -> bool:
    """True if the object's wiki_domain_tags list has ANY overlap with domain_tags.

    Reads the hydrated multi_select property (format verified: {"format":
    "multi_select", "multi_select": [{"name": ...}, ...]}). Objects lacking
    wiki_domain_tags do NOT pass when domain_tags is non-empty.
    """
    if not domain_tags:
        return True
    domain_tags_set = set(domain_tags)
    for prop in obj.get("properties", []):
        if not isinstance(prop, dict):
            continue
        if prop.get("key") == "wiki_domain_tags":
            multi = prop.get("multi_select")
            if isinstance(multi, list):
                obj_tags = {t["name"] for t in multi if isinstance(t, dict) and t.get("name")}
                return bool(obj_tags & domain_tags_set)  # ANY overlap
            return False  # multi_select present but None/malformed
    return False  # property absent → no match
```

These read from the HYDRATED Anytype GET-object shape (per prereq-verification.md:
`multi_select` returns full tag objects with `name`; `select` returns a full tag object).
They match Qdrant's filter semantics: missing field → no match.

### Tier-1 filter ordering in wiki_query

Following #323's ordering convention (cheapest-first):
1. type filter (already applied at `query.py:511-514`)
2. domain_tags filter (ANY-overlap on list → modest cost)
3. source_type filter (scalar match → also modest, but mostly moot for Tier-1)
4. date filter (already applied, requires ISO parse)

---

## Q7 — Indexes, Version Bump, and FakeQdrant

### _ensure_payload_indexes extension

Add `source_type` and `domain_tags` as KEYWORD indexes to the existing function
(`indexer.py` on #323 branch):

```python
def _ensure_payload_indexes(client: QdrantClient) -> None:
    from qdrant_client.models import PayloadSchemaType

    create_index = getattr(client, "create_payload_index", None)
    if create_index is None:
        return
    for field, schema in [
        ("type_key",           PayloadSchemaType.KEYWORD),
        ("space_id",           PayloadSchemaType.KEYWORD),
        ("last_modified_date", PayloadSchemaType.DATETIME),
        ("source_type",        PayloadSchemaType.KEYWORD),   # NEW in #336
        ("domain_tags",        PayloadSchemaType.KEYWORD),   # NEW in #336
    ]:
        create_index(config.QDRANT_COLLECTION, field, field_schema=schema)
```

`domain_tags` is a list-valued KEYWORD field. Qdrant KEYWORD indexing supports
array payload fields natively; `MatchAny` works against indexed array fields.

The `getattr` guard from #323 is RETAINED. It is critical because:
- Older `FakeQdrantClient` instances in `tests/test_indexer.py` (the ones NOT converted
  to `FakeQdrantClientWithSearch`) lack `create_payload_index`. Without the guard, a
  `reindex()` call through them raises `AttributeError`.
- The main-branch `tests/test_indexer.py` has two `FakeQdrantClient` classes
  (`test_indexer.py:172` and `test_indexer.py:283`) that do NOT have
  `create_payload_index`. These are used in tests that call `reindex()` indirectly.
  The `getattr` guard protects them.

### PAYLOAD_SCHEMA_VERSION bump: 2 → 3

```python
# config.py (on #323 branch already at 2)
PAYLOAD_SCHEMA_VERSION = 3  # v3 adds source_type and domain_tags payload fields
```

The D3 migration in `reindex` (`stored_schema = state.get("_payload_schema_version", 1)`,
`force_full = config.PAYLOAD_SCHEMA_VERSION > stored_schema`) auto-fires a full re-embed
when `3 > 2` (or `3 > 1` for pre-#323 installations). This picks up the new payload
fields for all objects. No new migration logic needed; the D3 mechanism from #323 is
reused as-is.

The `_payload_schema_version` marker is stamped only after a full (unscoped) `reindex()`
(gated by `if space_id is None` in the #323 implementation) — this rule is unchanged.

### FakeQdrantClient considerations

The `#323` branch introduces `FakeQdrantClientWithSearch` (test_indexer.py:364) which
has `create_payload_index`. The existing older fakes (`FakeQdrantClient` at lines 172,
283) do NOT have it — the `getattr` guard in `_ensure_payload_indexes` handles them.

For #336 tests:
- All filter tests use `FakeQdrantClientWithSearch` (which already has `create_payload_index`).
- The new `test_reindex_creates_payload_indexes` test (AC-F7 in #323) asserts
  `{"type_key", "space_id", "last_modified_date"} ⊆ fake.created_indexes` AND
  `"source_type" not in fake.created_indexes`. **This test MUST be updated in #336**
  to assert `{"type_key", "space_id", "last_modified_date", "source_type", "domain_tags"}
  ⊆ fake.created_indexes`.

### Auto-backfill on version bump

Yes: the forced re-embed picks up `source_type` and `domain_tags` payload fields for all
objects that carry those properties at re-embed time (i.e., after #336's write-side
changes have run). Objects that have not been re-ingested/re-remembered since the #336
deployment will have `wiki_domain_tags = []` on re-embed (no property present →
`domain_tags` absent from payload → filter never matches). This is correct behavior and
is consistent with the backfill analysis in Q3.

---

## Q8 — Documentation Staleness

### .aldeia/context/technical.md payload-schema section

**On the #323 branch**, `technical.md` has a "Qdrant chunk payload schema" section added
by #323:

```
As of PAYLOAD_SCHEMA_VERSION = 2 the payload is **7 fields**:
the 6 base fields (object_id, space_id, object_name, type_key, heading, text)
plus last_modified_date...
```

**#336 update required:** Change to:

```
As of PAYLOAD_SCHEMA_VERSION = 3 the payload is **up to 9 fields**:
the 6 base fields (object_id, space_id, object_name, type_key, heading, text),
plus optional last_modified_date (ISO-8601 string, all object types),
plus optional source_type (str, wiki_source objects only),
plus optional domain_tags (list[str] of tag names, entities/concepts carrying wiki_domain_tags).
All optional fields are absent from the payload dict (not null) when not present,
consistent with Qdrant's filter-miss-on-absent behavior.
```

Note: the `technical.md` on THIS BRANCH (main state) does NOT yet have the payload
schema section. When #336 is implemented (after #323 merges), the technical.md starting
point will be the #323 version. The updater should work from the #323 branch version.

### README tool docs

The `semantic_search` tool and `wiki_query` tool docs need new params documented:
- `source_type: list[str] | None = None` — filter by source type tag names
- `domain_tags: list[str] | None = None` — filter by domain tag names (ANY-overlap)

### Release note

The release note for the version carrying #336 should include:
1. The second payload-schema bump (v3) — a one-time full re-embed is auto-triggered on
   next `reindex` (same mechanics as #323's v2 bump).
2. New write-side behavior: `wiki_ingest` and `wiki_remember` now persist `wiki_domain_tags`
   on created/updated entities and concepts.
3. `wiki_ingest` now stamps `wiki_source_type = "document"` on source objects (if the
   recommendation in Q2 is accepted).
4. `semantic_search` now includes `wiki_source` excerpt chunks in default results
   (source excerpts are indexed via `wiki_excerpt` addition to `WIKI_TEXT_PROPERTY_KEYS`).
   `wiki_query` is unaffected.
5. New filter params: `source_type` and `domain_tags` on both `semantic_search` and
   `wiki_query`.

---

## Summary of Risks and Open Decisions

### Risks

1. **FakeQdrantClient test breakage (moderate, mitigable):** Adding two entries to
   `_ensure_payload_indexes` changes the set asserted in `test_reindex_creates_payload_indexes`.
   The #323 test explicitly asserts `"source_type" not in fake.created_indexes` — this
   assertion must be inverted in #336. The `getattr` guard prevents older fakes from
   raising on the `create_payload_index` call.

2. **domain_tags threading through the work-log queue (moderate):** `remember.py`'s
   `domain_tags` is validated in `wiki_remember` but never stored in `meta` (confirmed
   at `remember.py:336`). The work-log queue stores `meta` as JSON. Adding `domain_tags`
   to `meta` requires verifying the worklog serializer handles list values correctly
   (it stores `meta` as `{"relations": [...], "source": ..., "subject": ...}` via JSON,
   so a `"domain_tags": ["ai", "ml"]` list is clean JSON). Low technical risk but must
   be explicitly coded.

3. **source_type on ingest sources (low):** The `_resolve_wiki_source_type_tag` helper
   is currently in `remember.py`, not imported in `ingest.py`. Importing it creates a
   potential circular import (remember.py imports from ingest.py at line 39-46). Solution:
   move `_resolve_select_tag` and its wrappers to a shared module (e.g., `ingest.py`
   already has `_resolve_wiki_action_tag`), OR inline the `_resolve_select_tag` call in
   `_create_source` without importing from remember.py (duplicate the 15-line helper).
   Recommend: inline a direct `_resolve_select_tag(client, space_id, "wiki_source_type",
   "document")` call in `_create_source` using the existing `_resolve_select_tag`-style
   pattern already present in `ingest.py` (for `_resolve_wiki_action_tag`). Actually,
   `_resolve_select_tag` does NOT already exist in `ingest.py` — it's in `remember.py`.
   The circular import risk is real: `remember.py` imports `from .ingest import
   _resolve_wiki_action_tag` (line 39-46). If `ingest.py` then imports from `remember.py`,
   that's circular. **Recommended resolution: move `_resolve_select_tag` to a new
   shared helper module `wiki/tag_resolver.py` (or add it to `ingest.py` and have
   `remember.py` import it from there).** Or simply duplicate the 15-line function in
   `_create_source` directly (inline, named `_resolve_select_tag_local`).

4. **MatchAny on list payload field (low):** `domain_tags` in the Qdrant payload is
   a list of strings. Qdrant KEYWORD indexes support array fields and `MatchAny` works
   correctly against them. This is standard Qdrant behavior and is lower risk than a
   custom `Filter(should=[...])` approach.

### Open Decisions (for Jan/product sign-off)

1. **OD-Q2-resolved (the #336 ticket IS the resolution):** Should `wiki_excerpt` be added
   to `WIKI_TEXT_PROPERTY_KEYS`? The #336 ticket was created specifically to accept OD-2
   from #323. If this ticket is proceeding to implementation, OD-2 is accepted. The spec
   should state this explicitly.

2. **Should ingest sources get `wiki_source_type = "document"`?** Recommend YES (see Q2).
   If NO, document that the `source_type` filter only works for remember-produced sources.

3. **For the domain_tags update path in remember.py:** Should updating an existing entity
   SET (replace) or MERGE (union) the `wiki_domain_tags` multi_select? The current
   `update_object` PATCH semantics replace the property value. A merge would require a
   GET-then-PATCH cycle. Recommendation: SET (replace) for simplicity and consistency
   with how `wiki_facts`/`wiki_definition` are patched.

---

## Key File:Line References

| Subject | Location |
|---------|----------|
| `_WIKI_TYPE_KEYS` (excludes wiki_source) | `#323:query.py:50` |
| `_passes_type_filter`, `_passes_date_filter` | `#323:query.py:275-300` |
| `PAYLOAD_SCHEMA_VERSION = 2` | `#323:config.py:43` |
| `_chunk_to_payload` (shared payload builder) | `#323:indexer.py:22-37` |
| `_ensure_payload_indexes` with getattr guard | `#323:indexer.py:41-57` |
| `semantic_search_core` must-list build | `#323:indexer.py:83-108` |
| Version-marker migration | `#323:indexer.py:145-149` |
| `WIKI_TEXT_PROPERTY_KEYS` (no wiki_excerpt) | `#323:chunker.py:13-17` (same on main) |
| `chunk_object` with last_modified_date injection | `#323:chunker.py:27-64` |
| `_resolve_select_tag` (pattern to generalize) | `main:remember.py:124` |
| `_resolve_wiki_source_type_tag` | `main:remember.py:154-157` |
| `_create_remember_source` writes wiki_source_type | `main:remember.py:165-200` |
| `_create_source` (ingest, NO wiki_source_type) | `main:ingest.py:924-971` |
| `_run_ingest` entity create call site | `main:ingest.py:855` |
| `_run_ingest` entity update call site | `main:ingest.py:823-826` |
| `domain_hint` validation (NOT persisted) | `main:ingest.py:659-666` |
| `domain_tags` validation (NOT persisted, NOT in meta) | `main:remember.py:301-308, 336` |
| `_apply_batch` entity create call site | `main:remember.py:661-663` |
| `_apply_batch` entity update call site | `main:remember.py:649` |
| `_domain_taxonomy` (returns set of tag names) | `main:ingest.py:608-623` |
| `_WIKI_SOURCE_TYPE_TAGS = ["document","conversation","agent"]` | `main:bootstrap.py:60` |
| `WikiClient.list_tags`, `WikiClient.create_object`, `WikiClient.update_object` | `main:wiki_client.py:127-83` |
| `test_reindex_creates_payload_indexes` (asserts source_type NOT indexed) | `#323:tests/test_indexer.py:~564-580` |
| `FakeQdrantClientWithSearch` (has create_payload_index) | `#323:tests/test_indexer.py:364` |
| Existing `FakeQdrantClient` without create_payload_index | `main:tests/test_indexer.py:172, 283` |
