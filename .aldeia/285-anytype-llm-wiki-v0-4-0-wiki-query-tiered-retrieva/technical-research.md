# Research: wiki_query v0.4.0 — Post-#284 Codebase Grounding

**Date:** 2026-06-04
**Researcher:** technical-research worker (claude-sonnet-4-6)
**Questions investigated:** 11 questions per spec-scope.md briefing

---

## Research Questions

1. wiki/ surface inventory — public classes/functions, HTTP verb+path contracts
2. semantic_search wire contract — signature, return shape, call path
3. type_key + relation property keys — canonical values and shape on read
4. #284 indexer property-embedding fix — what is embedded, how type_key flows to Qdrant
5. Schema-compat + patch-decision pre-check reuse — existing helpers
6. File-back / object-create precedent — create + relation-write code
7. WikiLog pattern — fields, wiki_action value, result return
8. Config/env-var pattern — declaration style, which vars already exist
9. CLI + server registration pattern — decorators, return shape, error categories
10. Test patterns to mirror — respx mock style, live-test gate
11. Synthesis/LLM call — existing helper, env vars, client type

---

## Findings

### Q1: wiki/ Surface Inventory

**WikiClient** (`src/anytype_llm_wiki/wiki/wiki_client.py`):
- Inherits `_BaseAnytypeClient` (transport only)
- Base URL resolved at call time from `ANYTYPE_API_URL` (default `http://127.0.0.1:31012`) — `_base_client.py:28`
- Headers: `Authorization: Bearer <ANYTYPE_API_KEY>`, `Anytype-Version: <ANYTYPE_API_VERSION>` (default `2025-11-08`), `Content-Type: application/json` — `_base_client.py:55-59`
- HTTP client is `httpx.Client`, timeout 30s — `_base_client.py:68-74`

**Verb+path contracts (all on `WikiClient`):**

| Method | Verb | Path |
|--------|------|------|
| `list_objects(space_id, offset, limit)` | GET | `/v1/spaces/{space_id}/objects?offset=N&limit=N` |
| `list_types(space_id)` | GET | `/v1/spaces/{space_id}/types` |
| `list_properties(space_id)` | GET | `/v1/spaces/{space_id}/properties` |
| `list_tags(space_id, property_id)` | GET | `/v1/spaces/{space_id}/properties/{property_id}/tags` |
| `search(space_id, query, filter)` | POST | `/v1/spaces/{space_id}/search` |
| `create_object(space_id, type_key, name, properties, body)` | POST | `/v1/spaces/{space_id}/objects` |
| `update_object(space_id, object_id, patch)` | PATCH | `/v1/spaces/{space_id}/objects/{object_id}` |
| `delete_object(space_id, object_id)` | DELETE | `/v1/spaces/{space_id}/objects/{object_id}` |

**AnytypeReadClient** (`src/anytype_llm_wiki/anytype_client.py`):

| Method | Verb | Path |
|--------|------|------|
| `list_spaces()` | GET | `/v1/spaces?limit=100` |
| `list_objects(space_id, offset, limit)` | GET | `/v1/spaces/{space_id}/objects?offset=N&limit=N` |
| `get_object(space_id, object_id)` | GET | `/v1/spaces/{space_id}/objects/{object_id}?format=md` |

Response envelope: `list_objects` returns `{"data": [...], "pagination": {"has_more": bool}}`; `get_object` returns `{"object": {...}}`; `create_object`/`update_object` return `{"object": {...}}`. Pagination: `_paginated_get` accumulates `data[]` while `pagination.has_more == True`, tolerates missing `pagination` key — `wiki_client.py:142-158`.

**Other public functions relevant to wiki_query:**

| Module | Symbol | Signature |
|--------|--------|-----------|
| `wiki/bootstrap.py` | `_read_schema_version(client, space_id)` | `(WikiClient, str) -> str | None` |
| `wiki/bootstrap.py` | `_version_tuple(version)` | `(str) -> tuple[int, ...]` |
| `wiki/bootstrap.py` | `_object_deeplink(space_id, object_id)` | `(str, str) -> str` |
| `wiki/ingest.py` | `_cmp_versions(a, b)` | `(str, str) -> int` |
| `wiki/ingest.py` | `_resolve_wiki_action_tag(client, space_id, action_name)` | `(WikiClient, str, str) -> tuple[str|None, bool]` |
| `wiki/ingest.py` | `_write_wikilog(client, space_id, *, subject, created, updated, notes, action_tag_id, action_name)` | `-> str|None` |
| `wiki/ingest.py` | `_write_bidirectional_relations(client, space_id, relations, kind_by_id)` | `-> tuple[int, list[str]]` |
| `wiki/ingest.py` | `_maybe_reindex(space_id, result)` | `(str, dict) -> None` |
| `wiki/util.py` | `read_patch_decision()` | `() -> dict | None` |
| `wiki/util.py` | `normalize_title(raw)` | `(str) -> str` |
| `wiki/extraction.py` | `sanitize_name(name)` | `(str) -> str | None` |
| `wiki/extraction.py` | `sanitize_property_value(text)` | `(str) -> str` |

---

### Q2: semantic_search Wire Contract

**Signature** (`src/anytype_llm_wiki/server.py:24-29`):
```python
@mcp.tool()
def semantic_search(
    query: str,
    space_id: str | None = None,
    types: list[str] | None = None,
    limit: int = 10,
) -> list[dict]:
```

The `types` parameter accepts a list of type key strings (e.g. `["wiki_entity", "wiki_concept"]`). Each type generates a separate `FieldCondition` on `key="type_key"` in Qdrant — `server.py:52-53`. Multiple types are combined with `Filter(must=conditions)` which means a hit must match ALL supplied type conditions simultaneously. **This is a bug for wiki_query's use case**: passing multiple types in `types=["wiki_entity","wiki_concept"]` would require a chunk to match ALL type values at once — an impossible condition. The query pipeline must call `semantic_search` once per type, or call it with a single type at a time, or pass `types=None` and filter client-side on the `type` field of the returned dicts.

**Return payload shape** (`server.py:65-74`):
```python
{
    "object_name": r.payload.get("object_name", ""),
    "object_id": r.payload.get("object_id", ""),
    "type": r.payload.get("type_key", ""),     # NOTE: field name is "type", not "type_key"
    "heading": r.payload.get("heading", ""),
    "text": r.payload.get("text", "")[:500],
    "score": round(r.score, 4),
}
```

**Call path**: `embed_query(query)` → `QdrantClient.query_points()` on `config.QDRANT_COLLECTION`. Uses `config.QDRANT_URL` and `config.QDRANT_API_KEY`.

**Plain Python call vs MCP tool**: `semantic_search` is a plain Python function decorated with `@mcp.tool()`. It can be called directly as `from anytype_llm_wiki.server import semantic_search; results = semantic_search(query=..., types=[...])`. This is exactly what `test_ingest.py:1151` does in the live test. No async required.

**RISK — multi-type filter semantics**: passing `types=["wiki_entity","wiki_concept","wiki_comparison","wiki_query"]` to the current implementation builds `Filter(must=[eq(type_key,wiki_entity), eq(type_key,wiki_concept), ...])` which requires a point to match ALL four type conditions simultaneously (impossible). The spec intends OR semantics. The query pipeline must work around this by either calling `semantic_search` with `types=None` and post-filtering, or patching the server to use `Filter(should=...)` for multi-type. This is a **spec decision gap** — the implementation does not support multi-type OR filtering.

---

### Q3: type_key + Relation Property Keys

**Canonical type_key values** (`src/anytype_llm_wiki/wiki/types_schema.py:69-154`):

| Type | type_key |
|------|---------|
| Source | `wiki_source` |
| Entity | `wiki_entity` |
| Concept | `wiki_concept` |
| Comparison | `wiki_comparison` |
| Query | `wiki_query` |
| WikiLog | `wiki_log` |

**Relation property keys:**
- `wiki_entity` uses `wiki_relations` (format: `objects`) — `types_schema.py:92`
- `wiki_concept` uses `wiki_related` (format: `objects`) — `types_schema.py:108`
- `wiki_query` uses `wiki_drew_from` (format: `objects`) — `types_schema.py:135`
- `ingest.py:280` codifies: `_REL_KEY_BY_KIND = {"entity": "wiki_relations", "concept": "wiki_related"}`

**Shape of a relation property value on read**: Properties are written as `{"key": rel_key, "objects": list(ids)}` where `ids` is a list of object ID strings — `ingest.py:291-292`. On read from `get_object`, the response shape follows the standard Anytype format: `properties: [{"key": "wiki_relations", "objects": ["id1", "id2", ...]}]`. There is no existing code in the repo that reads back relation properties from a fetched object, so the exact read-back shape has not been verified against a live response in this codebase. The write path uses `"objects": list(ids)` (list of strings), consistent with Anytype's PropertyLinkWithValue format.

**Note**: `wiki_comparison` has no dedicated relation property; it has `wiki_subjects` (objects) — `types_schema.py:121`. `wiki_query` has `wiki_drew_from` (objects) — `types_schema.py:135`.

---

### Q4: #284 Indexer Property-Embedding Fix

**Chunker** (`src/anytype_llm_wiki/chunker.py:12-22`):
```python
WIKI_TEXT_PROPERTY_KEYS = frozenset({
    "wiki_facts", "wiki_description", "wiki_definition", "wiki_open_questions",
    "wiki_dimensions", "wiki_verdict", "wiki_question", "wiki_answer",
})
```
When an object has **no markdown body** (`markdown.strip()` is falsy), `chunk_object` falls through to `_chunk_properties`, which iterates `obj["properties"]`, matches keys against `WIKI_TEXT_PROPERTY_KEYS`, and emits chunks — `chunker.py:70-94`. Each chunk carries the full metadata: `object_id`, `space_id`, `object_name`, `type_key`, `heading` (synthetic, from `WIKI_PROPERTY_HEADING`), `text`.

**type_key in Qdrant payload**: Carried from `chunk["type_key"]` which is populated from `obj.get("type", {}).get("key", "unknown")` — `chunker.py:37`. The indexer stores it in the Qdrant payload as `"type_key": chunk["type_key"]` — `indexer.py:100`. So `semantic_search` can filter by it.

**Covered properties for wiki_query Tier 2**:
- `wiki_entity` objects: `wiki_facts`, `wiki_description` are embedded
- `wiki_concept` objects: `wiki_definition`, `wiki_open_questions` are embedded
- `wiki_comparison` objects: `wiki_dimensions`, `wiki_verdict` are embedded
- `wiki_query` objects: `wiki_question`, `wiki_answer` are embedded (the compounding mechanism)

**Prerequisite confirmed**: Because ingest creates objects with empty body (AC-P7/AC-L1), the property-embedding path is the ONLY path that makes wiki knowledge retrievable via Tier 2.

---

### Q5: Schema-Compat + Patch-Decision Pre-Check Reuse

**`_read_schema_version(client, space_id)`** — `bootstrap.py:486-509`:
- Calls `client.list_objects(space_id)` (GET `/v1/spaces/{space_id}/objects`)
- Scans for root "Wiki" Collection (name=="Wiki" AND type.key=="collection") and all wiki_log objects
- Returns `max(collection_version, wikilog_max_version)` or `None` if neither carries a marker
- Raises `httpx.HTTPError` on network failure (callers must catch)

**`_version_tuple(version)`** — `bootstrap.py:92-108`: parses dotted version string to `tuple[int, ...]`.

**`_cmp_versions(a, b)`** — `ingest.py:447-450`: returns `(ta > tb) - (ta < tb)`, i.e. -1/0/+1.

**Schema-compat error strings** (from `ingest.py:410-418` and `remember.py:290-299`):
- Missing: `"[CONFIG ERROR] wiki_schema_missing: run wiki_bootstrap on this space first"`
- Outdated: `f"[CONFIG ERROR] wiki_schema_outdated: space schema {live_version} < code {code_version}; run wiki_bootstrap to upgrade"`
- Newer: warning string: `f"wiki_schema_newer: space schema {live_version} > code {code_version}; continuing"`

**`read_patch_decision()`** — `util.py:229-268`:
- Reads from `ALDEIA_DIR/patch-decision.md` if `ALDEIA_DIR` env var is set, else `./aldeia/140-wiki-library-module-port-llm-wiki-pattern-onto-any/patch-decision.md`
- Returns parsed dict or `None` if file missing or unparseable

**Patch-decision error string** (from `ingest.py:386-392`):
```
"[CONFIG ERROR] patch_decision_missing_or_invalid: a valid patch-decision.md with patch_body_updates and implementation_path is required"
```
`remember.py:270-274` uses a slightly shorter version:
```
"[CONFIG ERROR] patch_decision_missing_or_invalid: a valid patch-decision.md is required"
```
The `ingest.py` version validates that `patch_body_updates` AND `implementation_path` keys are present; `remember.py` only checks that the result is not `None`. The spec-writer should align on which gate wiki_query uses.

---

### Q6: File-Back / Object-Create Precedent

**Create pattern** (`ingest.py:548-556`):
```python
created = client.create_object(
    space_id, type_key=type_key, name=clean_name, properties=props
)
obj_id = created.get("id")
```
`create_object` posts `{"type_key": ..., "name": ..., "properties": [...]}` to `POST /v1/spaces/{space_id}/objects` — `wiki_client.py:68-76`. Properties are a list of `{"key": property_key, <typed_field>: value}` dicts.

**Relation writes** (`ingest.py:287-293`):
```python
client.update_object(
    space_id, obj_id, {"properties": [{"key": rel_key, "objects": list(ids)}]}
)
```
`update_object` sends `PATCH /v1/spaces/{space_id}/objects/{object_id}` with `{"properties": [...]}` — `wiki_client.py:78-83`.

**wiki_drew_from** write for a filed wiki_query object: the same `_patch_relation` / `update_object` pattern applies. Write `{"key": "wiki_drew_from", "objects": [source_obj_id_1, source_obj_id_2, ...]}` via `PATCH`.

**wiki_answer** goes in properties, NOT body — `patch-decision.md` (verified): `patch_body_updates: silently_ignored`. So the filed Query object must store the answer in `{"key": "wiki_answer", "text": <answer>}` so the next `reindex_anytype` embeds it (this is the compounding mechanism).

**Select tag pre-creation** (`ingest.py:212-237`): The `_resolve_wiki_action_tag(client, space_id, action_name)` function:
1. Lists all properties in the space
2. Finds the property with `key == "wiki_action"` and reads its id
3. Lists tags on that property id
4. Returns `(tag_id, degraded)` for the matching `action_name`

For `wiki_query`, `action_name="query"` — already seeded by bootstrap (`bootstrap.py:54`: `_WIKI_ACTION_TAGS = ["ingest", "query", "lint", "bootstrap", "archive", "remember"]`).

**Deeplink format** (`bootstrap.py:83-84`): `f"anytype://object/{space_id}/{object_id}"`.

---

### Q7: WikiLog Pattern

**`_write_wikilog(...)` signature** (`ingest.py:241-268`):
```python
def _write_wikilog(
    client: WikiClient,
    space_id: str,
    *,
    subject: str,
    created: int,
    updated: int,
    notes: str,
    action_tag_id: str | None,
    action_name: str = "ingest",
) -> str | None:
```

**Properties written**:
```python
props = [
    {"key": "wiki_subject", "text": subject},
    {"key": "wiki_objects_created", "number": created},
    {"key": "wiki_objects_updated", "number": updated},
    {"key": "wiki_timestamp", "date": datetime.now(timezone.utc).isoformat()},
    {"key": "wiki_notes", "text": notes},
    {"key": "wiki_schema_version", "text": types_schema.WIKI_SCHEMA_VERSION},
]
if action_tag_id:
    props.append({"key": "wiki_action", "select": action_tag_id})
```

**Create call**: `client.create_object(space_id, type_key="wiki_log", name=f"{action_name} {subject}", properties=props)` — returns `obj.get("id")` or `None` on failure.

**For wiki_query**: call with `action_name="query"`, `subject=<question text[:50]>`, `notes=<synthesis summary or "query">`. The wiki_action tag must be resolved via `_resolve_wiki_action_tag(client, space_id, action_name="query")`.

**Result field**: `result["wiki_log_id"]` is set to the returned id. `wiki_log_deeplink` is computed via `_object_deeplink(space_id, wiki_log_id)` — both should be in the QueryResult.

---

### Q8: Config/Env-Var Pattern

**Pattern** (`wiki/config.py`): Each env var has a `DEFAULT_*` module-level constant and a resolver function that reads `os.environ` at call time (not import time). Non-numeric or invalid values fall back to the default. Boolean vars accept `1/true/yes/on` case-insensitively.

**Existing wiki config vars** (all in `wiki/config.py`):
- `WIKI_LOCK_DIR` (via `lock_dir()`)
- `WIKI_EXTRACT_MODEL` (via `extract_model()`, default `"qwen2.5:7b"`)
- `WIKI_EXTRACT_TIMEOUT` (via `extract_timeout()`, default `600.0`)
- `WIKI_EXTRACT_THINK` (via `extract_think()`, default `False`)
- `WIKI_LOG_LEVEL` (via `log_level()`)
- `WIKI_FETCH_EXTRA_PORTS` (via `fetch_extra_ports()`)

**Root config** (`config.py`):
- `QDRANT_URL`, `QDRANT_API_KEY`, `QDRANT_COLLECTION`, `OLLAMA_URL`, `EMBED_MODEL`, `EMBED_DIMS`
- Loaded at module import time via `os.environ.get()` (module-level, not call-time)

**In `ingest.py` (not config.py)**:
- `WIKI_AUTO_REINDEX` — read inline: `os.environ.get("WIKI_AUTO_REINDEX", "true").lower() == "false"` — `ingest.py:664`

**NEW vars for v0.4.0 — NOT yet in codebase**:
- `WIKI_INDEX_THRESHOLD` (default `200`) — not declared in `wiki/config.py`
- `WIKI_FILE_BACK_MIN_SOURCES` (default `3`) — not declared
- `WIKI_FILE_BACK_MIN_WORDS` (default `100`) — not declared
- **None of the three new v0.4.0 vars appear in `.env.example`**

**Spec must add**: resolver functions in `wiki/config.py` following the call-time pattern, plus entries in `.env.example`.

---

### Q9: CLI + Server Registration Pattern

**CLI subcommands** (`wiki/cli.py:21`):
```python
SUBCOMMANDS = ("wiki-bootstrap", "wiki-ingest", "wiki-remember", "doctor")
```
`wiki-query` is NOT in `SUBCOMMANDS` yet. Pattern for adding: add `"wiki-query"` to `SUBCOMMANDS`, add a `_cmd_query(args)` function, define a subparser, set `func=_cmd_query`.

**CLI routing** (`server.py:183-186`):
```python
if len(sys.argv) > 1 and sys.argv[1] in wiki_cli.SUBCOMMANDS:
    sys.exit(wiki_cli.main(sys.argv[1:]))
```

**Server MCP tool registration** (template from `wiki_ingest`, `server.py:109-129`):
```python
@mcp.tool()
def wiki_ingest(source: str, space_id: str, domain_hint: str | None = None) -> dict:
    ...
    from .wiki.ingest import wiki_ingest as _wiki_ingest
    return _wiki_ingest(source=source, space_id=space_id, domain_hint=domain_hint)
```

**Error-category convention**: three categories used across the codebase:
- `[API ERROR]` — Anytype or Qdrant unreachable, transport/HTTP error
- `[CONFIG ERROR]` — missing/outdated schema, invalid domain_hint, missing patch-decision, model not pulled
- `[DATA ERROR]` — SSRF blocked, file not found, ingest in progress

These strings appear in `result["error"]` and `result["warnings"]`; `result["status"] = "error"` accompanies them. There is no `result["error_category"]` field in wiki_ingest/wiki_remember (only bootstrap adds `error_category`). The spec-writer should confirm whether `wiki_query` adds it.

---

### Q10: Test Patterns to Mirror

**respx mock style** (from `test_ingest.py` and `test_wiki_client.py`):

For match-any (no URL-specific matcher) — use no-arg `respx.get()` / `respx.post()` / `respx.patch()`:
```python
respx.get().mock(return_value=httpx.Response(200, json=_make_schema_ok_response()))
respx.post().mock(return_value=httpx.Response(201, json={"object": {"id": "x"}}))
respx.patch().mock(side_effect=capture_patch)
```

For URL-specific matcher (when you want to assert the exact path):
```python
route = respx.post(f"{ANYTYPE_BASE}/v1/spaces/{FAKE_SPACE_ID}/types").mock(...)
assert route.called
```

**HTTP call mocks for wiki_query** (paths to mock):
- **list_objects** (schema-compat check + Tier 1 candidate enumeration): `respx.get().mock(...)` — GET `/v1/spaces/{space_id}/objects`
- **get_object** (fetch full object + relation props): `respx.get(f"{ANYTYPE_BASE}/v1/spaces/{space_id}/objects/{object_id}").mock(...)` or `respx.get().mock(side_effect=...)`
- **search** (entity resolution): `respx.post().mock(side_effect=capture_search)` — POST `/v1/spaces/{space_id}/search`
- **create_object** (file-back Query object + WikiLog): `respx.post().mock(side_effect=capture_post)` — POST `/v1/spaces/{space_id}/objects`
- **update_object** (wiki_drew_from relation write): `respx.patch().mock(...)` — PATCH `/v1/spaces/{space_id}/objects/{object_id}`
- **Qdrant** (Tier 2): monkeypatch `semantic_search` at the function boundary (no HTTP mock needed for Qdrant)

**respx 0.23.x gotcha** (confirmed via spec-scope.md + test patterns): use no-arg `respx.post()` / `respx.get()` for match-any. The `respx.patterns.M` combinator raises at registration. All existing tests use no-arg forms for catch-all mocks.

**live-test gate** (`test_ingest.py:1097-1117`):
```python
@pytest.mark.live
class TestIngestCreateEndToEnd:
    def test_create_side_named_entity_retrieval(self):
        space_id = os.environ.get("ANYTYPE_SPACE_ID")
        if not space_id:
            pytest.skip("ANYTYPE_SPACE_ID not set — live create-side retrieval test skipped")
```
Marker declared in `pyproject.toml`:
```toml
markers = [
    "live: marks tests as requiring live Anytype + Qdrant + Ollama services (skip with -m 'not live')",
]
```

**schema_ok mock helper** (`test_ingest.py:54-73`):
```python
def _make_schema_ok_response():
    from anytype_llm_wiki.wiki.types_schema import WIKI_SCHEMA_VERSION
    return {
        "data": [{"id": "coll-wiki-001", "name": "Wiki",
                  "type": {"key": "collection"},
                  "properties": [{"key": "wiki_schema_version", "text": WIKI_SCHEMA_VERSION}]}],
        "pagination": {"has_more": False},
    }
```
`wiki_query` tests should use the same helper pattern.

---

### Q11: Synthesis/LLM Call

**Existing LLM callers**: `extraction.py:extract()` and `extraction.py:consolidate()`. Both use the same wire path.

**LLM call mechanism** (`extraction.py:99-152`, `_call_ollama_prompt`):
- Endpoint: `WIKI_EXTRACT_ENDPOINT` env var OR `OLLAMA_URL` (from root `config.py`, default `http://127.0.0.1:11434`)
- Model: `config.extract_model()` → `WIKI_EXTRACT_MODEL` (default `"qwen2.5:7b"`)
- Think mode: `config.extract_think()` → `WIKI_EXTRACT_THINK` (default `False`, send `think=False`)
- Timeout: `config.extract_timeout()` → `WIKI_EXTRACT_TIMEOUT` (default `600.0s`)
- Deterministic options: `{"temperature": 0, "seed": 0, "top_p": 1}` — `extraction.py:42`
- Wire: `POST {base}/api/generate` then fallback to `POST {base}/api/chat` (both Ollama endpoints)
- Parses `response` (generate) or `message.content` (chat) from the JSON response

**Synthesis prompt**: No synthesis prompt exists yet. `wiki/prompts/` contains `extraction.md` and `consolidate.md` only. The spec must define a new `wiki/prompts/synthesis.md`.

**Reusable helper**: `_call_ollama_prompt(base, prompt)` — `extraction.py:99-152` — accepts a pre-built prompt string and returns `(parsed_or_None, last_resp)`. This is the right reuse point for the synthesis step (load a prompt file, substitute context, call `_call_ollama_prompt`). It handles generate→chat fallback and model-not-pulled detection.

**Return type for synthesis**: The wiki_query synthesis must produce a string (the answer), not a structured JSON dict. The existing `_parse_json_response` helper parses JSON; synthesis would need a plain-text extraction from the response. The spec must address whether synthesis uses the generate (`format: "json"`) path (which forces JSON) or a non-JSON request. The current `_call_ollama_prompt` always sends `"format": "json"` — **this is a gap**: synthesis should NOT use JSON format mode if the output is free-form prose.

---

## Risks / Gaps for the Spec

1. **multi-type OR filter in semantic_search is BROKEN**: `server.py:50-55` builds `Filter(must=[...])` with all type conditions, which requires a chunk to match ALL types simultaneously. Passing `types=["wiki_entity","wiki_concept","wiki_comparison","wiki_query"]` returns zero results. The spec must either (a) specify calling `semantic_search` with `types=None` and post-filtering on the returned `type` field, or (b) spec a fix to `semantic_search` to use `should` semantics for the `types` list before wiki_query is implemented. This is a blocking gap.

2. **No synthesis helper exists**: `extraction.py` has `_call_ollama_prompt` which is reusable, but it always sends `"format": "json"`. Synthesis needs free-form prose output. The spec must specify either (a) a new `synthesize()` function in `extraction.py` that omits `format: "json"`, or (b) a separate synthesis prompt + caller in `wiki/query.py`. No existing prompt file for synthesis exists in `wiki/prompts/`.

3. **Patch-decision validation gate inconsistency**: `ingest.py` checks that BOTH `patch_body_updates` AND `implementation_path` keys are present; `remember.py` only checks non-None. The spec should standardize on one gate for `wiki_query`. Given file-back writes a Query object, the stricter `ingest.py` gate is appropriate.

4. **`WIKI_INDEX_THRESHOLD`, `WIKI_FILE_BACK_MIN_SOURCES`, `WIKI_FILE_BACK_MIN_WORDS` do not exist yet** in `wiki/config.py` or `.env.example`. The spec must add them.

5. **Relation property read-back shape not verified in codebase**: No existing code reads back `wiki_relations`/`wiki_related`/`wiki_drew_from` from a fetched object. The 1-hop traversal implementation will need to parse `{"key": "wiki_relations", "objects": ["id1", "id2"]}` from `get_object`'s response properties list — consistent with the write-path format but not battle-tested in this codebase.

6. **`wiki-query` not in `SUBCOMMANDS`**: Must be added to `wiki/cli.py:21` for CLI routing in `server.py:185`.

7. **`wiki_schema_version` is NOT bumped for v0.4.0**: `types_schema.py:27` is currently `"0.3.1"`. Query adds no new schema property, so no bump is needed — but the spec must confirm this explicitly (the schema-compat check will require the space to be at `>= 0.3.1`).

---

## Key Findings

1. `semantic_search` is callable as a plain Python function and supports a `types` filter, but the current `must`-semantics make multi-type OR queries return zero results — the spec must resolve this before implementing Tier 2.
2. The `_call_ollama_prompt` helper in `extraction.py` is the right reuse point for synthesis, but it forces JSON format — a new non-JSON variant is needed.
3. All three new config vars (`WIKI_INDEX_THRESHOLD`, `WIKI_FILE_BACK_MIN_SOURCES`, `WIKI_FILE_BACK_MIN_WORDS`) must be added to `wiki/config.py` with call-time resolver functions.
4. `_read_schema_version`, `_cmp_versions`, `_write_wikilog`, `_resolve_wiki_action_tag`, `_write_bidirectional_relations`, `read_patch_decision`, and `_object_deeplink` are all directly reusable in `wiki/query.py`.
5. The respx no-arg pattern (`respx.get()`, `respx.post()`, `respx.patch()`) is the established CI mock style; live tests are `@pytest.mark.live` + `pytest.skip("... not set")`.
6. `wiki_action="query"` is already seeded by bootstrap (`bootstrap.py:54`).
7. The answer text must be stored in `wiki_answer` (text property), NOT in the body — `patch_body_updates: silently_ignored`.

---

## Open Questions

1. Should `wiki_query` use the stricter `ingest.py` patch-decision gate (requires `patch_body_updates` + `implementation_path` keys) or the looser `remember.py` gate (non-None only)?
2. Should `semantic_search` be fixed (use `Filter(should=...)` for multiple types) as part of this ticket, or should Tier 2 call `semantic_search` with `types=None` and post-filter?
3. Does `WIKI_SCHEMA_VERSION` stay at `"0.3.1"` for v0.4.0 (query adds no new properties)?
4. Should the synthesis LLM call use a separate function (new `synthesize()` in `extraction.py`) or inline in `wiki/query.py`?

---

## Sources

- `src/anytype_llm_wiki/wiki/wiki_client.py` — WikiClient method surface + verb+path
- `src/anytype_llm_wiki/wiki/_base_client.py` — transport base, headers, timeout
- `src/anytype_llm_wiki/anytype_client.py` — AnytypeReadClient, list_objects, get_object
- `src/anytype_llm_wiki/server.py` — semantic_search signature, MCP registration pattern
- `src/anytype_llm_wiki/wiki/types_schema.py` — type_keys, property keys, WIKI_SCHEMA_VERSION
- `src/anytype_llm_wiki/wiki/ingest.py` — create/update/relation patterns, WikiLog, pre-checks
- `src/anytype_llm_wiki/wiki/remember.py` — patch-decision gate, consolidation reuse
- `src/anytype_llm_wiki/wiki/bootstrap.py` — _read_schema_version, _cmp_versions, _object_deeplink, _WIKI_ACTION_TAGS
- `src/anytype_llm_wiki/wiki/config.py` — env-var pattern
- `src/anytype_llm_wiki/wiki/util.py` — read_patch_decision, normalize_title, space_ingest_lock
- `src/anytype_llm_wiki/wiki/extraction.py` — _call_ollama_prompt, _call_ollama, extract(), consolidate()
- `src/anytype_llm_wiki/chunker.py` — WIKI_TEXT_PROPERTY_KEYS, chunk_object, _chunk_properties
- `src/anytype_llm_wiki/indexer.py` — Qdrant payload fields including type_key
- `src/anytype_llm_wiki/wiki/cli.py` — SUBCOMMANDS, CLI pattern
- `src/anytype_llm_wiki/config.py` — root config (QDRANT_URL, OLLAMA_URL, EMBED_MODEL)
- `tests/wiki/test_ingest.py` — respx patterns, live-test gate, schema_ok helper
- `tests/wiki/test_wiki_client.py` — URL-specific respx matcher pattern
- `tests/wiki/test_server_registration.py` — MCP tool registration check pattern
- `tests/wiki/conftest.py` — shared fixtures, anytype_available live guard
- `.env.example` — existing env vars documented
- `.aldeia/285-.../spec-scope.md` — framing, wire-contract requirements
- `.aldeia/140-.../spec.md:449-518` — query pipeline design
