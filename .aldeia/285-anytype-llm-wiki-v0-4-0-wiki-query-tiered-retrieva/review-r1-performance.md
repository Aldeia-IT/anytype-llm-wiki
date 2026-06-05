# R1 Performance Review — wiki_query tiered retrieval (v0.4.0)

**Verdict: APPROVED WITH CONDITIONS**

Scope: `git diff 6975fff HEAD`, primary file `src/anytype_llm_wiki/wiki/query.py`.
Box: Mac Mini M4 / 32GB; Qdrant + Ollama; local-first. Scale assumption:
hundreds-to-low-thousands of objects on one box.

Counts: CRITICAL 0 / MAJOR 0 / MINOR 2.

---

## Checklist results

### 1-hop neighborhood cache — PASS
`_fetch_cached` (query.py:712) checks the per-run `cache` dict first and stores on
success (query.py:733), so any given `object_id` triggers at most one `get_object`
per run. Candidate loop (query.py:578) and neighbor loop (query.py:593) share the
same `cache`. Neighbor discovery de-dupes against both the candidate set and
already-queued neighbor ids (query.py:587), and the neighbor fetch loop skips ids
already fetched as candidates (query.py:594). No N+1 across candidate/neighbor sets.

### Synthesis input budget (B5) — PASS
`_build_context` (query.py:752) applies the object cap first (`synth_max_objects`,
default 24 — query.py:774), then the total-token budget (`synth_max_input_tokens`,
default 8192 — query.py:787), trimming the tail (neighbors first because candidates
are sorted to the front by score at query.py:769, then weakest candidates), then
head-truncates each surviving object (`synth_max_object_tokens`, default 1024 —
query.py:795/328). All applied BEFORE `synthesize` (query.py:625). Bounds match the
spec Resource Impact section.

"Could a large neighborhood blow memory before the trim?" — No, realistically.
Candidates + neighbors are fully fetched into the `candidates`/`neighbors` lists
before `_build_context` trims. But (a) Tier 2 candidates are capped at the Qdrant
`limit=10` (query.py:513) so the neighborhood is small; (b) Tier 1 fetches all wiki
objects, but those objects are ALREADY resident in `all_objects` from the single
enumeration (query.py:439) — the cache fallback even reuses that snapshot — so the
pre-trim fetch does not raise peak memory beyond the enumeration that already
happened. At hundreds-to-low-thousands of objects this is well inside 32GB. No
finding.

### Enumeration — PASS (single full enumeration)
Exactly one paginated `list_objects` (query.py:439). The schema-version pre-check
(`_schema_version_from_objects`, query.py:281) derives the live version from that
already-fetched list rather than re-enumerating. `enum_map` (query.py:569) is built
from the same snapshot. Tier 2 adds one Qdrant query + O(results) `get_object`
calls; it does not re-enumerate. No avoidable second full enumeration.

### Synthesis timeout / slow-synthesis signal — PASS
`_call_ollama_synthesis` uses a finite `httpx.Timeout(connect=5, read=600s,
write=10, pool=5)` (query.py:119). `_maybe_log_slow_synthesis` (query.py:176) warns
when a successful call exceeds `_SLOW_SYNTH_SECONDS = 60.0` (query.py:55). Both
present.

### Quadratic loops / repeated parse / unbounded accumulation — PASS
- `_build_context` token-budget `while` loop (query.py:787) re-sums `_est_tokens`
  over `ordered` each pop, but `ordered` is already capped to `max_objects` (24) at
  query.py:774, so it is at most ~24 × 24 trivial iterations. Not quadratic at scale.
- `contributing` filter (query.py:802) is O(candidates) over a bounded surviving set.
- Neighbor de-dupe membership scan (query.py:587) is over a small 1-hop list.
None of these are unbounded over the full object set.

---

## MINOR findings

### MINOR-1 — Cache is not seeded from `enum_map`; candidates/neighbors re-fetched via `get_object`
- **File:** `src/anytype_llm_wiki/wiki/query.py:569-601`, `_fetch_cached:712`
- **Category:** Performance / Optimization
- **Description:** The full object list (including `properties`) is already in memory
  from the single enumeration (`all_objects` → `enum_map`, query.py:569). However,
  `_fetch_cached` only consults `enum_map` as a *fallback* on a `KeyError`
  (list-envelope) path (query.py:727); on the normal path it issues a live
  `get_object` for every candidate and every neighbor. In Tier 1 on a ~200-object
  wiki this is up to ~200 `get_object` round-trips for data already resident in
  memory. This is explicitly acknowledged and accepted in the spec Resource Impact
  section ("up to ~200 get_object calls (mitigated by the 1-hop cache)"), so it is a
  documented design choice, not a regression. Flagging only as an available
  optimization: seeding `cache` from `enum_map` up front (or short-circuiting to the
  enum snapshot before the network call) would eliminate those round-trips. Note one
  intentional difference: `_refetch_for_writeback` (query.py:818) deliberately does a
  *fresh* write-time read and must NOT be cache-seeded (SF4 freshness) — only the
  read-side candidate/neighbor fetch is a seeding candidate.
- **Fix (optional):** Before the candidate loop, pre-populate
  `cache.update({oid: o for oid, o in enum_map.items()})`, or have `_fetch_cached`
  return `enum_map[object_id]` when present before attempting `get_object`. Keeps the
  freshness-sensitive write-back path on its separate `_refetch_for_writeback`.

### MINOR-2 — `pre_filter_count > 500` warning threshold is a soft scale signal only
- **File:** `src/anytype_llm_wiki/wiki/query.py:489-496`
- **Category:** Scalability (informational)
- **Description:** When enumeration returns >500 rows a `filterexpression_fallback`
  warning is logged, but the pipeline still client-side filters and proceeds to fetch
  candidates/neighbors. This is correct for the stated scale (low-thousands) and the
  B5 budget caps the synthesis cost regardless of object count. No action needed at
  current scale; recorded so the growth ceiling is visible. The dominant cost at high
  object counts is the Tier-1 per-candidate `get_object` fan-out (see MINOR-1), not
  the enumeration itself.

---

## Performance assessment

| Category | Status | Notes |
|----------|--------|-------|
| Single enumeration (no double full scan) | Pass | One `list_objects`; schema check reuses snapshot |
| 1-hop cache / N+1 avoidance | Pass | One `get_object` per unique id; candidate+neighbor share cache |
| Synthesis input budget (B5) | Pass | object cap → token budget → head-trunc, before model call |
| Pre-trim memory bound | Pass | bounded by enumeration already in memory; 32GB-safe at scale |
| Synthesis timeout finite | Pass | finite httpx.Timeout (read 600s) |
| Slow-synthesis signal >60s | Pass | `_maybe_log_slow_synthesis` |
| Quadratic / unbounded loops | Pass | budget loop bounded to ≤ max_objects |
| Cache seeding from enum_map | Minor | re-fetches data already in memory (spec-accepted) |
