# Council Meeting — Post-spec (Round 2) — QA Director Assessment

**Date:** 2026-04-22
**Ticket:** #140 — Wiki Library Module: Port LLM Wiki Pattern onto Anytype
**Role:** QA Director (calibration re-review)
**Spec under review:** `.aldeia/140-wiki-library-module-port-llm-wiki-pattern-onto-any/spec.md` (1912 lines, post-r1 fixer).

---

## Verdict

**SIGN OFF WITH CONDITIONS.**

The acceptance-criteria machinery is disciplined enough to proceed to the test phase, but there are three specific traceability gaps (lint check coverage, schema-compatibility outcomes, bidirectional-relation rollback) that must be closed before test authors begin writing `test_lint.py` / `test_ingest.py`. None of these are algorithmic defects — they are enumeration gaps between documented behavior and named ACs. One performance-gate inconsistency needs spec wording alignment.

---

## Summary

The spec invests unusually heavily in AC determinism: the dash-fold test is parametrized across eight codepoints, the 200-object boundary is nailed at 199/200/201, the concurrent-ingest AC makes three independent assertions, the prompt-injection AC specifies the failure policy at the ingestion boundary. The mock-strategy section differentiates unit/integration/cassette tiers and correctly scopes Hypothesis to `ExtractionModel` parsing.

The weaknesses are not algorithmic (the `normalize_title` dash-fold-before-casefold ordering is verified correct by executing Python; see Finding A-2) — they are **completeness** gaps where documented design behavior lacks a corresponding named AC:

1. Four of nine lint check enum values have no AC (R1 QA said five; the real count is four because `empty_type` IS covered by AC v0.5.0 #7). This is slightly better than R1 reported but still substantive.
2. Schema-compatibility check has three documented outcomes (missing / outdated / newer); only the `missing` outcome has any AC (v0.4.0 #6, and only for query). `_outdated` and `_newer` are untraced.
3. Bidirectional-relation rollback is specified in the Implementation Plan (line 424) and listed in v0.3.0 Deliverables as a test target, but the v0.3.0 AC list has no dedicated rollback AC — the invariant "if target-side write fails, the source-side write is reverted and neither appears in Anytype" is implicit at best.
4. Performance gates are internally inconsistent: v0.5.0 Success Criteria line 1680 states "<60 seconds" without the Mac-Mini-M4 qualifier that v0.5.0 AC #6 carries. Minor but the spec should be self-consistent.

Two ACs flagged as weak on reproducibility grounds: v0.2.0 #6 (bootstrap <30s on Jan's Mac Mini M4 — not CI-assertable) and the Wikipedia-fixture Success Criterion (live URL, no cassette fallback). Both are maintainer-local and both are acceptable with explicit labeling, but the spec should mark them explicitly as "maintainer-measured-at-release-time" rather than pretending they are green-or-red CI gates.

The concurrent-ingest AC (v0.3.0 #5) raises a real test-mechanics question: `respx` mocks synchronously; the actual race lives at `fcntl.flock`, which is an OS primitive and can only be exercised with multiprocessing/threading/subprocess. The spec does not spell out the test mechanism, and "respx makes it easy" would be a dangerous default assumption for the test author.

---

## Independent Findings

### BLOCKING

None. The gaps below are close-before-test-authoring-begins, not close-before-spec-advances. The council-chair's sign-off and my sign-off are both conditioned on these closing in the opening steps of the test phase.

### ADVISORY

**A-1. Lint check-count coverage gap (corrected).** v0.5.0 MoSCoW enumerates 9 check values (line 866): `orphan`, `pipeline_orphan`, `asymmetric_relation`, `contradiction_unresolved`, `stale`, `oversized`, `empty_type`, `stale_stub`, `potential_duplicate`. v0.5.0 ACs (lines 870–877) cover:

| AC# | Check covered |
|-----|---------------|
| 1 | `orphan` |
| 2 | `pipeline_orphan` |
| 3 | `asymmetric_relation` |
| 4 | `stale` |
| 5 | (severity filter — not a check) |
| 6 | (perf — not a check) |
| 7 | `empty_type` |

**Covered: 5 of 9. Missing: `contradiction_unresolved`, `oversized`, `stale_stub`, `potential_duplicate` — 4 of 9.**

R1 QA's Advisory #7 counted five missing by including `empty_type`; that is incorrect — AC #7 does cover `empty_type` at Informational severity with count=0. The substantive gap is four, not five, but four is still the single most material test-coverage hole in the spec. **Impact:** the Deliverables line says "seed a wiki with known defects and assert every check fires," but without named ACs the test author has no measurable target for four of the nine checks. **Recommended action:** add ACs for the four missing checks before test authoring of `test_lint.py` begins.

**A-2. Dash-fold ordering is correct; 8-codepoint list is consistent (verification only, no action).** Executed the following in Python 3 to independently verify:

```
U+2010 ('‐'): casefold unchanged  (same codepoint)
U+2011 ('‑'): casefold unchanged  (same codepoint)
U+2012 ('‒'): casefold unchanged  (same codepoint)
U+2013 ('–'): casefold unchanged  (same codepoint)
U+2014 ('—'): casefold unchanged  (same codepoint)
U+2212 ('−'): casefold unchanged  (same codepoint)
U+FE63 ('﹣'): casefold unchanged  (same codepoint)
U+FF0D ('－'): casefold unchanged  (same codepoint)
```

Casefold does NOT touch any of the dash codepoints, so fold-BEFORE-casefold is not semantically load-bearing for correctness in the current table — the ordering matters only if a future codepoint is both dash-like AND case-sensitive. The spec's justification ("casefold does not touch these codepoints, and the goal is for BGE-M3 and BGE‑M3 to compare equal") is accurate. The `_DASH_FOLDS` map at lines 1061–1070 (8 entries) matches the AC v0.3.0 #6 enumeration (8 codepoints) and the dash-fold table at lines 1100–1114 (also 8 codepoints, plus three pseudocode cases — casefold, whitespace-trim, non-match). **No finding.**

**A-3. Schema-compatibility AC coverage gap.** Lines 1429–1434 specify three outcomes for the schema-version check on every tool entry: (a) missing, (b) older, (c) newer. Only case (a) has a corresponding AC — v0.4.0 AC #6 ("Query on a space with no wiki types returns `[CONFIG ERROR]` naming `wiki.bootstrap`"). The `_outdated` and `_newer` outcomes are documented in the Implementation Plan but have **no AC in any version**. **Impact:** the test author writing `test_bootstrap.py`, `test_ingest.py`, `test_query.py`, or `test_lint.py` has no AC saying "an older schema-version value produces `wiki_schema_outdated`" or "a newer schema-version value emits a `wiki_schema_newer` warn-level log and the tool continues." Given the Implementation Plan says the check runs on *every* `wiki_*` tool entry, not just on `wiki_query`, this is a cross-cutting regression risk. **Recommended action:** add two ACs — one to v0.2.0 (likely AC#12) covering `_outdated` detected during `wiki_bootstrap` re-run, and one to v0.3.0 covering `_newer` warn-and-continue behavior. Or add a single "schema-compatibility" AC to each version that inherits behavior from the shared check.

**A-4. Bidirectional-relation rollback has no AC.** Implementation Plan line 424: "Write bidirectional relations: for every A→B relation, also write B→A. If either write fails, roll back both writes and record the failure in the WikiLog." Deliverables line 780 lists "bidirectional relation rollback" as test coverage. But the v0.3.0 AC list:
- AC #1 asserts bidirectional relations are *created*.
- AC #3 asserts partial-failure produces a coherent response with `status: "partial"`.
- Neither AC says "if B→A write fails, A→B is reverted and neither direction is visible in Anytype."

**Impact:** a test author could satisfy AC #1 by creating both directions, satisfy AC #3 by leaving A→B in place with a partial warning, and never exercise the rollback path. The lint suite's asymmetric-relation check would flag this post-hoc, but the ingest-time rollback invariant is the thing the Implementation Plan commits to. **Recommended action:** add v0.3.0 AC "If either direction of a bidirectional relation write fails, both directions are rolled back and the relation does not appear in Anytype. The WikiLog records `relation_rollback` with the attempted A/B object IDs."

**A-5. Concurrent-ingest test mechanism under-specified.** AC v0.3.0 #5 makes three assertions (same-space rejected, cross-space succeeds). The Test Plan line 1709 says "two overlapping `wiki_ingest` calls against the same space → second returns `[DATA ERROR] ingest_in_progress`." The Mock Strategy section (lines 1324–1331) says `respx` mocks `httpx` for API responses and `freezegun` handles time. **None of that creates a concurrent-ingest race.** `fcntl.flock` is an OS-level advisory lock keyed to a file descriptor; `respx` is a `httpx`-layer mock and operates in a single event loop. The only way to truly test the lock is:
- Two threads acquiring the same flock (works — the kernel serializes threads on the same fd if they open separately).
- Two processes via `multiprocessing.Process` or `subprocess.Popen` (most realistic).
- A fake context manager injected in place of `space_ingest_lock` (unit-level — doesn't exercise the real lock).

The spec does not name which of these the test author should use. **Impact:** the test author defaults to the easiest path (mocked lock) and the real-race behavior ships untested. **Recommended action:** add a sentence to the Test Plan (line 1709): "The test uses `multiprocessing.Process` (or equivalent) to acquire the flock in a second process; a pytest-level threading.Thread or async gather against a mocked lock does not exercise the kernel-held flock and is insufficient."

**A-6. Prompt-injection AC too permissive at the Anytype boundary.** AC v0.3.0 #12: "the resulting IngestResult either drops the injected name (policy rejects control characters / suspicious prefix) OR overrides its `is_central` to false (cross-check fails). Assertion: no object with that name appears in Anytype." The OR branch says `is_central=false` is an acceptable outcome, but the final assertion says "no object with that name appears in Anytype." If the injected name passes the name policy (it's not a control-char, not a prompt-like prefix — just "AcmeCorp Is A Scam" which is ordinary English) and the cross-check only demotes `is_central` to false, the object **will still be created** with `is_central=false`. The AC is internally contradictory — the OR branch creates the object, the final assertion says the object is not present. **Recommended action:** pick one. Either (a) the policy rejects injected-looking names outright and the object is never created, OR (b) `is_central=false` demotion is acceptable and the final assertion becomes "no object with that name appears with `is_central=true`." The current text is not testable without interpreting which branch the test author should assert against.

**A-7. Wikipedia-fixture AC lacks network-resilience policy.** Success Criteria line 1662 uses a live URL (`https://en.wikipedia.org/wiki/Mamba_(deep_learning_architecture)`). The AC does not specify behavior on:
- Wikipedia content update (new paragraphs, renamed entities → counts shift).
- Network outage at pre-release time.
- Wikipedia TOS / rate-limit edge.
- Schema changes to the article's HTML structure (infobox renames, new templates).

The AC says "Pass rule: a single clean run meets every count above. Re-run on any extraction-model change." What it does not say: what to do if the fixture stops passing due to a Wikipedia-side change rather than a wiki-library-side regression. **Recommended action:** capture a pinned archive.org snapshot of the Mamba page at spec-sign-off time; use the archive URL as the canonical fixture; note in the Success Criteria that the live URL is the aspirational target but the archive URL is the release-gate. This is ~15 minutes of work and eliminates an indefinite future maintenance surface. Alternatively: re-cast the Wikipedia fixture as a soft target and use a locally-bundled markdown file as the hard fixture.

**A-8. Performance-gate spec inconsistency.** Success Criteria line 1680 states the v0.5.0 lint perf target as "**under 60 seconds**" with no hardware qualifier. v0.5.0 AC #6 states the same target as "< 60s on Jan's Mac Mini M4 (p95 over 3 runs)." The Success Criteria should carry the same qualifier the AC does, or both should be moved to a shared "Performance Gates" subsection with one canonical formulation. Equivalent inconsistency check on v0.2.0 <30s and v0.4.0 <5s: both carry the Mac Mini M4 qualifier in the AC and also appear in Success Criteria. v0.2.0 (line 1652) says "under 30 seconds" without qualifier; v0.4.0 (line 1672) says "under 5 seconds for a wiki of ≤ 200 objects (p95)" without qualifier. **All three Success Criteria lines (1652, 1672, 1680) should match their ACs.** R1 QA + Infra flagged the contributor-hardware concern (Advisory #8 in council-spec-r1); this is the same root cause surfacing as a spec-wording inconsistency.

**A-9. v0.2.0 AC #6 is not CI-assertable (acknowledge, don't block).** "< 30s on a clean space (p95 over 5 runs on Jan's Mac Mini M4)" — this is a maintainer-local gate, not a CI gate. Same concern R1 QA voiced for AC #7 ("unambiguous decision"). Both ACs are acceptable as maintainer-local, but the spec should label them explicitly. The spec already labels verify-anytype-writes.sh as "maintainer-local" in the CI runnability paragraph (line 1295); it should do the same for performance ACs. **Recommended action:** add a sentence to each performance AC: "This AC is maintainer-measured-at-release-time. CI runs a sanity timing check (must complete within 5× the target) but does not enforce the p95 budget."

**A-10. Idempotency partial-state (Source exists, entities don't) has no AC.** v0.2.0 AC #2 says re-running bootstrap produces "no duplicates." v0.3.0 AC #2 says re-ingesting the same URL produces "0 created, ≥ 1 updated." Neither addresses a third case I think is realistic: the operator runs `wiki_ingest(url=X)`, the fetch succeeds and the Source object is created, extraction then fails (e.g. Ollama dies), the ingest returns `status: "partial"`, the Source exists in Anytype but no entities or concepts do. The operator reruns `wiki_ingest(url=X)`. What is the expected behavior? Does the library detect that a Source for this URL already exists and treat this as a resume? Does it create a second Source? Does extraction run again and create the entities, then relate them to the existing Source? The spec does not say. **Recommended action:** add v0.3.0 AC "Re-running `wiki_ingest(source=X)` after a prior partial-failure that created only the Source object reuses the existing Source, re-runs extraction, and attaches newly-created entities/concepts to it." Or explicitly document this as a v0.6.0+ concern and name it as out-of-scope for v0.3.0.

**A-11. Mock strategy scope decision is defensible.** Hypothesis is scoped to `ExtractionModel` parsing (line 1232). My initial concern was that entity-resolution is more complex (normalize_title + fuzzy match + embedding similarity). On reflection, entity resolution is already parametrized over the explicit dash-fold table, which is exactly the kind of table Hypothesis would generate anyway — and a Hypothesis strategy that generated Unicode strings would very likely produce false positives (e.g. generating U+2011 and asserting it normalizes to "-" is what the parametrized test already does; generating random surrogates is adversarial without clear expected behavior). Hypothesis on `ExtractionModel` parsing is higher-leverage because the shape of adversarial JSON (extra keys, wrong types, oversized fields) is open-ended in a way the dash-fold table is not. **No action.** The scope decision is right, and R1 QA's endorsement is right.

**A-12. Corrupted `patch-decision.md` failure-mode has no AC.** R1 QA noted this ("5 of 6 critical rows have ACs"). The Failure Modes table (line 1481) documents behavior: `wiki_ingest` and `wiki_query` refuse to start and return `[CONFIG ERROR] patch_decision_missing_or_invalid`. There is no AC in v0.3.0 or v0.4.0 covering this. **Recommended action:** add to v0.3.0 ACs and v0.4.0 ACs: "Missing or malformed `patch-decision.md` → `[CONFIG ERROR] patch_decision_missing_or_invalid` before any Anytype write or URL fetch." Low cost, closes a gap R1 QA already named.

---

## Traceability spot-check (AC ↔ Test Plan ↔ Failure Modes)

| AC | Test Plan line | Failure Mode | Status |
|---|---|---|---|
| v0.2.0 #1–5 bootstrap | 1694–1699 | row 1468 | Traced |
| v0.2.0 #6 perf | 1694 implicit | — | Untraced (A-9) |
| v0.2.0 #7 verification | maintainer-local, 1295 | — | Documented as local-only |
| v0.2.0 #11 respx mock | 1324–1331 | — | Traced |
| v0.3.0 #1 creation | 1702 | — | Traced |
| v0.3.0 #2 idempotence | 1703 | — | Traced |
| v0.3.0 #3 partial | 1706 | row 1469 | Traced |
| v0.3.0 #4 SSRF | 1707 | — | Traced |
| v0.3.0 #5 concurrent | 1709 | row 1469 | Partially traced (A-5) |
| v0.3.0 #6 dash-fold | 1708 | — | Traced (8/8 codepoints) |
| v0.3.0 #7 malformed | 1710 | row 1469 | Traced |
| v0.3.0 #8 empty source | — | row 1478 | Test case implicit |
| v0.3.0 #9 reindex | — | row 1470 | Test case implicit |
| v0.3.0 #10 invalid hint | — | — | Test case implicit |
| v0.3.0 #11 ollama not pulled | — | row 1482 | Test case implicit |
| v0.3.0 #12 prompt-injection | — | — | Test case in AC text (A-6) |
| Bidirectional rollback | 780 deliverable, 1705 | — | AC MISSING (A-4) |
| v0.4.0 #1–3 tier modes | 1714–1716 | — | Traced |
| v0.4.0 #4–5 file-back | 1717–1718 | — | Traced |
| v0.4.0 #6 schema missing | 1719 | — | Traced |
| v0.4.0 #7 perf | 1720 | — | Maintainer-local |
| Schema outdated | — | — | AC MISSING (A-3) |
| Schema newer | — | — | AC MISSING (A-3) |
| v0.5.0 #1 orphan | 1723 | — | Traced |
| v0.5.0 #2 pipeline_orphan | 1724 | — | Traced |
| v0.5.0 #3 asymmetric | 1725 | row 588 | Traced |
| v0.5.0 #4 stale | 1726 | — | Traced |
| v0.5.0 #5 severity filter | 1727 | — | Traced |
| v0.5.0 #6 perf | 1728 | — | Maintainer-local (A-8 inconsistency) |
| v0.5.0 #7 empty_type | — | — | Covered by AC but no Test Plan line |
| contradiction_unresolved | — | — | AC MISSING (A-1) |
| oversized | — | — | AC MISSING (A-1) |
| stale_stub | — | — | AC MISSING (A-1) |
| potential_duplicate | — | — | AC MISSING (A-1) |
| patch-decision.md | — | row 1481 | AC MISSING (A-12) |

Total: 35 traceable items, 5 ACs documented but not traced to a named Test Plan line (implicit), 7 AC-missing items (4 lint checks + 2 schema-compatibility outcomes + 1 relation rollback + 1 patch-decision).

---

## R1 Delta

Read R1 QA assessment (lines 74–91 of `council-spec-r1.md`) after forming my own view.

**Agreement:**
- AC quality endorsement of v0.3.0 #6 (dash-fold), v0.3.0 #5 (concurrent ingest), v0.4.0 #3 (boundary) — **concur.** These are the three best-formed ACs in the spec.
- v0.2.0 #7 "unambiguous decision" as human-judged / non-CI-assertable — **concur**, and I extend it to v0.2.0 #6 (perf on Jan's machine) with the same concern (my A-9).
- R1 advisories all landed — **concur** on concurrent-ingest, boundary test, and mock strategy. Hypothesis scope decision is defensible (my A-11 confirms independently).
- Regression guard via versioned test layout — **concur.** `_BaseAnytypeClient` changes trip both v0.2.0 and v0.3.0 client tests. Good design.
- Failure-modes table 5 of 6 critical rows with ACs, corrupted `patch-decision.md` untraced — **concur** and I add it to my findings as A-12.
- Performance gates lack contributor-hardware tier — **concur**, and I add that Success Criteria lines 1652/1672/1680 are not internally consistent with their ACs (my A-8).
- Pre-release checklists are convention-only — **concur** but I do not re-surface as a finding; it is council-level (Advisory #9 in r1 council notes).

**Disagreement:**
- R1 QA Advisory #7 says "5 of 9 lint checks have no named test." The real count is **4 of 9**, not 5. `empty_type` is covered by AC v0.5.0 #7. R1's miss list included `empty_type` incorrectly. This is a counting error, not a substantive miss — the gap is still the single largest coverage hole and my A-1 carries the same action item. Worth calibrating that R1 QA got the count off by one.

**Missed items by R1 QA (and by me, until I looked):**
- **Bidirectional-relation rollback AC missing (A-4).** R1 QA did not call this out. Deliverable says tests will cover it, Test Plan says A→B iff B→A post-ingest, but no AC commits to the rollback invariant. Substantive — the Implementation Plan makes a specific commitment about atomicity that no AC enforces.
- **Schema-compatibility outcomes (A-3).** R1 QA did not trace the three-outcome compat check to ACs. Implementation Plan defines missing/outdated/newer; only missing has an AC (v0.4.0 #6, query-only). Cross-cutting regression risk — the check runs on every tool entry.
- **Concurrent-ingest test mechanism (A-5).** R1 QA endorsed the three-assertion AC as "exactly what S37 asked for" but did not probe how `respx` (synchronous httpx mock) exercises `fcntl.flock` (OS-level advisory lock). They don't — a test author taking R1's endorsement at face value could write a test that never exercises the real race.
- **Prompt-injection AC internal contradiction (A-6).** R1 QA did not read AC v0.3.0 #12 closely. The OR branch (demote to `is_central=false`) is inconsistent with the final assertion (no object with that name appears in Anytype). Testable only by picking a branch.
- **Idempotency partial-state (A-10).** R1 QA did not surface the Source-exists-entities-don't re-run case.
- **Performance-gate Success Criteria inconsistency (A-8).** R1 QA + Infra concurred that all perf gates cite Jan's hardware. What neither noted is that the Success Criteria section drops the Jan's-hardware qualifier on lines 1652 / 1672 / 1680 while the ACs carry it. The spec is inconsistent with itself.

**R1 QA quality signal:** R1 QA caught the big hole (lint checks, even if off by one), endorsed the right things (boundary test, dash-fold parametrization, concurrent-ingest assertions, mock tiers), and correctly identified the human-judged AC (v0.2.0 #7). But R1 missed bidirectional rollback, the cross-cutting schema-compat check, the concurrent-ingest test mechanism, and the prompt-injection AC's internal contradiction. These are the kind of misses that come from document-level reading without probing the gap between Implementation Plan and AC list.

---

## Calibration verdict on R1

**R1 QA assessment was directionally correct but under-powered.** The three specific items R1 endorsed as "unusually disciplined" (boundary test, dash-fold, concurrent ingest) were correctly identified. The one substantive gap R1 called out (lint check coverage) was real but miscounted. What R1 missed — bidirectional-relation rollback AC, schema-compat outcomes, concurrent-ingest test mechanism, prompt-injection AC internal contradiction, Success Criteria / AC inconsistency on perf gates — are exactly the kind of defects a specialist QA review should catch: gaps between what the Implementation Plan commits to and what the AC list enforces. They are not algorithmic correctness defects of the kind the #172 re-review found in R1 impersonators (those were actual bugs in core algorithms; these are traceability gaps in a spec).

**Net assessment: R1 QA produced a directionally-right sign-off with conditions, but four items it should have caught and did not.** None of the four would have changed the R1 verdict from SIGN OFF WITH CONDITIONS — but they would have added substance to the conditions. The R1 recommendation to advance to test phase still stands; this re-review tightens the conditions attached to that advance.

I **SIGN OFF WITH CONDITIONS** — same verdict class as R1 QA, additional conditions.

Conditions attached (must close before test-phase authoring begins, not before spec advances):

1. Add four lint-check ACs (A-1): `contradiction_unresolved`, `oversized`, `stale_stub`, `potential_duplicate`.
2. Add schema-compatibility ACs for `_outdated` and `_newer` outcomes (A-3).
3. Add a bidirectional-relation rollback AC to v0.3.0 (A-4).
4. Add a Test Plan note naming the mechanism for concurrent-ingest testing (A-5).
5. Resolve the prompt-injection AC internal contradiction (A-6): pick one branch.
6. Align Success Criteria performance wording with AC performance wording on Jan's Mac Mini M4 qualifier (A-8).
7. Add `patch-decision.md`-missing AC to v0.3.0 and v0.4.0 (A-12).

The remaining advisories (A-7 Wikipedia fixture, A-9 CI-assertability labeling, A-10 partial-state idempotency) are polish — desirable but not test-phase-blocking.

---

**QA Director sign-off: SIGN OFF WITH CONDITIONS.**
