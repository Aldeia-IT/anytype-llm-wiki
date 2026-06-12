# Research: #324 Relationship-Aware Retrieval — Gap Verification

**Date:** 2026-06-11
**Researcher:** technical-research worker (claude-sonnet-4-6)
**Ticket:** Aldeia-IT/aldeia-box#324
**Branch:** aldeia/324-relationship-aware-retrieval-follow-anytype-relati
**Scope brief:** `.aldeia/324-relationship-aware-retrieval-follow-anytype-relati/spec-scope.md`

---

## Purpose

Verify the scope brief's gap analysis against live code and answer seven
confined questions. No redesign. All line citations are to the HEAD state of
this worktree.

---

## Gap Verification (scope brief claims vs. live code)

All five scope-brief gaps are **confirmed**.

| AC | Brief claim | Verified location | Status |
|----|------------|-------------------|--------|
| AC#1 | neighbours feed context but NOT `sources_consulted` | query.py:738-740 `contributing = [c for c in candidates if …]` | CONFIRMED |
| AC#2 | `_RELATION_KEYS` missing `wiki_sources`, has `wiki_subjects` | query.py:53 | CONFIRMED |
| AC#3 | dedup vs candidate set already done | query.py:521,525 | CONFIRMED |
| AC#4 | neighbours kept in discovery order (no rank/relation priority) | `_build_context` query.py:705-707: `sorted_candidates + list(neighbors)` | CONFIRMED |
| AC#5 | fan-out is unbounded; no cap config knob | query.py:527-535 loop over all `neighbor_ids`; no cap variable or config call | CONFIRMED |

Additional gap verified: `wiki_sources` is a property on `wiki_entity` (types_schema.py:93), `wiki_concept` (types_schema.py:109), AND `wiki_comparison` (types_schema.py:124) — so adding it covers three types. `wiki_subjects` is `wiki_comparison`-only (types_schema.py:121) and links to the compared subjects, not to external sources.

---

## Q1 — `semantic_search_core` Contract

**File:** `src/anytype_llm_wiki/indexer.py:20-82`

**Signature:**
```python
def semantic_search_core(
    query: str,
    space_id: str | None = None,
    types: list[str] | None = None,
    limit: int = 10,
) -> list[dict]:
```

**Return shape per result dict** (indexer.py:72-81):
```python
{
    "object_name": str,    # payload["object_name"]
    "object_id":   str,    # payload["object_id"]
    "type":        str,    # payload["type_key"]  — key is "type" NOT "type_key"
    "heading":     str,    # payload["heading"]
    "text":        str,    # payload["text"][:500]
    "score":       float,  # round(r.score, 4)
}
```

**Rank order:** Results are returned in Qdrant score-descending order. `client.query_points` returns points ordered by similarity score; indexer.py returns the list as-is (no re-sort). **Results ARE in rank order** (highest score first).

**Seed rank definition for spec:** rank = position in `raw` list from `semantic_search_core` (0-indexed). query.py:453-463 preserves this order when building `candidate_entries` (deduplication by first-seen, score from `r.get("score", 0.0)`).

**Type field name mismatch:** The return dict key is `"type"` (not `"type_key"`). query.py:461 reads this correctly: `r.get("type") or r.get("type_key", "")`.

---

## Q2 — Seed Relation Hydration in Tier-2

**How `_fetch_cached` works** (query.py:650-672):

1. If `object_id in cache` — return from cache (no HTTP call).
2. Else call `read_client.get_object(space_id, object_id)` → `GET /v1/spaces/{space_id}/objects/{object_id}?format=md` (anytype_client.py:44-52).
3. On `KeyError` (permissive mock returning list envelope) — fall back to `enum_map.get(object_id)`.
4. On `httpx.HTTPError` or `ConnectionError` — return `None` (fetch failure).

**enum_map construction** (query.py:503-506): `{o.get("id"): o for o in all_objects …}` where `all_objects` = result of `write_client.list_objects(space_id)`.

**What `list_objects` returns:** `GET /v1/spaces/{space_id}/objects?offset=N&limit=N` returns `{"data": [...], "pagination": {...}}` (anytype_client.py:23-42). The code comment at query.py:500 explicitly states: "Enumeration already returned full objects (with properties)". Objects in `all_objects` carry their `properties` arrays including relation `objects` arrays.

**Critical hydration question:** Seeds (candidates) go through `_fetch_cached`, which calls `get_object` first (NOT reading from `enum_map` unless get_object fails). So for a seed already in `enum_map`, `_fetch_cached` still issues `get_object` to get the definitive hydrated copy (with `?format=md`). The `enum_map` fallback is an error path only.

**Does `list_objects` hydrate relation `objects` arrays?** The comment at query.py:500 says yes ("full objects with properties"), and this is consistent with Anytype's REST API (list_objects returns full property objects). The `_neighbor_ids_of` function (query.py:679-687) reads from the fetched object's `properties` array, which works because `get_object` (primary path) definitively returns hydrated relation arrays.

**Fan-out bound scope implication:** Since seeds are fetched via `get_object` (one call per seed, not from enum_map except on failure), the seeds already incur get_object calls. The neighbours add further calls. The cap should bound the **neighbour** fan-out only (seeds are bounded by `semantic_search_core`'s `limit=10`). No additional seed reads are needed for #324.

**Wire path summary:**
- Seed read: `GET /v1/spaces/{space_id}/objects/{seed_id}?format=md` (via `_fetch_cached`)
- Neighbour read: `GET /v1/spaces/{space_id}/objects/{neighbour_id}?format=md` (via `_fetch_cached`)
- Both share the same `_fetch_cached` code path and per-run `cache` dict — QA-12 invariant.

---

## Q3 — Citation Plumbing

**`sources_consulted` entry construction** (query.py:562-572):
```python
sources_consulted.append({
    "title":     obj.get("name", ""),
    "type":      _short_type(_type_of(obj)),
    "object_id": oid,
    "deeplink":  _bootstrap._object_deeplink(space_id, oid),
})
```

**`_type_of(obj)`** (query.py:248-252): reads `obj["type"]`; if it's a dict returns `dict["key"]`; else returns the string directly or `""`.

**`_short_type(type_key)`** (query.py:255-262): maps
- `"wiki_entity"` → `"entity"`
- `"wiki_concept"` → `"concept"`
- `"wiki_comparison"` → `"comparison"`
- `"wiki_query"` → `"query"`
- fallback: strips `"wiki_"` prefix or returns `""` if empty

**`_bootstrap._object_deeplink(space_id, object_id)`** (bootstrap.py:83-84):
```python
return f"anytype://object/{space_id}/{object_id}"
```

**To cite a neighbour identically:** append to `sources_consulted` the same four-key dict. The `oid` is `c["object_id"]` for candidates; for a surviving neighbour it would be `n["object_id"]`. The `obj` is available from `n["obj"]`. No new helpers needed — the existing plumbing composes directly.

---

## Q4 — File-Back Coupling to `sources_consulted`

**`_maybe_file_back` signature** (query.py:777-778):
```python
def _maybe_file_back(write_client, read_client, space_id, question, answer,
                     sources_consulted, file_back, cache, enum_map=None):
```
It receives `sources_consulted` as the authoritative list. It does NOT iterate `contributing` separately — `contributing` only feeds `sources_consulted` at the call site (query.py:563-573), and then the fully assembled `sources_consulted` is passed to `_maybe_file_back`.

**Min-sources gate** (query.py:801-804):
```python
should_file = (
    len(sources_consulted) >= config.file_back_min_sources()  # default 3
    and len(answer.split()) >= config.file_back_min_words()    # default 100
)
```
This counts ALL entries in `sources_consulted`, not just candidates.

**SF4 write-time re-fetch loop** (query.py:808-817):
```python
for src in sources_consulted:
    oid = src["object_id"]
    obj = _refetch_for_writeback(read_client, space_id, oid, enum_map)
    if obj is None:
        warnings.append(f"cited_object_gone: {oid}")
        status = "partial"
        continue
    cited_entries.append((oid, _type_of(obj)))
```
This iterates every entry in `sources_consulted` and does a **fresh** `get_object` for each (bypasses the per-run cache). If neighbours enter `sources_consulted`, each surviving neighbour triggers one additional `_refetch_for_writeback` call at write time.

**`wiki_drew_from` write** (query.py:844-857):
```python
cited_ids = [oid for (oid, _t) in cited_entries]
write_client.update_object(
    space_id, query_id,
    {"properties": [{"key": "wiki_drew_from", "objects": cited_ids}]},
)
```
All `sources_consulted` entries (post-SF4 filter) are written into `wiki_drew_from`.

**Implication of option (a) vs (b):**

- **Option (a) — cite neighbours in result but keep file-back seed-only:** Requires either (i) splitting `sources_consulted` into a cited-in-result list vs. a filed list, or (ii) keeping a separate `filed_sources` list passed to `_maybe_file_back` while the result's `sources_consulted` carries all. This is a code-structural change to `_maybe_file_back`'s call signature.

- **Option (b) — full provenance incl. neighbours in `wiki_drew_from`:** Simplest: neighbours enter `sources_consulted` at query.py:562-572, `_maybe_file_back` sees them all, `wiki_drew_from` includes them. The only side effects: (i) min-sources gate counts neighbours (making file-back easier to trigger), (ii) each surviving neighbour triggers one extra `_refetch_for_writeback` call at write time, (iii) the filed Query's `wiki_drew_from` includes neighbours. Option (b) requires no signature change.

**Recommendation note for spec:** Option (b) is lower-complexity code change. Option (a) preserves the #285 invariant exactly but requires a signature change. The injection-amplifier bound is the SF1 gate (synthesis must be clean) + min-sources gate; neighbours are themselves fetched objects from the same vault, so including them in `wiki_drew_from` does not weaken the security bound.

---

## Q5 — Existing Test Patterns

### Single-dispatcher respx pattern (test_query_fetch_paths.py)

**Pattern** (test_query_fetch_paths.py:94-111):
```python
def dispatcher(request, **kwargs):
    if _is_list_request(request):
        return httpx.Response(200, json=list_resp)
    oid = _obj_id_from_request(request)
    fetch_counts[oid] = fetch_counts.get(oid, 0) + 1
    # build per-id response
    return httpx.Response(200, json={"object": { ... }})

respx.get().mock(side_effect=dispatcher)
respx.post().mock(return_value=httpx.Response(201, json={"object": {"id": "log-001"}}))
```

**Key helpers** (test_query_fetch_paths.py:56-70):
```python
def _obj_id_from_request(request):
    return str(request.url).rstrip("/").split("/")[-1].split("?")[0]

def _is_list_request(request):
    path = str(request.url).split("?")[0].rstrip("/")
    return path.endswith("/objects")

def _is_object_request(request):
    path = str(request.url).split("?")[0].rstrip("/")
    return "/objects/" in path
```

**Fetch-count capture:** `fetch_counts: dict[str, int] = {}` dict incremented in dispatcher per object_id. Assertion: `assert fetch_counts.get(shared_id, 0) == 1`.

**Wire path for get_object:** `GET http://127.0.0.1:31012/v1/spaces/{space_id}/objects/{object_id}?format=md` — confirmed by anytype_client.py:47-49. The `?format=md` query param is present; `_obj_id_from_request` strips it correctly (splits on `?` before extracting final path segment).

### Skipped test in test_query.py

**test_query.py:566-574:** `@pytest.mark.skip` on `test_neighborhood_cache_prevents_duplicate_fetches` with reason: "respx 0.23.1 ordering: a no-arg catch-all respx.get() registered before the regex get_object route wins every match". Points to `test_query_fetch_paths.py::TestNeighborhoodCacheReplacement` as the verified equivalent.

**Rule for new tests:** Fan-out-cap tests, neighbour-citation tests, and hydration tests MUST go in `test_query_fetch_paths.py` using the single-dispatcher pattern. Do NOT add new route-ordering-dependent tests to `test_query.py`.

**PATCH calls in tests:** `respx.patch().mock(...)` needed when testing file-back (test_query_fetch_paths.py:166-167). Neighbours in `sources_consulted` will cause additional `_refetch_for_writeback` calls (GET) in dispatcher, and may change the `cited_ids` array in the PATCH payload.

---

## Q6 — Config Knob Pattern

**`_positive_int` SF10 guard** (config.py:50-62):
```python
def _positive_int(env: str, default: int) -> int:
    raw = os.environ.get(env)
    if raw is None:
        return default
    try:
        val = int(raw)
    except (ValueError, TypeError):
        return default
    return val if val > 0 else default
```
Rejects 0 and negative values (returns default). Non-numeric values return default.

**Convention for a new knob (e.g. `WIKI_QUERY_MAX_NEIGHBORS`):**

1. Add constant to config.py: `DEFAULT_WIKI_QUERY_MAX_NEIGHBORS = 32`
2. Add accessor: `def query_max_neighbors() -> int: return _positive_int("WIKI_QUERY_MAX_NEIGHBORS", DEFAULT_WIKI_QUERY_MAX_NEIGHBORS)`
3. Add to `.env.example` under `# --- v0.4.0 wiki_query …` section (line 42 area), following the comment-block style already used for `WIKI_SYNTH_MAX_OBJECTS`.
4. Resolved at call time (not cached at import).

**Sensible default — reasoning:**
- `semantic_search_core` returns up to 10 seeds (limit=10).
- Each seed can have multiple relation properties, each with multiple object IDs.
- A typical wiki entity may have 3-10 `wiki_relations` entries; a concept 2-6 `wiki_related`.
- At 10 seeds × avg 4 relations each = ~40 raw neighbour IDs before dedup.
- Each neighbour = 1 `get_object` call (confirmed: no enum_map primary path).
- The #287 lesson: Anytype SEARCH does not hydrate relations; each neighbour requires a real HTTP round-trip.
- `WIKI_SYNTH_MAX_OBJECTS` defaults to 24 (config.py:47), which already bounds the synthesis context. A neighbour cap significantly above 24 provides no synthesis benefit (trimmed before synthesis anyway).
- **Recommended default: 32.** Rationale: covers 10 seeds × 3-4 neighbours each; aligns with `WIKI_SYNTH_MAX_OBJECTS=24` context ceiling (8 headroom for cap→trim interaction); low enough to bound latency on a small-device Anytype install; high enough to not undershoot on a well-linked wiki.
- Alternative: 20 (tighter, ~2 neighbours/seed average) or 48 (looser). 32 is the middle ground.

---

## Q7 — Logging and Measurability

**Logger** (query.py:47): `logger = logging.getLogger(__name__)` — module-level, standard Python logging. Level controlled by `config.log_level()` reading `WIKI_LOG_LEVEL`.

**Existing log signals:**

| Signal | Level | Location | Trigger |
|--------|-------|----------|---------|
| `slow_synthesis` | WARNING | query.py:158-165 (`_maybe_log_slow_synthesis`) | synthesis elapsed > 60s |
| `wiki_query error [category]: …` | WARNING | query.py:641-647 (`_log_error`) | `error_category` set |
| `filterexpression_fallback: …` | WARNING | query.py:427-433 | pre-filter count > 500 |

**Warnings in result dict** (NOT logger): `neighbor_fetch_failed: {oid}` (query.py:517, 533), `synthesis_context_trimmed: {N} objects dropped` (query.py:730), `synthesis_object_truncated: {title}` (query.py:302), `cited_object_gone: {oid}` (query.py:814).

**No existing per-run counter** for neighbour fetch calls.

**Recommended surfacing for AC#5 ("added get_object calls logged/measurable"):**

Option A — `logger.debug` line in the neighbour-fetch loop (counts calls without bloating result). Clean, low-noise. Not visible in result dict.

Option B — add `neighbour_fetch_count: N` to `result["warnings"]` (or a separate result key) so the operator can see it without log access. Consistent with the existing `synthesis_context_trimmed` warning pattern.

Option C — emit a WARNING when `len(neighbor_ids) > cap` (cap applied): `"neighbor_fan_out_capped: {original} → {capped}"` in `result["warnings"]`. This surfaces the cap-trigger event, not the count. Most actionable for operators.

**Recommendation:** Option C (cap-trigger warning in `result["warnings"]`) plus a `logger.debug` for the fetch count. The warning is machine-readable, consistent with existing trim warnings, and requires no new result fields. The debug log satisfies "measurable" for operators running with `WIKI_LOG_LEVEL=debug`.

---

## Alternatives Considered

### Cross-cutting decision 1: File-back coupling for neighbour citations

| Option | Mechanism | Pros | Cons |
|--------|-----------|------|------|
| (a) Cite neighbours in result, seed-only in file-back | Pass separate `filed_sources` (candidates only) to `_maybe_file_back`; result's `sources_consulted` carries all. Requires signature change. | Preserves #285 `wiki_drew_from` semantics exactly; file-back min-sources count unchanged | Adds a parameter; two lists in flight; spec must document the split |
| (b) Full provenance: neighbours enter `wiki_drew_from` (recommended by scope brief as option to avoid unless research shows otherwise) | No signature change; neighbours in `sources_consulted` flow through unchanged | Simplest code delta; `wiki_drew_from` gives richer provenance | Min-sources gate counts neighbours (easier to trigger file-back); each surviving neighbour adds 1 `_refetch_for_writeback` GET at write time |

**Research verdict:** Option (a) is architecturally cleaner and keeps #285 invariants intact. Option (b) is simpler code. The scope brief recommends (a) unless research shows otherwise. Research shows (b) adds ~N extra GETs at write time (N = surviving neighbours in `sources_consulted`), which is a real but bounded cost. Both options are feasible. No blocker either way.

### Cross-cutting decision 2: `wiki_subjects` retention

| Option | Types affected | Graph semantics | Risk |
|--------|---------------|-----------------|------|
| Drop `wiki_subjects` (scope-4 keys: `wiki_relations`, `wiki_related`, `wiki_sources`, `wiki_drew_from`) | Comparison objects lose neighbour traversal via subjects | Cleaner alignment with #324 spec intent; `wiki_subjects` links COMPARED subjects, not sources | Some Comparison-→Subject edges not traversed |
| Retain `wiki_subjects` (5 keys) | Comparison objects gain subject traversal | Richer context when querying about a comparison (subjects surface) | Extra fan-out; `wiki_subjects` not in the four-key spec; may traverse non-source objects |

**Research verdict:** `wiki_subjects` edges ARE semantically meaningful for retrieval (if a Comparison about A vs B is a seed, A and B are high-value context). However the scope brief explicitly names four keys and says "decide explicitly whether to retain". The schema shows `wiki_subjects` is `wiki_comparison`-only (types_schema.py:121), not a general relation. Retaining it is defensible but outside the named four. The spec must call this explicitly.

### Cross-cutting decision 3: Fan-out cap semantics

| Option | Semantics | Implementation |
|--------|-----------|----------------|
| Global cap (total neighbours across all seeds) | `neighbor_ids` list capped at N before fetch loop | Simple slice on `neighbor_ids`; deterministic if seeds processed in rank order |
| Per-seed cap (at most N neighbours per seed) | Cap applied inside the per-seed loop at query.py:520-522 | Requires inner counter; more complex; protects against one over-linked seed dominating |
| Both (per-seed inner cap + global outer cap) | Belt-and-suspenders | Most complex; two knobs; probably over-engineered for MVP |

**Research verdict:** Global cap (applied after `neighbor_ids` is fully assembled, before the fetch loop) is simplest and sufficient. Since `neighbor_ids` is already deduplicated against the candidate set (query.py:521), and assembled in seed-rank order, a global cap of N gives deterministic results ordered by seed rank then discovery order within seed. A per-seed cap adds complexity without significantly different outcomes at the default budget of 32. Recommend global cap.

---

## Summary Table: Spec Delta Inputs

| Question | Fact established | Spec implication |
|----------|-----------------|------------------|
| Q1 | `semantic_search_core` returns `object_id`, `score`, `type` (not `type_key`) in rank order | "seed rank" = position in returned list; use `r.get("type") or r.get("type_key","")` |
| Q2 | Seeds fetch via `get_object` (not enum_map primary); enum_map is fallback only | Fan-out cap bounds neighbours only; seeds already bounded at limit=10 |
| Q2 | `list_objects` does return full objects with properties (comment query.py:500) | enum_map fallback is viable for degraded-mode; not the primary hydration path |
| Q3 | Citation dict = `{title, type, object_id, deeplink}`; helpers `_short_type` + `_object_deeplink` are reusable | Cite neighbours identically; no new helpers needed |
| Q4 | `_maybe_file_back` iterates `sources_consulted` directly; min-sources gate counts all entries | Option (a) needs signature change; option (b) is free |
| Q4 | SF4 `_refetch_for_writeback` does fresh GET per cited entry (not cached) | Option (b) adds N extra GETs at write time per surviving neighbour |
| Q5 | Single-dispatcher pattern in test_query_fetch_paths.py; get_object wire = `GET .../objects/{id}?format=md` | New tests go in test_query_fetch_paths.py; dispatcher must handle `_is_object_request` vs `_is_list_request` |
| Q5 | `_obj_id_from_request` strips `?format=md` correctly | Can be reused as-is for new tests |
| Q6 | `_positive_int` rejects 0/negative → default; resolved per-call (not cached) | New knob: `DEFAULT_WIKI_QUERY_MAX_NEIGHBORS = 32`; `query_max_neighbors()` accessor |
| Q6 | `.env.example` style: commented-out line with `# KEY=default` + 1-line rationale | Add under `# --- v0.4.0 wiki_query …` block |
| Q7 | Logger is `logging.getLogger(__name__)`; existing signals are WARNING-level in logger OR strings in `result["warnings"]` | Use `result["warnings"]` for `neighbor_fan_out_capped` (cap trigger); use `logger.debug` for fetch count |

---

## Files Confirmed At Risk (verified)

- `src/anytype_llm_wiki/wiki/query.py` — `_RELATION_KEYS` (line 53), `_build_context` (line 690), `_maybe_file_back` (line 777), candidate/neighbour fetch loop (lines 512-535), sources_consulted assembly (lines 562-573)
- `src/anytype_llm_wiki/wiki/config.py` — add `DEFAULT_WIKI_QUERY_MAX_NEIGHBORS` constant and `query_max_neighbors()` accessor
- `tests/wiki/test_query_fetch_paths.py` — new fan-out-cap, neighbour-citation, hydration tests here
- `tests/wiki/test_query.py` — existing `sources_consulted` assertions may need updating if neighbour citation changes the list contents
- `.env.example` — new knob documentation under v0.4.0 block

---

## No Blockers Found

All proposed changes are mechanical deltas on top of the existing #285 scaffolding. No circular imports, no API contract changes, no schema version bump required (no new types or properties; `wiki_sources` already exists in types_schema.py). The `_positive_int` guard, `_fetch_cached` cache, and single-dispatcher test pattern are all directly reusable.
