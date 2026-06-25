# QA Director Council Assessment — Post-Spec R1 — #426

## Sign-off: APPROVE WITH CONDITIONS

## BLOCKING findings

None.

(Rationale for not blocking: the design's highest-risk path is adequately
test-gated and the AC coverage is verifiable. The one defect below is a
concrete, scoped test-plan correction, not a design hole — but it MUST be
carried into the test phase as a fixed instruction, so I record it as a
condition rather than a soft advisory.)

## ADVISORY findings

### A-1 — Test Plan instructs the test-writer to ignore a REAL `0.4.1` pin that the schema bump WILL break (regression-risk gap)
**Description.** Spec §1 bumps `WIKI_SCHEMA_VERSION` `0.4.1` → `0.4.2`. The
Test Plan's "Version bump (M3)" note (`spec.md:494-497`) states: *"There is NO
hardcoded `0.4.1` assertion in `test_bootstrap.py` … Do not invent a test edit
for a non-existent pin."* This is **false**. `tests/wiki/test_bootstrap.py:855`
`TestSchemaVersionBumped::test_wiki_schema_version_is_041` hard-asserts
`WIKI_SCHEMA_VERSION == "0.4.1"` (line 868). The R1 lead spot-check
(`review-r1.md:97`) also recorded this pin as "NOT FOUND" — the same factual
error propagated from R1 into the finalized spec and was not caught in R2.
**Impact.** After the §1 bump, `test_wiki_schema_version_is_041` deterministically
FAILS. Because the Test Plan affirmatively tells the test-writer the pin does
not exist, a literal-minded test/impl worker may treat the failure as a
genuine regression, get blocked, or "fix" it incorrectly. This is exactly the
class of silent test-suite breakage QA exists to prevent. It does not threaten
graph integrity, but it will halt or confuse the test phase.
**Recommended action.** Correct `spec.md:494-497`: the test-writer MUST update
`test_wiki_schema_version_is_041` to pin `"0.4.2"` (and refresh its docstring/
ticket reference) as part of the schema-bump step. The spec's own advice to
`grep -rn "0.4.1" tests/` before the bump lands is correct and would have
surfaced this — keep it, but invert the stated conclusion. Note also the stale
docstring at `tests/wiki/test_lint.py:1952` ("version older than '0.4.1'");
that one is cosmetic (the value is data-driven via `_schema_outdated_response()`,
no assertion breaks), fix opportunistically.

### A-2 — Carried-forward `get_type` read-side live-probe (BL-6.4) is a manual precondition with no automated gate — could be silently skipped
**Description.** The spec correctly makes the reconcile safe-by-construction
(monotonic-union guard, name/format-from-declared, pagination/shape guard) and
defers the empirical raw-`GET /types/{id}` field-set/pagination probe to the
impl/test phase as a non-blocking precondition (`spec.md:529-543`,
Open Questions). There is no automated artifact that fails if the probe is not
run — it relies on a human recording the transcript in `research.md`.
**Impact.** Acceptable residual risk *given* the three code-level guards (a
truncated/sparse echo aborts the reconcile rather than corrupting the graph).
But if the probe is skipped, the team ships on the assumption that the guards
are exercising the real shape, with no evidence. Low likelihood of corruption,
moderate likelihood of a silently-non-functional reconcile (e.g. every concept
type aborts via the pagination guard because the live shape was never confirmed).
**Recommended action.** The impl/test phase MUST (a) run the probe and commit
the `research.md §1` read-side transcript, and (b) make at least one
`test_reconcile_*` mock fixture mirror the *actual* observed `get_type` shape
(per-property key field, presence/absence of `name`/`format`, pagination shape)
rather than an invented one — otherwise the tests prove the guards against a
fictional contract. The chair should make committing the probe transcript an
explicit gate item for the impl-phase sign-off.

### A-3 — `test_reconcile_partial_failure_recovers_on_rerun` is the only guard on the marker-ordering invariant; ensure it asserts the marker state, not just recovery
**Description.** SF-3's recovery test (`spec.md:486-489`) is the sole automated
proof of the "version marker stamped only after the loop" invariant that makes
a mid-loop `update_type` failure recoverable. The spec text is correct and R2
verified both markers (collection `bootstrap.py:422-424`, WikiLog `:458`) are
post-loop.
**Impact.** If this test only asserts "re-run completes" without asserting the
marker is unstamped after the first (failing) run, a future refactor that moves
the marker before the loop would still pass the recovery half by accident,
silently reintroducing the unrecoverable-partial-reconcile failure mode.
**Recommended action.** The test-writer MUST assert all three: (1) the error
propagates out of `wiki_bootstrap`, (2) the schema-version marker is NOT stamped
after the failing run (assert on the PATCH-capture / object state), and (3) the
clean re-run completes the remaining type. The spec already enumerates these;
flag it so the assertion on (2) is not dropped as "implied."

### A-4 — `test_reconcile_no_op_when_complete` is not fail-first by design; ensure fail-first tests are confirmed RED before impl
**Description.** SG-a correctly labels `test_reconcile_no_op_when_complete` as a
forward regression guard (passes against current unimplemented code), while
`test_reconcile_adds_missing_property`, `test_reconcile_never_drops_existing_properties`,
and `test_concept_contradiction_unresolved` are fail-first. The current code
state confirms they will be RED: the lint gate is `wiki_entity`-only
(`lint.py:490`), and `get_type`/`update_type`/`types_reconciled` do not yet
exist (verified). So the fail-first tests cannot trivially pass.
**Impact.** Low — but a test that does not import a yet-missing symbol can
ERROR (collection error) rather than FAIL, which some workers mis-read as
"already failing for the right reason." The distinction matters for
test-first verification integrity.
**Recommended action.** The test phase MUST run the new tests against the
pre-impl tree and record that the three fail-first tests FAIL on a
*meaningful assertion* (gate behavior / union contents), not merely ImportError
or KeyError on a missing result key. `test_reconcile_no_op_when_complete`
passing pre-impl is expected and acceptable per SG-a.

## Rationale

The Test Plan covers all three Acceptance Criteria with verifiable evidence:
AC#1 maps to `test_concept_contradiction_unresolved` (fires + clears + absent
cases, field-level assertions on `check`/`severity`); AC#2 maps to the four
`test_reconcile_*` cases plus `test_result_has_required_keys`; AC#3 is correctly
scoped as a manual-review gate with one automatable substring-absence check, an
honest and appropriate framing for docs. The single highest-risk path —
replace-not-merge graph corruption — is backed by a genuine union-vs-delta
regression test (`test_reconcile_never_drops_existing_properties`) layered on
three independent code-level guards, which is strong. The one material defect is
factual, not architectural: the spec (inheriting an R1 spot-check error)
wrongly tells the test-writer there is no `0.4.1` pin to update, when
`test_bootstrap.py:868` hard-pins it and the §1 bump will break it. That is a
correctable test-phase instruction, so I approve with the conditions above
(fix A-1 in the spec or the test-phase brief; gate A-2's live probe; tighten
A-3/A-4 assertion intent) rather than block.
