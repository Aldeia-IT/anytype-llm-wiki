# Council Meeting — Post-test (Round 1)

**Date:** 2026-06-25
**Ticket:** #426 — Surface concept contradictions in wiki_lint
**Phase reviewed:** test
**Client:** anytype-llm-wiki (internal Aldeia fleet tooling — shared wiki-memory MCP)

## Attendance

| Role | Present | Reason |
|------|---------|--------|
| Council Chair | Yes | moderator |
| QA Director | Yes | minimum roster — the deliverable IS the test suite; quality-gate review is the core mandate |
| Chief Technology Officer | Yes | chair decision — reviewer-diligence + the BL-6.4 read-side probe was the spec gate's hard entry condition |
| Chief Security Officer | Yes | chair decision — destructive replace-not-merge PATCH (graph-corruption footgun) is the dominant threat |
| Infrastructure Lead | Yes | chair decision — mandatory re-bootstrap migration + ordering invariant are operational concerns |
| Chief Product Officer | Yes | chair decision — continuity with spec council; AC#3 docs are half the user-visible closure signal |
| Legal Counsel | No | internal fleet tooling; no PII, licensing, or regulatory dimension |
| Client Advocate | No | not a client project; consumers are the agent fleet + Jan |

## Context Presented

#426 closes the "recorded-but-invisible" gap from #325: concept-contradiction *detection*
shipped in #325 (records into `wiki_contradictions`), but `wiki_lint` only surfaces *entity*
contradictions today, so concept contradictions never reach the fleet/Jan, who consume them
through the health check rather than by browsing Anytype. This was the explicit declared
closure-condition follow-up of #325.

The **test phase** authored fail-first (TDD) tests covering all four spec change-sites
(schema + `SYSTEM_PROP_KEYS`; new `get_type`/`update_type` client methods; bootstrap
read-modify-write reconcile; lint-gate widening) plus AC#3 docs, and honored test-phase
addendum items 1–6 from the spec council. The test phase also discharged the spec gate's
hard entry condition: the BL-6.4 raw `get_type` read-side live probe (recorded in
`research.md §1b`). Internal review ran R1 (NEEDS CHANGES — missing AC#3 automatable check)
→ R2 (APPROVED). Verified suite baseline: **16 failed** (all intended fail-first/regression
guards), no previously-passing test broken (`uv run --extra dev pytest`).

## Discussion

The council converged unanimously and independently. Each member ran the suite and verified
claims against source rather than trusting the debriefs.

- **The spec gate's dominant condition is discharged.** At the post-spec council, the
  unverified `get_type` *read*-side contract (BL-6.4) was the cross-functional theme — the
  council accepted the spec's "safe-by-construction" disposition only on condition the live
  probe became a hard entry condition before the reconcile PATCH ships. CTO and CSO both
  independently confirmed `research.md §1b` records a **real** raw `GET /types/{id}` probe
  against `wiki-validation-throwaway`: per-property field set (`object/id/key/name/format`;
  live uses `key` not `property_key`), and the completeness/nested-pagination dimension the
  CTO demanded — single-type GET carries **no `pagination` key**, array returned inline and
  complete. `_make_live_type_response()` (`test_bootstrap.py:2000`) mirrors this exact shape
  and drives the success-path reconcile tests; the pagination-abort mocks are explicitly
  labelled synthetic (defending an unadvertised future change).

- **The replace-not-merge graph-corruption footgun is defended by real fail-first tests**
  (CSO, QA, Infra concurring), from four independent angles: (a) union-not-delta —
  `test_reconcile_never_drops_existing_properties` asserts the PATCH payload carries the live
  custom user prop AND the missing declared prop, plus the F-2 system-prop exclusion;
  (b) pagination/partial-read abort — two cases asserting zero PATCH + `warnings[]`;
  (c) empty/None payload refused inside `update_type` itself (addendum item 6); (d) partial
  failure leaves the schema-version marker UNSTAMPED so a clean re-run recovers (addendum
  item 4, the ordering invariant).

- **Reviewer diligence was genuine, not a rubber-stamp** (CTO, QA). R1 caught a real BLOCKING
  gap — the test-writer had demoted AC#3's README check to "manual-review" with a
  rationalization that would have invalidated every fail-first test — and forced a portable
  automated substring-absence test (`test_docs_surfacing.py`), re-verified at R2 to fail on
  content (not IO). The inherited spec factual error (addendum item 1 / QA-1: the `0.4.1`
  version pin the spec wrongly claimed did not exist) was correctly discharged — the pin now
  positively asserts `0.4.2` and a `grep` sweep confirmed no other hardcoded pin.

- **Scope is coherent; no decomposition.** CTO and CPO independently declined to split. The
  five change-sites form one dependency chain with a deliberate safety coupling: the lint
  gate (§4) and bootstrap reconcile (§3) MUST ship together or existing spaces fire an
  un-clearable `critical`. The all-six-`WIKI_TYPES` reconcile generalization is justified
  forward-design (every non-concept type is a no-op this release), not creep.

- **The one material consumer risk** (CPO, Infra) is an un-clearable `critical` if the
  mandatory re-bootstrap migration sequencing is violated — the worst outcome for a lint
  tool, since it trains consumers to ignore the signal. Mitigated by ship-together + REQUIRED
  re-bootstrap in MIGRATIONS.md/runbook; recoverability is encoded in tests. Infra added a
  concrete new gap: **there is no operational deploy runbook in the repo** (`docs/releasing.md`
  is PyPI-publish only), so MIGRATIONS.md alone does not satisfy addendum item 7's
  "deploy runbook" clause — an impl obligation.

## Findings

### BLOCKING
None.

### ADVISORY

1. **[CTO-A1/QA-ADV-1/CSO-ADV-1/Infra] Partial-failure ordering-invariant assertion is
   vacuous pre-impl; impl-reviewer must confirm it has teeth post-impl.** Assertion B of
   `test_reconcile_partial_failure_recovers_on_rerun` (marker NOT stamped to `0.4.2` after a
   mid-loop failure) passes vacuously today because the unimplemented code stamps `0.4.1`.
   It is the **sole** automated guard on the marker-after-loop ordering invariant. The
   impl-reviewer MUST confirm the test actually fails if the marker stamp is moved before the
   reconcile loop. (Infra verified by source inspection that the invariant currently holds by
   construction at `bootstrap.py:281-285` vs. stamps at `:419`/`:446`.)

2. **[QA-ADV-3/CPO-ADV-1/CTO-A3] AC#3 prose docs are manual-review gates beyond the one
   automatable check.** The green README substring test covers only the surfacing-gap clause
   removal. The CHANGELOG 0.4.2 entry, the MIGRATIONS.md "re-bootstrap REQUIRED / un-clearable
   critical" note, and the README "surfacing is live" statement rest on manual inspection at
   the post-impl council. QA should enumerate them as hard checklist items.

3. **[Infra-3] No operational deploy runbook exists in the repo — impl must create/extend one.**
   `docs/releasing.md` is PyPI-publish only. Addendum item 7 requires "re-running
   `wiki_bootstrap` is REQUIRED" to appear in the deploy runbook *in addition to*
   MIGRATIONS.md; satisfying it requires a runbook file that does not currently exist. The
   MIGRATIONS.md 0.4.2 note belongs in the "Unreleased" section (`MIGRATIONS.md:89`) and must
   explicitly warn that running the new `wiki_lint` before re-bootstrapping yields an
   un-clearable `critical` (precedent at the v0.3.0 section, `MIGRATIONS.md:60-75`).

4. **[CTO-A4/QA-ADV-5/CSO] `update_type` refusal should settle on a single exception type.**
   The guard tests accept a broad exception tuple (`ValueError, AssertionError, TypeError[,
   KeyError]`) and `test_update_type_raises_on_empty_properties` retains a permissive
   `except Exception` fallthrough. Impl should standardize on a single refusal exception
   (suggest `ValueError`) and the impl-reviewer should tighten the corresponding assertion.

5. **[CSO-ADV-2/Infra/CTO-A2] Addendum items 7–8 (operational/release) carried forward.**
   Lint gate (§4) + reconcile (§3) MUST ship in the same change; the SG-e INFO-level union
   audit log emitted before each destructive PATCH must be durably captured by the deployment
   so a corruption event is reconstructable. Correctly untestable at the test phase; these are
   impl/release exit criteria.

## Decomposition

None. Both the CTO and CPO — the two members empowered to emit a SPLIT RECOMMENDATION —
explicitly declined. The reconcile infrastructure and the lint-gate widening are not
independently shippable: gate-alone strands existing spaces in un-clearable `critical`;
reconcile-alone delivers zero visible value. Shipping them together is the safe choice. The
change stays within single-PR / single-impl-lead bounds.

## Resolutions

No findings were withdrawn during discussion; all five members reached SIGN-OFF independently.
The recurring cross-functional concern from the spec gate (the `get_type` read-side contract)
was confirmed resolved by the BL-6.4 live probe, removing the only conditional attached to the
spec-gate approval.

## Recommendation

**Recommended target:** impl
**Confidence:** high
**Rationale:** The test phase is a faithful, verified, fail-first contract for the impl phase.
All four spec change-sites and all six test-phase addendum items are covered by substantive
(non-vacuous) assertions; the central graph-corruption footgun is guarded from four angles;
the spec gate's hard entry condition (BL-6.4 read-side probe) is discharged with mock fidelity
to the real contract; reviewer diligence was genuine; and the inherited spec factual error was
corrected. Zero BLOCKING findings. The impl phase must honor the five advisories — chiefly the
operational requirements (deploy runbook, ship-together sequencing, durable audit log) and the
AC#3 prose docs — captured authoritatively in `spec-addendum-post-test-r1.md` for the impl
lead. The watcher enforces autonomy policy and may route to `decide` if impl is not yet
autonomous; the council's finding-based recommendation is to advance to impl.
**Dissent:** None.
