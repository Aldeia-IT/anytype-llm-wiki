# Council Impl Review R1 — Client Advocate

**Ticket:** #426 — Surface concept contradictions in wiki_lint
**Reviewer:** Client Advocate (stakeholder lens — Aldeia fleet/Jan + Anytype OSS community)
**Date:** 2026-06-25
**Review type:** Post-implementation governance (NOT code review)

---

## Summary

This deliverable closes the declared #325 follow-up: `wiki_lint` now surfaces
`wiki_concept` contradictions at `critical` severity, exactly mirroring the existing
`wiki_entity` behaviour. The fleet and Jan finally get a health-check signal for
concept-level contradictions that were previously detected, cross-linked, but silently
ignored. That is precisely the stakeholder need stated in the spec Problem Statement —
delivered, with no scope creep and no gold-plating.

The deliverable correctly recognized that the lint gate alone would be a footgun (an
un-clearable `critical` with no `wiki_last_reviewed` field to set on `wiki_concept`), and
shipped the schema bump (0.4.2), the idempotent bootstrap reconcile, and the lint gate
**together** as one atomic, coherent change. The required re-bootstrap is the central ask
of existing users, and it is communicated honestly and prominently across three docs
(MIGRATIONS.md, docs/deploy-runbook.md, CHANGELOG.md) with an explicit warning about the
un-clearable-`critical` footgun.

From both stakeholder perspectives this is a clean, demo-ready release. The public docs
hold the developer-facing, no-fluff brand voice. I have no BLOCKING findings.

---

## Findings

### BLOCKING

None.

The two stakeholder risks I screened for are both adequately handled:

- **Un-clearable-`critical` footgun for users who skip the migration.** The risk is real
  (a space that runs the new `wiki_lint` without re-bootstrapping strands `wiki_concept`
  contradictions in an unresolvable `critical` state). But it is disclosed honestly and
  redundantly: MIGRATIONS.md carries a ⚠️ callout, docs/deploy-runbook.md makes
  "re-bootstrap before linting" the documented golden rule with a numbered sequence, and
  the CHANGELOG flags re-bootstrap as REQUIRED with cross-links. The mitigation is
  documentation rather than a code-level guard, which is a reasonable engagement decision
  given (a) bootstrap is idempotent and non-destructive so the recovery action is trivial
  and self-explanatory, and (b) the optional lint guidance-warning was explicitly deferred
  in the spec, not silently dropped. This does not block; see ADVISORY-1.

- **#325 closure expectation.** The #325 CHANGELOG entry previously promised concept
  surfacing as a follow-up; that promise is now fulfilled and the stale "not yet flagged"
  clause is removed from both CHANGELOG.md and README.md (verified: no residual
  surfacing-gap clause remains in user-facing docs). Acceptance Criterion #3 is satisfied.

### ADVISORY

**ADVISORY-1 — The footgun mitigation is documentation-only; a runtime nudge was deferred.**
- *Description:* A user who upgrades, skips `wiki_bootstrap`, and runs `wiki_lint` gets an
  un-clearable `critical`. The only guardrail is prose in MIGRATIONS/runbook/CHANGELOG. The
  spec deferred (SF-4) an optional `wiki_lint` guidance-warning when `wiki_concept` lacks
  `wiki_last_reviewed`. For Aldeia's own fleet this is low-risk (Jan controls the release
  sequence and the deploy runbook is followed). For the OSS community — who upgrade via PyPI
  on their own cadence and may never read MIGRATIONS.md — the silent-strand experience is a
  worse first impression and a plausible "why is lint broken?" GitHub issue.
- *Stakeholder impact:* Community user friction; potential support burden; mild reputational
  cost given the repo is Aldeia's public open-source presence.
- *Recommended action:* Accept for this release (documentation is sufficient and the recovery
  is one idempotent command). File the deferred SF-4 lint guidance-warning as a fast-follow
  ticket so a stranded user is told *exactly* what to run, rather than left to discover the
  migration note. Not a release blocker.

**ADVISORY-2 — Migration burden on the OSS community is reasonable but under-signposted at
the top-level entry point.**
- *Description:* For existing OSS adopters, "you must re-run a CLI command on every space
  before the new lint works" is a fair ask — bootstrap is idempotent, non-destructive, and
  cheap (≤6 GETs + 1 PATCH). The MIGRATIONS/runbook coverage is excellent. However, the
  README "Key behaviors" edit now simply states both contradiction kinds are flagged and
  resolved via `wiki_last_reviewed`; it does not hint that existing spaces need a
  re-bootstrap to get there. A reader who only skims the README could miss the prerequisite.
- *Stakeholder impact:* Minor. Discoverability gap for upgraders who read README but not
  MIGRATIONS.
- *Recommended action:* Optional — consider a one-line README pointer ("upgrading an existing
  space? re-run `wiki_bootstrap` first — see MIGRATIONS.md") near the contradiction bullet.
  Nice-to-have, not required.

**ADVISORY-3 — Stakeholder context files are thin on engagement/compliance dimensions.**
- *Description:* The `.aldeia/context/` set covers business, product, brand, and stakeholders
  well, but there is no `engagement.md` or `compliance.md`. For this internal/OSS dual-purpose
  product that is acceptable (no paying client, no client-specific regulatory regime), and the
  local-first / no-cloud-by-default principle in product.md is the de-facto compliance posture.
  Noting it only so the council is aware decisions are made against a deliberately lightweight
  context set, not a gap that affects this ticket.
- *Stakeholder impact:* None for #426.
- *Recommended action:* No action for this ticket.

---

## Brand / Voice Check

The new docs (deploy-runbook.md, MIGRATIONS.md entry, CHANGELOG, README edit) are concise,
technical, and free of marketing fluff — consistent with the developer-facing, practical
brand. The runbook's "golden rule" framing and the explicit blast-radius/audit-log guidance
are appropriately operational without over-explaining. Commit hygiene and documentation
quality meet the bar expected of Aldeia's public repo. Voice: PASS.

---

## Sign-off

**SIGN-OFF: YES**

**Rationale:** The deliverable serves the stated stakeholder need exactly — the fleet and Jan
now get a `wiki_lint` signal for concept contradictions, closing the #325 follow-up with no
scope creep. The required re-bootstrap is a reasonable, cheap, non-destructive ask of existing
users, and the central footgun (un-clearable `critical` on a skipped migration) is disclosed
honestly and redundantly across MIGRATIONS, the new deploy runbook, and the CHANGELOG. The
brand voice holds. My only substantive concern — that the footgun mitigation is
documentation-only for OSS users who upgrade on their own cadence — is a deferred, spec-
acknowledged item suitable for a fast-follow ticket, not a release blocker. No BLOCKING
findings.
