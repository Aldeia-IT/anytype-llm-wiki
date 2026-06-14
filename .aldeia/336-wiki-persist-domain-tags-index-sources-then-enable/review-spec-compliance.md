# Spec-Compliance + Performance Review — aldeia-box#336

**Reviewer lens:** spec-compliance + performance (most important lens)
**Branch:** `aldeia/336-wiki-persist-domain-tags-index-sources-then-enable`
**Diff reviewed:** `git diff main...HEAD -- src/ docs/` (merge-base = `6281f5e`/#323)
**Test suite:** `uv run pytest -m "not live" -q` → **697 passed, 29 skipped, 8 deselected, 2 xfailed, 1 xpassed (AC-V-WARN), 0 failures**.

## Verdict: CLEAN on all RATIFIED decisions and §12 ACs. Two MINOR items (one unmet authoritative addendum item; one test-coverage gap). No CRITICAL/MAJOR findings.

---

## Note on the three-dot diff

The `main...HEAD` diff includes `_reindex_lock` + atomic `_save_state` in `indexer.py`. These are **NOT #336 work** — they come from #342 (PR #48, commit `c849fae`), which post-dates the `...` merge-base (#323). They surface only because the three-dot base is the older #323 commit. Not in scope for this review; flagged so the next reader does not attribute them to #336.

---

## RATIFIED decisions — verified honored exactly

### OD-A forward-only — HONORED
No automated Anytype-property backfill exists. The only "backfill" references in `indexer.py:263-335` are the **Qdrant re-embed** migration (OD-A operation #1, expected/required), not a property write. `grep -niE "backfill|retroactive" src/` confirms no `update_object`/`create_object` backfill path. Forward-only is also documented in `technical.md` and `CHANGELOG.md` (release note reaches operators — post-test addendum item 6 satisfied).

### OD-B Option 2 — HONORED (guard in server.py, not core)
- `server.py:_SEMANTIC_SEARCH_DEFAULT_TYPES` + `effective_types = list(...)` only `if types is None and not source_type`. Guard is in `server.py:semantic_search`, NOT `semantic_search_core` (`test_no_filter_regression` stays green — verified).
- Explicit `types=["wiki_source"]` passes through unchanged (pinned by `test_semantic_search_default_excludes_wiki_source` (b)).
- **Critical sub-decision (source_type given ⇒ default-exclude must NOT fire):** the `and not source_type` clause is present and correct — a `source_type` filter targets `wiki_source` chunks, and the guard correctly does not strip them. See MINOR-2 below (code-correct but not test-pinned).
- `wiki_query` unaffected (`_WIKI_TYPE_KEYS` excludes `wiki_source`; no change).

### OD-C SET (replace) — HONORED
`remember.py:_apply_batch` appends `{"key":"wiki_domain_tags","multi_select":domain_tag_ids}` directly to `patch_props` (line ~652) — **no GET-then-merge**, no read of the existing value. A pre-existing tag id is replaced wholesale on update. Comment explicitly states "SET (replace) — no merge with the existing value (OD-C)". Lossy caveat documented in CHANGELOG. Confirmed REPLACE semantics.

---

## Critical compliance checks

### §9-vs-AC-T1-ST-NOOP conflict (worker-flagged) — RESOLVED CORRECTLY
The worker resolved the spec §9 (apply `_passes_source_type_filter` in Tier-1 + thread to Tier-2) vs D10/§6.2/AC-T1-ST-NOOP (source_type is a permanent no-op) conflict by NOT applying/threading `source_type` in `wiki_query`. Verified consistent across BOTH tiers:
- **Tier-1** (`query.py:700-714`): only `_passes_type_filter` and (conditionally) `_passes_domain_tags_filter` applied. `_passes_source_type_filter` is deliberately NOT applied (explicit comment). `domain_tags` IS applied.
- **Tier-2** (`query.py:649-669`): `source_type` is intentionally NOT threaded to `semantic_search_core`; `domain_tags` IS threaded conditionally.
- **No path empties wiki_query results from source_type.** Both `_passes_source_type_filter` and `_passes_domain_tags_filter` are implemented (for cross-tier/API completeness) and unit-pinned (AC-T1-ST, AC-T1-DT), but only `domain_tags` is wired into the live query path. This is the only defensible reading — applying the source_type predicate to entities/concepts (which lack `wiki_source_type`) would zero out every result, directly violating AC-T1-ST-NOOP. Resolution is correct.

`domain_tags` confirmed applied in BOTH Tier-1 and Tier-2 of wiki_query.

### Per-candidate props append in ingest `_run_ingest` — CORRECT
`domain_tag_prop` resolved ONCE before the candidate loop (`ingest.py:871-879`). `props` is rebuilt each iteration (`:891`/`:895`); `domain_tag_prop` is appended at `:899-900` AFTER props is built and BEFORE both the update branch (`:908`) and the create branch (`:940`). It is not lost. Append guarded by `if domain_tag_prop is not None`. Matches D2/SF3 exactly.

### `_create_source` shared props — CORRECT
`wiki_source_type="document"` resolved and appended to the SHARED `props` (`ingest.py:1033-1039`) BEFORE both branches: the dedup-reuse `update_object` (`:1051`) AND the `create_object` (`:1059`). Both paths stamp it. Matches D4/SF4; pinned by AC-S-REUSE.

### chunker omit-when-absent — CORRECT
`chunker.py`: `source_type` injected only `if source_type is not None`; `domain_tags` only `if domain_tags` (truthy). Absent → key absent from chunk dict (not null). `_chunk_to_payload` mirrors with `if "source_type" in chunk` / `if "domain_tags" in chunk`. Matches D5/D6; pinned by AC-S4/AC-PAYLOAD.

### getattr guard + two new KEYWORD indexes — CORRECT
`indexer.py:58 create_index = getattr(client, "create_payload_index", None)` retained. Two new entries added: `("source_type", KEYWORD)`, `("domain_tags", KEYWORD)`. Matches D7; pinned by AC-IDX (`test_reindex_creates_payload_indexes`).

### AC-V-WARN — IMPLEMENTED, latency constraint HONORED
The taxonomy fetch (`_ingest._domain_taxonomy` for domain_tags; `_WIKI_SOURCE_TYPE_TAGS` for source_type) runs ONLY inside `if domain_tags_filter:` / `if source_type_filter:` blocks (`query.py:593-616`) — i.e. solely on the opt-in filtered path. **No hot-path (unfiltered query) latency cost.** This matches the §13/D11 deferral constraint: the constraint was "defer IF it adds material latency"; because it adds latency only on already-opt-in filtered calls (not the common path), implementing it is consistent with the constraint. Called via module reference (`_ingest._domain_taxonomy`) so the test monkeypatch resolves. XPASS confirmed. AC-V-ZERO (mandatory) independently satisfied (the filter still builds and returns zero on unknown values).

### Addendum post-test item 1 (FakeWikiClient.update_object signature) — SATISFIED
Real `WikiClient.update_object(self, space_id, object_id, patch)` (`wiki/wiki_client.py:78`). Reuse-path test fake (`test_ingest.py:3182`) declares `update_object(self, space_id, object_id, data)` — 4th param named `data` not `patch`. `_create_source` calls it **positionally** (`client.update_object(space_id, sid, {...})`), so the 3 positional args line up and the guard remains meaningful. No mismatch that neuters the guard; no change needed. Worker's analysis verified correct.

---

## Performance — all confirmed

- **`_resolve_multi_select_tags` call cost:** one `list_properties` + `list_tags` pair per ingest run (`_run_ingest` resolves once before the candidate loop, `:871`) and per remember batch (`_apply_batch` resolves once, `:512`). NOT per-candidate. Matches §13.
- **AC-V-WARN taxonomy fetch:** only on filtered `wiki_query` calls (gated by `if domain_tags_filter`/`if source_type_filter`). No unfiltered hot-path cost.
- **Reembed hot path:** indexes created only in `_ensure_payload_indexes` (reindex path). `_chunk_to_payload` gains two `if key in chunk` checks — negligible, no new I/O. No change to the per-object `reembed_object` hot path.

---

## §12 Acceptance Criteria — genuinely met vs test-covered

All §12 ACs are both test-covered AND genuinely met by inspection of the implementation seams:

| AC | Genuinely met (code-verified) |
|----|-------------------------------|
| AC-P1/P2 (ingest domain_tags create+update) | YES — `:899-900` appends to per-iteration props before both branches |
| AC-P3 (remember meta threading) | YES — `meta["domain_tags"] = domain_tags or []` at `remember.py:323` (real `worklog.begin` seam) |
| AC-P4/P5 (remember domain_tags create+update) | YES — appended to both `patch_props` and `create_props` |
| AC-S1 (wiki_source chunks via wiki_excerpt) | YES — `wiki_excerpt` in allowlist; empty-markdown source → `_chunk_properties` path produces chunk |
| AC-S2/S3 (payload carries source_type/domain_tags) | YES — chunker extracts `.name` inline, injects per-chunk |
| AC-S4 (absent → key absent) | YES — `is not None`/truthy gating, mirrored in `_chunk_to_payload` |
| AC-F-ST/F-DT/F-COMB (MatchAny clauses) | YES — two `must.append(FieldCondition(... MatchAny ...))` truthy-gated |
| AC-F-REG (no-filter → query_filter=None) | YES — `Filter(must=must) if must else None` unchanged; guard in server not core |
| AC-V-SS (semantic_search raises ValueError) | YES — structural validation raises with offending param name |
| AC-V-WQ (wiki_query returns config_error dict) | YES — returns dict before client construction, never raises |
| AC-S-REUSE (source_type on reuse-update) | YES — shared props append covers reuse-update branch |
| AC-S-AGENT (stub excerpt → chunkable) | YES — `excerpt = name` when source_note empty (D4b) |
| AC-PAYLOAD (copy + omit) | YES — `_chunk_to_payload` |
| AC-RESOLVER (success/skip/degraded) | YES — `_resolve_multi_select_tags` returns `([], True)` on HTTPError/Exception, silently skips unknown names |
| AC-V-ZERO (unknown value → zero, no raise) | YES — clause still builds; Qdrant returns empty |
| AC-V-WARN (schema_warnings) | YES — XPASS; gated on filtered path |
| AC-T1-DT / AC-T1-ST (predicates) | YES — both predicates implemented & unit-pinned |
| AC-T1-ST-NOOP (source_type no-op) | YES — not applied/threaded in either tier |
| AC-IDX (two new indexes asserted) | YES |
| Chunker contract inversions (count 8→9, exact-set, `in_allowlist`, `excerpt_included`) | YES |
| PAYLOAD_SCHEMA_VERSION == 3 | YES — `config.py` + `test_payload_schema_version_is_3` guard |

---

## Findings

### MINOR-1 — Post-test addendum item 3 NOT done (stale test name)
`tests/test_chunker.py:197` `test_wiki_property_heading_maps_all_eight_keys` (docstring "all 8 allowlist keys") now iterates the 9-entry `WIKI_TEXT_PROPERTY_KEYS`. The post-test council addendum item 3 ([QA/CTO]) authoritatively required renaming it to reflect nine keys ("cosmetic, opportunistic — no logic change"). The test passes (it iterates the live set), but the authoritative addendum item is unmet.
**Fix:** rename to `test_wiki_property_heading_maps_all_nine_keys` and update the docstring "8"→"9". (Test file, outside the `src/ docs/` diff scope, but explicitly listed as a compliance check in the brief.)

### MINOR-2 — OD-B "source_type given ⇒ default-exclude must NOT fire" is code-correct but not test-pinned
The trickiest OD-B sub-decision (the brief's "when `source_type` is given the default-exclude must NOT fire (else inert filter)") is correctly implemented (`server.py`: `if types is None and not source_type`), but no test asserts that `semantic_search(query=..., source_type=["document"])` reaches core WITHOUT the non-source default-types being applied (which would make the source_type filter inert). `test_semantic_search_default_excludes_wiki_source` covers only (a) bare default and (b) explicit `types=["wiki_source"]`. A future refactor could drop `and not source_type` and silently re-introduce an inert source_type filter on `semantic_search` without any red.
**Fix (non-blocking, recommended):** add a case asserting `semantic_search(query="t", source_type=["document"])` passes `types=None` (or a list containing `wiki_source`) to core — i.e. the default-exclude did not fire. Pure test addition.

---

## Summary
The implementation honors OD-A (forward-only, no property backfill), OD-B Option 2 (guard in server.py, default-exclude correctly suppressed when `source_type` is supplied, `wiki_query` unaffected), and OD-C SET (replace, no merge). The §9-vs-NOOP conflict is resolved correctly and consistently across both tiers — `domain_tags` live in both, `source_type` a clean no-op in both. All per-candidate/shared-props append sites, the chunker omit-when-absent, the getattr guard, the two new KEYWORD indexes, and the latency-gated AC-V-WARN are all correct. Performance constraints met (resolver pair per run/batch, taxonomy fetch only on filtered path, no reembed hot-path change). All §12 ACs genuinely met, not merely test-green. Two MINOR items: one unmet cosmetic addendum item (test rename) and one missing test for the trickiest OD-B sub-decision (code is correct).
