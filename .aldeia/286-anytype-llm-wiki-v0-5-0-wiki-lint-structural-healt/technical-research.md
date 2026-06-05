# Technical Research: wiki_lint v0.5.0 (#286)

**Date:** 2026-06-05
**Branch:** aldeia/286-anytype-llm-wiki-v0-5-0-wiki-lint-structural-healt
**Codebase snapshot:** post-#303 (WIKI_SCHEMA_VERSION = "0.4.1")

---

## Deltas Verdict (D1–D5)

| Delta | Verdict | Summary |
|-------|---------|---------|
| D1 — native `backlinks` primary | CONFIRMED with caveat | `backlinks` is NOT parsed by any current client code. The session finding (live API returns it) is the sole source. The client's `get_object` returns `resp.json()["object"]` verbatim, so whatever the API returns in that dict (including a `backlinks` key) is available at call time. Lint must read it defensively (key may be absent). |
| D2 — `stub` tag absent | CONFIRMED | `_WIKI_STATUS_TAGS = ["needs-review", "reviewed", "archived"]` (bootstrap.py:57). No `stub` tag. Re-targeting to `needs-review` age-based is the correct path. |
| D3 — conflict-flagged High signal | CONFIRMED | `_flag_conflict_status` (remember.py:659–673) sets `wiki_status=needs-review` on conflict. `result["conflicts_flagged"]` is incremented (remember.py:481). Two distinct checks are needed: age-based (D2, Medium) and conflict-presence (D3, High). |
| D4 — v0.4.0 reuse map | CONFIRMED | `cache: dict[str, dict] = {}` (query.py:474), `_fetch_cached` (query.py:684), `_qdrant()` (indexer.py:16), `semantic_search_core` (indexer.py:20). All importable and directly reusable. |
| D5 — wire contracts | CONFIRMED | All verb+path+mock patterns verified below. `lint` tag already seeded in `_WIKI_ACTION_TAGS` (bootstrap.py:54). |

---

## A. The `wiki/` Surface

### Modules and relevant public functions

**`_base_client.py`** — Transport only. `_BaseAnytypeClient.__init__`, `_client()`, `_headers()`, `close()`. No API methods. Lint inherits via `WikiClient` or `AnytypeReadClient`.

**`anytype_client.py`** (in `src/anytype_llm_wiki/`) — Read-plane.
- `AnytypeReadClient.list_objects(space_id, offset=0, limit=100) -> list[dict]` — paginating GET with `has_more` loop. Same as `WikiClient.list_objects`.
- `AnytypeReadClient.get_object(space_id, object_id) -> dict` — `GET /v1/spaces/{space_id}/objects/{object_id}?format=md`, returns `resp.json()["object"]`.
- Module-level wrappers: `get_object(space_id, object_id)`, `list_objects(space_id, ...)`.

**`wiki_client.py`** — Write-plane + list helpers.
- `WikiClient.list_objects(space_id, offset=0, limit=100) -> list[dict]` — delegates to `_paginated_get`. (wiki_client.py:136–140)
- `WikiClient.list_properties(space_id) -> list[dict]` — `GET /v1/spaces/{space_id}/properties`. (wiki_client.py:124–125)
- `WikiClient.list_tags(space_id, property_id) -> list[dict]` — `GET /v1/spaces/{space_id}/properties/{property_id}/tags`. (wiki_client.py:127–134)
- `WikiClient.create_object(space_id, type_key, name, properties, body) -> dict` — `POST /v1/spaces/{space_id}/objects`, returns `resp.json()["object"]`. (wiki_client.py:53–76)
- `WikiClient.update_object(space_id, object_id, patch) -> dict` — `PATCH /v1/spaces/{space_id}/objects/{object_id}`. (wiki_client.py:78–83)
- `WikiClient.search(space_id, query, filter) -> list[dict]` — `POST /v1/spaces/{space_id}/search`, returns `resp.json()["data"]`. (wiki_client.py:91–115)
- `WikiClient._paginated_get(path, offset=0, limit=100) -> list[dict]` — shared pagination loop, reads `data[]` + `pagination.has_more`. (wiki_client.py:142–158)

**`bootstrap.py`** — Schema bootstrap. Functions lint reuses:
- `_schema_version_from_objects(objects: list[dict]) -> str | None` (bootstrap.py:486–509) — pure function, reads `wiki_schema_version` off an already-fetched object list. Used by `query.py` at line 421 for the QA#25 pre-check without a second `list_objects` call.
- `_read_schema_version(client, space_id) -> str | None` (bootstrap.py:512–519) — calls `list_objects` + delegates to above.
- `_object_deeplink(space_id, object_id) -> str` (bootstrap.py:83) — returns `anytype://object/{space_id}/{object_id}`.
- `_WIKI_ACTION_TAGS = ["ingest", "query", "lint", "bootstrap", "archive", "remember"]` (bootstrap.py:54) — `lint` is index 2, already seeded.
- `_WIKI_STATUS_TAGS = ["needs-review", "reviewed", "archived"]` (bootstrap.py:57).

**`ingest.py`** — Functions lint reuses:
- `_resolve_wiki_action_tag(client, space_id, action_name="ingest") -> tuple[str | None, bool]` (ingest.py:212–238) — two-step `list_properties` → `list_tags`, returns `(tag_id, degraded)`.
- `_write_wikilog(client, space_id, *, subject, created, updated, notes, action_tag_id, action_name="ingest") -> str | None` (ingest.py:241–268) — creates a `wiki_log` object via `create_object`.
- `_cmp_versions(a, b) -> int` (ingest.py:447–450) — version comparison helper.

**`query.py`** — v0.4.0 pipeline. Functions lint reuses for D4:
- `_fetch_cached(read_client, space_id, object_id, cache, enum_map=None) -> dict | None` (query.py:684–706) — per-run cache using `dict[str, dict]`, falls back to `enum_map` on KeyError, returns None on real HTTP error.
- `_looks_like_object(obj) -> bool` (query.py:709–710) — `isinstance(obj, dict) and bool(obj.get("id"))`.
- `_parse_relation_elements(elements) -> list[str]` (query.py:72–91) — normalizes relation `objects` arrays (bare str or `{"id": ...}` dict).

**`remember.py`** — `_flag_conflict_status(client, space_id, object_id, result)` (remember.py:659–673) — the conflict-flagging path that sets `wiki_status=needs-review`. Returns nothing; result gets a warning on failure.

**`config.py`** — `index_threshold()` (config.py:67), `_positive_int(env, default)` (config.py:45). The `WIKI_INDEX_THRESHOLD` default is 200 — this is the upper bound for the duplicate-sweep threshold (lint uses `config.index_threshold()` as the upper band limit per D5 scope brief).

**`doctor.py`** — `run_doctor() -> dict` (doctor.py:384–417). Not directly reused by lint but the pre-check pattern (checks fire before any write) mirrors lint's pre-check ordering.

**`util.py`** — `read_patch_decision() -> dict | None` (util.py:229–268) — reads `.aldeia/140-.../patch-decision.md` (path overridable via `ALDEIA_DIR` env). `scrub_credentials(url) -> str` (util.py:98).

**`types_schema.py`** — `WIKI_SCHEMA_VERSION = "0.4.1"` (types_schema.py:27). `WIKI_TYPES` (types_schema.py:69–154). No `wiki_status` in schema master spec master-spec lists `active|archived|stub` but the SEEDED TAGS are `needs-review|reviewed|archived` — the schema definition in the master spec (line 258) is diverged from bootstrap reality.

**`cli.py`** — `SUBCOMMANDS = ("wiki-bootstrap", "wiki-ingest", "wiki-remember", "wiki-query", "doctor")` (cli.py:21). Lint needs `"wiki-lint"` added.

---

## B. D1 — Native `backlinks`

**Finding: no existing client code reads `backlinks`.**

`AnytypeReadClient.get_object` returns `resp.json()["object"]` verbatim (anytype_client.py:44–52). It does not strip any keys. Whatever the Anytype API includes in the `object` envelope (including a `backlinks` key containing an array of referring objects) will be present in the returned dict.

The session finding (verified 2026-06-03) states `get-object` returns a top-level `backlinks` property — a list of objects auto-populated by inbound `wiki_relations`/`wiki_related`/`wiki_subjects`/`wiki_sources`. That key would appear alongside `"id"`, `"name"`, `"type"`, `"properties"` in the returned dict.

**Shape (from session finding):** `obj["backlinks"]` is a list of object stubs (same shape as relation `objects` entries: either bare id strings or `{"id": ..., ...}` dicts). The `_parse_relation_elements` helper in `query.py:72–91` handles both shapes.

**How lint reads inbound relations:**
- Primary path: `obj.get("backlinks", [])` on the object dict returned by `get_object`. Each element parsed via `_parse_relation_elements`. No additional API call required — the backlinks are in the already-fetched object. This is O(1) per object (after enumeration).
- Fallback path: when `backlinks` is absent or empty in the API response, lint falls back to the O(N) reciprocal traversal: for each object whose outbound `wiki_relations`/`wiki_related` points to target T, count T's inbound links.

**Verdict:** Lint CAN read inbound relations O(1) from a single `get_object` response. The field name is `backlinks`. The client does not strip it. The fallback must be explicit (the field may not be present on all API versions).

---

## C. D2/D3 — `wiki_status` Tags

**`_WIKI_STATUS_TAGS`** confirmed at bootstrap.py:57:
```python
_WIKI_STATUS_TAGS = ["needs-review", "reviewed", "archived"]
```

There is NO `"stub"` tag. The master spec line 258 (`wiki_status: active | archived | stub`) is diverged from the shipped seeded values. The "stale stub" check as written in the master spec CANNOT fire.

**D2 resolution (option B confirmed):** Re-target to `needs-review` age-based. The check detects objects whose `wiki_status` select value resolves to `"needs-review"` AND whose `wiki_ingested_at` date property is older than N days (default 30d, per master spec). Rename check to `stale_needs_review` (or keep `stale_stub` enum string — spec to decide, but the detection logic changes).

How a tag value is read from a fetched object: the `properties` array contains `{"key": "wiki_status", "select": <tag_id>}` entries. The `select` field holds the tag id, not the tag name. Lint must resolve tag name → id via the two-step (`list_properties` → `list_tags`) to compare by name, OR compare by id (storing a resolved `needs-review` tag id at the start of the lint run). The `_resolve_select_tag` helper in `remember.py:124–145` does exactly this two-step.

**D3 — conflict-flagged High check:** `_flag_conflict_status` (remember.py:659–673) sets `wiki_status=needs-review` on objects where `wiki_remember` detected intra-entity conflicts. The `result["conflicts_flagged"]` counter is incremented (remember.py:481). However, there is NO separate property that records `conflicts_were_flagged` beyond the `wiki_status=needs-review` tag. Lint cannot distinguish a "needs-review because of a conflict" from a "needs-review for any other reason" by reading the object alone.

**Recommendation (two checks):**
- `stale_needs_review` (Medium): `wiki_status == "needs-review"` AND `wiki_ingested_at < now − 30d`. Catches stale objects that were never reviewed.
- `unreviewed_conflict` (High): `wiki_status == "needs-review"` AND any of the WikiLog `wiki_notes` for that space contains `"conflicts_flagged"` for an object id matching this one. The practical approach: lint scans WikiLog objects (`wiki_action=remember`) whose `wiki_notes` contains `"conflicts_flagged"` for any subject name that resolves to the object. This is heuristic. A simpler approach: add `unreviewed_conflict` as a High check that fires on ALL `wiki_status == "needs-review"` objects (regardless of age), and use the Medium stale_needs_review only for old ones. Since every `needs-review` object was either set by a conflict flag or manually, this covers D3 without requiring WikiLog cross-reference.

**Final recommendation:** Two separate checks keyed on `wiki_status == "needs-review"`:
1. High: `wiki_status == "needs-review"` (any age) → check enum `unreviewed_needs_review`. This fires for the conflict-flagged signal from `wiki_remember`.
2. Medium: `wiki_status == "needs-review"` AND `wiki_ingested_at < now − 30d` → check enum `stale_needs_review`. Subset of above; a finding appears for both if both conditions hold.

**Property key for status:** `wiki_status` (select format). Written as `{"key": "wiki_status", "select": <tag_id>}`. The `wiki_status` property is defined on `wiki_entity` (types_schema.py:97) and `wiki_concept` (types_schema.py:113) but NOT on `wiki_comparison`, `wiki_query`, or `wiki_source`.

---

## D. D4 — v0.4.0 Reuse Map

All items confirmed at exact locations:

**Per-run object-fetch cache:** `cache: dict[str, dict] = {}` — a plain Python dict initialized at query.py:474, passed through `_fetch_cached`. Lint initializes the same pattern.

**`_fetch_cached` signature:** `_fetch_cached(read_client, space_id, object_id, cache, enum_map=None) -> dict | None` (query.py:684). Uses `AnytypeReadClient.get_object`. Single-path: try cache → try get_object → try enum_map fallback → return None on HTTP error.

**`_qdrant()` factory:** `indexer._qdrant() -> QdrantClient` (indexer.py:16–17) — `QdrantClient(url=config.QDRANT_URL, api_key=config.QDRANT_API_KEY or None)`. Module-level function.

**`semantic_search_core` signature:** `semantic_search_core(query: str, space_id: str | None = None, types: list[str] | None = None, limit: int = 10) -> list[dict]` (indexer.py:20–82). Returns `[{object_name, object_id, type, heading, text, score}]`. Filter: nested AND-of-OR (space_id in `must`, type list as a nested `should`-group in `must`). Embedder: `embed_query` from `anytype_llm_wiki.embedder` (Ollama bge-m3).

**Reuse for lint duplicate sweep:** Call `semantic_search_core(query=<object_text>, space_id=space_id, types=["wiki_entity","wiki_concept","wiki_comparison","wiki_query"], limit=10)` for each object (or a sample). Filter results to the 0.70–`config.index_threshold()` similarity band (the `score` field is already 0.0–1.0 cosine similarity). The `WIKI_INDEX_THRESHOLD` env var (default 200) is the same upper bound the scope brief references as `WIKI_INDEX_THRESHOLD` for the upsert-threshold parameter.

**Embedder:** `from anytype_llm_wiki.embedder import embed_query` — Ollama bge-m3 (default `EMBED_MODEL`). Confirmed in `indexer.py:14` import and `doctor.py` embed model check.

---

## E. D5 — Wire Contracts

### Tag resolution (property-scoped two-step)

`_resolve_wiki_action_tag` (ingest.py:212–238) and `_resolve_select_tag` (remember.py:124–145) both perform:
1. `GET /v1/spaces/{space_id}/properties` → find property with `key == "wiki_action"` (or other key), get its `id`.
2. `GET /v1/spaces/{space_id}/properties/{property_id}/tags` → scan for tag with matching `name`.

There is NO space-level `/tags` endpoint used anywhere. `WikiClient.list_tags(space_id, property_id)` (wiki_client.py:127–134) calls `_paginated_get(f"/v1/spaces/{space_id}/properties/{property_id}/tags")`.

### `search`

`POST /v1/spaces/{space_id}/search` with `{"query": ...}` body. (wiki_client.py:113). Returns `resp.json()["data"]` — a list of object dicts.

### `list_objects` batching

`GET /v1/spaces/{space_id}/objects?limit=100&offset=N`. Both `WikiClient._paginated_get` (wiki_client.py:142–158) and `AnytypeReadClient.list_objects` (anytype_client.py:23–42) implement the same pagination loop reading `pagination.has_more`. The `WikiClient.list_objects` is the canonical call for enumeration in `bootstrap.py` and `ingest.py`. `query.py` uses `write_client.list_objects(space_id)` (query.py:410) which resolves to the WikiClient variant.

### `get_object`

`GET /v1/spaces/{space_id}/objects/{object_id}?format=md` (anytype_client.py:46–52). Returns `resp.json()["object"]` — the full object dict. The `?format=md` param is sent on every call. **This is the `AnytypeReadClient` path.**

### WikiLog create (lint emits `wiki_action=lint` receipt)

`POST /v1/spaces/{space_id}/objects` with body `{"type_key": "wiki_log", "name": "lint {subject}", "properties": [...]}`. (wiki_client.py:64–76 via `create_object`).

The `lint` tag already exists in `_WIKI_ACTION_TAGS` (bootstrap.py:54, index 2). Resolution via `_resolve_wiki_action_tag(client, space_id, "lint")` (ingest.py:212).

WikiLog `wiki_action` enum values in `_WIKI_ACTION_TAGS`: `["ingest", "query", "lint", "bootstrap", "archive", "remember"]`. `lint` is at index 2. CONFIRMED present.

The master spec (lines 287, 614) lists `ingest|query|lint|bootstrap|archive` — `remember` was added in #289 (bootstrap.py:54 comment: "v0.3.1 adds 'remember'").

**Representative mock from `test_ingest.py` (line 314–315):**
```python
respx.get().mock(return_value=httpx.Response(200, json=_make_schema_ok_response()))
respx.post().mock(side_effect=partial_post)
```
Both are no-arg catch-alls (respx 0.23.x pattern). For WikiLog create specifically, `test_ingest.py` captures POSTs via a `side_effect` that inspects `request.content` JSON. Example from lines 471–473:
```python
respx.get().mock(return_value=httpx.Response(200, json=_make_schema_ok_response()))
respx.post().mock(side_effect=mock_post)
respx.patch().mock(side_effect=mock_patch)
```
Mock file to mirror: `tests/wiki/test_ingest.py` — all WikiLog create assertions capture `request.content` and filter for `type_key="wiki_log"` in the JSON body.

---

## F. Pipeline-Orphan Cross-Reference (#284)

The WikiLog object fields (types_schema.py:140–153):
- `wiki_action` (select): the action (e.g. `"ingest"`)
- `wiki_subject` (text): the source URL/title (up to 50 chars, from ingest.py:579)
- `wiki_objects_created` (number): count of objects created
- `wiki_objects_updated` (number): count of objects updated
- `wiki_timestamp` (date): operation timestamp
- `wiki_notes` (text): errors, skips, noteworthy events — on partial failure, contains `relation_rollback` notes
- `wiki_schema_version` (text): schema version at time of run

**There is NO run-id linkage.** Objects created by an ingest run are NOT linked back to the WikiLog entry by any property. There is no `wiki_ingest_run_id` or `wiki_created_by_log` field on wiki_entity or wiki_concept objects.

**Partial-failure detection:** `_run_ingest` sets `status="partial"` and appends `rollback_notes` to `result["warnings"]` when a bidirectional relation fails (ingest.py:568–570). Those notes are written to `wiki_notes` in the WikiLog (ingest.py:576: `notes = "; ".join(rollback_notes) if rollback_notes else "ingest"`). A WikiLog with `wiki_action=ingest` AND `wiki_notes` containing `"relation_rollback"` identifies a partial-failure ingest run.

**Timestamp heuristic:** Objects do not carry a `wiki_ingested_at` at the top level — that property is on `wiki_source` objects (types_schema.py:79), not on entities. There is no direct timestamp link from an entity to its ingest WikiLog.

**Practical pipeline-orphan approach for lint:**
1. Enumerate all WikiLog objects with `wiki_action=ingest` and `wiki_notes` containing a failure marker (client-side string match on `wiki_notes` text).
2. For each such partial-failure WikiLog, use `wiki_timestamp` to define a time window.
3. Objects with `wiki_relations == []` and no inbound backlinks that have `wiki_sources` created around the same timestamp as the failed WikiLog are candidate pipeline orphans.

This is heuristic. The spec brief acknowledges the WikiLog cross-ref is the mechanism — lint should scan WikiLog entries, match by timestamp approximation, and flag zero-relation objects created near a partial-failure run as `pipeline_orphan` (High, no grace).

---

## G. Pre-Checks

**QA#25 — `wiki_schema_outdated`:**
- Implementation: `bootstrap._schema_version_from_objects(all_objects)` (bootstrap.py:486–509) — pure, no I/O. Used in `query.py:421`.
- Pattern: lint enumerates objects first (to get `all_objects`), then calls `_schema_version_from_objects(all_objects)` + `_cmp_versions(live, code)`. If `< 0` → `[CONFIG ERROR] wiki_schema_outdated`. If `is None` → `[CONFIG ERROR] wiki_schema_missing`.
- Module: `anytype_llm_wiki.wiki.bootstrap._schema_version_from_objects` and `anytype_llm_wiki.wiki.ingest._cmp_versions`.
- Fires BEFORE any WikiLog write (same ordering as `query.py:421` before `_wikilog()`).

**QA#30 — `patch_decision_missing_or_invalid`:**
- Implementation: `util.read_patch_decision()` (util.py:229–268) — reads `.aldeia/140-.../patch-decision.md`. Returns `None` if absent/unparseable.
- Query validation check: `decision is None or not ("patch_body_updates" in decision and "implementation_path" in decision)` (query.py:395–398). The ingest check is the same (ingest.py:385–388).
- Fires BEFORE any Anytype call (pure filesystem read). No network calls made before this check.
- Module: `anytype_llm_wiki.wiki.util.read_patch_decision`.

Both checks are already called identically in `query.py` and `ingest.py`. Lint reuses the same helpers in the same order: QA#30 first (no network), then enumerate objects, then QA#25 on the enumerated list.

---

## H. Performance / O(N)

From `docs/known-limitations.md §9` (lines 159–176):

> Every `wiki_query` calls `list_objects` to enumerate the entire wiki on **both** tiers — Tier 1 navigation reads the full object set, and Tier 2 still enumerates to compute the count that selects the tier (`WIKI_INDEX_THRESHOLD=200`). Cost is therefore O(N) in the number of wiki objects, per query.

And:

> The fix is deferred to **v0.5.0**: cache the object count / index size (invalidated on write) so the tier decision and Tier 1 navigation avoid a full re-enumeration on every call.

**Lint's O(N) budget:** Lint calls `list_objects` once (O(N)). With D1's `backlinks` primary path, there is no second O(N) reciprocal traversal. The per-run cache (`_fetch_cached`) ensures each object is fetched at most once across all checks. The 500-object budget (≤60s) is achievable.

**`list_objects` pagination helper lint reuses:** `WikiClient.list_objects(space_id)` (wiki_client.py:136–140) — calls `_paginated_get` which loops on `has_more`. This is the single enumeration that seeds `all_objects` (and `enum_map`).

**Count-cache note:** §9 states this was deferred to v0.5.0. It remains unimplemented. Lint spec should reference §9 and state the count-cache is not a v0.5.0 deliverable unless the budget proof requires it.

---

## I. Test Harness

### Structure

Tests live in `tests/wiki/`. Each tool has its own test file:
- `test_ingest.py` — `wiki_ingest` (respx mocks, multiprocessing for lock test)
- `test_query.py` — `wiki_query` (respx mocks, monkeypatched `synthesize`)
- `test_remember.py` — `wiki_remember`
- `test_bootstrap.py` — `wiki_bootstrap`
- `conftest.py` — shared fixtures (`anytype_env`, `mock_anytype`, canned response builders)

### respx pattern (0.23.x)

No-arg `respx.get()` and `respx.post()` are **catch-alls** that match any URL. Used as the outer fallback. Specific URLs are registered AFTER the catch-all:

```python
respx.get().mock(return_value=httpx.Response(200, json=list_resp))          # catch-all
respx.get(f"{ANYTYPE_BASE}/v1/spaces/{FAKE_SPACE_ID}/objects/{obj_id}").mock(...)  # specific
respx.post().mock(return_value=httpx.Response(201, json=_make_create_object_response("log-001")))
respx.patch().mock(return_value=httpx.Response(200, json=_make_update_object_response("obj-0000")))
```

**Ordering gotcha (confirmed):** In respx 0.23.x, Router resolves FIRST MATCH. A no-arg `respx.get()` catch-all registered BEFORE a specific URL route will win every match. The codebase works around this by registering the no-arg catch-all BEFORE specific routes — so specific routes come after and are checked first (respx uses a list where specific routes are inserted at position 0 for regex/url patterns). See `test_query.py:602–607` for the explicit skip comment documenting this behavior.

**Practical implication for lint tests:** register specific URL mocks (e.g. `get_object` per-object route) as `respx.get(url=...).mock(...)` BEFORE or AFTER the catch-all in a consistent ordering. Look at `test_query.py:517–522` as the canonical working example.

**`respx.patterns.M` is not used anywhere** — confirmed by absence in codebase. No-arg `respx.post()` is the pattern for "match any POST".

### `@pytest.mark.live` skip-gate

Registered in `pyproject.toml:45`:
```
"live: marks tests as requiring live Anytype + Qdrant + Ollama services (skip with -m 'not live')"
```

Used in `test_ingest.py:1097`, `test_query.py:2774`, `test_remember.py:2980`. Pattern: `@pytest.mark.live` on a module-level test function (not a class method). The test body typically calls `pytest.skip(...)` if the required env vars (`ANYTYPE_SPACE_ID`, etc.) are absent.

### Mocked-test skeleton (representative from `test_ingest.py:113–115`)

```python
@respx.mock
def test_some_path(self, monkeypatch, tmp_path):
    monkeypatch.setenv("ALDEIA_DIR", str(tmp_path))  # for patch-decision
    respx.get().mock(return_value=httpx.Response(200, json=_make_schema_ok_response()))
    respx.post().mock(return_value=httpx.Response(201, json={"object": {"id": "x"}}))
    from anytype_llm_wiki.wiki.ingest import wiki_ingest
    result = wiki_ingest(source="https://example.com/paper", space_id=FAKE_SPACE_ID)
    ...
```

The `_make_schema_ok_response()` helper (test_ingest.py:54–73) stamps `WIKI_SCHEMA_VERSION` onto a `collection`-type object named `"Wiki"` — this is what both `query.py` and `ingest.py` use for the QA#25 pre-check.

---

## Additional Notes

**`wiki_status` on `wiki_entity` and `wiki_concept` only** — `wiki_comparison`, `wiki_query`, `wiki_source` do not have this property in `types_schema.WIKI_TYPES`. Lint's D2/D3 checks apply only to entity and concept objects.

**`wiki_ingested_at` is on `wiki_source` objects**, not on `wiki_entity`/`wiki_concept`. The stale check (Medium, `last_modified < linked source wiki_ingested_at − 90d`) must read the linked source's `wiki_ingested_at` via the `wiki_sources` relation on the entity/concept.

**`wiki_last_reviewed` is on `wiki_entity`** (types_schema.py:97) but NOT on `wiki_concept` (types_schema.py:106–113). The unresolved-contradiction check (passive, High) reads both `wiki_contradictions` (non-empty) AND null `wiki_last_reviewed` — for concepts, `wiki_last_reviewed` is absent from schema.

**The `wiki_log` type does NOT have `wiki_status`** — it has `wiki_action`, `wiki_subject`, `wiki_objects_created`, `wiki_objects_updated`, `wiki_timestamp`, `wiki_notes`, `wiki_schema_version` (types_schema.py:140–153). Note `wiki_objects_updated` IS a field (the master spec line 291 matches the schema). The scope brief notes `lint` emits `wiki_action=lint` — confirmed seeded (bootstrap.py:54).
