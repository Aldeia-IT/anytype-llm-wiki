# Council Spec Review R1 — QA Director (#286 wiki_lint v0.5.0)

**Date:** 2026-06-05
**Reviewer:** QA Director (review council)
**Phase:** Spec (pre-implementation). Lens: AC↔test traceability, test satisfiability, coverage adequacy, regression risk.
**Spec:** `.aldeia/286-anytype-llm-wiki-v0-5-0-wiki-lint-structural-healt/spec.md`

---

## Verdict: SIGN OFF (no BLOCKING)

The R1 satisfiability defects (B1/B2) are genuinely resolved. The duplicate band is now the literal half-open `[0.70, 0.85)` backed by a real float knob — the unsatisfiable-test class (#285/#289 failure mode) is eliminated. All 15 ACs map to at least one named test; all 33 named tests map to an AC. No unsatisfiable test found. Two ADVISORY items (test-gap documentation), neither blocks advancing.

---

## AC↔Test Traceability Map (independently built)

| AC | Subject | Mapped test(s) | Status |
|----|---------|----------------|--------|
| AC1 | Backlinks primary, traversal fallback | `test_backlinks_primary_no_traversal`, `test_backlinks_malformed_falls_back`, `test_asymmetric_relation_check_fires` | MAPPED |
| AC2 | `stale_needs_review` replaces `stale_stub` | `test_stale_needs_review_fires`, `test_stale_stub_check_never_emitted` | MAPPED |
| AC3 | `unreviewed_needs_review` fires High | `test_unreviewed_needs_review_fires` | MAPPED |
| AC4 | Double-count rule | `test_both_needs_review_checks_fire_on_aged_object` | MAPPED |
| AC5 | All 10 checks fire on fixtures | one dedicated test per check (10 firing tests) | MAPPED |
| AC6 | Contradiction passive | `test_contradiction_check_passive` | MAPPED |
| AC7 | severity_threshold filtering + info gating | `test_severity_threshold_high_filters_medium_low`, `test_severity_threshold_low_excludes_informational` | MAPPED |
| AC8 | Duplicate band + dedup | `test_duplicate_sweep_fires_in_band`, `test_duplicate_sweep_excludes_outside_band`, `test_duplicate_sweep_self_match_and_pair_dedup` | MAPPED |
| AC9 | QA#25 schema gate — 3 branches | `test_pre_check_schema_outdated_fires_before_write`, `test_pre_check_schema_missing_aborts`, `test_pre_check_schema_newer_warns_and_continues` | MAPPED |
| AC10 | QA#30 fires before write | `test_pre_check_patch_decision_missing_fires_before_write`, `test_pre_checks_fire_before_wikilog_write` | MAPPED |
| AC11 | WikiLog receipt + status lifecycle | `test_wikilog_receipt_written_on_clean_run`, `test_partial_status_on_get_object_failure`, `test_wikilog_skipped_on_pre_check_failure` | MAPPED |
| AC12 | Object budget warning + sweep cap | `test_object_count_budget_warning_above_500`, `test_duplicate_sweep_skipped_over_object_cap` | MAPPED |
| AC13 | Tag resolution two-step (no `/tags`) | `test_asymmetric_relation_check_fires` + needs-review tests (implicit two-step) | MAPPED (weak — see ADV-1) |
| AC14 | CLI + server registration | `test_wiki_lint_registered_and_cli_routed` | MAPPED |
| AC15 | Live smoke | `TestLintLive.test_end_to_end_lint` (`@pytest.mark.live`) | MAPPED |

**Unmapped ACs:** None.
**Tests with no AC:** None. Every one of the 33 named tests services an AC. The `test_duplicate_sweep_skipped_under_threshold` test (sweep skipped under `="high"`) supports AC7/AC8; `test_backlinks_primary_no_traversal` / `test_backlinks_malformed_falls_back` support AC1. R2's "all 15 ACs map to named tests" claim is INDEPENDENTLY CONFIRMED.

---

## Test Satisfiability — duplicate band re-verification (the R1 BLOCKING domain)

Band is now defined (spec §96, check table §141, AC8) as half-open `0.70 <= s < lint_duplicate_max_score()`, default `0.85`, via the new `WIKI_LINT_DUPLICATE_MAX_SCORE` float knob guarded by the new `_bounded_float([0,1])`. `index_threshold()` and the `/1000` hack are fully purged from all band/AC/test sites (only "do-not-use" explanatory mentions remain).

- `test_duplicate_sweep_fires_in_band` — candidate score **0.75**: `0.70 <= 0.75 < 0.85` = TRUE → one entry produced. **SATISFIABLE.** (Under the R1 design this asserted a finding the impl could never produce — that defect is gone.)
- `test_duplicate_sweep_excludes_outside_band` — **0.60** (`< 0.70` → excluded) and **0.95** (`>= 0.85` → excluded). Both branches genuinely reachable. **SATISFIABLE.**
- `test_duplicate_sweep_self_match_and_pair_dedup` — self-match excluded via `candidate_id != object_id` (sound against `semantic_search_core` returning `object_id`, indexer.py:75); reciprocal A→B/B→A canonicalized to a sorted tuple in a `set` → single emission. **SATISFIABLE.**

The band is a non-empty real interval and every duplicate-sweep test asserts behavior the design can produce. **B1 (test-satisfiability) is truly resolved.** I scanned the remaining 30 tests for the same defect class (a test asserting a value/branch the spec's design cannot generate) and found none.

---

## Coverage Adequacy (QA checklist)

- **10 checks, each a firing test (AC5/G2):** YES. asymmetric, pipeline_orphan, orphan, unreviewed_needs_review, contradiction (manual-populated branch), stale, stale_needs_review, oversized, empty_type, potential_duplicate. The "9→10" relabel landed in AC5, check table, and signature note; `test_stale_stub_check_never_emitted` is a negative guard the dropped enum never appears.
- **Double-count rule (aged needs-review → High + Medium):** TESTED — `test_both_needs_review_checks_fire_on_aged_object` asserts both findings present AND both counted in `summary`. Good (asserts the summary, not just the array).
- **Age-derivation (SF5: `wiki_sources` → linked source `wiki_ingested_at`):** TESTED for `stale` (`test_stale_check_fires` explicitly asserts "the source dereference happens"). For `orphan`, `test_orphan_check_fires_after_grace`/`_suppressed_within_grace` exercise the grace boundary. ADVISORY: see ADV-2 — the orphan/stale_needs_review tests as worded seed `wiki_ingested_at` on the object, but SF5 says that property lives only on `wiki_source`; the impl/test phase must seed it on a linked source for these tests to exercise the real derivation path.
- **QA#25 three branches (missing/outdated/newer):** each has a dedicated test (`_schema_missing_aborts`, `_schema_outdated_fires_before_write`, `_schema_newer_warns_and_continues`). Strong.
- **`partial` status path (get_object 5xx):** TESTED — `test_partial_status_on_get_object_failure` (object skipped, in `warnings[]`, status partial, WikiLog still written).
- **Severity-threshold filtering (high excludes med/low/info; low excludes info):** TESTED — both `_high_filters_medium_low` and `_low_excludes_informational`, the latter also asserting `potential_duplicates[]` empty.
- **Pre-checks-fire-before-write:** TESTED — `test_pre_checks_fire_before_wikilog_write` + `test_wikilog_skipped_on_pre_check_failure` assert zero POSTs.
- **Sweep gating (B2):** `test_duplicate_sweep_skipped_under_threshold` (high → no `semantic_search_core` call) and `test_duplicate_sweep_skipped_over_object_cap` (cap → sweep skipped, High/Critical still produced). Good — the cap test specifically asserts High/Critical findings survive degradation, which is the right regression guard.

Tests are meaningful, not trivial: they assert check enum + severity + summary counts + warning strings + POST presence/absence, not mere non-emptiness.

---

## Regression Risk

- **~80% infra reuse (per-run cache, `_fetch_cached`, `_parse_relation_elements`, `_qdrant()`, `semantic_search_core`, `_write_wikilog`, schema/patch pre-checks):** lint is additive — a NEW module (`lint.py`), NEW test file, plus EDIT-only touches to `cli.py` (append a subcommand), `server.py` (register a tool), `config.py` (add accessors + a new guard), and docs. No existing helper signature is modified; reuse is by import/call, not by edit. Regression surface to existing tools (`wiki_query`/`wiki_ingest`/`wiki_remember`) is low. The one shared-code edit is `config.py` gaining `_bounded_float` and six accessors — additive, does not touch `_positive_int` or `index_threshold()`. AC14 explicitly guards "without shadowing existing tools."
- **Mock strategy soundness:** no-arg `respx.get()/post()` catch-alls + specific `get_object` route + `semantic_search_core` monkeypatched at the function boundary. This is the established `test_ingest.py`/`test_query.py` pattern and is CI-runnable with zero live services (no Ollama/Qdrant/Anytype). Monkeypatching `semantic_search_core` at the function boundary correctly avoids exercising the embedder — sound and aligned with the #284 lesson (every check has a CI-runnable mocked backstop; live smoke is additive). CONFIRMED.
- **Test-first verification:** this is a spec phase — tests are specified but not yet authored. The test-phase worker must verify each test FAILS before implementation. Spec descriptions are clear enough to author from. Not a blocker at spec gate, but flag forward to the test phase.

---

## BLOCKING

None.

The two R1 BLOCKINGs were satisfiability defects in the QA domain. Both are confirmed resolved: B1 (empty/no-op duplicate band) replaced by a real `[0.70, 0.85)` interval with satisfiable firing/exclusion/dedup tests; B2 (uncapped sweep) gated to `="all"` + auto-skip above `WIKI_LINT_MAX_OBJECTS`, with a test asserting High/Critical findings survive the skip.

---

## ADVISORY

### ADV-1 — AC13 (tag-resolution two-step) has no dedicated assertion
AC13 ("no call to `/v1/spaces/{space_id}/tags`; resolution via `list_properties` → `list_tags`") is mapped only implicitly — "the asymmetric + needs-review tests verify the two-step path." No test explicitly asserts the negative (zero requests to the space-level `/tags` route) or that both `properties` and `properties/{id}/tags` GETs occur. The space-level `/tags` 404 is a documented past failure mode; an implicit assertion may pass even if a regression reintroduces the wrong route under a catch-all mock.
**Impact:** low-probability regression of the exact wire defect the #285/#289 lesson warns about could slip the CI net.
**Recommended action (test phase):** add one explicit assertion — either that `list_tags` is invoked with a resolved `property_id`, or that no request hits `/v1/spaces/{space_id}/tags` (route-not-registered / respx call inspection). Document, not block.

### ADV-2 — Age-derivation fixtures must seed `wiki_ingested_at` on a linked source, not the object
`test_orphan_check_fires_after_grace`, `test_orphan_check_suppressed_within_grace`, and `test_stale_needs_review_fires` are worded as seeding `wiki_ingested_at` directly on the entity. Per SF5 (verified: types_schema.py:79), that property lives only on `wiki_source`; entity/concept reach it via `wiki_sources`. If the test fixtures seed it on the object, they would pass against a buggy impl that reads an absent property (silently never firing the age gate) — a false-green. `test_stale_check_fires` is correctly worded ("the source dereference happens"); the orphan and stale_needs_review tests should match.
**Impact:** medium if uncorrected at authoring — could mask the exact "check silently never fires" defect SF5 was raised to prevent. Caught here at spec gate, so it is a wording/authoring instruction, not a design defect.
**Recommended action (test phase):** author orphan + stale_needs_review fixtures so the age timestamp is on a linked `wiki_source` reached through `wiki_sources`, exercising the dereference. Note in test-plan handoff.

### ADV-3 — `pipeline_orphan` heuristic and `backlinks` shape are correctly fenced, recorded for the chair
The `pipeline_orphan` ±300s window is pinned (`WIKI_LINT_PIPELINE_WINDOW_SECONDS`, G3) so `test_pipeline_orphan_check_fires` is deterministic — this satisfiability concern is resolved. Separately, the `backlinks` field shape is sourced from a single live session (2026-06-03), not a committed fixture (research §B; CTO-flagged). The spec correctly makes the primary path defensive and provides `test_backlinks_malformed_falls_back` (non-list → treated as absent → fallback) plus `test_backlinks_primary_no_traversal`, so a wrong-shape assumption degrades to the tested fallback rather than crashing. This is adequate coverage for an unverified-by-fixture field. No action required; recorded so the council chair notes the live smoke (`test_end_to_end_lint`) is the only check against the real backlinks shape — keep it in the suite, do not let it rot to skip-always.

---

## Rationale

A 33-test plan (32 CI-mocked + 1 live smoke) with full bidirectional AC↔test traceability and no unsatisfiable assertions is a strong contract. The single class of defect that has bitten this project twice (#285/#289 — a test asserting a value the design cannot produce) was the R1 BLOCKING here and is genuinely fixed: the duplicate band is a real non-empty interval and every duplicate test is satisfiable. Coverage hits every check, the double-count rule, all three schema branches, the partial path, both severity-filter directions, the sweep cap, and pre-checks-before-write. Regression risk is low (additive module, no existing-helper edits). The two ADVISORYs are test-authoring instructions for the downstream test phase, not design gaps — they sharpen fixtures so two known "silent never-fires" traps (wrong wire route, age-property-on-wrong-object) cannot produce false-green tests. Neither prevents advancing.

**Sign-off:** Quality gates met for the spec phase. I sign off. Advance to test/implementation, carrying ADV-1 and ADV-2 as test-authoring constraints and ADV-3 as a note to keep the live smoke alive.
