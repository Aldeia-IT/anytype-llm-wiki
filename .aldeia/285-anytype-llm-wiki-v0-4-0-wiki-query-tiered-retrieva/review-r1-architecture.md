# Architecture Review R1 — wiki_query v0.4.0 (#285)

**Verdict:** REQUEST CHANGES — sound overall design and well-grounded helper reuse, but two concrete code-level defects in the locked decisions (Qdrant `min_should` type, synthesis transport reuse contradiction) plus a module-placement/circular-import hazard must be fixed before implementation.

**Severity counts:** BLOCKING 3 · SHOULD-FIX 4 · SUGGESTION 4

Reviewer scope: software architecture (agent-ops / Python MCP server). Reviewed against the real codebase, not just research notes.

---

## BLOCKING

### B1 — Decision 2 `min_should=1` (int) is invalid for qdrant-client 1.18 → ValidationError at runtime
**Spec:** `spec.md:97-99` (pseudo-construction `min_should = 1 ... Filter(..., min_should=min_should)`).
**Code/fact:** qdrant-client `1.18.0` (`pyproject.toml:16`). `Filter.min_should` is typed `Optional[MinShould]`, NOT `int`. Verified empirically:
```
Filter(must=[...], should=[...], min_should=1)
-> ValidationError: min_should Input should be a valid dictionary or instance of MinShould
```
The spec's own pseudo-code, if implemented literally, raises at filter construction for every multi-type Tier 2 call — i.e. it reintroduces a hard failure in the exact path Decision 2 exists to fix.

**Fix (pick one, both correct OR-semantics):**
- Preferred — drop `min_should` entirely. A `should` list with no `min_should` already means "≥1 should matches" in Qdrant when combined with `must`. Use `Filter(must=must or None, should=should or None)`.
- Or, if an explicit min is wanted: `from qdrant_client.models import MinShould; min_should=MinShould(conditions=should, min_count=1)`.

The spec says "(exact Qdrant client API in implementation)" as a hedge — that hedge is not acceptable here because the concrete value it printed is wrong and would be copied. Replace the pseudo-code with one of the two correct forms above.

### B2 — Decision 3 is internally contradictory: cannot "reuse `_call_ollama_prompt`" AND "omit `format: json`"
**Spec:** task brief + `spec.md:115-128` ("reuses the Ollama transport pattern from `extraction.py`"; "Omits `format: json`"). The task framing explicitly states synthesis "reusing `extraction.py:_call_ollama_prompt` transport but omitting `format: json`".
**Code:** `extraction.py:_call_ollama_prompt` (`extraction.py:99-152`) **hardcodes** `"format": "json"` in BOTH the `/api/generate` (line 120) and `/api/chat` (line 139) bodies, and parses the result through `_parse_json_response` (line 129/148), which `json.loads()` the model output and returns `None` for non-JSON. There is no parameter to disable JSON mode. `_call_ollama_prompt` therefore **cannot** be reused for free-form prose: it will force the model to emit JSON and then the prose answer will be lost/mis-parsed.

The spec body (`spec.md:116`) is actually more careful — it says synthesis reuses "the Ollama transport *pattern*" and lists the wire fields, which implies a *new* function, not a call into `_call_ollama_prompt`. But the decision header and the task brief say "reuse `_call_ollama_prompt`". These must be reconciled.

**Fix:** State explicitly that `synthesize()` is a NEW transport function (parallel to, not calling, `_call_ollama_prompt`) that (a) omits `format: json`, (b) does NOT route through `_parse_json_response`, and (c) reads `response`/`message.content` as raw text. Reuse the shared pieces that ARE reusable: `_DETERMINISTIC_OPTS` (extraction.py:42), `_is_model_not_pulled` (extraction.py:92), `config.extract_model/extract_timeout/extract_think`, and the `WIKI_EXTRACT_ENDPOINT or _ollama_url()` base resolution (extraction.py:172). Recommend placing `synthesize()` in `extraction.py` next to `_call_ollama_prompt` so it can share those private helpers without a cross-module import of underscored names; `wiki/query.py` then calls `extraction.synthesize(...)`. (The spec currently puts `synthesize()` in `query.py`, which would force importing `extraction._is_model_not_pulled` / `_DETERMINISTIC_OPTS` across modules — see S2.)

### B3 — Module placement of `_semantic_search_core` in `server.py` inverts the layering and risks a circular import
**Spec:** `spec.md:103` ("`_semantic_search_core(...)` in `server.py` (or `indexer.py`)") and `spec.md:512` (reused helper located in `server.py`); `spec.md:488` (EDIT server.py to extract it); `spec.md:228` (query.py calls it).
**Code/fact:** The dependency direction in this codebase is strictly `server.py → wiki/*` and `server.py → indexer.py`. Nothing under `wiki/` imports from `server.py` (verified: only `cli.py` mentions server in a docstring; `ingest.py` imports `..indexer`, never `..server`). `server.py` registers the tool by importing `wiki.query` (the `wiki_ingest`/`wiki_remember` pattern, `server.py:127,168`). If `wiki/query.py` then imports `_semantic_search_core` from `server.py`, you get `server → wiki.query → server`. Even with deferred (function-body) imports it is a fragile upward dependency that contradicts the established architecture.

**Fix:** Extract `_semantic_search_core` into a module that `wiki/` already depends on — `indexer.py` is the natural home (it owns Qdrant/embedding concerns and is already imported by `wiki/ingest.py`). `server.py`'s `@mcp.tool() semantic_search` wrapper and `wiki/query.py` both import it from there. The spec must LOCK the location (not leave "server.py (or indexer.py)" as an either/or) and lock it to a non-`server` module. Update `spec.md:103,488,512` and the wire-contract row at `spec.md:340` accordingly.

---

## SHOULD-FIX

### S1 — Backward-compat of the `semantic_search` refactor: confirm the decorated symbol stays directly callable
**Spec:** `spec.md:102-108` asserts the `@mcp.tool()` wrapper "calls this helper" and that direct calls remain valid.
**Code/fact (verified):** `from anytype_llm_wiki.server import semantic_search` yields a plain `function` that is directly callable (the live test at `test_ingest.py:1151` relies on this). So extracting a core and having the tool delegate is backward-compatible *for the single existing caller*. Blast radius is genuinely small: grep shows `semantic_search` has NO internal callers besides its own definition; `reindex`/`reindex_anytype` do not touch it. Single-type and no-type paths: with the B1 fix (`should` w/o `min_should`, `must` for space_id), a single type produces one `should` condition = identical hit set to today's single-`must` condition; no-type/no-space produces `Filter(must=None, should=None)` which the code must collapse to `search_filter = None` exactly as today (`server.py:55`). **Action:** add an explicit AC/test that `types=None, space_id=None` yields `query_filter=None` (not an empty `Filter`), since an empty `Filter()` is not guaranteed equivalent to `None` and today's code passes `None`. The spec's `test_single_type_semantic_search_unchanged` (`spec.md:434`) covers single-type but not the no-filter degenerate case.

### S2 — Synthesis cross-module use of underscored helpers (follows from B2)
**Spec:** `spec.md:115` places `synthesize()` in `wiki/query.py`.
If B2 is resolved by a new function but it stays in `query.py`, it will need `extraction._DETERMINISTIC_OPTS`, `extraction._is_model_not_pulled`, and `extraction._ollama_url` — all private. Reaching across modules for underscored names is the kind of coupling that breaks silently on refactor. **Fix:** put `synthesize()` in `extraction.py` (co-located with the transport it mirrors) and call it from `query.py`. Keeps `query.py` as orchestration-only and the LLM transport layered cleanly in one module.

### S3 — `get_object` return shape: spec/research mismatch (harmless but document it)
**Spec:** `spec.md:246,253-254` reads `properties: [...]` off the `get_object` result and notes the wire path `GET /objects/{id}?format=md`.
**Code:** `AnytypeReadClient.get_object` (`anytype_client.py:44-52`) returns `resp.json()["object"]` — it **unwraps** the envelope. Research note `technical-research.md:56` says `get_object` returns `{"object": {...}}`, which describes the raw HTTP body, not the method's return. The spec's consumer code (reading `.properties` directly off the returned dict) is correct against the real method, but the test mocks must return `{"object": {...}}` at the HTTP layer (respx) while the in-process code sees the unwrapped dict. **Fix:** add one sentence pinning that `get_object()` returns the already-unwrapped object dict; ensure the `respx.get` mock at `spec.md:337` returns `{"object": {properties:[...]}}` and not a bare object.

### S4 — 1-hop relation read-back shape is unverified in the codebase (call out the assumption)
**Spec:** `spec.md:246` asserts read shape `properties: [{"key": "wiki_relations", "objects": ["id1","id2"]}]`.
**Code/fact:** The WRITE path uses exactly this shape (`ingest.py:291-292`, `_patch_relation`), but there is NO existing code that READS relation properties back from a fetched object (`technical-research.md:131,417` flags this). The format=md render may key linked objects differently (e.g. nested objects vs bare id strings). This is the one wire contract in the pipeline NOT verified against a real response. **Fix:** the spec should mark this read shape as an assumption and require the live smoke test (`spec.md:442-453`) to assert the actual relation read-back shape before the implementer hard-codes the parser; add a defensive branch (accept both `"objects": [ids]` and a list of `{"id": ...}` dicts).

---

## SUGGESTIONS

### G1 — Object-count source consistency: OK, note the double `list_objects`
Object count = Entity+Concept+Comparison+Query (`spec.md:201`) matches master spec `:453-471` exactly. But the count is derived from a full `list_objects` enumeration, and Tier 1 ALSO does a full `list_objects` (`spec.md:221`). On the <200 path that's two full scans unless the spec reuses the candidate enumeration for the count. Suggest: enumerate once, count from the same page set, then branch. Minor; matters only for the count+Tier1 combined path.

### G2 — `error_category` field consistency
`technical-research.md:324` notes `wiki_ingest`/`wiki_remember` do NOT add `result["error_category"]` (only `bootstrap` does). The QueryResult schema (`spec.md:176-197`) omits it too — consistent with the sibling tools. Good; just confirm the implementer follows the `[API ERROR]`/`[CONFIG ERROR]`/`[DATA ERROR]` prefix-in-string convention (`technical-research.md:319-323`) rather than inventing a field.

### G3 — File-back step 1 properties list: include `wiki_asked_at` value source
`spec.md:276` builds `create_object(... properties=[wiki_question, wiki_answer, wiki_asked_at])`. `wiki_asked_at` is a `date` property (`types_schema.py:137`); the spec should pin its value to the ISO-8601 `...Z` form Anytype accepts (`bootstrap.py:_now_iso`, line 87) rather than a bare `datetime`. Reuse `_now_iso()`.

### G4 — `_write_bidirectional_relations` reuse for file-back is a partial fit
`spec.md:278` reuses `_write_bidirectional_relations` (`ingest.py:296`) "IF the cited objects are entities or concepts." That helper keys the relation property via `_REL_KEY_BY_KIND` which only knows `entity`→`wiki_relations`, `concept`→`wiki_related` (`ingest.py:280`); it has no notion of the Query's own `wiki_drew_from`. So the Query→source link (`wiki_drew_from`) is correctly written via the separate `update_object` PATCH at `spec.md:277`, and `_write_bidirectional_relations` would only write the *reciprocal* entity/concept side back to the Query. That reciprocal write would land in `wiki_relations`/`wiki_related` on the entity (pointing at a Query id) — semantically a "Query is related to this entity" backlink. Confirm that is intended; if the desired backlink is one-directional provenance only, skip `_write_bidirectional_relations` and just write `wiki_drew_from`. The spec should state the intended graph shape explicitly.

---

## Verified-correct (no action)

- All "reused" helpers exist with the claimed signatures/locations: `_read_schema_version` (`bootstrap.py:486`), `_object_deeplink` (`bootstrap.py:83`), `_cmp_versions` (`ingest.py:447`), `_resolve_wiki_action_tag` (`ingest.py:212`), `_write_wikilog` (`ingest.py:241`, kwargs match `spec.md:285-293`), `_write_bidirectional_relations` (`ingest.py:296`), `read_patch_decision` (`util.py:229`), `WikiClient.list_objects/create_object/update_object` (`wiki_client.py:136/53/78`), `AnytypeReadClient.get_object` (`anytype_client.py:44`).
- `wiki_answer`, `wiki_question`, `wiki_asked_at`, `wiki_drew_from` all exist on `wiki_query` type (`types_schema.py:128-138`); `WIKI_SCHEMA_VERSION="0.3.1"` (`types_schema.py:27`) — no schema bump needed, spec correct (`spec.md:146-147`).
- Wire contracts (verb+path) all correct vs real client: list_objects GET (`wiki_client.py:138`), get_object GET ?format=md (`anytype_client.py:47`), create_object POST (`wiki_client.py:74`), update_object PATCH (`wiki_client.py:81`).
- Patch-decision gate (`spec.md:309-314`) and schema-version error strings (`spec.md:304-307`) are byte-identical to the existing `ingest.py` gate (`ingest.py:386-418`). Stricter-gate choice is correct.
- Threshold logic `count >= WIKI_INDEX_THRESHOLD` (inclusive at 200) and boundary matrix match master spec `:511`. Qdrant-down fallback (below→Tier1, at/above→error) matches master spec `:461-462`.
- Config resolver pattern (`spec.md:353-375`) matches the call-time `os.environ.get` style in `config.py`; new vars genuinely absent today.
- `semantic_search` blast radius minimal: no internal callers; `reindex` independent.
- 1-hop cache design (dict keyed by object_id, per-run, not persisted) is correct and bounds traversal to exactly one hop — no accidental multi-hop, since neighbors are fetched but their relations are not re-expanded.
