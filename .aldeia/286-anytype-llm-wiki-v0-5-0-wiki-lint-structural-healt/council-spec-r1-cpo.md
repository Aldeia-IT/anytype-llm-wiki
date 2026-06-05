# Council Spec Review R1 — Chief Product Officer

**Ticket:** #286 — anytype-llm-wiki v0.5.0 `wiki_lint` (Structural Health Check)
**Phase:** Spec (strategic governance review)
**Reviewer:** CPO (product lens — user value, scope discipline, roadmap coherence)
**Date:** 2026-06-05

---

## Verdict: **SIGN OFF** (no blocking product concerns)

The increment delivers a real, usable maintain capability now, stays inside the master-spec roadmap, and holds scope discipline against the explicit anti-bloat directive. The product story is coherent. My concerns are ADVISORY only — items to track into implementation and the v0.6.0 follow-up, not gates.

---

## BLOCKING

**None.**

---

## ADVISORY

### A1 — The passive contradiction check is dead weight *as a finding*, but justified as a contract. Track it; don't expand it.
`contradiction_unresolved` (High) provably emits zero findings on every pipeline-produced wiki until v0.6.0/#287 populates `wiki_contradictions`. From a pure user-value standpoint a check that never fires for the real user journey is noise — it appears in the 10-check surface and in AC5's "all 10 produce findings on seeded fixtures," which can read as more delivered value than the live behaviour warrants.

I am NOT asking to defer it, because the spec keeps the cost honest: detection is a trivial property read (non-empty `wiki_contradictions` AND null `wiki_last_reviewed`), it is scoped to `wiki_entity` only (SF9), and it preserves the report-schema and enum contract that #287 lights up without a re-plumb. Shipping the wire now and activating the signal in v0.6.0 is the right sequencing for a roadmapped tool. **Impact:** minor — risk is operator over-trust ("contradiction check is green, so I have no contradictions") when the check is structurally passive.
**Action:** ensure the README/CHANGELOG and the LintReport (or tool docstring) state plainly that `contradiction_unresolved` is passive until v0.6.0 so operators do not read a clean result as a guarantee. The live-vs-passive distinction must reach the end user, not just the spec.

### A2 — The D2/D3 double-count is the right product call, but the operator-facing framing carries confusion risk.
One aged needs-review object emits BOTH `unreviewed_needs_review` (High) and `stale_needs_review` (Medium), and the summary counts each. I agree this is a feature, not a bug: the two findings are distinct *actions* (resolve the unreviewed conflict now vs. this has been rotting for 30+ days), and collapsing them would hide the urgency signal. The live-vs-passive split (D3 fires off the `needs-review` status `wiki_remember` already sets — so v0.5.0 produces a genuine populated High finding, not a passive one) is the single most important user-value decision in this spec and it is sound.

The risk is purely presentational: an operator scanning `summary` counts may double-count one object as two problems and misjudge wiki health. **Impact:** low — affects perceived severity totals, not correctness.
**Action (implementation, not spec):** the per-finding `detail` for the two needs-review checks should make the shared-object relationship legible (e.g. reference the same object_id/title in both details), so an operator reading the report understands one object generated two findings. Worth a note to the QA Director so acceptance verification confirms the report is *readable*, not just numerically correct.

### A3 — Report-only is unambiguously the right v0.5.0 scope; guard the deferral in messaging.
Lint mutating nothing but its own WikiLog receipt is the correct call. Auto-fix on structural findings (asymmetric relations, orphan rewiring, merge of potential duplicates) is destructive and irreversible against a user's knowledge base; shipping it before the *detection* surface has been validated on real wikis would be reckless. Report-only also keeps the tool's blast radius tiny and the maintenance burden low — exactly right for a sole-maintainer open-source project that doubles as a reputation funnel. **Impact:** positive. **Action:** keep auto-fix explicitly out of scope in the public README so the community does not file it as a v0.5.0 regression; the Deferred Items section already does this internally.

### A4 — `potential_duplicate` band rests on heuristic thresholds; set expectations as "surfacing," not "truth."
The `[0.70, 0.85)` half-open band is well-reasoned (0.70 master surfacing floor, 0.85 = the auto-upsert threshold above which the pipeline would already have merged). The product caveat: this is a *suggestion* surface (Informational, `recommendation: "review_manually"`), and on real wikis it may produce false-positive pairs. That is acceptable for an Informational signal gated to the `all` pass. **Impact:** low. **Action:** none for spec; ensure README frames duplicates as "candidates for human review," consistent with the Informational severity and the existing recommendation field.

### A5 — Deferrals are the right ones; one to keep on the roadmap radar.
Count-cache, contradiction population (#287), multi-space federation, and duplicate random-sampling are all correctly deferred. The sampling deferral is the one most likely to bite real users: the current design is all-or-nothing — above `WIKI_LINT_MAX_OBJECTS` (2000) the duplicate sweep is skipped entirely, so the largest, most decay-prone wikis get *no* duplicate detection. For v0.5.0 this is acceptable (High/Critical findings are never lost, only the Informational sweep) and is documented. **Impact:** low now, grows with adoption. **Action:** keep `WIKI_LINT_DUPLICATE_SAMPLE` on the roadmap as the natural follow-up the spec already names; no change required now.

---

## Rationale

This is a textbook well-scoped increment. It closes the genuinely missing fourth leg of the Karpathy maintain loop (ingest → remember → query → **audit**), and it does so with a capability that produces live, actionable findings on day one rather than a hollow battery of checks that never fire — the D3 `unreviewed_needs_review` High signal, keyed off a status `wiki_remember` already writes, is the proof that v0.5.0 delivers real user value and not just a roadmap placeholder. Scope discipline is strong: the spec corrected two latent master-spec defects (the impossible `stale_stub` check, the absent `wiki_ingested_at` on entity/concept) by *re-targeting to real signals* rather than bolting on schema changes, held to 458 lines / 15 ACs against the explicit #289 anti-bloat directive, and reused ~80% of shipped v0.4.0 infra rather than re-deriving it. The report-only decision keeps the blast radius and maintenance burden appropriate for a sole-maintainer open-source tool whose business value is reputation. My five ADVISORY items are all about how passive/heuristic behaviours are *communicated to operators* — none of them block, and none indicate scope creep or strategic misalignment. The 10-check surface is coherent, the deferrals are the correct things to defer, and the increment fits the master roadmap cleanly. Signed off from a product perspective.
