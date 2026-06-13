# Implementation Review — #323 (type + date metadata filters)

## Round 2 verdict (post-fix) — APPROVED

**Date:** 2026-06-13 | **Fix commit:** `d058fc3`

C1 resolved: `reindex` now gates the global `_payload_schema_version` stamp behind `if space_id is None`
(`indexer.py`), with an explanatory comment. The `force_full` backfill is unchanged, so a scoped reindex
still re-embeds its named space; only the global marker advance is restricted to full-corpus runs. A
genuine CI-runnable regression test (`test_scoped_reindex_does_not_stamp_schema_marker`, tests/test_indexer.py)
asserts both behaviors. Spec §3 D3 carries a one-line clarification.

Lead-verified independently: full suite **641 passed, 0 failed, 37 skipped, 2 xfailed**; fixer added test
lines only (no existing test modified); fix diff touches only `indexer.py`, `tests/test_indexer.py`, `spec.md`.

No BLOCKING or SHOULD-FIX findings remain. The four MINOR items (M1, M2, Q1, Q2) are advisory and
intentionally left per their rationale below (M1's probe is spec-pinned §9.1; Q2 centralization is a #336
item per addendum CSO-6). **Cleared for PR.**

---

## Round 1 verdict — NEEDS CHANGES (1 CRITICAL data-integrity finding; rest clean)
**Reviewers:** security/correctness reviewer, code-quality/DRY/spec-compliance reviewer, + lead inline checks
**Diff under review:** `cb9ee05..bad3f33..c3ab88f` (src + docs)
**Test state:** 640 passed, 0 failed, 37 skipped, 2 xfailed (independently verified by lead). No committed test modified.

---

## BLOCKING

### C1 — Single-space `reindex` stamps the schema-version marker globally, permanently stranding other spaces (data-integrity)

**Source:** security reviewer; lead-verified.

`indexer.reindex` stamps `state["_payload_schema_version"] = config.PAYLOAD_SCHEMA_VERSION`
unconditionally at the end of every run, including scoped `reindex(space_id="sp-X")` calls.

`wiki/ingest.py:979 _maybe_reindex` calls `reindex_anytype(space_id)` (→ `reindex(space_id=...)`)
**after every `wiki_ingest` / `wiki_remember`** by default (`WIKI_AUTO_REINDEX=true`). Verified call
chain. `remember.py` reuses the same seam.

**Failure scenario (default config, post-upgrade, stored=1 / code=2):** the first ingest/remember
fires a single-space reindex → `force_full=True` backfills only that one space's chunks → then stamps
`_payload_schema_version = 2` globally. Every subsequent full `reindex()` sees `force_full=False` and
skips all unchanged objects in the *other* spaces forever. Those spaces keep the old 6-field payload
and the `date` filter silently under-returns against them indefinitely — exactly the permanent-skip
outcome spec §3 D3 is meant to prevent.

This is a faithful implementation of the spec §3 D3 / §15 pseudocode (which stamps unconditionally and
implicitly assumes the migration is an *unscoped* `reindex`); the spec pseudocode itself did not
contemplate `reindex` being invoked with a `space_id`. The latent gap is in the spec; the fix is a
correctness improvement beyond the literal spec text.

**Fix:** only advance the global marker after a full-corpus pass:
```python
if space_id is None:
    state["_payload_schema_version"] = config.PAYLOAD_SCHEMA_VERSION
```
A scoped backfill still re-embeds the named space (force_full applies regardless of scope); only the
global marker advance is gated until an unscoped `reindex()` (manual or launchd cron) completes.

**Test impact:** the AC-F11 migration tests use unscoped `reindex()` → stay green. The live-gated
`test_reindex_specific_space` asserts only `stats["spaces"] == 1` → unaffected. Add a NEW
CI-runnable regression test (does not touch existing tests): a scoped `reindex(space_id=...)` with
stored=1/code=2 must NOT stamp the marker.

**Also (cosmetic, bundle with fix):** add a one-line note to spec §3 D3 that the marker is stamped only
after a full (unscoped) reindex, so an auto-fired single-space reindex cannot prematurely advance it.

---

## MINOR (advisory — no fix required this round)

- **M1 (security reviewer):** the MCP-boundary date probe uses `DatetimeRange(gte=val)` (pydantic)
  while Tier-1 reparses with `_parse_iso` (`datetime.fromisoformat`). They accept slightly different
  grammars for exotic inputs (e.g. `"2026"` → pydantic reads a Unix timestamp, `_parse_iso` returns
  None). Both effectively no-op for such inputs; full ISO-8601 (the documented usage) is consistent.
  Spec §9.1 explicitly pins the `DatetimeRange` probe — do NOT deviate. Documented only.
- **M2 (security reviewer):** Tier-1 applies `_passes_type_filter` over an already-type-narrowed list
  (no-op when `types` omitted). Harmless; kept for cross-tier symmetry/clarity.
- **Q1 (quality reviewer):** `_WIKI_TYPE_KEYS_SET` rebuilt per call — could be module-level. Trivial.
- **Q2 (quality reviewer):** date-validation block duplicated in server.py + query.py — *justified* by
  divergent error contracts (raise vs error-dict); addendum CSO-6 tracks centralizing as a #336
  longer-term item, not #323.

---

## Confirmed correct (explicitly checked by reviewers + lead)

- Validation short-circuits BEFORE `AnytypeReadClient()`/`WikiClient()` construction (CTO-ADV1). F6b/F6c
  return `config_error`; `semantic_search` raises `ValueError`. Malformed dates rejected, not ignored.
- No-filter path byte-identical (`search_filter=None`); empty `types=[]` falsy → no clause.
- `DatetimeRange` (not `Range`) used; nested-`should` type filter shape preserved (not `MatchAny`).
- `_chunk_to_payload` genuinely shared by `reindex` + `reembed_object`; date written only when present.
- `_payload_schema_version` key never mistaken for a space id (loop iterates `list_spaces()`).
- No new network egress; no unsafe interpolation; local-first posture preserved.
- No `source_type`/`domain_tags` leakage anywhere; no dead code; all new imports used.
- All addendum impl ACs shipped (product.md, CHANGELOG release note, README params+Roadmap,
  technical.md payload, spec #336 citations, CTO-10 path fix, CSO-6 §14 cross-ref, Infra-7/9 deploy note).
