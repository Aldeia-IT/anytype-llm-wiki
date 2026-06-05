# Implementation Review — wiki_query v0.4.0 (Round 1)

**Verdict: APPROVED WITH CONDITIONS**

**Date:** 2026-06-05
**Ticket:** #285 · **Branch:** `aldeia/285-anytype-llm-wiki-v0-4-0-wiki-query-tiered-retrieva`
**Scope:** `git diff 6975fff HEAD` (impl commits `6d6ddc1`, `d9c8960`, `d97fefc`)
**Reviewers:** 5 parallel specialists (security, completeness/correctness, DRY, simplification, performance) + lead inline checks.

## Summary

0 CRITICAL · 1 MAJOR · 11 MINOR across all specialists. No security or correctness defect. All 20 ACs satisfied by the code (not just by passing tests — verified by code-path reading). The council's two highest-risk surfaces are confirmed genuinely honored:

- **N1 relation integrity (AC#16):** `_write_bidirectional_relations` is never imported/called by `query.py`. Reciprocal back-references use explicit read-merge-write via a FRESH write-time read (`_refetch_for_writeback`, not the per-run cache) + `prior ∪ [query_id]` union. Forward `wiki_drew_from` is the only plain overwrite and targets cached fetched `object_id`s, never LLM titles. The replacement N1 test exercises a non-empty prior set (`["e1","e2"]`) distinct from the enumeration snapshot, so the guard is non-vacuous (addendum item-2's binding condition is honored for the mocked shapes; live-shape pin remains a release gate).
- **Decision 2 multi-type filter:** `indexer.semantic_search_core` uses nested `Filter(should=[...])` inside `must` (no `min_should`); `embed_query` imported into `indexer.py`; client built via `_qdrant()`; single-type backward-compat preserved.

Test state independently verified by lead: `test_query.py` + `test_query_fetch_paths.py` = 60 passed / 5 skipped; full non-live suite 514 passed / 0 failed / no regressions. The 5 skipped `test_query.py` tests are genuinely unsatisfiable under respx 0.23.1 (no-arg catch-all registered before the URL-specific route wins every match — empirically confirmed by the lead) and are re-covered with equivalent-or-stronger assertions in `test_query_fetch_paths.py`. This is a justified, well-documented test-infrastructure fix, not a weakening of the contract.

---

## Findings

### MAJOR (Should Fix)

**MAJOR-1 — Synthesis-error return violates the QueryResult contract.** `query.py:626/639/642-654` (Spec Compliance).
On the synthesis-error return path, `result["answer"]` is left as the `[CONFIG ERROR]`/`[API ERROR]` sentinel and `result["sources_consulted"]` stays populated. spec.md:240 mandates: "On any error return, `answer` is `""`, `sources_consulted` is `[]`, `filed_back` is `false`." The error sentinel belongs in `error`/`error_category` (already set). Passes the council-approved tests (they assert only `error`/`error_category`/`filed_back`), but diverges from the documented machine contract.
**Fix:** in the synth-error block, set `result["answer"] = ""` and `result["sources_consulted"] = []` (keep `error`/`error_category`/`status`/`filed_back`). Lead verified no test asserts non-empty `answer`/`sources_consulted` on this path — safe.

### MINOR (Consider Fixing — fix unless noted DEFER)

**MINOR-1 — SF8 literal gap: file-back warnings interpolate raw `{exc}`.** `query.py:900/918/942` (Security).
Three file-back warning strings (`file_back_failed`, `drew_from_write_failed`, `reciprocal_write_failed`) interpolate the exception without `scrub_credentials()`. Exposure is low (Anytype creds are in headers, not URLs), but SF8 says "all warning strings." **Fix:** wrap each `{exc}` interpolation in `scrub_credentials(...)`.

**MINOR-2 — `_object_deeplink` duplicated.** `query.py:259-260` (DRY).
Local re-implementation of `bootstrap._object_deeplink` (bootstrap.py:83). The circular-import justification does not hold — `query.py` already imports `bootstrap as _bootstrap` and uses its symbols; bootstrap imports nothing from query. **Fix:** call `_bootstrap._object_deeplink`.

**MINOR-3 — `_schema_version_from_objects` near-verbatim copy.** `query.py:281-302` (DRY).
The N+1-avoidance rationale is legitimate (bootstrap's `_read_schema_version` calls `list_objects` internally; query already enumerated), but the marker-scanning body duplicates bootstrap's loop. **Fix:** extract a pure `_schema_version_from_objects(objects)` helper in `bootstrap.py`, have both `_read_schema_version` and `query.py` call it. Verify the bootstrap suite stays green after the refactor.

**MINOR-4 — Unreachable `count < threshold` guard.** `query.py:528-531` (Simplification).
Inside the Tier-2 Qdrant-down `except`, `count < threshold` is always False (the except only runs when `tier2`, and `tier2 = count >= threshold` is unmutated). **Fix:** collapse the except to its only reachable (error) arm; removes reader confusion about where the Tier-2→Tier-1 fallback lives.

**MINOR-5 — Hoist `from pathlib import Path`.** `query.py:208` (Simplification).
Function-local import in `_build_synthesis_prompt` with no cycle reason. **Fix:** hoist to module top. (Leave the `root_config` / `WIKI_TEXT_PROPERTY_KEYS` function-local imports — those are deliberate lazy-load/cycle avoidance.)

**MINOR-6 — Local `status` var duplicates `result["status"]`.** `query.py:502/604/666-672` (Simplification — OPTIONAL).
The local `status` is only ever set to "partial" and reconciled at the tail. Apply only if trivially safe while the file is already open; otherwise leave — no clobber risk today.

### DEFER (with rationale — no action this round)

- **Security MINOR (content control/bidi strip at query time).** `query.py:_truncate_object_content` re-policies object *names* but not fenced *content*. The spec's B4 decision is deliberately to FENCE content (under the DATA preamble), NOT to sanitize it — content-stripping risks corrupting legitimate wiki data and was not specified. The fence + preamble is the spec's chosen control. DEFER.
- **Security MINOR (literal `</context>` fence-forge).** Standard LLM-fence residual; mitigated by the preamble's explicit delimiter-injection instruction. Accepted by the security reviewer. No action.
- **Performance MINOR (seed per-run cache from `enum_map`).** Spec §Resource Impact explicitly accepts the O(N) `get_object` calls. Seeding the cache directly from enumeration summaries is risky: `list_objects` returns summary objects while `get_object(?format=md)` returns the full object — seeding could feed incomplete objects into synthesis. The current `enum_map`-as-fallback approach is correct. DEFER (would be a correctness risk, not just an optimization).
- **Performance MINOR (`>500` rows warning).** Informational soft scale signal; correct at current scale.

---

## Conditions to reach full APPROVED
Address MAJOR-1 (contract) + MINOR-1..5 (and MINOR-6 if trivial). Re-run `test_query.py` + `test_query_fetch_paths.py` + full non-live suite green. The DEFER items are recorded with rationale and require no change.
