# Council Impl Review R1 — CPO (Product / Scope / User-Value Governance)

**Ticket:** #426 — Surface concept contradictions in wiki_lint
**Phase:** Post-implementation governance review
**Reviewer:** Chief Product Officer
**Date:** 2026-06-25
**Verdict:** SIGN-OFF (YES) — 0 BLOCKING

---

## Summary

#426 is the declared closure-condition follow-up for #325. #325 shipped concept
contradiction *detection* at ingest, but `wiki_lint` only *surfaced* entity
contradictions — concept contradictions were detected, cross-linked, and then
silently ignored by the health check. That is a textbook trust-eroding gap: the
health signal told fleet/Jan "clean" when it was not, on a knowledge type the
product treats as first-class. This ticket closes the gap.

From a product standpoint the deliverable is faithful, focused, and correctly
sized. The user-visible behavior change is a single, well-motivated line in
`lint.py` (`tk == "wiki_entity"` → `tk in ("wiki_entity", "wiki_concept")`),
mirroring the tuple idiom already used by the adjacent stale/needs-review checks
(`lint.py:506,516`). Concept contradictions now fire `critical` and are resolved
by setting `wiki_last_reviewed` — behavior identical to entities, which is exactly
what a user would expect and exactly what the spec's intent demanded. No new
mental model is introduced for the user; the existing one is simply made complete.

The bulk of the diff (bootstrap reconcile, +137 LOC) is *enabling machinery*, not
scope creep — `wiki_concept` lacked the `wiki_last_reviewed` field that lint uses
to clear the finding, and the bootstrap path skipped existing types, so the field
could never reach already-bootstrapped spaces. Without the reconcile, the lint gate
would fire an *un-clearable* `critical` — the precise broken UX the ticket exists to
avoid. The reconcile is the minimum viable mechanism to make the user-facing feature
*usable*, and it was built general (iterates all `WIKI_TYPES`) rather than as a
`wiki_concept` special-case — a reasonable, documented trade-off that pays forward
for any future schema addition without adding user-facing surface area.

The required-re-bootstrap migration is the one genuine product wart, but it is
handled about as well as it can be (see ADVISORY-1). The user-facing docs
(README/CHANGELOG/MIGRATIONS/deploy-runbook) are clear, honest, and written for the
open-source audience, not just internal fleet.

---

## Findings

### BLOCKING

None.

### ADVISORY

**ADVISORY-1 — Required re-bootstrap is a product wart, but correctly mitigated; consider a self-healing path later.**
- *Description:* The feature only works after an operator manually re-runs
  `wiki_bootstrap` on every existing space. A space that runs the new `wiki_lint`
  without re-bootstrapping is stranded in an un-clearable `critical` state (the
  finding fires but there is no `wiki_last_reviewed` field to set). The team
  mitigated this correctly: the lint gate and the reconcile ship in the same change
  (no half-shipped journey), and the sequencing is documented prominently in
  MIGRATIONS.md (with a ⚠️ warning block) and a new `docs/deploy-runbook.md` with a
  "golden rule" and a numbered deploy sequence.
- *Impact:* For the **internal** audience (fleet/Jan) this is low-risk — the release
  owner controls all spaces and the runbook is explicit. For the **public**
  open-source audience it is a sharper edge: a community user who upgrades the
  package and runs `wiki_lint` before reading MIGRATIONS will hit a confusing
  un-clearable critical with no in-product nudge. The spec already deferred the
  obvious in-product mitigation (a lint guidance-warning when `wiki_concept` lacks
  `wiki_last_reviewed`) as out of scope. I agree with deferring it for *this* ticket
  — it is not required for correctness and adding it here would be scope creep — but
  I want it tracked as the right next product increment for the public audience.
- *Recommended action:* No change to this deliverable. Track the deferred
  lint guidance-warning (spec Deferred Items / SF-4) as a candidate follow-up
  ticket; it converts a silent footgun into a self-explaining one for community
  users. Advisory only — Jan decides whether the public-audience risk justifies a
  follow-up now or later.

**ADVISORY-2 — Reconcile generality is justified but slightly exceeds the literal ticket scope; documented and acceptable.**
- *Description:* The ticket's user-facing objective is narrow (surface concept
  contradictions). The implementation adds a *general* idempotent type-reconcile
  capability to bootstrap that runs on every bootstrap for all six wiki types, not
  just `wiki_concept`. This is, strictly, more than the ticket asked for.
- *Impact:* Net positive. The alternative (a one-off `wiki_concept` migration script)
  was explicitly considered and rejected in the spec because it would not close the
  bootstrap gap for future schema additions. The generality is the same code path
  either way — the loop already iterates all types — so it is not gold-plating that
  adds maintenance surface; it is the natural shape of the fix. Steady-state cost is
  6 GETs per bootstrap, negligible and consistent with the local-first product
  principle (no new cloud calls, no new trust boundary). The replace-not-merge
  footgun it introduces is the real risk, but that is a CTO/CSO concern and was
  defended in depth (four guards + audit log + regression tests); from a product/
  viability angle the maintenance burden is proportional to the value.
- *Recommended action:* None. Accept the documented trade-off.

**ADVISORY-3 — User-facing docs are strong; one honesty check passed.**
- *Description:* I verified the README, CHANGELOG, MIGRATIONS, and deploy-runbook
  copy against the actual behavior. The README "surfacing gap" disclosure (which
  honestly warned users not to over-trust a clean contradiction column) is correctly
  *replaced* with a positive "both entity and concept contradictions are now flagged"
  statement that still preserves the broader honesty caveat ("Don't over-trust a
  clean contradiction column" — because detection is still bounded to already-linked
  peers). That nuance was retained rather than over-claimed, which is the right call
  for an open-source tool's credibility. CHANGELOG correctly attributes both #325 and
  #426 and states the re-bootstrap requirement inline.
- *Impact:* Positive — the closure signal for this ticket lives substantially in
  docs, and the docs land it honestly.
- *Recommended action:* None.

---

## Split Recommendation

**No split recommendation.**

This is a post-impl review, so the bar is "was proceeding un-split unsafe?" — it
was not. More importantly, even prospectively this ticket should NOT have been split.
Although the diff touches four source areas (schema, client, bootstrap, lint), they
are not *independently shippable user increments* — they are a single dependency
chain culminating in one user-facing outcome:

- The lint gate (the actual user value) is meaningless without `wiki_last_reviewed`
  on `wiki_concept` (schema).
- The schema field is unreachable on existing spaces without the bootstrap reconcile.
- The reconcile needs the new `get_type`/`update_type` client methods.

Shipping any subset independently would either deliver nothing the user can perceive
or — worse — reintroduce the un-clearable-`critical` footgun (the exact reason the
spec mandates the gate and reconcile ship together). The components are sequenced
internal steps toward one increment, not separable concerns. A reviewer can follow
the PR as one coherent story. Keeping it whole was the correct decomposition.

---

## Addendum Verification (prior CPO items)

- **CPO-1 (spec-addendum-post-spec item 7) — Migration sequencing enforced at
  release; "re-running `wiki_bootstrap` is REQUIRED" must appear in the deploy
  runbook in addition to MIGRATIONS.md.** ✅ HONORED. The lint gate and reconcile
  ship in the same change (confirmed: both present in this diff). MIGRATIONS.md has a
  dedicated 0.4.2 section under "Unreleased" with the REQUIRED language and a ⚠️
  un-clearable-`critical` warning. `docs/deploy-runbook.md` was newly created with
  the golden rule and a numbered deploy sequence. Fully satisfied.

- **CPO-ADV-1 (spec-addendum-post-test item 2) — Complete the AC#3 prose docs:
  CHANGELOG 0.4.2 entry, MIGRATIONS note, README surfacing-gap clause flipped to
  "live".** ✅ HONORED. (a) CHANGELOG records the 0.4.2 bump and concept-contradiction
  surfacing-is-live. (b) MIGRATIONS note present (see above). (c) README clause
  replaced with a positive "now flagged by `wiki_lint`" statement; the automatable
  substring-absence test (`test_docs_surfacing.py`) and the updated
  `test_docs_disclosure.py` cover it. All three landed.

- **CPO-ADV-2 (spec-addendum-post-test item 3) — Migration sequencing + deploy
  runbook; the repo had no operational runbook and MIGRATIONS alone did not satisfy
  the "deploy runbook" requirement; the 0.4.2 note belongs in the Unreleased section
  with an explicit un-clearable-`critical` warning.** ✅ HONORED. A new
  `docs/deploy-runbook.md` was created (distinct from the PyPI-only `releasing.md`).
  The MIGRATIONS note is in the Unreleased section and carries the explicit
  un-clearable-`critical` warning, following the v0.3.0 precedent. Fully satisfied.

All three prior CPO items honored. No regressions against my earlier advisories.

---

## Sign-off

**SIGN-OFF: YES.**

*Rationale:* The deliverable faithfully implements the spec's intent and closes the
#325 closure-condition gap with real, perceivable user value — the health check no
longer lies about concept contradictions. Scope is disciplined: the user-facing
change is a one-line gate widening; the larger bootstrap-reconcile machinery is the
minimum necessary to make that change *usable* on existing spaces and is a justified,
documented general-purpose trade-off rather than gold-plating. The migration's one
genuine wart (required re-bootstrap) is mitigated correctly — gate and reconcile ship
together, and the sequencing is documented prominently in both MIGRATIONS.md and a
new deploy runbook honoring all three of my prior advisories. The user-facing docs
are clear and honest for the open-source audience. No blocking product concerns; no
split warranted. I sign off.
