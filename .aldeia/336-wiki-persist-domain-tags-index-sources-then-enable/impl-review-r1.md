# Implementation Review — #336 (Round 1)

**Date:** 2026-06-13 | **Branch:** aldeia/336-wiki-persist-domain-tags-index-sources-then-enable
**Reviewers:** security+correctness (sub-agent), DRY+simplification (sub-agent), spec-compliance+performance (sub-agent), lead inline checks
**Suite:** 697 passed, 29 skipped, 8 deselected, 2 xfailed, 1 xpassed (AC-V-WARN), **0 failures**. Baseline was 33 failed.

## Verdict: APPROVED WITH CONDITIONS

Production code in `src/` is fully spec-compliant. All ratified Decide decisions (OD-A forward-only, OD-B Option 2 default-exclude, OD-C SET) honored exactly. No CRITICAL/MAJOR findings from any lens. Two MINOR items (both test-only) are fixed by the lead inline (see Resolution).

## What was verified genuinely met (not just test-green)
- **OD-A forward-only:** no automated Anytype-property backfill code exists; only the required Qdrant re-embed migration (version bump) + release note.
- **OD-B Option 2:** `semantic_search` default-exclude guard in `server.py` (NOT core), gated `if types is None and not source_type` — correctly suppressed when a `source_type` filter is supplied (avoids inert filter); explicit `types=["wiki_source"]` passes through. `test_no_filter_regression` stays green. `wiki_query` unaffected.
- **OD-C SET:** `remember.py:_apply_batch` appends `wiki_domain_tags` to `patch_props` with no GET-then-merge (pre-existing tag ids replaced).
- **§9-vs-AC-T1-ST-NOOP conflict:** worker's resolution (do NOT apply/thread `source_type` in `wiki_query`; `domain_tags` applied in both tiers) is the only defensible reading and is consistent across both tiers. Confirmed correct by spec-compliance reviewer.
- **Write side:** ingest `domain_tag_prop` resolved once/run, appended per-iteration for both create+update; `_create_source` stamps `wiki_source_type` on shared props (reuse + create); remember stub excerpt for note-less agent sources; chunker omit-when-absent mirrored in `_chunk_to_payload`.
- **#323 data-integrity invariant NOT regressed:** `_payload_schema_version` advance still gated on `if space_id is None:`.
- **getattr guard** on `create_payload_index` retained; two new KEYWORD indexes added.
- **AC-V-WARN** implemented (XPASS); taxonomy fetch gated solely on the filtered path — no hot-path latency.
- **Perf:** `_resolve_multi_select_tags` is one `list_properties`+`list_tags` pair per run/batch (not per-candidate); no reembed hot-path change.

## Findings

### MINOR-1 (spec-compliance) — post-test addendum item 3 unmet [FIXED INLINE]
`tests/test_chunker.py` `test_wiki_property_heading_maps_all_eight_keys` still names/says "eight" while iterating the 9-key set. Authoritative addendum item 3 requires the cosmetic rename. **Resolution:** lead renamed to `_nine_keys` + updated docstring/assert message.

### MINOR-2 (spec-compliance) — OD-B sub-decision not test-pinned [FIXED INLINE]
The "`source_type` supplied ⇒ default-exclude must NOT fire" branch is code-correct but had no regression test; a future refactor could silently re-introduce an inert filter. **Resolution:** lead added a test asserting `semantic_search(source_type=["document"])` with no `types` passes `types=None` (no non-source default) to the core, so the source_type filter is not starved.

### MINOR (security) — accepted, no action
- Whitespace-only filter values pass structural validation but match nothing — correct fail-safe behavior, not a defect.
- Source `name` field not control-char-stripped — pre-existing main behavior, off the embed path, out of scope.

### MINOR (DRY) — deferred, no action
- Resolver-family ~8-line skeleton repeats across 3 resolvers, and the select/multi_select name-extraction repeats across chunker + query predicate. Both follow the established #323 `_passes_date_filter` / `_resolve_wiki_action_tag` precedent (consistency wins); cross-module coupling would be worse. Optional future helper if a 4th resolver/reader appears.

## Lead inline checks (review-impl-reference.md Pass 1 + 2)
- stdout/stderr discipline, degrade-not-abort, input validation against allowlists: PASS.
- Every §12 acceptance criterion addressed; CLAUDE.md/technical.md/README/CHANGELOG updated: PASS (docs verified in PR-prep).
- No skipped tests beyond pre-existing; no dead code (unused `_passes_source_type_filter` is intentional, documented, unit-pinned).
