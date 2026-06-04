# wiki_query v0.4.0 — Tiered Retrieval and Synthesis

**Status:** DRAFT
**Date:** 2026-06-04
**Author:** spec-writer agent
**Review rounds:** 0
**Ticket:** #285 (Aldeia-IT/aldeia-box)
**Master spec:** `.aldeia/140-wiki-library-module-port-llm-wiki-pattern-onto-any/spec.md` (status: SPEC)
**Hard dependency:** #284 — `wiki_ingest` v0.3.0 incl. indexer property-embedding fix (merged)

---

## Nature of This Spec

INCREMENT spec. The master spec (#140) is the authoritative design baseline.
This document does NOT re-derive the query design; it:

1. References the master spec for data-flow diagram, signature, QueryResult schema, tier
   definitions, file-back policy, compounding, MCP conventions, and deeplink format
   (master spec §"Query Pipeline" lines 449–518, §"MCP Tool Interface" lines 609–618,
   §v0.4.0 delivery lines 878–905, §Schema Compatibility lines 1590–1607).
2. Locks four decisions the master spec left open (verified against the post-#284 codebase).
3. Grounds every helper and wire contract against real function names.
4. Firms the AC list.

---

## Problem Statement

After v0.3.0, agents can ingest sources into a typed Anytype wiki. There is no tool to
query that wiki and receive a synthesized answer. Without `wiki_query`, the "compile
once, query later" payoff (Karpathy pattern) is unreachable. This release closes the loop
and activates the compounding mechanism: filed Query objects are indexed on next
`reindex_anytype` and become sources for future queries.

---

## Research Summary

Research findings are in
`.aldeia/285-anytype-llm-wiki-v0-4-0-wiki-query-tiered-retrieva/technical-research.md`.
Key findings that drove the four locked decisions below:

- `semantic_search` (server.py:51-55) uses `Filter(must=[...])` for the type list —
  a multi-type call returns zero results (AND-semantics bug). Decision 2 fixes this.
- `extraction.py:_call_ollama_prompt` always sends `"format": "json"` — unusable for
  free-form synthesis. Decision 3 specifies a new `synthesize()` helper.
- `wiki_answer` IS in `types_schema.py:134` — no schema bump required.
- All three new config vars are absent from `wiki/config.py` and `.env.example`.
- `wiki_action="query"` tag is already seeded by `bootstrap.py:54`.

---

## Proposed Solution

### Locked Decisions

#### Decision 1 — Tier 1 candidate enumeration (FilterExpression no-op, LOCKED)

`patch-decision.md` (anytype 2025-11-08): `filter_expression: no_op`.

**Canonical path (only path):** enumerate candidates via `WikiClient.list_objects()` →
`GET /v1/spaces/{space_id}/objects?offset=N&limit=N` (paginate while
`pagination.has_more == True`), then client-side filter by `type_key` for the four wiki
types (`wiki_entity`, `wiki_concept`, `wiki_comparison`, `wiki_query`).

Emit a warning in `QueryResult.warnings` when the pre-filter row count exceeds 500:

```
filterexpression_fallback: returned {N} rows before client-side filter — rerun scripts/verify-anytype-writes.sh to confirm upstream filter support
```

The "if FilterExpression works" branch is DEPRECATED. It does not appear in code.

#### Decision 2 — Tier 2 multi-type semantic_search filter (LOCKED)

**Root cause:** `server.py:51-55` builds `Filter(must=[FieldCondition(key="type_key",
match=MatchValue(value=t)) for t in types])`. When `len(types) > 1` every condition must
match simultaneously — impossible for a single Qdrant point. Multi-type query returns
zero.

**Fix (additive, backward-compatible):** Change the type-filter construction in
`server.py` to use OR-semantics:

- Keep `space_id` equality as a `must` condition (unchanged).
- Move type-key conditions to a `should` list with `min_should=1`.
- Single-type behavior is identical to current (one condition, min_should=1).

Pseudo-construction (exact Qdrant client API in implementation):

```python
# must: space_id filter (unchanged)
must = [FieldCondition(key="space_id", match=MatchValue(value=space_id))] if space_id else []

# should: type conditions — OR semantics
should = [FieldCondition(key="type_key", match=MatchValue(value=t)) for t in types] if types else []
min_should = 1 if should else None

filter_ = Filter(must=must, should=should or None, min_should=min_should)
```

**Search-core extraction:** Extract the Qdrant query logic from the `@mcp.tool()
semantic_search` decorator body into a plain Python-callable helper `_semantic_search_core(query, space_id, types, limit)` in `server.py` (or `indexer.py`). The `@mcp.tool() semantic_search` wrapper calls this helper. `wiki/query.py` also calls this helper directly — avoiding any dependence on FastMCP decorator-wrapping semantics.

**Blast radius:** This touches the shared v0.1 `semantic_search` MCP tool. Reviewers
must verify single-type queries still return the same results. A regression test
asserts single-type behavior is unchanged and a new test asserts multi-type OR returns
results.

#### Decision 3 — Synthesis LLM call (LOCKED)

No free-form synthesis helper exists. `extraction.py:_call_ollama_prompt` always sends
`"format": "json"` — it cannot be reused as-is.

**Canonical path:** Add `synthesize(question: str, context_objects: list[dict]) -> str`
to `wiki/query.py`. It reuses the Ollama transport pattern from `extraction.py`:

- Endpoint: `WIKI_EXTRACT_ENDPOINT` OR `OLLAMA_URL` (same as extraction).
- Model: `config.extract_model()` → `WIKI_EXTRACT_MODEL` (default `"qwen2.5:7b"`). No
  new `WIKI_SYNTH_MODEL` env var — reuse the extraction model to minimize config surface.
  If operators need a separate synthesis model, that is a v0.5.0+ consideration.
- Options: `{"temperature": 0, "seed": 0, "top_p": 1, "think": false}` (same as
  extraction).
- Timeout: `config.extract_timeout()` → `WIKI_EXTRACT_TIMEOUT`.
- Wire: `POST {base}/api/generate`, fallback to `POST {base}/api/chat`.
- Omits `"format": "json"` — free-form prose output.
- On model-not-pulled, returns error string `[CONFIG ERROR] model_not_pulled: {model}`.

Synthesis prompt contract:
- Prompt file: `wiki/prompts/synthesis.md` (new file).
- Context objects are interpolated inside `<context>…</context>` fences (parallel to
  extraction's `<source>…</source>`).
- Object names pass through the same name-policy regex used at extraction before
  interpolation (length cap 200, no control chars, no prompt-like prefix). Rejected names
  are replaced with `[REDACTED]` and recorded in `QueryResult.warnings` as
  `synthesis_name_rejected: {original}` (master spec AC #10, CSO #4).
- The prompt instructs the model to cite sources by title and produce the `wiki_answer`
  text.
- Return value is the raw prose string that becomes the filed Query's `wiki_answer` property.

#### Decision 4 — File-back write path (LOCKED)

`patch_body_updates: silently_ignored` (patch-decision.md). The answer MUST go in a
text property, not the object body.

- `wiki_answer` text property EXISTS in `types_schema.py:134`. No schema bump required.
  `WIKI_SCHEMA_VERSION` stays at `"0.3.1"`. No `MIGRATIONS.md` entry needed.
- Filed Query object properties: `wiki_question` (text), `wiki_answer` (text),
  `wiki_asked_at` (date), `wiki_drew_from` (objects — the cited source IDs).
- Patch-decision gate for `wiki_query`: use the stricter `ingest.py` gate — checks that
  BOTH `patch_body_updates` AND `implementation_path` keys are present. This is correct
  since the file-back write path depends on property writes working.

---

### Query Pipeline

Data-flow diagram: master spec lines 453–471 (normative). Reproduced by reference only.

#### Tool Signature

Per master spec lines 473–479:

```python
def wiki_query(
    question: str,
    space_id: str,
    file_back: bool | None = None,
) -> dict:  # QueryResult
```

#### QueryResult Schema (tool contract)

Per master spec lines 484–499:

```json
{
  "answer": "string",
  "sources_consulted": [
    {
      "title": "string",
      "type": "entity|concept|comparison|query",
      "object_id": "string",
      "deeplink": "anytype://object/{space_id}/{object_id}"
    }
  ],
  "filed_back": false,
  "query_object_id": "string|null",
  "query_object_deeplink": "anytype://object/{space_id}/{query_object_id}|null",
  "retrieval_mode": "index_navigation|vector_augmented",
  "object_count_at_decision": 147,
  "wiki_log_id": "string",
  "wiki_log_deeplink": "anytype://object/{space_id}/{wiki_log_id}",
  "warnings": ["string"],
  "status": "ok|partial|error"
}
```

#### Tiered Retrieval

Object count = Entity + Concept + Comparison + Query objects in the space.
Threshold constant: `WIKI_INDEX_THRESHOLD` (default 200). Mode flips at `count >= threshold` (200 inclusive).

| count | mode | path |
|-------|------|------|
| < 200 | `index_navigation` | Tier 1 |
| >= 200 | `vector_augmented` | Tier 2 |

**Boundary matrix (test fixture values):**

| count | threshold | expected mode |
|-------|-----------|---------------|
| 199 | 200 (default) | `index_navigation` |
| 200 | 200 (default) | `vector_augmented` |
| 201 | 200 (default) | `vector_augmented` |
| 99 | 100 (custom) | `index_navigation` |
| 100 | 100 (custom) | `vector_augmented` |

**Tier 1 — index-navigation:**

1. `WikiClient.list_objects(space_id, offset, limit)` → paginate while `pagination.has_more`.
2. Client-side filter: keep objects where `obj["type"]["key"] in {"wiki_entity", "wiki_concept", "wiki_comparison", "wiki_query"}`.
3. Emit `filterexpression_fallback` warning if pre-filter count > 500.
4. Fetch full objects + 1-hop neighborhood (see below).

**Tier 2 — vector-augmented:**

1. Call `_semantic_search_core(question, space_id=space_id, types=["wiki_entity", "wiki_concept", "wiki_comparison", "wiki_query"], limit=10)`.
2. Use OR-semantics fix (Decision 2). Returns `[{"object_id": ..., "type": ..., "score": ..., ...}]`.
3. Collect candidate `object_id` values.
4. Fetch full objects + 1-hop neighborhood (see below).

**Qdrant-down fallback (master spec lines 461–462):**

- Qdrant down + `count < threshold` → silently fall back to Tier 1.
- Qdrant down + `count >= threshold` → return `[API ERROR] qdrant_unavailable` with `status: "error"`.

#### 1-Hop Neighborhood Traversal

For each candidate object, fetch linked objects via:
- `wiki_relations` (Entity → other objects)
- `wiki_related` (Concept → other objects)
- `wiki_drew_from` (Query → source objects)
- `wiki_subjects` (Comparison → subject objects)

Read shape from `get_object` response: `properties: [{"key": "wiki_relations", "objects": ["id1", "id2"]}, ...]`.

**Per-run object cache:** a `dict[str, dict]` keyed by `object_id`, populated on first
fetch via `AnytypeReadClient.get_object()`. All subsequent lookups for the same
`object_id` read from the cache. This prevents N+1 fetches and duplicate API calls within
a single `wiki_query` invocation. The cache is NOT persisted between calls.

Fetch: `AnytypeReadClient.get_object(space_id, object_id)` →
`GET /v1/spaces/{space_id}/objects/{object_id}?format=md`.

#### Synthesis

Call `synthesize(question, context_objects)` → prose string.
Context objects include both candidates and their 1-hop neighbors (deduplicated via cache).
Apply name-policy filter before interpolation (Decision 3 / CSO #4).

`sources_consulted` in QueryResult is built from objects whose content contributed to
the answer (title, type, object_id, deeplink). Deeplink format:
`anytype://object/{space_id}/{object_id}` (master spec §MCP line 615).

#### File-Back Gate

Create a filed Query object when:
- `file_back=True` (override), OR
- `file_back` is `None` AND `len(sources_consulted) >= WIKI_FILE_BACK_MIN_SOURCES` AND
  `len(answer.split()) >= WIKI_FILE_BACK_MIN_WORDS`

Suppress when `file_back=False` (override) regardless of thresholds.

File-back writes:
1. `WikiClient.create_object(space_id, type_key="wiki_query", name=question[:100], properties=[wiki_question, wiki_answer, wiki_asked_at])` → `POST /v1/spaces/{space_id}/objects`.
2. `WikiClient.update_object(space_id, query_obj_id, {"properties": [{"key": "wiki_drew_from", "objects": [ids...]}]})` → `PATCH /v1/spaces/{space_id}/objects/{object_id}`.
3. Reuse `_write_bidirectional_relations` (ingest.py:296) for reciprocal relation writes IF the cited objects are entities or concepts.

#### WikiLog

After every `wiki_query` invocation (success or partial):

```python
_write_wikilog(
    client, space_id,
    subject=question[:50],
    created=1 if filed_back else 0,
    updated=0,
    notes=f"query: {len(sources_consulted)} sources, {retrieval_mode}",
    action_tag_id=action_tag_id,  # from _resolve_wiki_action_tag(client, space_id, "query")
    action_name="query",
)
```

#### Pre-Checks (fire before any write or Qdrant call)

Both checks run before any `list_objects`, `semantic_search`, or object create/update.

**QA#25 — wiki_schema_outdated:**
Reuse `_read_schema_version(client, space_id)` (bootstrap.py:486) +
`_cmp_versions(a, b)` (ingest.py:447).

Error strings (exact):
- Missing: `"[CONFIG ERROR] wiki_schema_missing: run wiki_bootstrap on this space first"`
- Outdated: `"[CONFIG ERROR] wiki_schema_outdated: space schema {live_version} < code {code_version}; run wiki_bootstrap to upgrade"`
- Newer: warning `"wiki_schema_newer: space schema {live_version} > code {code_version}; continuing"` (warn-and-continue, does not abort).

**QA#30 — patch_decision_missing_or_invalid:**
Reuse `read_patch_decision()` (util.py:229). Gate: result must be non-None AND contain
both `patch_body_updates` AND `implementation_path` keys (stricter `ingest.py` gate).

Error string (exact):
`"[CONFIG ERROR] patch_decision_missing_or_invalid: a valid patch-decision.md with patch_body_updates and implementation_path is required"`

This fires before any Anytype write or Qdrant call.

#### Compounding (hard dependency on #284)

**#284 is a hard prerequisite for meaningful Tier-2 retrieval.** The indexer
property-embedding fix (chunker.py `WIKI_TEXT_PROPERTY_KEYS`) ensures wiki content in
text properties (`wiki_answer`, `wiki_question`, etc.) is embedded. Without #284, filed
Query objects produce no Qdrant points and Tier 2 cannot surface them.

The compounding loop: file back → next `reindex_anytype` embeds `wiki_answer` →
future `wiki_query` Tier-2 calls can surface the filed Query as a candidate.

---

## Wire-Contract Pinning

Every endpoint `wiki_query` calls:

| Call site | Verb | Path | Mock to mirror |
|-----------|------|------|----------------|
| `WikiClient.list_objects` (schema check + Tier 1 enum) | GET | `/v1/spaces/{space_id}/objects?offset=N&limit=N` | `respx.get()` (no-arg) — mirror `test_ingest.py:_make_schema_ok_response` |
| `AnytypeReadClient.get_object` (full object fetch + neighbors) | GET | `/v1/spaces/{space_id}/objects/{object_id}?format=md` | `respx.get(f"{ANYTYPE_BASE}/v1/spaces/{space_id}/objects/{object_id}")` |
| `WikiClient.create_object` (file-back Query + WikiLog) | POST | `/v1/spaces/{space_id}/objects` | `respx.post()` (no-arg) — mirror `test_ingest.py` create mock |
| `WikiClient.update_object` (wiki_drew_from relations) | PATCH | `/v1/spaces/{space_id}/objects/{object_id}` | `respx.patch()` (no-arg) |
| `_semantic_search_core` (Tier 2) | N/A — Qdrant internal | Collection query via `qdrant-client` | monkeypatch `_semantic_search_core` at function boundary — no HTTP mock |

**respx 0.23.x note:** Use no-arg `respx.get()` / `respx.post()` / `respx.patch()` for
catch-all mocks. `respx.patterns.M` raises at registration. URL-specific matchers:
`respx.get(f"{base}/v1/spaces/{space_id}/objects/{object_id}")` — only when the test
must assert a specific path was called.

---

## Configuration

Add to `wiki/config.py` following the call-time resolver pattern:

```python
DEFAULT_WIKI_INDEX_THRESHOLD = 200
DEFAULT_WIKI_FILE_BACK_MIN_SOURCES = 3
DEFAULT_WIKI_FILE_BACK_MIN_WORDS = 100

def index_threshold() -> int:
    try:
        return int(os.environ.get("WIKI_INDEX_THRESHOLD", DEFAULT_WIKI_INDEX_THRESHOLD))
    except (ValueError, TypeError):
        return DEFAULT_WIKI_INDEX_THRESHOLD

def file_back_min_sources() -> int:
    try:
        return int(os.environ.get("WIKI_FILE_BACK_MIN_SOURCES", DEFAULT_WIKI_FILE_BACK_MIN_SOURCES))
    except (ValueError, TypeError):
        return DEFAULT_WIKI_FILE_BACK_MIN_SOURCES

def file_back_min_words() -> int:
    try:
        return int(os.environ.get("WIKI_FILE_BACK_MIN_WORDS", DEFAULT_WIKI_FILE_BACK_MIN_WORDS))
    except (ValueError, TypeError):
        return DEFAULT_WIKI_FILE_BACK_MIN_WORDS
```

Add to `.env.example`:

```
WIKI_INDEX_THRESHOLD=200
WIKI_FILE_BACK_MIN_SOURCES=3
WIKI_FILE_BACK_MIN_WORDS=100
```

---

## Security Considerations

**Prompt injection:** Object names from Anytype are attacker-controlled if an adversary
can create wiki objects. Apply the same name-policy regex used at extraction (master spec
CSO #4) before interpolating any name into the synthesis prompt. Wrap all context in
`<context>…</context>` fences. Rejected names → `[REDACTED]` + warning in
`QueryResult.warnings`.

**No SSRF risk:** `wiki_query` fetches only Anytype objects by ID (known host) and
calls Ollama (localhost). No user-supplied URLs are fetched.

**Credentials:** Bearer token via `ANYTYPE_API_KEY` env var; Qdrant key via
`QDRANT_API_KEY`. No new credential surfaces.

---

## Resource Impact

- Tier 1 on a 200-object wiki: O(N) `list_objects` pages + O(candidates) `get_object`
  calls. At 200 objects with default page size, this is ≤ 4 paginated GETs + up to
  ~200 object fetches (mitigated by 1-hop cache). Acceptable on Mac Mini M4.
- Tier 2: 1 Qdrant query + O(results) `get_object` calls (limit=10 by default).
- Synthesis: 1 Ollama call. Timeout governed by `WIKI_EXTRACT_TIMEOUT` (default 600s).
- Per-run object cache is in-process dict; no persistent memory overhead.

---

## Test Plan

All tests in `tests/wiki/test_query.py`. CI-runnable tests use respx mocks and
monkeypatching. Live tests are `@pytest.mark.live` + `pytest.skip` if
`ANYTYPE_SPACE_ID` not set (mirror `test_ingest.py:1097-1117` pattern).

### CI-runnable mocked tests (backstops)

| Test | What it verifies |
|------|-----------------|
| `test_query_returns_answer_with_cited_source` | QueryResult has non-empty `answer` and `sources_consulted[0].deeplink` (mocked Anytype + monkeypatched synthesis) |
| `test_retrieval_mode_boundary_matrix` | `retrieval_mode` correct at count=199, 200, 201 (default threshold) and 99, 100 (custom threshold=100) — mocked list_objects returns |
| `test_neighborhood_cache_prevents_duplicate_fetches` | assert `get_object` called once per unique `object_id`; a two-candidate run sharing a neighbor triggers only one fetch for the shared neighbor |
| `test_file_back_creates_query_object_when_thresholds_met` | mocked create returns obj_id; assert `POST /objects` called and `QueryResult.filed_back == True`; word count and source count meet defaults |
| `test_file_back_suppressed_when_below_threshold` | word count < 100 OR source count < 3 → `filed_back == False`, no POST to objects |
| `test_file_back_false_override_suppresses` | `file_back=False` → `filed_back == False` even when thresholds met |
| `test_file_back_true_override_forces` | `file_back=True` → `filed_back == True` even when thresholds not met |
| `test_pre_check_schema_outdated_fires_before_write` | mocked schema version older than code → returns `[CONFIG ERROR] wiki_schema_outdated`; assert no POST/PATCH calls made |
| `test_pre_check_patch_decision_missing_fires_before_write` | missing patch-decision → `[CONFIG ERROR] patch_decision_missing_or_invalid`; assert no Anytype write or Qdrant call |
| `test_multi_type_semantic_search_returns_results` | regression for Decision 2: monkeypatched `_semantic_search_core` with OR-semantics mock returns results for `types=["wiki_entity","wiki_concept","wiki_comparison","wiki_query"]`; assert non-empty candidates |
| `test_single_type_semantic_search_unchanged` | single type still returns results — backward-compat regression |
| `test_filterexpression_fallback_warning_above_500` | mocked list_objects returns 501 pre-filter rows; assert `filterexpression_fallback` in `QueryResult.warnings` |
| `test_qdrant_down_below_threshold_falls_back_to_tier1` | _semantic_search_core raises; count < threshold → mode = `index_navigation`, no error |
| `test_qdrant_down_at_threshold_returns_api_error` | _semantic_search_core raises; count >= threshold → `[API ERROR] qdrant_unavailable` |
| `test_synthesis_name_injection_rejected` | object name containing injection prefix → `[REDACTED]` in prompt, `synthesis_name_rejected` in warnings |

### Live smoke test (additive, skip-gated)

```python
@pytest.mark.live
class TestQueryLive:
    def test_end_to_end_query(self):
        space_id = os.environ.get("ANYTYPE_SPACE_ID")
        if not space_id:
            pytest.skip("ANYTYPE_SPACE_ID not set — live query test skipped")
        result = wiki_query(question="What is a wiki entity?", space_id=space_id)
        assert result["status"] in ("ok", "partial")
        assert result["answer"]
        assert result["retrieval_mode"] in ("index_navigation", "vector_augmented")
```

Run with: `uv run pytest -m live tests/wiki/test_query.py`
Exclude from CI: `uv run pytest -m 'not live'`

---

## Acceptance Criteria

1. **Tier 1 mode:** query on a wiki with < 200 wiki objects returns `retrieval_mode: "index_navigation"` (CI-mocked).
2. **Tier 2 mode:** query on a wiki with >= 200 wiki objects returns `retrieval_mode: "vector_augmented"` (CI-mocked).
3. **Boundary matrix:** counts 199/200/201 flip mode at exactly 200; custom threshold tested with 99/100 (CI-mocked, `test_retrieval_mode_boundary_matrix`).
4. **Answer + cited deeplink:** query returns non-empty `answer` and at least one `sources_consulted` entry with a valid `anytype://object/{space_id}/{object_id}` deeplink (CI-mocked backstop).
5. **Multi-type search fix (Decision 2):** `_semantic_search_core` with `types` list of 4 wiki types returns results; single-type backward compatibility preserved (CI regression tests).
6. **File-back gate:** creates Query object (POST + PATCH for relations) when `len(sources) >= 3` AND `len(answer.split()) >= 100`; suppressed when below threshold; `file_back=True/False` override honored (CI-mocked).
7. **Compounding prerequisite:** spec and README state that Tier-2 retrieval of filed Queries requires #284's indexer property-embedding fix. No AC gating this in CI — it is a documented prerequisite (verify via live test after reindex).
8. **Neighborhood cache:** each unique `object_id` fetched at most once per `wiki_query` call (CI-mocked, `test_neighborhood_cache_prevents_duplicate_fetches`).
9. **QA#25 — schema outdated:** outdated space schema → `[CONFIG ERROR] wiki_schema_outdated` naming found + expected versions, before any write (CI-mocked).
10. **QA#30 — patch-decision pre-check:** missing/malformed `patch-decision.md` → `[CONFIG ERROR] patch_decision_missing_or_invalid` before any Anytype write or Qdrant call (CI-mocked).
11. **CSO#4 — synthesis-prompt injection defense:** object name with injected directive prefix → `[REDACTED]` substituted, `synthesis_name_rejected` in `QueryResult.warnings` (CI-mocked, `test_synthesis_name_injection_rejected`).
12. **Qdrant-down fallback:** down + below threshold → Tier 1 fallback, no error; down + at/above threshold → `[API ERROR] qdrant_unavailable` (CI-mocked).
13. **`filterexpression_fallback` warning:** pre-filter count > 500 → warning string in `QueryResult.warnings` (CI-mocked).
14. **CLI + server registration:** `wiki-query` in `SUBCOMMANDS`; `wiki_query` registered as MCP tool in `server.py`; full test suite green.
15. **Performance sanity (CI):** mocked query completes within 5s. Maintainer-measured p95 < 5s on Mac Mini M4 at release time (master spec AC#7).

---

## Implementation Plan

### Files Changed

| File | Action |
|------|--------|
| `src/anytype_llm_wiki/wiki/query.py` | NEW — tiered retrieval, 1-hop cache, synthesis, file-back, WikiLog |
| `src/anytype_llm_wiki/wiki/prompts/synthesis.md` | NEW — synthesis prompt template |
| `src/anytype_llm_wiki/server.py` | EDIT — extract `_semantic_search_core`, fix OR-filter, register `wiki_query` tool |
| `src/anytype_llm_wiki/wiki/cli.py` | EDIT — add `"wiki-query"` to `SUBCOMMANDS`, add `_cmd_query` |
| `src/anytype_llm_wiki/wiki/config.py` | EDIT — add `index_threshold`, `file_back_min_sources`, `file_back_min_words` |
| `.env.example` | EDIT — add three new vars |
| `README.md` | EDIT — add query section to quick-start and "How it works" |
| `CHANGELOG.md` | EDIT — v0.4.0 entry |
| `MIGRATIONS.md` | NOT touched — `WIKI_SCHEMA_VERSION` stays at `"0.3.1"` (no new properties) |
| `tests/wiki/test_query.py` | NEW — all tests per test plan |

### Reused Helpers (verbatim names from codebase)

| Helper | Module | Purpose |
|--------|--------|---------|
| `_read_schema_version(client, space_id)` | `wiki/bootstrap.py:486` | QA#25 schema check |
| `_cmp_versions(a, b)` | `wiki/ingest.py:447` | version comparison |
| `_object_deeplink(space_id, object_id)` | `wiki/bootstrap.py:83` | deeplink generation |
| `read_patch_decision()` | `wiki/util.py:229` | QA#30 patch-decision gate |
| `_resolve_wiki_action_tag(client, space_id, "query")` | `wiki/ingest.py:212` | WikiLog action tag |
| `_write_wikilog(client, space_id, ...)` | `wiki/ingest.py:241` | WikiLog write |
| `_write_bidirectional_relations(client, space_id, ...)` | `wiki/ingest.py:296` | reciprocal relations |
| `WikiClient.list_objects` | `wiki/wiki_client.py` | Tier 1 enumeration |
| `WikiClient.create_object` | `wiki/wiki_client.py` | file-back create |
| `WikiClient.update_object` | `wiki/wiki_client.py` | relation writes |
| `AnytypeReadClient.get_object` | `anytype_client.py` | full object + neighbor fetch |
| `_semantic_search_core` | `server.py` (extracted in this ticket) | Tier 2 search |

### Ordering

1. Fix `server.py`: extract `_semantic_search_core`, apply OR-semantics to type filter.
2. Add three config vars to `wiki/config.py` and `.env.example`.
3. Add `synthesize()` to `wiki/query.py` + create `wiki/prompts/synthesis.md`.
4. Implement `wiki/query.py`: pre-checks → count → tier → neighborhood → synthesis → file-back → WikiLog.
5. Register `wiki_query` in `server.py` and add `wiki-query` to `cli.py`.
6. Write `tests/wiki/test_query.py` — CI tests first, live smoke test last.
7. Update `README.md` and `CHANGELOG.md`.

---

## Open Questions

None. All four decision gaps are locked above.

---

## Deferred Items

- **`WIKI_SYNTH_MODEL` env var:** separate synthesis model config — deferred to v0.5.0+.
  Rationale: adds config surface without proven need; extraction model is adequate for synthesis.
- **Multi-hop (>1) neighborhood traversal:** explicitly out of scope (master spec §v0.4.0 scope-out).
- **Streaming query responses:** out of scope (master spec §v0.4.0 "Won't").
- **Inline tool-use during synthesis:** out of scope (master spec §v0.4.0 "Won't").
