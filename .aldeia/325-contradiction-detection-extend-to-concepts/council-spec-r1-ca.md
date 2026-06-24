# Council Spec Review R1 — Client Advocate — #325 Contradiction Detection: Extend to Concepts

**Date:** 2026-06-18
**Reviewer:** Client Advocate (stakeholder/client lens)
**Client for this engagement:** Aldeia itself. Stakeholders: Jan (owner/decision-maker) and the agent fleet that reads/writes the wiki.
**Artifacts reviewed:** spec.md, spec-scope.md, review-r1.md, review-r2.md, phase-summary-spec.md, context/{business,product,stakeholders}.md

---

## Verdict: SIGN-OFF (no blocking client objections), with strong advisories

The spec phase is well-run from a client-interest standpoint. The re-scope is honest, both decision options are genuinely one step away, and Jan's choice is surfaced fairly rather than buried. My one serious concern is not with the spec's correctness but with the **value-realization timeline and the durability of the follow-up** — addressed below as advisories, not blockers, because they are exactly the kind of thing a well-informed Jan can weigh at Decide.

I am NOT vetoing. The core meets its literal ACs, the re-scope is defensible, and the decision is being handed to the right person with the right information.

---

## BLOCKING

None.

I considered whether the "detected-but-not-surfaced" outcome (Advisory A1) rose to blocking — i.e. shipping a feature whose value is invisible to the stakeholders who asked for it. It does not, for two reasons: (1) the spec is fully transparent that this is the outcome and frames it as Jan's explicit decision, not a silent compromise; (2) option (b) — fold surfacing back in — is fully specified and one step away, so Jan can simply choose the complete feature. A blocking finding would be appropriate only if the half-feature were being shipped *without* Jan's informed consent. It is not.

---

## ADVISORY

### A1 — "Browsable in Anytype but not lint-flagged" is thin value for THIS fleet until surfacing ships
**Client impact (high).** The stated purpose of #325 is wiki knowledge-base integrity: catching contradictory concept definitions so they get reconciled. Consider who the stakeholders actually are (stakeholders.md): the primary consumers are **agents** (Claude Code, IronClaw/JC) and Jan. The fleet does not "browse Anytype" looking for `wiki_contradictions` links — it consumes the wiki programmatically and relies on `wiki_lint` as the surfacing channel. A contradiction that is recorded on a `wiki_concept` but never emitted by `wiki_lint` is, for practical purposes, **invisible to every automated consumer**. It surfaces only if a human (Jan) manually opens the linked objects in the Anytype UI and notices the cross-link.

So the confined core delivers real *mechanism* (detection + cross-linking is genuinely done and tested) but the *payoff the stakeholders experience* — "a contradiction gets flagged so someone fixes it" — does not arrive until the surfacing follow-up ships. Entity contradictions today ARE lint-flagged (`critical`); concept contradictions after this core would be detected and silently stored. That is an integrity asymmetry the fleet will not see.

This is the single most important point in my review: **the confined core is correct and shippable, but its standalone user-facing value is low for this specific stakeholder set.** That fact should weigh heavily in Jan's Decide choice and is the strongest argument for option (b).

**Recommended action:** Ensure Jan reads A1 explicitly at Decide. If he values the confined core landing now (smaller review surface, low risk, unblocks the detection engine), option (a) is fine — *provided* the follow-up is committed (see A2). If he wants the integrity benefit to be real on landing, option (b) is the honest choice despite the larger bootstrap scope.

### A2 — Risk the surfacing follow-up is dropped, leaving concept contradictions silently recorded forever
**Client impact (high).** This is the durable-harm scenario. If option (a) ships and the follow-up ticket is deprioritized or forgotten, the wiki ends up in a worse-than-before state for concepts: contradictions are *detected and written* (so the system "thinks" it is handling them) but *never surfaced* (so nobody acts on them). Stale `wiki_contradictions` links accumulate on concepts with no lint pressure to resolve them. That is arguably worse than today's honest "we don't detect concept contradictions at all," because it creates a false sense of coverage. The README rewrite (spec line 362-364) will say detection covers concepts — a reader could reasonably infer the integrity loop is closed when it is not.

The spec mitigates this well (the follow-up is fully specified, BL-R2-1 documented so it is well-scoped) but a *spec* cannot guarantee a *ticket gets filed and prioritized*. Single-developer project (stakeholders.md: Jan is sole developer); follow-up tickets in a one-person shop are at real risk of indefinite deferral.

**Recommended action:** Make follow-up creation a *gating condition* of choosing option (a), not a soft recommendation. Concretely: the Decide record should require the surfacing follow-up ticket to be **created and linked before the #325 core merges**, not "opened later." Additionally, the CHANGELOG/README wording (spec lines 362-364) must not overclaim: it already says "wiki_lint surfacing for concepts is a follow-up" — good; keep that exact framing so no reader infers closed-loop coverage. I endorse SF-R2-1's High→critical fix for the same honesty reason.

### A3 — Decision burden on Jan is handled well; one refinement
**Client impact (medium, positive).** The spec does the right thing by Jan's time: both options are one step away, the follow-up is fully specified, BL-R2-1 is documented so Jan does not have to re-derive why surfacing got bigger, and the recommendation is explicit. This is a model of *not* offloading analysis back onto the decision-maker. Credit to the lead.

The one refinement: the Decide framing presents this as a binary (a) vs (b). There is an implicit third axis Jan should see — **timing/sequencing**. Option (a) is not merely "ship less"; it is "ship the detection engine now, surface later." If the detection core has value as a *dependency-unblocker* for other work, (a) is more attractive than the raw feature-value comparison suggests. Conversely if nothing depends on it landing first, the case for (a) weakens to "smaller review surface," which may not be worth shipping invisible value. Jan should weigh sequencing, not just scope size.

**Recommended action:** When the lead presents Decide, frame it as "ship-now-surface-later (a) vs ship-complete (b)," explicitly noting whether anything is blocked on the detection core landing. If nothing is, say so — it sharpens the choice.

### A4 — Unverified Anytype property-link API is a real but correctly-quarantined risk
**Client impact (medium).** The follow-up's central mechanism (ensure-declared-properties-on-existing-types) depends on an Anytype `API-update-type`/property-link endpoint that **no current repo code path uses and that was not verified to exist** (spec line 384; phase-summary line 31). If it does not exist or is not idempotent, the surfacing follow-up needs a different mechanism entirely — which could materially change its size, or in the worst case make clean surfacing hard. From the client's seat this matters because it affects whether option (a)'s "follow-up will close the loop" promise is even deliverable as described.

This is correctly fenced into the follow-up and flagged as the first thing follow-up research must confirm. It is not a #325-core risk. But Jan should know that choosing (a) carries a small tail risk: the loop-closing follow-up rests on an unverified dependency.

**Recommended action:** No spec change needed. At Decide, state plainly: "option (a)'s follow-up depends on an unverified Anytype API; if Jan wants certainty the loop will close, that API should be verified before committing to (a) as the path." This is a one-line caveat, not a blocker.

### A5 — No stakeholder constraint is violated by the confined core
**Client impact (low, confirmatory).** I checked the core against the context files:
- **Local-first / zero-config (product.md):** core is code-only in `ingest.py`, no new dependency, no cloud, no config, no deployment, trivial git-revert rollback. Fully respected.
- **Resource constraints (32 GB Mac Mini):** per-concept-update fan-out shape is inherited from the entity path, not enlarged; negligible added load (spec 208-210). Respected. The pre-existing unbounded fan-out (SG-1) is honestly deferred with rationale and tracked.
- **Open-source/reputation purpose (business.md):** a half-surfaced feature is a mild reputational wrinkle if a community user reads the README as closed-loop — mitigated by the honest "surfacing is a follow-up" wording (ties to A2). The follow-up's schema-version bump + MIGRATIONS note (spec 387-388) correctly respects the public-distribution constraint that schema changes must be versioned and migration-documented.

No constraint is ignored by the core. The follow-up correctly carries the schema/migration/version obligations that public distribution imposes.

---

## Bottom line

From the client/stakeholder seat: the spec phase served Jan and the fleet well. The re-scope is honest, not a quiet deferral of the payoff — the deferred payoff is named explicitly and handed to Jan as a clean, well-informed choice with both options one step away. That is exactly how a decision of this kind should reach the owner.

My substantive concern is not correctness but **value realization**: for this fleet, "detected and cross-linked but not lint-surfaced" is low standalone value, because every automated consumer relies on `wiki_lint`, not Anytype browsing, to see contradictions (A1). And the durable risk is a **forgotten follow-up** leaving concepts in a false-coverage state worse than today's honest no-detection (A2). Neither is blocking — both are precisely what an informed Jan should weigh — but they should be put in front of him in plain terms.

**SIGN-OFF.** No client veto. Two conditions I strongly urge be attached to choosing option (a): (1) the surfacing follow-up ticket is created and linked **before** the core merges, not "later"; (2) README/CHANGELOG keep the explicit "surfacing is a follow-up" framing so no reader — fleet or community — infers a closed integrity loop that does not yet exist. If Jan prefers the integrity benefit to be real on landing, option (b) is the honest path and the spec supports it without further analysis.

**Cross-flags:** To CPO — A1/A3 (value realization + Decide framing as ship-now-surface-later vs ship-complete). No Legal flag (no client-specific compliance dimension here; internal infra).
