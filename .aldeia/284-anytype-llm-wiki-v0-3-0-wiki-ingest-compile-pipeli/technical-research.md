# Technical Research: #284 — anytype-llm-wiki v0.3.0 `wiki_ingest`

**Date:** 2026-06-03
**Researcher:** technical-research worker
**Questions investigated:** (1) Indexer property-gap closure; (2) Schema-version marker home reconciliation; (3) `wiki_action` select-tag pre-creation

---

## Question 1 — Indexer Property-Gap Closure

### 1a. API data shape returned by get_object and list_objects

**list_objects (summary objects)**

`anytype_client.py:list_objects` (`AnytypeReadClient.list_objects`, lines 23-40) calls
`GET /v1/spaces/{space_id}/objects` with pagination. The response is `{"data": [...], "pagination": {...}}`;
each item in `data[]` is a summary object dict. From the live `impl-review-r2.md` verification
(gate table, line 27):

> Live `GET /v1/spaces/{wiki-e2e-1}/objects`: per-object `properties[]` array present;
> WikiLog carries `wiki_schema_version=0.2.0`; root "Wiki" collection has NO `wiki_schema_version` property

The live-verified shape per object summary is:
```json
{
  "id":   "...",
  "name": "...",
  "type": {"key": "wiki_entity"},
  "properties": [
    {"key": "wiki_description",   "text":   "..."},
    {"key": "wiki_facts",         "text":   "..."},
    {"key": "wiki_schema_version","text":   "0.2.0"},
    {"key": "last_modified_date", "date":   "2026-06-01T09:05:56Z"},
    {"key": "wiki_status",        "select": "active"},
    {"key": "wiki_sources",       "objects": ["<id1>", "<id2>"]},
    ...
  ]
}
```

The code in `indexer.py:_get_last_modified` (lines 40-45) already reads `last_modified_date` from
this array shape — it iterates `obj.get("properties", [])` and looks for `prop.get("key") == "last_modified_date"`,
returning `prop.get("date")`. This confirms the properties-as-list shape is the live contract.

The test `test_bootstrap.py:TestFoundSchemaVersionRealShape` (lines 860-914) explicitly documents:
> "Against a live Anytype API, `GET /objects` returns each object's `properties` as a LIST of
> `{"key": ..., "text": ...}` entries."

And seeds `{"properties": [{"key": "wiki_schema_version", "text": "0.2.0"}]}` as the authoritative shape.

**get_object (full object with format=md)**

`anytype_client.py:get_object` (lines 44-52) calls `GET /v1/spaces/{space_id}/objects/{object_id}?format=md`.
It returns `resp.json()["object"]`. The test mock at `test_anytype_client.py:189` seeds:
```json
{"id": "obj-1", "name": "Note", "markdown": "# Note\nContent."}
```

The `format=md` parameter is documented to add a `markdown` key. However, there is **no test or
documented evidence that `format=md` also strips or suppresses the `properties[]` array**. The
`list_objects` shape includes `properties[]`. The single-object GET simply unwraps `resp.json()["object"]`
— it does not post-process the response. Pending live confirmation, the safe assumption (and the
one the implementation must be built to) is:

- `get_object(format=md)` returns a dict with AT MINIMUM `{"id", "name", "markdown", "type", "space_id"}`.
- Whether `properties[]` is also present in the single-object response is **not confirmed** by the
  current test suite or the impl-review-r2 live run. The live run only exercised `list_objects`.

**Consequence for the chunker fix:** The chunker must NOT assume `get_object` returns `properties[]`.
The indexer already fetches the summary from `list_objects` (which carries `properties[]`) before
calling `get_object`. The fix can either:
(i) Pass the summary dict's `properties[]` alongside the `get_object` result, or
(ii) Read properties from the `get_object` result if present, falling back gracefully if absent.

Option (ii) is safer (one source of truth per object, natural shape if the API does include properties
in single-object GET). A pre-release verification item (see 1d below) must confirm whether
`GET /objects/{id}?format=md` includes `properties[]`.

**Confirmed dict keys the chunker can rely on from the summary (list_objects):**
- `id`, `name`, `type.key`, `space_id` — top-level
- `properties[]` — list of `{"key": str, <typed_field>: <value>}` where typed_field is one of:
  `text`, `date`, `number`, `select`, `multi_select`, `url`, `objects`

**Confirmed dict keys the chunker can rely on from get_object:**
- `id`, `name`, `markdown`, `type` (at minimum)
- `space_id` — present in the object summary; likely present in single-object GET but unconfirmed by test

### 1b. Wiki text properties carrying embeddable knowledge

Cross-referencing `types_schema.py` (lines 67-152) with the master spec type schema
(spec.md lines 243-292):

| Type | Property Key | Format | Embeddable? | Rationale |
|------|-------------|--------|------------|-----------|
| wiki_entity | `wiki_description` | text | YES | synthesized description, human-readable prose |
| wiki_entity | `wiki_facts` | text | YES | bullet-list of key facts |
| wiki_entity | `wiki_relations` | objects | NO | object links, not text |
| wiki_entity | `wiki_sources` | objects | NO | object links |
| wiki_entity | `wiki_domain_tags` | multi_select | NO | taxonomy tags, not prose |
| wiki_entity | `wiki_contradictions` | objects | NO | object links |
| wiki_entity | `wiki_status` | select | NO | enum, not prose |
| wiki_entity | `wiki_last_reviewed` | date | NO | timestamp |
| wiki_concept | `wiki_definition` | text | YES | synthesized definition, human-readable prose |
| wiki_concept | `wiki_open_questions` | text | YES | unresolved questions |
| wiki_concept | `wiki_related` | objects | NO | object links |
| wiki_concept | `wiki_sources` | objects | NO | object links |
| wiki_concept | `wiki_domain_tags` | multi_select | NO | taxonomy |
| wiki_concept | `wiki_contradictions` | objects | NO | object links |
| wiki_concept | `wiki_status` | select | NO | enum |
| wiki_source | `wiki_url` | url | NO | URL, not embeddable prose |
| wiki_source | `wiki_file_path` | text | NO | path string, not meaningful prose |
| wiki_source | `wiki_excerpt` | text | YES (marginal) | first 500 chars of content; low priority |
| wiki_source | `wiki_domain_tags` | multi_select | NO | taxonomy |
| wiki_source | `wiki_source_type` | select | NO | enum |
| wiki_comparison | `wiki_dimensions` | text | YES | comparison axes in markdown/bullets |
| wiki_comparison | `wiki_verdict` | text | YES | synthesized conclusion |
| wiki_comparison | `wiki_subjects` | objects | NO | object links |
| wiki_comparison | `wiki_sources` | objects | NO | object links |
| wiki_query | `wiki_question` | text | YES | the question asked |
| wiki_query | `wiki_answer` | text | YES | synthesized answer |
| wiki_query | `wiki_drew_from` | objects | NO | object links |
| wiki_query | `wiki_asked_at` | date | NO | timestamp |
| wiki_log | `wiki_subject` | text | NO | operational metadata, not knowledge |
| wiki_log | `wiki_notes` | text | NO | operational metadata |
| wiki_log | `wiki_action` | select | NO | enum |
| wiki_log | `wiki_objects_created` | number | NO | count |
| wiki_log | `wiki_schema_version` | text | NO | version string, not knowledge |
| wiki_log | `wiki_timestamp` | date | NO | timestamp |

**Primary embeddable properties (the EMBED_ALLOWLIST):**

| Property Key | Types | Rationale |
|-------------|-------|-----------|
| `wiki_facts` | wiki_entity | core knowledge, always populated by ingest |
| `wiki_description` | wiki_entity | synthesized description |
| `wiki_definition` | wiki_concept | core knowledge for concepts |
| `wiki_open_questions` | wiki_concept | secondary; valuable for retrieval |
| `wiki_dimensions` | wiki_comparison | comparison axes |
| `wiki_verdict` | wiki_comparison | synthesis conclusion |
| `wiki_question` | wiki_query | the question text |
| `wiki_answer` | wiki_query | the answer |

`wiki_excerpt` (wiki_source) is intentionally excluded from the primary allowlist: the Source
object's value comes from the origin document body (the markdown converted from HTML), which is
already chunked from the markdown body. Including `wiki_excerpt` would double-index the opening
500 characters. It may be added as an opt-in in a later version.

WikiLog properties are excluded entirely — they are operational metadata, not knowledge.

### 1c. Recommended design

**Approach (a) — ingest writes a markdown body on create:**
The PATCH body is silently ignored (`patch-decision.md: patch_body_updates: silently_ignored`).
CREATE-time body is persisted. On RE-INGEST of an existing entity (the update path), ingest
can only update the entity via property PATCH — the body cannot be refreshed. Therefore, if the
body is the primary knowledge surface, re-ingested and updated knowledge in properties becomes
invisible to `semantic_search` until a manual delete-and-recreate (which breaks inbound Relations).
**Approach (a) is rejected.** It cannot maintain body freshness on the update path without
violating the "no delete-and-recreate" constraint.

**Approach (b) — extend chunk_object to emit property-based chunks:**
Property PATCH works (`patch-decision.md: patch_property_updates: works`). Every time ingest
updates an entity's `wiki_facts` / `wiki_description` via property PATCH, those values are durable.
If `chunk_object` reads the `properties[]` array from the object dict and emits chunks from the
allowlisted text properties, the reindex will pick up the fresh content after every property update.
This approach is also correct for MANUALLY CREATED wiki objects (e.g. a user creates an Entity
directly in Anytype and fills in `wiki_facts` manually) — the indexer will find and embed them on
the next reindex without any ingest cooperation.

**Recommendation: Approach (b).**

**Detailed design for approach (b):**

The change is **purely in `chunker.py`** (plus a constant for the allowlist). The indexer does
not need to change; `reindex` already calls `chunk_object(obj)` where `obj` is the dict from
`get_object`. The fix is:

1. Add a module-level constant in `chunker.py`:
```python
# Property keys whose text values are worth embedding. Keyed to the wiki_* namespace
# so non-wiki objects (ordinary Anytype notes) are unaffected.
WIKI_TEXT_PROPERTY_KEYS = frozenset({
    "wiki_facts",
    "wiki_description",
    "wiki_definition",
    "wiki_open_questions",
    "wiki_dimensions",
    "wiki_verdict",
    "wiki_question",
    "wiki_answer",
})
```

2. Add a helper to `chunk_object` that reads `obj.get("properties", [])`, filters to
   `WIKI_TEXT_PROPERTY_KEYS`, and emits one chunk per property key whose `text` value is
   non-empty.

3. Each property chunk uses the same metadata shape as body chunks:
```python
{
    "object_id":   obj["id"],
    "space_id":    obj["space_id"],
    "object_name": obj.get("name", ""),
    "type_key":    obj.get("type", {}).get("key", "unknown"),
    "heading":     "<property_display_name>",   # e.g. "Facts", "Definition"
    "text":        <property text value>,
}
```
The `heading` field maps property key to display name for intelligible search results:
`wiki_facts→"Facts"`, `wiki_description→"Description"`, `wiki_definition→"Definition"`,
`wiki_open_questions→"Open Questions"`, `wiki_dimensions→"Dimensions"`,
`wiki_verdict→"Verdict"`, `wiki_question→"Question"`, `wiki_answer→"Answer"`.

4. **Dedup against body:** If the body markdown already contains the same text (e.g. ingest
   wrote the description into the body on create), embedding it again as a property chunk would
   double-index identical text. The recommended approach is: **emit property chunks ONLY if
   the overall markdown body is empty or absent**. If `markdown` is non-empty, the body chunks
   already cover the content; the property chunks add the structured alternative representation
   only when the body is blank (the normal case for wiki objects after a property-only ingest).
   An alternative is to always emit property chunks and accept some overlap — acceptable since
   Qdrant similarity search degrades gracefully with near-duplicate vectors, but the
   markdown-absent guard is cleaner.

5. **Property chunk splitting:** Each property value is split by the same `_split_large`
   function if it exceeds `MAX_CHUNK_CHARS` (1500 chars). For `wiki_facts` (a bullet list that
   could be several KB after multiple ingests), this is important.

**Scope of change:** `chunker.py` only. The indexer already passes the full `obj` dict from
`get_object` to `chunk_object` (`indexer.py:75`). No changes to `indexer.py` or `anytype_client.py`
are needed for the chunker extension.

**Backward compatibility / blast radius:**

The allowlist is explicitly scoped to `wiki_*` keys. An ordinary Anytype note or page with
properties like `name`, `description`, `status` etc. will have none of its property keys in
`WIKI_TEXT_PROPERTY_KEYS`, so `chunk_object` behavior for non-wiki objects is unchanged.
A user's custom property named `wiki_description` (accidentally matching the prefix) would be
embedded — this is acceptable; it matches the wiki convention, and the `wiki_` prefix is
explicitly reserved by the module.

**`_get_last_modified` and change detection:**

`indexer.py:_get_last_modified` (lines 40-45) already reads `last_modified_date` from the summary
object's `properties[]`. Property updates via PATCH bump `last_modified_date` on the Anytype
server — this is standard Anytype behavior (the field is a system-maintained timestamp). This
is not explicitly live-verified in the current test suite; it should be confirmed during the
v0.3.0 pre-release live run (see verification item below).

### 1d. Verification items (live pre-release)

**V1 (MUST):** Confirm `GET /v1/spaces/{id}/objects/{id}?format=md` response includes `properties[]`
array. Pass criterion: the object dict from `get_object()` contains a `"properties"` key that is
a list. If absent: add a step in the indexer to carry the summary's `properties[]` into the
full-object dict before calling `chunk_object`.

**V2 (MUST):** After a property PATCH (`update_object` with a `properties` payload), confirm
`last_modified_date` is updated. Pass criterion: re-read the object via `list_objects` and compare
`last_modified_date` before and after. If NOT updated: the incremental reindex will miss
property-only updates and a full-reindex trigger (or a different change-detection field) is needed.

**V3 (SHOULD):** Confirm `chunk_object` on a live wiki Entity with `wiki_facts` populated yields
at least one chunk. This validates the full pipeline: `list_objects` → detect change →
`get_object` → `chunk_object` → embed → Qdrant.

---

**Recommendation:** Implement approach (b). Add `WIKI_TEXT_PROPERTY_KEYS` frozenset to `chunker.py`;
extend `chunk_object` to read `properties[]` and emit one chunk per allowlisted key with non-empty
text; use property key → display name mapping for the `heading` field; emit property chunks only
when body is absent; run V1/V2/V3 live verification at pre-release.

**Spec actions:**
- Spec must state: `chunk_object` emits property-based chunks for `WIKI_TEXT_PROPERTY_KEYS`
  when `properties[]` is present on the object dict.
- Spec must list the exact EMBED_ALLOWLIST: `wiki_facts`, `wiki_description`, `wiki_definition`,
  `wiki_open_questions`, `wiki_dimensions`, `wiki_verdict`, `wiki_question`, `wiki_answer`.
- Spec must state: non-wiki properties (any key not in the allowlist) are never embedded, preserving
  backward compatibility for ordinary Anytype objects.
- Spec must state: each property chunk carries `heading = <display_name>` (enumerated in spec or
  delegated to code constant) so search results are intelligible.
- Spec must include V1 and V2 as pre-release checklist items.
- Spec must state: the `wiki_excerpt` (wiki_source) property is NOT in the primary allowlist
  to avoid double-indexing; deferred to a future version.

---

## Question 2 — Schema-Version Marker Home Reconciliation

### 2a. Current state and the core question

The v0.2.0 implementation stamps `wiki_schema_version` on the per-run **WikiLog** object, not on
the root Collection (`bootstrap.py:416`). The root Collection is created with `properties=None`
(`bootstrap.py:383`). This is confirmed live:

> "root 'Wiki' collection has NO `wiki_schema_version` property" (`impl-review-r2.md` gate table, line 28)

The master spec (spec.md:1590) states: "The bootstrap records this version on a dedicated object
created by `wiki_bootstrap` (the root Collection carries a `wiki_schema_version` text property
set to `WIKI_SCHEMA_VERSION` at creation time)."

The spec's upgrade path (spec.md:1603) says: "On success, updates `wiki_schema_version` on the
root Collection to the running code's `WIKI_SCHEMA_VERSION`."

And AC #13 (spec.md:743) and v0.3.0 AC #14 (spec.md:834) reference reading the marker "from the
root Collection."

**The question:** Can a custom text property be reliably persisted on a system `collection`-typed
root object via property PATCH?

### 2b. Evidence on collection type and property PATCH

The root "Wiki" object has `type.key == "collection"` (verified live, `impl-review-r2.md` gate
table). The system `collection` type is not created by bootstrap — it is a built-in Anytype type.

The v0.2.0 decision NOT to stamp it on the root Collection is documented in `known-limitations.md:#2`:
> "the system `collection` type did not reliably persist a custom property"

However, the `patch-decision.md` record (`patch_property_updates: works`) refers to PATCH of a
**property value on an existing object**. The v0.2.0 limitation is specifically about whether a
CUSTOM property can be READ BACK on a collection-typed object — not about whether PATCH of a
property value works once the property is linked.

`bootstrap.py:_found_schema_version` (lines 97-120) reads `wiki_schema_version` by iterating the
`properties[]` array returned by `list_objects`. If the "collection" type does not include
`wiki_schema_version` in its property list, `GET /objects` would return the collection object
without that property in its `properties[]` array, making the marker invisible to the reader.

The `update_object` PATCH path (`wiki_client.py:78-83`) sends:
`PATCH /v1/spaces/{id}/objects/{id}` with a JSON body containing `properties` as a PropertyLinkWithValue
array. If `patch_property_updates: works`, and if the collection type allows linking the
`wiki_schema_version` property to it, then the PATCH would persist.

**Ambiguity that cannot be resolved without a live probe:**
The v0.2.0 finding says custom properties did NOT reliably persist on the collection type. This
could mean:
(a) The Anytype API refuses to link a custom property to a system collection type, or
(b) The API accepts the PATCH (returns 2xx) but the property is silently dropped from the
    returned `properties[]` array — a "silently ignored" behavior analogous to `patch_body_updates`.

Either (a) or (b) would cause `_found_schema_version` to return `None` even after a successful-seeming
PATCH. Since no live probe was run this session (instructions: headless), this must be flagged as
a required live verification item.

### 2c. Option evaluation

**Option (a) — stamp the root Collection (spec as written):**
- Mechanism: after creating or finding the root Collection, call `client.update_object(space_id, collection_id, {"properties": [{"key": "wiki_schema_version", "text": WIKI_SCHEMA_VERSION}]})`.
- Read back: `_found_schema_version(root_collection_obj)` from the summary returned by `list_objects`.
- Single authoritative value: yes — one long-lived object, one property.
- Upgrade path: re-run `update_object` PATCH on the collection on any schema upgrade.
- Risk: the v0.2.0 live finding that "collection did not reliably persist a custom property" may
  still hold. If the PATCH silently drops the property, `wiki_ingest` would incorrectly report
  `wiki_schema_missing` and block.
- Migration for existing v0.2.0 spaces: the bootstrap upgrade path PATCHes the collection; on
  first v0.3.0 bootstrap, the WikiLog markers are still present, so `_max_version` over all
  objects finds the existing version, confirms it is an upgrade, proceeds, and stamps the
  collection after completion.

**Option (b-1) — keep WikiLog approach, make it idempotent/single-valued:**
- Mechanism: on first bootstrap, create ONE canonical "schema marker" WikiLog entry with a
  stable name (e.g. `"wiki:schema-marker"`). On re-bootstrap, detect this marker by name and
  PATCH it. On upgrade, PATCH the same marker object.
- Read back: `_found_schema_version` finds it by name, reads `wiki_schema_version` from its
  `properties[]`.
- Single authoritative value: yes — one named object.
- Advantage: avoids the collection-type PATCH uncertainty entirely (wiki_log type is
  wiki-owned, not a system type, so custom properties are guaranteed to persist).
- Risk: a marker with a predictable name could be accidentally deleted or edited by the user.
  Lower risk than unbounded accumulation.
- Does NOT require spec-writer sign-off to amend AC #13 — it can be framed as "the marker
  object is a dedicated WikiLog entry named `wiki:schema-marker`, which serves as the singleton
  root for schema version reads."

**Option (b-2) — dedicated marker type (new type, not WikiLog):**
Overkill for v0.3.0. Deferred.

### 2d. Recommendation

**Recommend Option (a) with a live verification gate, falling back to Option (b-1) if the gate fails.**

The spec-writer should specify Option (a) as the primary design (it matches the existing spec
and AC #13). The v0.3.0 pre-release checklist MUST include a live verification gate:

**Live verification gate V4 (MUST for v0.3.0):**
1. After `wiki_bootstrap` runs on a fresh space, call `update_object(space_id, collection_id, {"properties": [{"key": "wiki_schema_version", "text": "0.3.0"}]})`.
2. Re-read the collection via `list_objects` (NOT `get_object` — the summary is what `_found_schema_version` reads).
3. Pass criterion: `_found_schema_version(collection_summary) == "0.3.0"`.
4. Fail criterion: property is absent or blank. If FAIL: adopt Option (b-1) and amend the spec with sign-off.

**Option (a) implementation details:**

Bootstrap changes:
- In `_run_bootstrap` at `bootstrap.py:374-387`, after creating or locating the root Collection,
  add a PATCH step: `client.update_object(space_id, collection_id, {"properties": [{"key": "wiki_schema_version", "text": WIKI_SCHEMA_VERSION}]})`.
- Wrap in a try/except that logs a warning and falls back to the WikiLog-stamp behavior if the
  PATCH fails (so bootstrap remains functional even if the collection type rejects the property).
- The WikiLog stamp (`bootstrap.py:416`) is KEPT as informational/redundant — do not remove it.
  This provides a read-fallback for `_found_schema_version` if the collection PATCH fails silently.

Schema compat check in wiki_ingest / wiki_query / wiki_lint:
- Step 1: call `list_objects(space_id)`, find the object with `name == "Wiki"` and
  `type.key == "collection"`. Call `_found_schema_version(collection_obj)`. If found, use it as
  authoritative.
- Step 2 (fallback): if not found on the collection, fall back to `_max_version` over all
  `wiki_log` typed objects (this handles v0.2.0 spaces that only have WikiLog markers, and
  handles the case where Option (a) PATCH failed silently).
- If neither finds a version: `[CONFIG ERROR] wiki_schema_missing`.

**Migration for existing v0.2.0 spaces:**
v0.2.0 spaces have the marker on WikiLog only. On first v0.3.0 `wiki_bootstrap` run:
1. `_run_bootstrap` scans all objects, finds `wiki_schema_version=0.2.0` on a WikiLog.
2. Detects `is_upgrade = True` (0.2.0 < 0.3.0).
3. Runs upgrade path, then PATCHes the root Collection with `wiki_schema_version=0.3.0`.
4. After the upgrade, the collection carries the authoritative marker.
For existing v0.2.0 spaces that do NOT run `wiki_bootstrap` before using v0.3.0 tools:
the fallback read path (step 2 above) finds the WikiLog markers and returns `0.2.0`, which triggers
`wiki_schema_outdated` → operator is directed to run `wiki_bootstrap` → upgrade proceeds.

**`known-limitations.md #2` reconciliation:**
Item #2 is resolved by either confirming Option (a) works (collection PATCH sticks) or by
adopting Option (b-1) (idempotent single-marker WikiLog). Either way, the "v0.3.0+ must
reconcile" condition is addressed. `known-limitations.md #2` should be updated to record the
chosen path and mark it resolved.

---

**Recommendation:** Specify Option (a) — stamp root Collection via property PATCH — as the primary
design. Make the PATCH best-effort with a WikiLog stamp fallback. Gate the release on live
verification V4. If V4 fails, pivot to Option (b-1) (idempotent single-named WikiLog marker).

**Spec actions:**
- Spec must state: `wiki_bootstrap` PATCHes `wiki_schema_version` onto the root Collection after
  creating it (or after locating it on re-bootstrap). PATCH is best-effort; WikiLog stamp is
  retained as informational fallback.
- Spec must state: schema-compat read order is (1) root Collection `wiki_schema_version`,
  (2) `_max_version` over `wiki_log` typed objects.
- Spec must add V4 as a pre-release checklist MUST item.
- Spec must provide Option (b-1) as the fallback design with explicit pivot criterion
  (V4 fails at gate).
- `docs/known-limitations.md #2` must be updated/closed when the chosen mechanism is confirmed.
- `impl-review-r2.md` SHOULD-FIX-1 is addressed by this design (collection-as-authoritative-marker
  ends the unbounded WikiLog accumulation problem).

---

## Question 3 — `wiki_action` Select-Tag Pre-Creation

### 3a. How select tag creation works

From `wiki_client.py:create_tag` (lines 36-51): creating a select/multi-select option requires
a call to `POST /v1/spaces/{id}/properties/{property_id}/tags` with a body containing at least
`{"name": <tag_name>, "color": <color>}`. The API returns `{"tag": {"id": ..., "name": ..., "color": ...}}`.

Setting a select value on an object requires passing the tag's **id** (not its name) in the
PropertyLinkWithValue: `{"key": "wiki_action", "select": "<tag_id>"}`.

From `bootstrap.py:_build_props_list` (lines 439-451): the `select` format maps to a `select`
field in the PropertyLinkWithValue dict. If the tag id does not pre-exist, writing the bare name
as a select value would fail or be ignored by the API — this is confirmed by the v0.2.0 behavior
(wiki_action was silently dropped, `impl-review-r2.md` SHOULD-FIX-2, line 58-73).

The `wiki_action` property is on the `wiki_log` type (types_schema.py:143). Its property ID is
resolved from `client.list_properties(space_id)` — it is the same resolution path used for
`wiki_domain_tags`.

### 3b. Where tag creation should happen

**Option A — create `wiki_action` tags during `wiki_bootstrap`:**
- All five enum values (`ingest`, `query`, `lint`, `bootstrap`, `archive`) are created when the
  schema is bootstrapped.
- Subsequent tools (`wiki_ingest`, `wiki_query`, `wiki_lint`) can safely reference tag IDs.
- Bootstrap is already the place where `wiki_domain_tags` options are created (bootstrap.py:331-367).
- Creating the full enum up front is consistent with the "complete schema from day one" principle
  (spec.md:276 on the Comparison type).
- Re-bootstrap (idempotent run) would detect existing tags and skip them — same union-only logic
  used for `wiki_domain_tags`.

**Option B — lazy creation in each tool (ingest creates `ingest` tag, etc.):**
- Each tool creates its own tag option on first use.
- More complex: each tool must handle the "tag already exists" case and retry reads.
- Race conditions if two tools run concurrently (though the per-space lock serializes ingest).
- Against the "spec-correct" principle of having a complete schema post-bootstrap.

**Recommendation: Option A.** Create all five `wiki_action` tag options during `wiki_bootstrap`.
This is the right design because:
1. Bootstrap already creates domain tag options — the same code path handles `wiki_action` tags.
2. `wiki_ingest` is the first consumer; it should not be responsible for schema provisioning.
3. The full enum is known at spec time; creating all values up front avoids drift.

### 3c. Exact call sequence

1. In `_run_bootstrap`, after the properties loop, resolve the `wiki_action` property ID from
   `prop_map`:
   ```python
   action_pid = prop_map.get("wiki_action")
   ```
2. If `action_pid` is available, fetch existing tags:
   ```python
   existing_action_tags = client.list_tags(space_id, action_pid)
   existing_action_names = {t.get("name") for t in existing_action_tags}
   ```
3. For each value in `["ingest", "query", "lint", "bootstrap", "archive"]` NOT in
   `existing_action_names`, create the tag:
   ```python
   created = client.create_tag(space_id, action_pid, {"name": value, "color": color})
   ```
   (color cycles from `TAG_COLOR_PALETTE`)
4. Build a `action_tag_id_map: dict[str, str]` from all tags (existing + newly created):
   ```python
   all_action_tags = client.list_tags(space_id, action_pid)
   action_tag_id_map = {t["name"]: t["id"] for t in all_action_tags}
   ```
5. When writing the WikiLog entry, pass the tag ID:
   ```python
   action_id = action_tag_id_map.get("bootstrap")
   if action_id:
       log_props.append({"key": "wiki_action", "select": action_id})
   ```

In `wiki_ingest`, the same approach: at ingest start, resolve `wiki_action` property ID from
`list_properties`, read existing tags, look up the `"ingest"` tag ID:
```python
action_pid = prop_map["wiki_action"]
all_tags = client.list_tags(space_id, action_pid)
action_tag_id_map = {t["name"]: t["id"] for t in all_tags}
ingest_tag_id = action_tag_id_map.get("ingest")
```
When writing the WikiLog at the end of ingest, include `{"key": "wiki_action", "select": ingest_tag_id}`
if `ingest_tag_id` is not None.

### 3d. Failure behavior

The WikiLog must still be written even if tag resolution fails. The write path must be:

```python
# ingest.py — WikiLog creation
try:
    action_pid = prop_map.get("wiki_action")
    action_tag_id = None
    if action_pid:
        all_action_tags = client.list_tags(space_id, action_pid)
        action_tag_id = {t["name"]: t["id"] for t in all_action_tags}.get("ingest")
except Exception:
    action_tag_id = None  # degraded: WikiLog is written without wiki_action

log_props = [...]
if action_tag_id:
    log_props.append({"key": "wiki_action", "select": action_tag_id})
# else: wiki_action is omitted; WikiLog still written
```

This matches the existing error-tolerance pattern in `bootstrap.py:429-434` where the WikiLog
write itself is wrapped in a try/except that adds to `result["warnings"]` without aborting bootstrap.

The `wiki_action` tag resolution failure must NOT abort the ingest. At most it adds a warning to
`IngestResult.warnings` (e.g. `"wiki_action_tag_not_found: WikiLog written without action discriminator"`).

### 3e. Backward compatibility — v0.2.0 bootstrap spaces

Existing v0.2.0 spaces have no `wiki_action` tags. On first v0.3.0 `wiki_bootstrap`, the tag
creation step creates all five. For `wiki_ingest` run against a v0.2.0 space that has NOT been
re-bootstrapped with v0.3.0: `list_tags` returns an empty set, `action_tag_id = None`, WikiLog is
written without `wiki_action` (same state as v0.2.0). The degraded-but-written behavior is
acceptable and the operator is expected to run `wiki_bootstrap` before running `wiki_ingest`
(the schema-compat check enforces this).

`known-limitations.md #3` is resolved by this design.

---

**Recommendation:** Create all five `wiki_action` tag options (`ingest`, `query`, `lint`,
`bootstrap`, `archive`) during `wiki_bootstrap` using the same tag-creation loop already used
for `wiki_domain_tags`. Store the resulting tag-id map for use in the bootstrap WikiLog write.
In `wiki_ingest`, resolve the `ingest` tag id via `list_tags` at the start of the ingest
pipeline and include it in the WikiLog write. If resolution fails for any reason, write the
WikiLog without `wiki_action` and record a warning.

**Spec actions:**
- Spec must state: `wiki_bootstrap` creates all five `wiki_action` option tags during the
  bootstrap phase, using the same color-palette cycling and union-only re-bootstrap semantics
  as `wiki_domain_tags`.
- Spec must state: `wiki_ingest` resolves the `ingest` tag ID via `list_tags` before writing
  the WikiLog; failure to resolve does NOT abort ingest.
- Spec must state: the WikiLog is always written, even if `wiki_action` cannot be populated
  (degraded-but-written behavior).
- Spec must add an AC: "WikiLog written by `wiki_bootstrap` carries `wiki_action = bootstrap`".
- Spec must add an AC: "WikiLog written by `wiki_ingest` carries `wiki_action = ingest`".
- `docs/known-limitations.md #3` must be updated/closed.

---

## Key Findings

1. The `objects_checked: 22, objects_indexed: 0` bug is confirmed: `chunk_object` only reads
   `obj.get("markdown")` and wiki objects store knowledge in `properties[]`. The fix is purely
   in `chunker.py`.

2. The live-verified `properties[]` shape is `[{"key": str, "text": str}, ...]` (or other
   typed fields). Both `list_objects` summary objects and (likely) `get_object` single-object
   responses carry this array; `_get_last_modified` in `indexer.py` already relies on it.

3. The `PATCH body silently ignored` constraint definitively kills approach (a) for the
   property-gap fix. Approach (b) (extend chunker) is the only path that works for
   incremental re-ingest.

4. The schema marker question cannot be fully resolved without a live probe: the v0.2.0
   finding that the system `collection` type did not persist custom properties may still hold
   under the current API version.

5. `wiki_action` tag creation during bootstrap is the clean solution for both the v0.2.0 gap
   (SHOULD-FIX-2) and the v0.3.0 requirement (WikiLog discrimination). The existing bootstrap
   tag-creation infrastructure handles this with minimal new code.

## Open Questions / Live Verification Gates

- **V1:** Does `GET /objects/{id}?format=md` include `properties[]`? (MUST confirm before
  implementing chunker fix that reads from single-object response)
- **V2:** Does property PATCH via `update_object` bump `last_modified_date`? (MUST confirm for
  change-detection to work on re-ingest)
- **V3:** Does `chunk_object` on a live wiki Entity with `wiki_facts` populated yield at least
  one chunk? (End-to-end validation)
- **V4:** Does `update_object` PATCH of `wiki_schema_version` on the root `collection`-typed
  object persist and appear in `list_objects` `properties[]`? (Determines Option a vs b-1 for
  schema marker)

## Sources

- `src/anytype_llm_wiki/indexer.py` — reindex flow, `_get_last_modified`, chunk_object call
- `src/anytype_llm_wiki/chunker.py` — chunk_object implementation (body-only)
- `src/anytype_llm_wiki/anytype_client.py` — get_object, list_objects
- `src/anytype_llm_wiki/wiki/types_schema.py` — WIKI_TYPES, property definitions
- `src/anytype_llm_wiki/wiki/bootstrap.py` — _run_bootstrap, _found_schema_version, _max_version,
  _find_root_collection, _build_props_list, _create_tag
- `src/anytype_llm_wiki/wiki/wiki_client.py` — create_tag, update_object, list_tags
- `src/anytype_llm_wiki/wiki/util.py` — normalize_title, space_ingest_lock
- `.aldeia/140-wiki-library-module-port-llm-wiki-pattern-onto-any/patch-decision.md` — verified API decisions
- `.aldeia/234-v0-2-0-tag-prep-checklist-anytype-llm-wiki-post-im/impl-review-r2.md` — live verification findings
- `.aldeia/140-wiki-library-module-port-llm-wiki-pattern-onto-any/spec.md` — master spec
- `docs/known-limitations.md` — items #2, #3, #4, #5
- `.aldeia/284-anytype-llm-wiki-v0-3-0-wiki-ingest-compile-pipeli/spec-scope.md` — increment spec scope
- `tests/wiki/test_bootstrap.py` — TestFoundSchemaVersionRealShape (live API shape confirmation)
- `tests/test_anytype_client.py` — get_object mock shape
