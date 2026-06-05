# Council Impl R1 — QA Director

**Ticket:** Aldeia-IT/aldeia-box #286 — v0.5.0 `wiki_lint` structural health check
**Phase:** post-implementation (final delivery gate)
**Reviewer:** QA Director (independent; no Mem0 recall)
**Date:** 2026-06-05

## Verdict

**SIGN OFF.** (0 BLOCKING, 3 ADVISORY)

The suite is AC-complete, all 16 ACs are satisfied by the real implementation (not just by mocks),
the change is purely additive with zero shared-helper edits, and the one documented spec/test
divergence is a correct resolution in favor of the authoritative test. Nothing here rises to a quality
gate failure.

## Test evidence (independently re-run)

| Run | Result |
|-----|--------|
| `uv run pytest tests/wiki/test_lint.py -m 'not live' -q` | **44 passed, 2 deselected** in ~1.1s |
| `uv run pytest tests/wiki/ -m 'not live' -q` | **472 passed, 6 skipped, 6 deselected, 2 xfailed** in ~3.4s |
| `--collect-only` on test_lint.py | 46 collected → 44 CI + 2 `@pytest.mark.live` deselected |

Deselected/skipped accounting:
- **2 deselected in test_lint.py** = the two `@pytest.mark.live` smokes (`test_end_to_end_lint`,
  `test_backlinks_field_shape_live`). Correct and expected — they skip-gate on `ANYTYPE_SPACE_ID` /
  `ANYTYPE_BACKLINKED_OBJECT_ID` and are excluded by `-m 'not live'`.
- The 6 skipped / 2 xfailed in the full wiki run are pre-existing in `test_ingest.py`/`test_remember.py`
  (qdrant/live-gated), unrelated to #286. Matches the in-phase review evidence (impl-review-r1.md lines
  14-16) and the phase summary exactly. No newly-introduced skips or xfails attributable to lint.

Green confirmed independently of the worker and the in-phase reviewers.

## AC coverage assessment

All 16 ACs map to ≥1 CI test AND are satisfied by the impl, not vacuously by the mock. Spot-checks
requested by the brief:

- **AC8 (duplicate band half-open `[0.70, max)`):** SATISFIED non-vacuously. Impl `lint.py:489-511`
  uses `lo = _DUPLICATE_LO (0.70)`, `hi = config.lint_duplicate_max_score()` (default 0.85), and gates
  on `if not (lo <= s < hi): continue` — a genuine half-open interval. The boundary is exercised by
  `test_duplicate_sweep_excludes_outside_band`: 0.60 (below floor) AND **0.95 ≥ upper bound** both
  excluded; 0.75 admitted by `test_duplicate_sweep_fires_when_opted_in`. The upper-bound exclusion is
  a real assertion, not a trivially-passing one. Self-exclusion (`cid == o["id"]`) and canonical pair
  dedup (`tuple(sorted(...))` into `seen_pairs`) are covered by `test_duplicate_sweep_self_match_and_pair_dedup`.

- **AC15 (backlinks live smoke):** SATISFIED with the documented caveat (see ADVISORY-1). The live
  shape assertion (`"backlinks" in obj`, `isinstance(list)`) is skip-gated and unexercised in CI. The
  CI compensation is real: `_backlinks_inbound` (lint.py:117-127) treats absent/None/dict/scalar as
  "fallback needed, never raise", proven by `test_backlinks_malformed_falls_back` (None, `{"invalid":...}`,
  scalar `42`) which asserts no raise and `status in (ok, partial)`. The primary-vs-fallback split is
  proven by `test_backlinks_primary_no_traversal`.

- **AC16 (sweep opt-in gate):** SATISFIED non-vacuously. Impl gates the entire sweep behind
  `if include_duplicates:` (lint.py:481) then the cap check. `test_duplicate_sweep_off_by_default`
  installs tracking shims on BOTH `indexer.semantic_search_core` and `indexer._qdrant` and asserts
  zero calls to each on the default call AND on `severity_threshold="all"` — so the gate is proven to
  be `include_duplicates`, decoupled from `severity_threshold` (the CA-B1 fix).
  `test_duplicate_sweep_runs_regardless_of_threshold` proves the array populates under `="high"` while
  the informational `potential_duplicate` finding is post-filtered out of `findings[]` (gates orthogonal).

- **No AC tested only vacuously.** The severity tests assert *absence* of lower bands (negative
  assertions), the orphan tests seed age on a linked `wiki_source` via `wiki_sources` (not on the
  object — the ADV-3 false-green guard, which I carried from post-test), and AC13 has an explicit
  negative route (`test_tag_resolution_never_calls_space_level_tags`) asserting the space-level `/tags`
  route `.called is False`. These are the three places a weaker suite would false-green, and all three
  are fenced.

## Findings

### BLOCKING

None.

### ADVISORY-1 — AC15 live backlinks shape unverified in CI (accepted risk, documented)

The D1 primary path rests on the `obj["backlinks"]` shape, which is asserted only from a single live
session finding and is unexercised in CI (`test_backlinks_field_shape_live` is skip-gated). **This is
adequate compensation and NOT a block,** for three reasons: (1) the malformed-fallback CI test proves
that if the live shape differs from the assumption, lint degrades to the O(N) reciprocal-traversal
fallback rather than raising or producing wrong Critical findings — the failure mode is graceful and
report-only; (2) `wiki_lint` mutates nothing but its own WikiLog receipt, so a wrong inbound count
produces an over- or under-reported advisory finding, never data corruption; (3) the skip-gated smoke
keeps the live-confirmation obligation alive for the maintainer.
**Recommended action:** before or shortly after merge, run `uv run pytest -m live tests/wiki/test_lint.py`
once against Jan's real space with `ANYTYPE_BACKLINKED_OBJECT_ID` set, to discharge impl-task-ONE. Not
a merge precondition.

### ADVISORY-2 — `orphan` check stricter than master-spec definition (no AC/test impact)

`lint.py:377` requires `not has_inbound AND not _outbound(o)`; the master spec defines orphan as "no
inbound relations". An outbound-only, aged object is therefore not flagged `orphan`. This is the same
SUGGESTION the in-phase review recorded (impl-review-r1.md lines 46-51). It violates no AC and no test,
and such objects already trip `asymmetric_relation` (Critical) — a louder signal. Acceptable risk.
**Recommended action:** track as a v0.6.0 refinement candidate; no change this release.

### ADVISORY-3 — CPO-ADV-1 isolation test not added (explicitly non-gating)

The post-spec CPO suggested an all-empty-pipeline fixture asserting zero `contradiction_unresolved`
findings *in isolation*. It was not added — `test_contradiction_check_passive` proves passivity inside
a fixture that also contains a firing conflict entity, so the "green-is-not-a-guarantee" contract is
demonstrated but not isolated. The spec-addendum marked this CPO-ADV-1 explicitly non-gating
(addendum line 76-79), and the impl honestly documents the passive caveat in the module docstring,
`wiki_lint` docstring, README, and finding `detail` text.
**Recommended action:** optional test hardening for v0.6.0 when #287 re-activates the check; no action
required for v0.5.0.

## Rationale

**The documented spec/test divergence is a correct resolution, not a quality concern.** The spec
pseudocode implied the >500 budget warning counts `len(all_objects)`; the committed test seeds 501
content objects + 1 schema marker (502 in `all_objects`) and asserts the `"501"` substring. The impl
counts `len(wiki_objects)` — the content objects actually subject to the battery, excluding the
schema-marker collection (lint.py:260-280). This is both the semantically correct figure (the schema
marker is never linted) and the only reading that satisfies the authoritative test. The worker changed
the **impl**, not the test — exactly the right discipline. The test is authoritative over spec
pseudocode on a precise value, and the impl satisfies it correctly. No concern.

**Regression risk is minimal and bounded.** `git diff main...HEAD` confirms the change is purely
additive: `lint.py` is NEW; `config.py`/`cli.py`/`server.py` gain new symbols; `README`/`CHANGELOG`/
`.env.example` are doc edits. Critically, **`query.py`, `remember.py`, `ingest.py`, and `indexer.py`
are untouched** — the lint module reuses their helpers (`_parse_relation_elements`, `_fetch_cached`,
`_resolve_select_tag`, `_cmp_versions`, `_resolve_wiki_action_tag`, `_write_wikilog`,
`_schema_version_from_objects`, `semantic_search_core`) by import only, with zero edits to shared
behavior. The full wiki suite (472 passed) confirms ingest/query/remember are intact. There is no
path by which this change breaks existing functionality.

**Quality gates met.** In-phase code review completed (impl-review-r1.md, APPROVED, 0 BLOCKING /
0 SHOULD-FIX, 2 non-blocking SUGGESTIONS — both surfaced here as ADVISORY-2 and a benign client-
construction note). No deferred BLOCKING items. Doc-honesty deliverables from the test-phase addendum
(passive-contradiction caveat, opt-in sweep, truthful "≤60s/≤500 default sweep-off only" perf claim,
compact knob docs, honest ±300s `pipeline_orphan` heuristic) are all present in README/docstring/
CHANGELOG per the in-phase review. The single-enumeration constraint (CTO-BLOCKING-1) is satisfied —
`list_objects` called exactly once (lint.py:228) feeding both the schema gate and the battery, and the
corrected single-page fixtures would fail a two-call impl.

Test coverage is meaningful: critical paths (all 10 checks), edge cases (within/after grace, malformed
backlinks, band boundaries, schema 3-branch gate), negative cases (pre-checks fire before write, sweep
off by default, space-level `/tags` never called, informational excluded under thresholds), and
integration points (CLI routing, MCP registration, WikiLog receipt) are all exercised with real
assertions.

**Signed off for merge.** The three advisories are accepted risks with documentation; none gates the
release.

---

**Relevant paths:**
- `/Users/Shared/development/anytype-llm-wiki-worktrees/286-anytype-llm-wiki-v0-5-0-wiki-lint-structural-healt/src/anytype_llm_wiki/wiki/lint.py`
- `/Users/Shared/development/anytype-llm-wiki-worktrees/286-anytype-llm-wiki-v0-5-0-wiki-lint-structural-healt/tests/wiki/test_lint.py`
- `/Users/Shared/development/anytype-llm-wiki-worktrees/286-anytype-llm-wiki-v0-5-0-wiki-lint-structural-healt/.aldeia/286-anytype-llm-wiki-v0-5-0-wiki-lint-structural-healt/spec.md`
