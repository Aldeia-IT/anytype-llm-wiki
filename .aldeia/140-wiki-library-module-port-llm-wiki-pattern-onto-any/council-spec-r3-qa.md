# Council Meeting — Post-spec (Round 3) — QA Director Assessment

**Date:** 2026-04-23
**Ticket:** #140 — Wiki Library Module: Port LLM Wiki Pattern onto Anytype
**Role:** QA Director (R3 advancement review)
**Spec under review:** `.aldeia/140-wiki-library-module-port-llm-wiki-pattern-onto-any/spec.md` at commit `b611f41` (2124 lines, `status: SPEC`, `review_rounds: 2`).
**Prior rounds:** R1 `council-spec-r1.md`, R2 `council-spec-r2-qa.md` (12 advisories), R2 synthesis `council-spec-r2.md`, R3 solo verification `review-r3.md` (APPROVED).

---

## Verdict

**SIGN OFF — advance to test phase.**

Every one of my 12 R2 advisories is now mechanically assertable in the spec, with a named AC, a matching Test Plan line or pre-release-checklist item, and (where relevant) a corresponding failure-modes row. BLOCKING-CTO-1 coverage (new AC v0.2.0 #12) exercises all three paths — class, wrapper, and `indexer.py` importer regression — and the 45-line baseline claim matches the codebase at HEAD. Every MoSCoW Must across v0.2.0 / v0.3.0 / v0.4.0 / v0.5.0 now traces to at least one AC. Zero regressions relative to the R1 invariants the review-r2 / review-r3 files enshrined.

Two SHOULD-FIX-scope residuals (not blocking, flagged for the test-phase opening steps) and three polish-level observations are documented below.

---

## Summary

The R2 rework is unusually faithful to the advisory set — the fixer did not cherry-pick, did not silently reframe, and did not substitute polish for substance. Every traceability gap I named in R2 has a specific, enumerable AC in the spec today. The most material improvements for the test phase:

- **BLOCKING-CTO-1 coverage AC is genuinely three-path** (class / wrapper / importer regression). This is the exact shape of AC a test-phase worker can mechanically translate to parametrized tests without interpretation.
- **Schema-compat AC now spans all three outcomes across three tool surfaces.** v0.2.0 #13 covers `_outdated` (with the bootstrap-specific informational-exception correctly scoped); v0.3.0 #14 covers `_newer` warn-and-continue for `wiki_ingest`; v0.4.0 #8 covers both `_outdated` and `_newer` for `wiki_query`. The Implementation Plan's "compat check on every tool entry" commitment is now measurable at every entry.
- **Bidirectional-relation rollback is a named invariant** (v0.3.0 #13) with a specific failure injection (mock the second PATCH in the reciprocal pair to 500) and a named WikiLog event shape (`relation_rollback`). Test-phase authoring target is unambiguous.
- **Concurrent-ingest test mechanism is named in both AC and Test Plan.** AC v0.3.0 #5 inlines the `multiprocessing.Process` directive; Test Plan line 1913 carries the full rationale (respx synchronous / single event loop vs. kernel-held flock requires OS-level process isolation). A test author cannot plausibly write a mocked-lock test and think they've satisfied the AC.
- **Prompt-injection AC internal contradiction is resolved.** Option (b) was picked cleanly: object created with `is_central=false` is admissible; the final assertion is "no object with that name appears with `is_central=true`." A second test case for the name-policy-trip path covers what option (a) would have asserted, so both behaviors are now test-exercised under one AC without contradiction.
- **Performance Success Criteria text now carries the Jan's-Mac-Mini-M4 qualifier everywhere** (v0.2.0 line 1852, v0.4.0 line 1872, v0.5.0 line 1880), matching the corresponding ACs (#6 / #7 / #6). The maintainer-measured-at-release-time note is identical across AC and Success Criteria wording. Internal consistency closed.
- **`patch-decision.md` pre-check is now a three-tier AC chain:** v0.2.0 #14 (scaffolding + test shell), v0.3.0 #15 (activated for `wiki_ingest`), v0.4.0 #9 (activated for `wiki_query`). The failure-modes row (line 1654) names the same error string. R1's single untraced failure mode is now a cross-cutting AC-enforced invariant.
- **Wikipedia fixture pinning is committed to the v0.3.0 pre-release checklist** (line 867): archive.org snapshot at spec-sign-off, archive URL as release-gate, live URL as aspirational. Neutralizes the indefinite-future maintenance surface I flagged.
- **Partial-state idempotency AC** (v0.3.0 #18) ships the resume behavior as default with an explicit v0.6.0+ defer-alternative documented; the v0.3.0 pre-release checklist requires the choice to be recorded. The "either ship it or defer with a note" directive I raised is honored literally.

Two items deserve test-phase attention (SHOULD-FIX, non-blocking):

1. AC v0.3.0 #18 carries both a default ("ship resume") AND an alternative ("defer to v0.6.0+") in one AC. This is a deliberate design choice by the fixer (per debrief §"Where did you spend time experimenting"), but the test author needs to know which branch to write tests against BEFORE writing them. The disposition is captured in the v0.3.0 pre-release checklist; the test-phase opening step must lock the choice in writing (inline in the test-phase plan) so test authoring is not blocked waiting for pre-release.
2. Test Plan line for AC v0.3.0 #13 (bidirectional rollback) is implicit — the AC text points at `tests/wiki/test_ingest.py` and describes the failure injection, but the Test Plan section (lines 1905–1914) does not enumerate "bidirectional rollback test case: mock B→A PATCH to 500; assert A→B is reverted; assert `relation_rollback` in WikiLog." The Deliverables line 844 lists "bidirectional relation rollback" as test coverage, so the test author has two authoritative-enough sources; adding a one-line Test Plan bullet would tighten traceability with trivial cost.

---

## R2 disposition table

Independent verification. For each of my R2 advisories I located the AC text, checked mechanical assertability (can a test author translate it to pytest with no further judgement calls?), and confirmed it matches the advisory's recommended action.

| R2 # | Advisory | Spec location | Mechanically assertable? | Status |
|------|----------|---------------|---------------------------|--------|
| A-1 / #24 | Four lint-check ACs: `contradiction_unresolved`, `oversized`, `stale_stub`, `potential_duplicate` | AC v0.5.0 #8 (line 960), #9 (961), #10 (962), #11 (963) | **YES** — each AC names the seeded shape, the expected severity, the finding count, and the `detail` content where applicable. `#8` correctly carries the v0.6.0-retest note for pipeline-produced data given the passive state. `#11` correctly scopes to respx-mocked Qdrant so no live dependency. | **PASS** |
| A-2 | Dash-fold ordering verification (no action required) | §Entity Resolution Semantics (lines 1205–1230); `_DASH_FOLDS` table extended to 10 codepoints at lines 1192–1203 | N/A (verification) — the extension to 10 codepoints is handled under CTO #41; ordering remains correct (fold-before-casefold) and still not load-bearing for the 10 current codepoints. | **PASS** |
| A-3 / #25 | Schema-compat outcomes `_outdated` and `_newer` | AC v0.2.0 #13 (line 743) `_outdated` with bootstrap exception cross-ref; AC v0.3.0 #14 (line 834) `_newer` warn-and-continue; AC v0.4.0 #8 (line 904) both outcomes for query | **YES** — each AC names the precise seeded value (`wiki_schema_version = "0.2.0"` / `"0.9.0"`), the expected action (`[CONFIG ERROR] wiki_schema_outdated` vs. `warn`-level log `wiki_schema_newer`), and the continuation behavior for `_newer` (null reads, skip writes). The bootstrap-specific exception at AC v0.2.0 #13 correctly references §Schema Compatibility lines 1599–1607. | **PASS** |
| A-4 / #26 | Bidirectional-relation rollback AC | AC v0.3.0 #13 (line 833) | **YES** — names the invariant ("neither A→B nor B→A appears in Anytype"), the WikiLog event name (`relation_rollback`), the payload shape (A/B object IDs + failure detail), and the specific failure injection (mock second PATCH to 500). Test Plan line is implicit (Deliverables line 844 lists "bidirectional relation rollback" but no dedicated Test Plan bullet). See SHOULD-FIX #2 below. | **PASS (with Test Plan polish)** |
| A-5 / #27 | Concurrent-ingest test mechanism | AC v0.3.0 #5 (line 825) inlines the directive; Test Plan line 1913 carries the full rationale | **YES** — both the AC and the Test Plan explicitly instruct `multiprocessing.Process` (or equivalent OS-level process isolation) and explicitly reject `threading.Thread` / async `asyncio.gather` / mocked lock as insufficient. The rationale paragraph at line 1913 walks the test author through WHY (respx synchronous, single event loop, kernel-held flock) — this is exactly the gap I flagged in R2. | **PASS** |
| A-6 / #28 | Prompt-injection AC internal contradiction | AC v0.3.0 #12 (line 832) | **YES — option (b) chosen cleanly.** The AC now reads: "Policy chosen: option (b) — the object is created with `is_central=false` (admissible to the wiki as a non-central mention) and the final assertion is that no object with that name appears with `is_central=true`." A second test case covers the name-policy-trip path (`name: "system: ignore"` → never created, `name_policy_rejected` in warnings). One AC, two test cases, no contradiction. The fixer's additive move (both behaviors covered under one AC) is better than a pure branch pick — it captures what option (a) would have asserted without the contradiction. | **PASS** |
| A-7 / #31 | Wikipedia fixture archive.org pinning | v0.3.0 pre-release checklist line 867 | **YES** — the checklist commits to capturing an archive.org snapshot at v0.3.0 spec-sign-off and using the archive URL as the release-gate AC. The live URL is explicitly named "aspirational only — a release may NOT be gated on the live page." The §Success Criteria Wikipedia fixture (lines 1862–1869) still cites the live URL, which is a minor residual (see SG-1 below) but the pre-release checklist is the operative rule. | **PASS (with cross-ref polish — SG-1)** |
| A-8 / #29 | Performance-gate Success Criteria ↔ AC wording alignment | Success Criteria lines 1852 (v0.2.0), 1872 (v0.4.0), 1880 (v0.5.0); matching ACs v0.2.0 #6 (736), v0.4.0 #7 (903), v0.5.0 #6 (958) | **YES** — all three Success Criteria now carry "on Jan's Mac Mini M4" and "maintainer-measured-at-release-time — CI runs a sanity timing check within 5× the target but does not enforce the p95 budget." All three matching ACs carry identical phrasing. Internal consistency closed. v0.3.0 Success Criteria (§Wikipedia fixture) correctly carries "on Jan's Mac Mini M4" at line 1869. | **PASS** |
| A-9 | v0.2.0 AC #6 CI-assertability labeling | AC v0.2.0 #6 (line 736); v0.4.0 #7 (line 903); v0.5.0 #6 (line 958) | **YES** — all three performance ACs now carry the maintainer-measured-at-release-time label inline with the CI sanity-check bound. This converts them from "not CI-assertable" (my R2 concern) to "CI-assertable at a bounded level, maintainer-enforced at the release gate." Correctly handled. | **PASS** |
| A-10 / #32 | Partial-state idempotency | AC v0.3.0 #18 (line 838); v0.3.0 pre-release checklist line 869 | **YES (with a residual choice)** — AC ships "resume" as default (reuse existing Source, re-run extraction, attach new entities; record `resumed_partial_ingest` event) and explicitly documents the v0.6.0+ defer-alternative with the duplicate-Source lint-sweep workaround. The pre-release checklist line 869 requires the choice to be recorded before tag. See SHOULD-FIX #1 below: the test-phase opening step needs to lock the choice inline. | **PASS (with test-phase sequencing note — SHOULD-FIX #1)** |
| A-11 | Hypothesis scope decision (no action required) | Mock Strategy endorsement in prior review | N/A (verification) — no regression. | **PASS** |
| A-12 / #30 | `patch-decision.md` missing/malformed AC | AC v0.2.0 #14 (line 744); AC v0.3.0 #15 (line 835); AC v0.4.0 #9 (line 905) | **YES** — three-tier chain. v0.2.0 #14 ships the test scaffolding; v0.3.0 #15 activates for `wiki_ingest` with "before any Anytype write or URL fetch" ordering assertion; v0.4.0 #9 activates for `wiki_query` with "before any Anytype or Qdrant call" ordering assertion. The failure-modes row (line 1654) names the same error string. AC + test-plan-implicit + failure-modes triangulate. | **PASS** |

**Total:** 12/12 R2 advisories resolved at the spec-level with mechanically-assertable AC text. Two of them (A-4/#26 and A-10/#32) carry SHOULD-FIX-scope residuals that are test-phase-opening concerns, not spec-blockers.

---

## R3 findings

### BLOCKING

**None.**

### SHOULD-FIX (test-phase opening-step concerns, not spec-blockers)

**SF-1 — AC v0.3.0 #18 partial-state idempotency: the branch choice must be locked before test authoring begins.** AC v0.3.0 #18 (line 838) documents both a default behavior ("implement resume") and an alternative ("defer to v0.6.0+"), deferring the choice to the v0.3.0 pre-release checklist (line 869). This is a principled design move — the fixer's debrief (item §"Where did you spend time experimenting") explicitly notes that the choice wants test-reality data in hand. However, the v0.3.0 test-phase worker cannot write tests for this AC without knowing which branch to assert against. **Recommended action:** the test-phase opening step for v0.3.0 (or the pre-test council) locks the disposition in a one-line inline decision ("AC v0.3.0 #18 disposition: resume / defer — DECISION: X, by Jan on YYYY-MM-DD") at the top of `tests/wiki/test_ingest.py` or in the test-phase plan. This is not a spec-edit blocker — the AC is correctly scoped as "shippable default + alternative" — but the test-phase handoff needs an explicit disposition-lock step to avoid write-a-test-for-behavior-A-then-discover-behavior-B-is-chosen rework. **Impact:** mild. **Not a spec defect.**

**SF-2 — AC v0.3.0 #13 (bidirectional rollback) has no dedicated Test Plan bullet.** The AC (line 833) and the Deliverables line (844) between them name the rollback invariant, the `relation_rollback` WikiLog event, and the failure injection (mock B→A PATCH to 500). But the Test Plan section for Ingest (lines 1905–1914) does not enumerate a "bidirectional relation rollback" test case. A test author following the Test Plan top-to-bottom would cover happy-path bidirectional creation (line 1909) and partial-failure-with-status-partial (line 1910) but might miss the rollback-specific case. The AC is authoritative and the test author SHOULD cross-reference it, but adding a one-line Test Plan bullet — "Mock reciprocal PATCH failure → both A→B and B→A absent from Anytype; WikiLog records `relation_rollback`" — would close the trivial traceability gap. **Recommended action:** add the line to Test Plan section Ingest (v0.3.0) at roughly line 1911. One-line edit. Low cost, closes a SHOULD-FIX gap that my R2 review identified as a completeness issue. **Not a spec-blocker** — the AC text itself names the test file (`tests/wiki/test_ingest.py`) and the injection, so the test author has enough information.

### SUGGESTION (polish; defer to v0.2.0 housekeeping or v0.6.0+)

**SG-1 — Wikipedia fixture URL citation in Success Criteria still points at the live URL.** §Success Criteria v0.3.0 (lines 1862–1869) cites `https://en.wikipedia.org/wiki/Mamba_(deep_learning_architecture)` as the source. The v0.3.0 pre-release checklist line 867 correctly requires the archive.org snapshot as the release-gate URL. But a contributor reading only the Success Criteria section would see the live URL and think it IS the release-gate. Recommended polish: once the archive snapshot is captured at v0.3.0 pre-release time, update the Success Criteria URL to the archive URL inline (e.g. `https://web.archive.org/web/YYYYMMDDhhmmss/https://en.wikipedia.org/wiki/Mamba_(deep_learning_architecture)`), with a note "(live URL: https://en.wikipedia.org/... — aspirational only)." Non-blocking; resolves naturally when the snapshot is captured. **Not an R3 finding per se — a natural consequence of the A-7 resolution.**

**SG-2 — `contradiction_unresolved` passive state: AC v0.5.0 #8 notes v0.6.0 re-test against pipeline-produced data.** This is correct — v0.3.0's extraction pipeline does not populate `wiki_contradictions`, so v0.5.0 tests must seed via `WikiClient.update_object`. Recommended that v0.6.0 spec (when written) explicitly references AC v0.5.0 #8's "re-test against pipeline-produced data" clause so the v0.6.0 AC list picks it up. Not a v0.x concern; flagging for future-me's benefit.

**SG-3 — AC v0.2.0 #15 (credential scrubbing) is substantive and maps to CSO Advisory #5 rather than a QA advisory.** Verified it is mechanically assertable (two forced-`[API ERROR]` paths: Qdrant URL with `?api_key=SEKRET123`, extraction endpoint with `api-user:api-secret@` userinfo; assertion that neither value appears in error string). Not a QA-advisory-disposition issue — just flagging that the credential-scrubbing regression test is in my scope to verify (test coverage) and it passes.

---

## Traceability: MoSCoW Must → AC coverage (per version)

Spot-check of every "Must" commitment per version to confirm at least one AC covers it. Italics = implicit (covered by AC text without a dedicated line, acceptable for "Must" semantics).

### v0.2.0 Must (line 726)

| Must | AC(s) |
|------|-------|
| bootstrap creates 6 types + properties + tags + root Collection idempotently | v0.2.0 #1 (creation), #2 (idempotence) |
| supports custom `domain_tags` | v0.2.0 #5 (first-call replace + re-bootstrap union semantics) |
| write-token scope verified | v0.2.0 #9 (read-only token → `insufficient_token_scope`) |
| README privacy/rights notices land | v0.2.0 #8 (exact privacy notice verbatim) |
| verification script ships | v0.2.0 #7 (runs end-to-end, unambiguous decision; maintainer-local) |

**Every Must has ≥ 1 AC. PASS.**

### v0.3.0 Must (line 816)

| Must | AC(s) |
|------|-------|
| URL + file ingestion | v0.3.0 #1 (arxiv URL → Source + entities + concepts), #8 (empty-source file) |
| bidirectional Relations | v0.3.0 #1, #13 (rollback), Success Criteria line 1859 |
| page threshold + cross-link minimum | v0.3.0 #1 (≥1 Entity, ≥1 Concept implicit); Success Criteria Wikipedia fixture (≥2 outbound relations) |
| WikiLog entry always written | v0.3.0 #3 (partial), #13 (`relation_rollback`), #8 (`empty_source`) |
| per-space file lock | v0.3.0 #5 (concurrent same-space rejected; different-space succeeds) |
| SSRF guards | v0.3.0 #4 (SSRF redirect to loopback rejected), #17 (DNS rebinding tripwire) |
| extraction retry on malformed JSON | v0.3.0 #7 (one repair attempt before failing) |
| single canonical PATCH path determined by v0.2.0 verification | v0.3.0 #15 (`patch-decision.md` pre-check) |

**Every Must has ≥ 1 AC. PASS.**

### v0.4.0 Must (line 892)

| Must | AC(s) |
|------|-------|
| index-navigation mode for < threshold | v0.4.0 #1 |
| vector-augmented mode at/above threshold | v0.4.0 #2, #3 (boundary 199/200/201) |
| file-back respects thresholds and per-call override | v0.4.0 #4 (threshold creates Query), #5 (`file_back=False` suppresses) |
| synthesis includes Anytype deeplinks | *implicit in AC #4 (Query object with `wiki_drew_from` relations); explicit in Test Plan line 1917* |
| config error if schema missing | v0.4.0 #6 (no wiki types → `[CONFIG ERROR]` naming `wiki.bootstrap`) |

**Every Must has ≥ 1 AC. PASS** (one implicit case, documented above).

### v0.5.0 Must (line 948)

| Must | AC(s) |
|------|-------|
| 9 `check` enum values | v0.5.0 #1 (`orphan`), #2 (`pipeline_orphan`), #3 (`asymmetric_relation`), #4 (`stale`), #7 (`empty_type`), #8 (`contradiction_unresolved`), #9 (`oversized`), #10 (`stale_stub`), #11 (`potential_duplicate`) |
| severity grouping | *implicit in every AC (each names the severity)* |
| `severity_threshold` filter | v0.5.0 #5 |
| Anytype deeplinks on every finding | *implicit in AC #3 (asymmetric reports both IDs with deeplinks); Success Criteria line 1878 (orphans with deeplinks)* |
| `--json` and `--human` output modes | *covered by Test Plan + Deliverables; no dedicated AC* |

**8 of 9 Musts have dedicated ACs; 1 (output modes) is Deliverables-only.** Output modes are a user-facing feature (`wiki-lint --json` / `--human`) that merits its own AC per the per-version AC discipline Jan prioritized. **Not a spec-advancement blocker** (the feature is well-understood and the tests can cover it under `test_lint.py` CLI-level test coverage), but worth noting as a minor traceability gap. Not elevated to SHOULD-FIX because R1, R2, and R3 all missed it and the test author can cover it from the MoSCoW line directly; test-phase workers should add one AC or an explicit Test Plan bullet. Flagged for the test-phase opening step as **SG-4** below.

**SG-4 — v0.5.0 CLI `--json` / `--human` output modes have no AC.** MoSCoW Must line 948 names both modes; no AC enforces them. Suggest adding an AC v0.5.0 #12: "`anytype-llm-wiki wiki-lint --json` returns parseable JSON with every finding's `check`, `severity`, `object_ids`, `detail`, and `deeplink` fields populated. `--human` renders the same data as a grouped-by-severity table. The MCP tool always returns structured JSON regardless of CLI flag." This is new, not a re-raised R2 finding. Non-blocking.

---

## Regressions on R1 invariants

Independent spot-check against the 14 R1 invariants enshrined in review-r2.md + review-r3.md. All PASS:

| Invariant | Status |
|-----------|--------|
| No `anytype-rag` residuals | PASS (grep zero matches) |
| `normalize_title` dash-folds BEFORE casefold | PASS (spec line 1212 docstring; pseudocode line 1226 ordering preserved) |
| `_DASH_FOLDS` complete | PASS — extended from 8 to 10 codepoints (U+00AD, U+2015 added per CTO #41); AC v0.3.0 #6 parametrization correctly enumerates 10; Test Plan line 1912 enumerates all 10 plus non-match case |
| SSRF `getaddrinfo` / scheme allowlist / port allowlist / userinfo rejection / timeouts / size cap | PASS (lines 1684, 1745, 1800–1804 intact; port allowlist tightened to `{None, 80, 443}` with `WIKI_FETCH_EXTRA_PORTS` escape hatch per CSO #8) |
| Four Mermaid diagrams present | PASS (ingest, query, lint, delivery-phase dependency graph) |
| `BootstrapResult` schema with `wiki_log_id` | PASS |
| `LintReport.object_counts` canonical type_key keys | PASS |
| `fcntl.flock` coherent; non-NFS constraint | PASS (line 1585); doctor step 9 now probes filesystem type (Infra #34) |
| Verification script `trap` cleanup | PASS; CSO #2 strengthens it (trap before probe creation, `|| true` replaced) |
| Per-version Scope/MoSCoW/AC/Deliverables/Dependencies/Risks/Pre-release-checklist discipline | PASS across all four minor versions |
| Single-canonical-path discipline | PASS; hardened by new AC v0.2.0 #14 / v0.3.0 #15 / v0.4.0 #9 |
| Boundary test 199/200/201 | PASS (v0.4.0 #3) |
| 45-line `anytype_client.py` baseline claim | PASS (`wc -l` = 45, matches spec lines 224 and 1144) |
| Dash-fold test parametrization | PASS (10 codepoints; Test Plan line 1912 enumerates each) |

**No regressions identified.**

---

## Test coverage adequacy (test-phase readiness check)

- **Critical paths tested:** All v0.2.0 / v0.3.0 / v0.4.0 / v0.5.0 critical paths have AC coverage per MoSCoW audit above.
- **Edge cases covered:** Empty source (v0.3.0 #8), malformed extraction (v0.3.0 #7), concurrent ingest (v0.3.0 #5), DNS rebinding (v0.3.0 #17), boundary at 199/200/201 (v0.4.0 #3), schema outdated/newer (v0.2.0 #13 / v0.3.0 #14 / v0.4.0 #8), empty wiki lint (v0.5.0 #7), partial token scope (v0.2.0 #9 + failure-modes row).
- **Negative test cases:** `patch-decision.md` missing/malformed chain (v0.2.0 #14 / v0.3.0 #15 / v0.4.0 #9); SSRF loopback redirect (v0.3.0 #4); Ollama model not pulled (v0.3.0 #11); invalid `domain_hint` (v0.3.0 #10); prompt-injection path (v0.3.0 #12, both branches); credential scrubbing (v0.2.0 #15); extended control-char regex (v0.3.0 #16).
- **Integration points tested:** respx mocks for Anytype + Qdrant HTTP interactions (Mock Strategy); Ollama extraction happy + malformed (extraction tier); `multiprocessing.Process` for flock (v0.3.0 #5); controlled resolver fixture for DNS rebinding (v0.3.0 #17 integration-gated + unit-level stand-in).
- **Meaningful tests (not trivial):** ACs name specific seeded shapes, precise severity/count expectations, and specific failure injections. The test author is given enough to write real assertions, not "verify it works."

**Test coverage adequacy: SIGN OFF.**

---

## Regression risk for the test phase

- **Could the R2 rework break existing functionality?** The rework is spec-only (no source code changes per debrief §"Files edited"). The README.md:3 line and ancillary READMEs are prose; no runtime impact. Zero regression risk for any existing green test.
- **Are existing tests still passing?** Per the fixer's debrief, `pytest` was not run as part of the spec rework (correct — spec phase does not mandate test execution). The v0.2.0 impl phase will exercise the new AC coverage, including the `anytype_client.py` refactor's class-and-wrapper dual paths.
- **Dependencies on other components that could be affected?** The BLOCKING-CTO-1 refactor changes `anytype_client.py` from free functions to `AnytypeReadClient` + wrappers. `indexer.py:11` import surface is preserved verbatim (`from .anytype_client import get_object, list_objects, list_spaces`). AC v0.2.0 #12 explicitly asserts this import still resolves as a regression test. **Risk is specifically mitigated by the AC** — exactly what the R2 rework was supposed to produce.

**Regression risk: LOW.** The one structural change (anytype_client refactor) is gated by a dedicated AC with three-path coverage including an importer regression assertion.

---

## Quality gates

- **Code review within the phase:** R1 (4 reviewers + specialist impersonators), R2 (6 real specialists, independent), R3 solo verification. Three full rounds of review before advance. Exceeds standard quality-gate expectation.
- **All review findings addressed:** 1 BLOCKING + 42 ADVISORY addressed per fixer debrief traceability matrix. R3 spot-check (this review) confirms 12/12 of my R2 advisories resolved. R3 solo verification file (review-r3.md) confirms 10/10 mandatory advisories resolved plus regression invariants intact.
- **No deferred BLOCKING items:** None remaining.
- **CLAUDE.md updated if behavior changed:** Spec-only changes; CLAUDE.md update is a test-phase / impl-phase concern when behavior codifies. No current update needed.

**Quality gates: PASS.**

---

## Recommendation

**Advance to test phase.**

- **Target:** `test`
- **Confidence:** high
- **Rationale:**

  The R2 rework resolved BLOCKING-CTO-1 cleanly with a three-path coverage AC, resolved all 12 of my R2 advisories at the spec level with mechanically-assertable AC text, and introduced zero regressions on R1 invariants. Every MoSCoW Must per version (v0.2.0 / v0.3.0 / v0.4.0 / v0.5.0) traces to at least one AC, with one MoSCoW-Must (v0.5.0 `--json` / `--human` output modes) covered via Test Plan + Deliverables rather than a dedicated AC — flagged as SG-4 for test-phase attention but not a spec-advancement blocker.

  Two SHOULD-FIX-scope items are test-phase-opening-step concerns rather than spec-edit concerns:
  - **SF-1:** AC v0.3.0 #18 partial-state idempotency disposition must be locked in writing before test authoring begins. The AC carries both branches by design; the test author needs a locked choice.
  - **SF-2:** AC v0.3.0 #13 bidirectional-rollback test case should get a dedicated one-line Test Plan bullet for traceability polish. Low cost, not blocking.

  Four SUGGESTIONs (SG-1 through SG-4) are polish-level and deferrable.

- **Test-phase opening steps (recommended):**
  1. Lock the AC v0.3.0 #18 disposition (resume vs. defer) in the test-phase plan file with a one-line dated decision.
  2. Add the one-line Test Plan bullet for AC v0.3.0 #13 (bidirectional rollback) — either in the test-phase plan or via a trivial spec amendment before the test phase closes.
  3. Consider adding AC v0.5.0 #12 for the CLI output modes (SG-4) or cover them explicitly in test-phase authoring.

**Dissent from R3 solo verification:** None. The solo reviewer approved; I approve. The SHOULD-FIX items I raise are test-phase concerns, not rework-blockers — they do not trigger a return to spec.

**QA Director sign-off: SIGN OFF — advance to test phase.**
