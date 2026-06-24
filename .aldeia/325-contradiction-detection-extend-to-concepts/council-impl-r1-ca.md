# Council Impl Review R1 — Client Advocate — #325 Contradiction Detection: Extend to Concepts

**Date:** 2026-06-24
**Reviewer:** Client Advocate (stakeholder/client lens)
**Phase reviewed:** post-impl (governance, advance-to-`done` decision)
**Client for this engagement:** Aldeia itself. Stakeholders: Jan (owner/sole decision-maker) and the agent fleet (Claude Code, IronClaw/JC) that reads contradictions via `wiki_lint`.
**Artifacts reviewed:** context/{business,product,compliance,stakeholders}.md; spec-scope.md; spec-addendum-post-spec-r1.md; council-spec-r1.md; council-spec-r1-ca.md (my own spec-phase review); README/CHANGELOG diff (`origin/main...HEAD`); live verification of #426 and #325 on Aldeia-IT/aldeia-box.

---

## Verdict: SIGN-OFF — advance to `done`. No client veto.

At spec phase I gave SIGN-OFF with two strongly-urged conditions attached to choosing option (a):
1. the surfacing follow-up ticket created and **linked before the core merges** — not "later";
2. README/CHANGELOG keep the explicit "surfacing is a follow-up" framing so neither the fleet nor the OSS community infers a closed integrity loop.

**Both conditions are verifiably satisfied.** My central spec-phase concern — that option (a) could leave concept contradictions in a *false-coverage* state (detected and silently recorded, never surfaced, worse than today's honest no-detection) — is adequately closed. There is no client-interest reason to hold.

---

## BLOCKING

None.

---

## ADVISORY

### A1 — Value-realization gap is real but correctly tracked; not a hold reason (CARRIED, now mitigated)
**Client impact (medium, was high).** My spec-phase A1 stands as a fact: for this product's actual consumers — the agent fleet and Jan, who read contradictions through `wiki_lint`, not by browsing the Anytype graph — the shipped core's standalone payoff is *latent/foundational*. Concept contradictions are now detected and cross-linked, but the user-visible "a contradiction gets flagged so someone fixes it" moment does not arrive until #426 ships. Entity contradictions are lint-flagged (`critical`); concept contradictions are recorded but not yet lint-flagged. That asymmetry is exactly what I flagged at spec.

What changed between spec and now: this is no longer an *open risk*, it is a *tracked, honestly-disclosed deferral*. #426 ("Surface concept contradictions in `wiki_lint`") is OPEN, names #325 as parent, names this exact false-coverage scenario in its own body, and carries the README/CHANGELOG-revert task as an explicit AC. The latent value is correctly parked, not lost.

**Recommended action:** None blocking. Jan should keep #426 prioritized — its body already states it is "the council closure condition" and that #325 "must not merge presenting false coverage without this follow-up filed." Treat #426 as the ticket that *realizes* the value #325 *enables*; do not let #325 reaching `done` create a false sense that the concept-integrity loop is closed. It is not — and the docs say so honestly.

### A2 — False-coverage risk: CLOSED
**Client impact (high → resolved).** This was the durable-harm scenario in my spec review: a forgotten follow-up leaving concepts silently "detected but never surfaced," giving a false sense of coverage worse than honest no-detection. Verified resolved on all three legs:
- **Ticket exists and is durable:** #426 OPEN on Aldeia-IT/aldeia-box, titled "Surface concept contradictions in `wiki_lint`," parent #325, origin "post-spec council Round 1 sign-off on #325 (option (a) closure condition)."
- **It self-documents the harm:** #426's body explicitly states concept contradictions are "recorded-but-invisible to the primary consumers" and that #325 "must not merge presenting false coverage." A future reader cannot mistake this for a nice-to-have.
- **Docs do not overclaim:** the README now reads "**concept** contradictions are detected and cross-linked yet **not yet flagged by `wiki_lint`** — a planned follow-up … Don't over-trust a clean contradiction column." CHANGELOG mirrors it and names #426. The roadmap line was correctly trimmed (the "across Concepts" detection promise is now delivered; only the semantic-pre-filter item remains).

The mitigation I asked for ("gating condition, not soft recommendation; created and linked before merge") was honored in substance.

### A3 — Doc honesty protects both the fleet and the OSS community (CONFIRMED, positive)
**Client impact (medium, positive).** The README edit is a model disclosure for a half-surfaced feature. It (a) states the new capability plainly (Entity *or* Concept, `wiki_related` candidates, `wiki_definition` text), (b) states the bounded scope (already-linked peers only), (c) names the precise surfacing gap with correct severity wording (`critical`, not the old erroneous `High` — SF-R2-1 honored), and (d) keeps the standing "Don't over-trust a clean contradiction column" caution. For the OSS reputation purpose (business.md), this is the right posture: a community user reading the README will not infer closed-loop concept coverage. No reputational wrinkle. CHANGELOG correctly files the change under `[Unreleased] → Added` and links #426 for traceability.

### A4 — Follow-up rests on an unverified Anytype property-link API (CARRIED, correctly quarantined)
**Client impact (low for the core; medium for #426).** My spec-phase A4 caveat persists: #426's loop-closing mechanism depends on an Anytype `update-type`/property-link endpoint that no repo code path currently uses and that was not verified to exist. This is correctly fenced entirely out of the shipped core (zero schema/bootstrap/migration change in this work — confirmed by the docs-only nature of the surface diff and the spec's "rollback is a trivial `git revert`"). It does not affect the #325 `done` decision. It does mean the *promise* that #426 will close the loop carries a small tail risk. #426's body already lists endpoint verification as its first task — appropriately handled.

**Recommended action:** None for #325. When #426 is picked up, verify the endpoint exists and is idempotent before any schema-version bump, exactly as already scoped.

---

## Constraint check (context files) — all respected

- **Local-first / zero-config (product.md, compliance.md):** core is code-only logic in `ingest.py`; no new dependency, no cloud call, no new config, no telemetry, no new data destination. The remote-extraction opt-in boundary is untouched. Respected.
- **Resource constraints (32 GB Mac Mini):** per-concept-update fan-out shape is inherited from the entity path, not enlarged; the densest-concept latency concern is correctly deferred to the SG-1 follow-up, not this core. Respected.
- **Open-source / reputation purpose (business.md):** honest README/CHANGELOG protect the community-facing promise; no overclaim. Respected.
- **MIT / data-privacy (compliance.md):** no new data handling, no PII surface, no licensing surface. No Legal dimension (consistent with Legal Counsel's spec-phase absence rationale).
- **Sole-developer reality (stakeholders.md):** the single-developer false-coverage risk that worried me at spec is exactly the risk #426's existence neutralizes.

---

## Answers to the three key questions

1. **Ship now, or hold for value realization?** Ship now. The value-realization gap is genuine but is now a *tracked deferral* (#426 OPEN, parented, self-documenting), not an open risk. My spec-phase false-coverage concern is adequately closed by the #426 filing plus honest docs — exactly the two conditions I attached to endorsing option (a).
2. **Do the README/CHANGELOG protect against over-trusting a clean contradiction column?** Yes, well. Both name the surfacing gap explicitly, use the correct `critical` severity, retain the "Don't over-trust a clean contradiction column" caution, and link #426. Neither fleet nor community can reasonably infer a closed integrity loop.
3. **Any client-interest reason not to advance to `done`?** No.

---

## Sign-off

**SIGN-OFF.** No client veto. Advance #325 to `done`. The two conditions I attached at spec phase to endorsing the confined-core path are both satisfied: #426 is a real, linked, OPEN closure ticket created before merge, and the docs honestly disclose detected-but-not-yet-surfaced. The one residual is product-prioritization, not a blocker: keep #426 prioritized so the deferred value is realized — the integrity loop for concepts is *enabled* by #325 but only *closed* by #426.

**Cross-flags:** To CPO — carry A1 forward: #325 reaching `done` realizes mechanism, not user-visible payoff; #426 owns the payoff and should retain priority. No Legal flag (internal infra, no new data/PII/licensing surface).
