# Council Review — Spec R1 — CPO (Product)

**Ticket:** aldeia-box#325 — Contradiction Detection: Extend to Concepts
**Phase:** Spec, post-council Round 1
**Reviewer:** Chief Product Officer (product strategy / user value / scope discipline)
**Date:** 2026-06-18

> Users here = the agent fleet + Jan operating Aldeia's internal fleet-memory infrastructure, not external customers. "User value" is read through that lens.

---

## Verdict: SIGN-OFF (with one ADVISORY that must reach the Decide gate)

The re-scope is product-sound. The confined detection core delivers real, standable-on-its-own value, respects the ticket's explicit "confined extension of #287" framing, and the deferred surfacing work is well-framed enough not to be silently dropped. The single most important thing is that the scope choice is a genuine product decision that belongs to Jan at Decide — the spec correctly routes it there rather than burying it. No BLOCKING product findings.

---

## BLOCKING

None.

---

## ADVISORY

### A1 — The scope call is a real product decision; it must be made explicitly at Decide, not defaulted.
**Description.** The crux question — ship confined detection-only core now (option a) vs. fold surfacing back in (option b) — is correctly surfaced to Jan. My product read favors **option (a)**, but the decision is load-bearing and should be made consciously, not by inertia. The risk is not that the spec is wrong; it is that "advance the core" becomes the silent default and the surfacing follow-up never gets a ticket number.
**Impact on product/users.** If surfacing never ships, the realized end-user payoff (an operator/agent *seeing* a concept contradiction in `wiki_lint` output) is deferred indefinitely. The core writes correct data that, for the primary consumption path (lint), remains invisible.
**Recommended action.** At Decide, Jan should make an explicit a/b call AND, if (a), require the follow-up ticket be filed before #325 closes (not "later"). Tie #325's closure to the follow-up's existence.

### A2 — Detection-without-surfacing is a partial-value increment, not zero-value — but the spec slightly over-states "browsable in Anytype" as user value.
**Description.** The spec leans on "concept contradictions ARE recorded in `wiki_contradictions` and browsable in Anytype" to argue the core stands alone. That is true and matters, but for *this product's actual users* (agents + Jan), the designed consumption surface is `wiki_lint`, not manual Anytype graph browsing. An agent will not discover a contradiction by manually opening the linked object in Anytype; it consumes lint output. So the core's standalone value is real but is mostly **latent / foundational** (correct graph state that the follow-up activates) plus a modest direct win (a human spot-checking in Anytype, and the cross-link itself being present for any future consumer).
**Impact on product/users.** Honest framing matters so Jan weighs the decision correctly: the core is "lay the rails correctly, light them up next ticket," not "users get the feature now." The README/CHANGELOG wording in the Implementation Plan already gets this right (it explicitly says concept contradictions are "recorded and browsable… but not yet flagged by lint") — keep that honesty; do not let it drift toward overclaiming "contradiction detection for concepts shipped" without the surfacing caveat.
**Recommended action.** Preserve the caveated README/CHANGELOG language as specified. Do not market the core as user-complete. This is consistent with the QA Director's concern that ACs match real user needs — flag to QA that the ticket's literal ACs are satisfied while the *user-visible* payoff is in the follow-up.

### A3 — Scope discipline is being respected, not scope-shaved — but only because the deferral is honestly motivated by a genuine cost discovery.
**Description.** I specifically tested whether this is scope-shaving (deferring the payoff to hit a smaller diff). It is not. The deferral is driven by BL-R2-1: surfacing requires a genuinely new bootstrap capability (link a declared property onto an already-existing type) that no code path in the repo currently performs, plus an unverified Anytype API dependency. That is a materially different and larger unit of work with its own review surface and a real unknown. Splitting a confined, low-risk, fully-AC-satisfying core from a larger, riskier capability is textbook good scope discipline, and it matches the spec-scope brief's explicit "confined extension… reuse the detect + cross-link path, not a new approach" mandate. Folding the bootstrap capability in (option b) would be the scope *creep* here, not the discipline.
**Impact on product/users.** Shipping the core now de-risks the foundation and lets the riskier bootstrap work be researched properly (API verification first) rather than rushed under a ticket sized "trivial–moderate."
**Recommended action.** None required. Endorse the re-scope as disciplined. Note for the record that option (b) carries the larger product/maintenance risk.

### A4 — Follow-up framing is strong but lacks an owner and a ticket number.
**Description.** The "Recommended Follow-Up" section is unusually well-specified for a deferral: it enumerates the 6 deliverables (bootstrap capability, schema property, lint gate, version bump, MIGRATIONS note, AC-C11), states the BL-R2-1 root cause, and names the first open question (verify the Anytype property-link API). This is exactly what prevents silent drop. What it lacks is (a) a filed ticket number and (b) a named owner/path. The phase summary recommends filing "a dedicated follow-up ticket" but none exists yet.
**Impact on product/users.** Without a ticket, the activated user-visible feature has no commitment device. The detailed spec text is worthless as a backlog item until it is an actual backlog item.
**Recommended action.** Make filing the follow-up ticket (carrying the "Recommended Follow-Up" section verbatim + the unverified-API open question as its first research task) a closure condition of #325. Same applies to the SG-1/SG-2/SG-4 observability + fan-out deferrals, which currently point to a hypothetical "follow-up ticket" with no number.

### A5 — The kind-discriminated degraded warning (CS-9) is the one in-scope user-facing observability win; good product instinct, keep it.
**Description.** CS-9 adds `:concept` to the degraded warning only on the concept path, leaving entity byte-identical. For an operator (Jan) diagnosing why a contradiction wasn't caught, being able to tell *which* path degraded is genuine operational value at near-zero cost and zero entity regression risk. This is the correct kind of in-scope polish — proportional, user-facing, no over-engineering.
**Impact on product/users.** Direct diagnosability win for the operator; no cost.
**Recommended action.** None. Endorsed.

---

## Cross-criteria notes

- **Spec alignment:** Faithful. All three literal ACs are met by the core. No scope creep in the core (R1's surfacing addition was correctly pulled back out once its true cost was found). No unaddressed gap *within the ticket's literal scope* — the gap is the user-visible payoff, which is a deliberate, documented deferral.
- **Business viability:** Cost/complexity is proportional and small — seven change sites in one file, no schema/bootstrap/migration, trivial git-revert rollback, negligible load on the Mac Mini. The expensive part (bootstrap capability) is correctly NOT being taken on speculatively. Good stewardship for a no-revenue internal/OSS tool.
- **Competitive position:** Neutral-to-positive. This strengthens the "reliable typed knowledge graph" story that differentiates the tool from the keyword-only community alternative; nothing here weakens it. No cannibalization.
- **Over-engineering check:** The `_TEXT_KEY_BY_TYPE_KEY` constant + separate `_facts_key_for_peer` helper (vs. reusing `_type_for_kind`) is a justified, documented small duplication, not gold-plating. Acceptable.

---

## Bottom line

**SIGN-OFF from the product lens.** The re-scope is the right product call: it ships a low-risk, correctly-built foundation that satisfies the ticket in full, while deferring a genuinely larger, riskier capability to a properly-researched follow-up. This is scope discipline, not scope-shaving — the deferral is motivated by a real cost discovery (BL-R2-1), not by diff-minimization.

Two things must be true for this sign-off to hold, both routed through **Decide**:
1. Jan makes the a/b scope choice **explicitly** (my recommendation: option a — confined core + follow-up).
2. The surfacing follow-up is filed as a real ticket (owner + number, carrying the verbatim follow-up spec and the unverified-Anytype-API open question) as a **closure condition of #325**, so the user-visible payoff is committed, not just documented.

Recommendation on next step: **escalate to Jan at the Decide gate** for the scope call (the spec correctly frames it as a decision, not a default), then advance the confined core to Implement. Do not advance straight to test without the explicit scope decision being recorded.
