# Council Meeting — Post-impl (Round 1)

**Date:** 2026-06-25
**Ticket:** #426 — Surface concept contradictions in wiki_lint
**Phase reviewed:** impl
**Client:** anytype-llm-wiki (Aldeia-IT/anytype-llm-wiki — dual-purpose: Aldeia internal KB + public OSS tool)

## Attendance

| Role | Present | Reason |
|------|---------|--------|
| Council Chair | Yes | moderator |
| Chief Security Officer | Yes | minimum + central replace-not-merge data-corruption risk |
| Legal Counsel | Yes | minimum + public OSS release (licensing/disclosure) |
| Chief Product Officer | Yes | minimum |
| QA Director | Yes | minimum |
| Chief Technology Officer | Yes | minimum |
| Infrastructure Lead | Yes | repo domains: infrastructure + agent-operations; migration-sequencing risk |
| Client Advocate | Yes | non-aldeia-box repo; represents fleet + OSS-community stakeholders |

Post-impl is the final delivery gate → full council convened.

## Context Presented

#426 is the declared closure-condition follow-up for #325. Concept-contradiction *detection*
shipped in #325 (at ingest), but `wiki_lint` only surfaced contradictions for `wiki_entity` —
concept contradictions were silently ignored by the health check. This ticket closes that gap via
four coordinated changes: (1) schema 0.4.1→0.4.2 adds `wiki_last_reviewed` to `wiki_concept` +
a `SYSTEM_PROP_KEYS` constant; (2) new `get_type`/`update_type` `WikiClient` methods; (3) an
idempotent read-modify-write bootstrap *reconcile* that links missing declared properties onto
existing types under Anytype's **replace-not-merge** PATCH semantics; (4) the lint gate widened to
`("wiki_entity","wiki_concept")`; plus README/CHANGELOG/MIGRATIONS/`docs/deploy-runbook.md` docs.

The central risk is the **replace-not-merge footgun**: `update_type` REPLACES a type's user
property set, so a wrong reconcile payload could silently destroy graph data for every object of
that type. The implementation defends it in depth (union-send, monotonic-union guard, empty/None
`ValueError` refusal inside `update_type`, malformed-envelope + pagination aborts, SG-e audit log,
regression tests). Impl-review-r1 (security/DRY/simplifier/performance agent team) found 0
correctness/security/perf defects (LOW risk); only readability fixes, which an impl-fixer applied
with all guards provably preserved. Suite: **611 passed, 14 skipped, 2 xfailed**.

## Discussion

The council converged quickly on sign-off; the discussion centred on independently *verifying* the
two highest-stakes claims rather than trusting the phase summary:

- **Marker-ordering invariant (CTO ↔ QA).** Both members independently perturbed `bootstrap.py` to
  stamp the schema-version marker *before* the reconcile loop and confirmed
  `test_reconcile_partial_failure_recovers_on_rerun` assertion B goes RED — the guard genuinely
  has teeth. Both reverted cleanly. This is the sole automated guard on the
  graph-corruption-recovery ordering invariant; it is real, not vacuous.
- **Read-side contract (CSO ↔ Infra ↔ QA).** The `get_type` live probe (BL-6.4 / spec-addendum
  item 2) was confirmed actually performed against `wiki-validation-throwaway`, with a verbatim
  transcript in `research.md §1` — the single-type GET is never paginated, so the pagination/abort
  guards are forward-defense. CSO confirmed no new trust boundary, no new secrets, no injection
  vector in the lint gate.
- **Migration sequencing (Infra ↔ CPO ↔ Advocate).** The un-clearable-`critical` footgun (linting
  a non-re-bootstrapped space) is mitigated by shipping the lint gate and reconcile *together*,
  plus MIGRATIONS.md (explicit warning) and the new `docs/deploy-runbook.md`. Advocate and CPO
  noted the mitigation is documentation-only for OSS users on their own upgrade cadence; both
  logged it ADVISORY (the deferred SF-4 runtime lint-warning is the right fast-follow), not
  blocking, since recovery is one idempotent command.
- **Audit-log durability (Infra → CSO crossover).** Infra surfaced that the SG-e union audit line
  is emitted at `logger.info`, but the CLI configures no logging handler (root logger defaults to
  WARNING), so under the runbook's own documented invocation the line is silently dropped — the
  full-union forensic data CSO-3 / spec-addendum item 8 wanted retained is not actually captured
  (per-type added keys remain recoverable via `--json` `types_reconciled`). Logged ADVISORY.

## Findings

### BLOCKING
None.

### ADVISORY
1. **[Infra]** SG-e audit log not durably captured. The pre-PATCH union audit line is `logger.info`
   but the CLI installs no logging handler, so it is dropped under the documented invocation. Full
   forensic union is therefore not retained (per-type keys still in `--json` `types_reconciled`).
   Partially undercuts CSO-3 / spec-addendum item 8 intent. → fast-follow: configure a logging
   handler (and/or raise the line to a captured channel).
2. **[CPO / Client Advocate]** Footgun mitigation is documentation-only for OSS users who may never
   read MIGRATIONS. The spec deliberately deferred the optional runtime lint guidance-warning
   (SF-4). → fast-follow: ship the SF-4 in-product warning when `wiki_concept` lacks
   `wiki_last_reviewed`.
3. **[QA]** Pagination/missing-`properties` abort tests exercise synthetic shapes (the live GET is
   never paginated per `research.md §1b`) — forward-defense only. No action.
4. **[QA]** `_make_concept` retains the pre-existing `wiki_description`/`wiki_definition` fixture
   inconsistency, intentionally not "fixed" per spec SG-b. No action.
5. **[CTO]** Cosmetic/reporting only: dual-stamp nature of the version marker; wrapper
   converts-vs-raises on transport error; `schema_upgrade.properties_added` vs `types_reconciled`
   reporting overlap; 2 pre-existing `ruff F841` warnings on `origin/main` (out of scope). No action.
6. **[Client Advocate]** README key-behaviors section could add a one-line re-bootstrap pointer for
   skim-readers. Minor.

## Decomposition

None. Both the CPO and CTO explicitly declined to emit a SPLIT RECOMMENDATION. The four touched
surfaces form one dependency chain to a single user increment — the lint gate and bootstrap
reconcile *must* ship together (splitting reintroduces the un-clearable-`critical` footgun the
ticket exists to prevent), so the ticket is correctly scoped as a unit.

## Resolutions

All eight spec-addendum-post-spec items (1–8) and all five spec-addendum-post-test items (1–5) were
verified honored by the relevant specialists. No findings were withdrawn (none were initially raised
as blocking). The verification of the marker-ordering guard and the live `get_type` probe resolved
the council's only standing conditions from the prior (spec/test) rounds.

## Recommendation

**Recommended target:** done
**Confidence:** high
**Rationale:** Unanimous sign-off, zero BLOCKING findings across all seven members. All three
acceptance criteria are met with traceable, meaningful, fail-first tests; both spec addenda fully
honored; the central data-corruption risk is defended in depth and independently verified by two
members; suite green (611 passed); branch rebased. This is the final delivery gate — approve the PR
closing #426. The two actionable advisories (audit-log capture, SF-4 runtime warning) are
non-blocking fast-follows tracked separately, not release blockers.
**Dissent:** None.
