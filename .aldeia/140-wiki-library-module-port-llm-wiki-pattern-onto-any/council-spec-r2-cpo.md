# Council Meeting — Post-spec (Round 2, Calibration Re-review) — CPO

**Date:** 2026-04-22
**Ticket:** #140 — Wiki Library Module: Port LLM Wiki Pattern onto Anytype
**Reviewer:** Chief Product Officer (real specialist, architectural fix in place)
**Spec under review:** `.aldeia/140-wiki-library-module-port-llm-wiki-pattern-onto-any/spec.md` (1912 lines)
**Prior review referenced (only after independent findings):** `council-spec-r1.md` (CPO section, lines 60–72)

---

## Verdict

**SIGN OFF WITH CONDITIONS.**

The spec is product-ready for implementation start on v0.2.0. The per-version Scope/MoSCoW/AC/Deliverables/Dependencies/Risks backbone is the strongest structural response in the spec and it directly answers Jan's explicit ticket feedback on "phases of delivery." Personas are clearly articulated, market positioning is credible with a responsible fallback, and the additive architecture preserves v0.1.0 shipped value.

Conditions are five advisories: (1) the PyPI-vs-git-tag question for v0.2.0 must be explicitly resolved before tag day, (2) the 15-minute quick-start promise and the README must be made temporally honest across v0.2.0–v0.4.0, (3) the "first" claim's verification artifact must precede the v0.2.0 branch name being locked into marketing copy, (4) the 16 GB default-extraction-model tension needs a README-level disclosure, and (5) the community branding question (OQ #5) needs a single documented resolution rather than a proposal awaiting Jan's sign-off.

None of these gate implementation start on v0.2.0. All five must be addressed before the v0.2.0 PyPI publish (or git-tag-only decision) lands.

## Summary (Independent assessment — formed before reading R1)

### Spec Alignment

Faithful. Every must-have in the product-brief (bootstrap, ingest, query, lint, entity resolution, bidirectional relations, pip-installable, 15-minute quick-start, deeplinks, comparison documentation) traces to a named deliverable in a specific phase. Scope-out list in the brief matches deferred items (multi-space federation, ASMR, LLM Wiki v2, PDF, auto-merge below threshold, Marp/matplotlib).

Traceability: the spec's §Delivery Phases → product-brief's §Requirements → ticket objective is clean. No drift.

### User Value Per Version

- **v0.2.0 alone:** Low-to-moderate direct end-user value. Bootstrap + doctor + verification script = schema ready in a space and infrastructure confidence. The community-developer persona (who wants to *evaluate* the module) is **not** fully served by v0.2.0 — evaluation requires observable ingest behavior.
- **v0.3.0:** High. This is the first phase where the full Karpathy-pattern premise ("compile once, query later") becomes visible. Ingest + WikiLog + bidirectional relations = observable compounding.
- **v0.4.0:** High. Query with file-back is the compounding loop closing. This is the version most likely to convert a community evaluator into an adopter.
- **v0.5.0:** Moderate. Lint is operator hygiene — valuable to Jan, marginal to a new evaluator who has <50 objects. The 500-object perf budget is honest about where lint becomes necessary.

The spec's claim that "each version is internally shippable — you could freeze development after any tag and have a coherent artifact" is **only half true**: v0.2.0 is structurally coherent (schema exists, tools exist) but not user-valuable on its own. The spec should be slightly more honest about this in the §Delivery Phases intro.

### Product Strategy / Positioning

The "first Anytype-native LLM wiki" claim with a "to our knowledge" qualifier + documented fallback is a reasonable posture. Legal signed off on it R1; I agree from a product standpoint. However, the current committed README (`README.md:3`) makes a **broader** claim: *"The first open-source LLM wiki that uses a typed knowledge-graph store — Anytype's native Objects, Types, and Relations — instead of a filesystem of markdown files."* That is "first typed-KG LLM wiki, period" — not "first Anytype-native." This is a larger surface area than the spec's own positioning statement. I treat this as a significant product-strategy concern below.

The Comparison table (spec lines 183–192) is the right persuasion artifact. Eight dimensions, clean delineation, one-glance readability.

### Business Viability

Additive package; reuses v0.1.0 Qdrant + bge-m3 + FastMCP; new files under `wiki/`; 7 new files for v0.2.0 is lean. Maintenance burden is proportional — solo-maintainer-realistic. No new infra dependencies for v0.2.0. v0.3.0 adds `markdownify` (MIT, minor pin). Cost profile acceptable.

### Scope Discipline

Strong. MoSCoW Won'ts per version are specific, not hand-wavy: "auto-configuration of WIKI_EXTRACT_MODEL", "PDF parsing", "streaming responses", "auto-fix mode." Deferred items each carry a rationale. No gold-plating — I looked specifically at v0.2.0's 6-file merge (`locks.py` + `normalize.py` → `util.py`) as evidence of scope rigor and it is the right call.

The `_BaseAnytypeClient` scaffold in v0.2.0 (transport-only) is on the edge of premature abstraction but justifies itself: it lands before the write-client lands, avoiding a v0.2.0→v0.3.0 surgical refactor. Acceptable as-specified; Infra/CTO correctly named "scope creep risk" as the implementation-time concern.

---

## Independent Findings

### BLOCKING

**None.** The spec is advanceable. Every concern below is addressable as an advisory with a clear closing condition before v0.2.0 tag.

### ADVISORY

#### ADV-CPO-R2-1: v0.2.0 publishing strategy is under-specified and is the biggest OSS-perception risk

**Finding.** The v0.2.0 pre-release checklist (spec line 735) includes `Git tag v0.2.0` but does **not** say whether v0.2.0 is published to PyPI. The README quick-start already instructs `pip install anytype-llm-wiki` (README:53). v0.2.0 contains bootstrap + doctor + verification script only — no ingest, no query. A community developer who `pip install`s v0.2.0 after seeing a "First Anytype-native LLM wiki" positioning line and the Comparison table will bootstrap an empty schema and then have nothing to do with it.

**Impact on product/users.**
- **Community developer persona:** cannot evaluate the module on v0.2.0 alone. The persona's stated behavior (README → quick-start → try it → decide) terminates in "I bootstrapped some types, now what." This is a silent disappointment that produces zero GitHub-star conversion and possibly a negative first impression ("vapor-ware scaffold").
- **Aldeia reputation signal persona:** the v0.2.0 README/CHANGELOG is the public first impression. If v0.2.0 is the visible first release on PyPI and is incomplete, the reputation signal degrades rather than improves. This is the opposite of the stated business goal.
- **Jan as operator:** fine either way — Jan knows the roadmap. The risk is entirely community-facing.

**Recommended action.** Decide explicitly before v0.2.0 tag between one of two paths and reflect the decision in the pre-release checklist, README, and CHANGELOG:
- **Option A (recommended):** Tag v0.2.0 in git only. Do **not** publish to PyPI. Announce nothing publicly. First PyPI publish is v0.3.0 after ingest lands. README's `pip install` block is removed until v0.3.0 and replaced with "Install from source" during v0.2.x.
- **Option B:** Publish v0.2.0 to PyPI explicitly framed as a preview: the CHANGELOG entry leads with "**Preview release — schema and preflight only; ingest in v0.3.0**," the README version-stamped section at the top says the same thing in the first 80 characters, and the Comparison table is held back until v0.3.0. The "First Anytype-native LLM wiki" positioning line is replaced with "Preview of the Anytype-native LLM wiki (schema-only; ingest in v0.3.0)."

Either way, the v0.2.0 pre-release checklist must gain an explicit item that reads: "PyPI publish decision recorded; README content matches the decision." Absent that, the spec allows a plausible state where v0.2.0 is pip-installable and marketed as a first LLM wiki — which breaks the product promise on contact with a real user.

#### ADV-CPO-R2-2: The 15-minute quick-start promise spans v0.2.0, v0.3.0, and v0.4.0 — but the README will be read by v0.2.0 adopters first

**Finding.** Two promises live in the spec:
- Line 63 (Product Context, user story): "evaluate the module within 15 minutes of `pip install` (with prerequisites already running) on my own data."
- Line 1684 (Success Criteria): "Quick-start (bootstrap → first ingest → first query) can be completed in under 15 minutes by a new user on a clean Anytype space."

Both promises presume ingest+query exist. Ingest is v0.3.0, query is v0.4.0. The 15-minute quick-start is therefore a **v0.4.0 promise, not a v0.2.0 promise.**

Line 1654 addresses the v0.2.0 version honestly ("about five minutes with prerequisites already met" for bootstrap alone, aspirational not an AC) but the two promises above are not scoped to v0.4.0 anywhere, and the user-story form of the promise is the community evaluator's read of the README.

**Impact on product/users.** A community developer reading the v0.2.0 README's quick-start section expects the 15-minute promise to be honored by v0.2.0. It cannot be — there is no ingest, no query. This creates unambiguous promise-vs-reality drift that every first-adopter will hit.

**Recommended action.** In v0.2.0's README update, explicitly version-stamp the quick-start: "In v0.2.0, the quick-start is: install → bootstrap → inspect schema in Anytype (about 5 minutes). The full workflow (ingest → query) lands in v0.3.0 and v0.4.0 respectively." Remove or defer the 15-minute promise prose from the v0.2.0 README. The success-criteria sentence at line 1684 can stand as a v0.4.0 commitment; rename it "Community Quick-Start (v0.4.0)".

This is tightly coupled to ADV-CPO-R2-1 and can be addressed in the same README PR.

#### ADV-CPO-R2-3: "First Anytype-native LLM wiki" verification must precede any marketing commitment — not be swappable post-hoc

**Finding.** The spec (line 179) says: "If one is found, revise the positioning to differentiate on specific features rather than priority." The pre-release checklist (line 729) requires the verification to happen in the v0.2.0 PR description. ADV-CPO R1 #12 asked for the queries to be recorded verbatim.

The sequencing is subtly wrong from a product-strategy standpoint: if a prior Anytype-native LLM wiki is found mid-v0.2.0, the spec plans to "swap the fallback line" — but by that point, the repo has been named, the README's lead-line prose has been written, the announcement tweet is drafted, and any branch / tag naming decisions have been made assuming the claim holds. Reactive-swap is fine for the README one-liner but risks being incomplete elsewhere (screenshots? social copy? the existing `README.md:3` line that already says "The first open-source LLM wiki that uses a typed knowledge-graph store"?).

Additionally, the currently-committed `README.md:3` makes an even **broader** claim than the spec's positioning statement — "first typed-KG LLM wiki, period" rather than "first Anytype-native." That line exists **today** without the verification having been run. It is a larger claim than Legal signed off on.

**Impact on product/users.** Low legal risk (Legal already signed off with qualifier). Moderate reputation risk: a community developer who finds prior art and compares it to the current README headline could reasonably accuse the project of over-claiming. This is precisely the OSS-community perception that Jan explicitly wants to protect.

**Recommended action.**
1. Move the prior-art verification **forward** — run it as the first v0.2.0 implementation task, record the searched queries + dates + findings in `.aldeia/140-.../positioning-verification.md`, commit that before any README prose is merged.
2. Audit the currently-committed `README.md:3` line against the verification result. If it says "first open-source LLM wiki that uses a typed knowledge-graph store" and the spec's positioning is "first Anytype-native," reconcile. Either tighten the README line to match the spec's narrower claim, or widen the spec's positioning to match the README (and Legal must re-sign on the wider claim).
3. Add the verification date to the README's Comparison table footnote so a reader in 2027 can see when the claim was last checked.

#### ADV-CPO-R2-4: OQ #3 (qwen2.5:7b default) creates a 16 GB adopter trap that needs a README-level mitigation, not just a doctor WARN

**Finding.** OQ #3 is marked CLOSED with default `qwen2.5:7b` on Ollama. The spec flags it as "marginal on 16 GB" and R1 Infra advised a doctor WARN (R1 ADV #19). But the community developer persona's first interaction with the extraction model is the README's quick-start — not the doctor output. A 16 GB MacBook Air user who follows the README verbatim, runs `ollama pull qwen2.5:7b`, and then ingests their first source will hit Ollama's back-to-back swap (bge-m3 + qwen2.5:7b), and their first ingest experience will be "it's slow / my machine locked up."

The doctor WARN is necessary but insufficient — it fires at install time but the user has already downloaded the 4.7 GB model and invested time. The failure mode should be prevented upstream, at the README configuration reference, not remediated downstream.

**Impact on product/users.** First-ingest disappointment is a conversion-killer for the community developer persona. The Karpathy pattern's core promise is "compiled once, queryable forever" — if that first compile takes 15 minutes on their laptop, they'll leave before v0.4.0's query shows them the payoff.

**Recommended action.** In the v0.3.0 README configuration table, show **two recommended defaults**:
- 32 GB+: `WIKI_EXTRACT_MODEL=qwen2.5:7b` (current default)
- 16 GB: `WIKI_EXTRACT_MODEL=qwen2.5:3b` with a note "extraction quality is marginally lower; revisit at 32 GB"

The doctor's 16 GB warning (R1 ADV #19) should reference this README table by anchor, not emit generic advice. This frames it as a first-class product decision rather than an operational papercut. Re-evaluate at v0.3.0 pre-release once the Wikipedia fixture AC runs against both model sizes.

Adjacent: OQ #3's labelling is self-contradictory — "CLOSED at v0.3.0 specification" with "(provisional — empirical validation tracked as v0.3.0 pre-release item)" (spec line 1742). R1 ADV #10 already flagged this. Re-state as "DEFAULT SET; validation gate at v0.3.0 pre-release" to remove the contradiction.

#### ADV-CPO-R2-5: OQ #5 (community branding) is a decision-not-made and it's blocking the README

**Finding.** OQ #5 (spec line 1746): "Current repo name is `anytype-llm-wiki`. Proposal: keep the repo name; the wiki module is 'Anytype LLM Wiki' in documentation — no second brand. Jan's call." "Must resolve by v0.2.0 README update." This is the correct minimum bar. But the spec treats it as an open question; the README updates are part of the v0.2.0 deliverable; the open question cannot be open when that deliverable is being written.

**Impact on product/users.** SEO discovery is moderate-positive with the current name. "Anytype LLM wiki" is straightforwardly searchable and maps directly to the prior-art claim. No trademark conflict identified (Legal R1 signed off on nominative use with a Trademarks footer advisory). The name signals "AI wiki on Anytype" with reasonable specificity — it leans general-purpose rather than "Karpathy pattern" — but the Karpathy-pattern angle is the *product* story not the *brand* story. That asymmetry is fine.

**Recommended action.** Close OQ #5 in the spec before v0.2.0 implementation begins by editing the spec line to read: "**Resolved 2026-04-22.** Module name is 'Anytype LLM Wiki' in documentation; repo name is `anytype-llm-wiki`; PyPI package is `anytype-llm-wiki`. Legal's Trademarks footer advisory (R1 ADV #4) is adopted." Then the v0.2.0 README work can proceed without a decision dependency.

---

## Checks requested in the brief — answered inline

### Check 1: v0.2.0 release framing (PyPI vs git-tag-only)
See **ADV-CPO-R2-1.** The spec has an ambiguity; it must be resolved with an explicit checklist item before tag day. My recommendation is git-tag-only for v0.2.0, PyPI publish at v0.3.0.

### Check 2: 15-minute quick-start promise honesty
See **ADV-CPO-R2-2.** The promise applies from v0.4.0 forward. The v0.2.0 README must say so explicitly. This is not a marketing nicety — it's a promise-tracking requirement for the OSS-scrutiny bar Jan named.

### Check 3: Persona fit — community developer in v0.2.0
**Partially served.** v0.2.0 lets a community developer bootstrap a schema and run doctor — but "evaluate the module" requires ingest+query (v0.3.0+v0.4.0). This means v0.2.0's community-facing value is limited to "I can see where this is going." Which is fine — **if the release framing (ADV-CPO-R2-1) is honest.** If v0.2.0 pretends to be a full release, the persona is mis-served. If it's framed as preview / preflight, the persona is correctly served.

### Check 4: Positioning claim timing
See **ADV-CPO-R2-3.** Verification must precede marketing commitment, not follow it. The currently-committed `README.md:3` line is already broader than the spec's positioning and is committed without verification — that is a pre-existing inconsistency that this spec inherits and must resolve.

### Check 5: OQ #3 extraction model default (qwen2.5:7b)
See **ADV-CPO-R2-4.** The default is defensible for Jan (32 GB M4) but a trap for 16 GB community users. The README must give them an explicit alternative, not just a doctor warning at install time.

### Check 6: OQ #5 community branding
See **ADV-CPO-R2-5.** Close the question. SEO is fine as-is. Naming signals are fine.

### Check 7: Per-version shippability claim
**Mostly honest, slightly overstated.** v0.2.0 is "structurally shippable" (has a coherent deliverable artifact) but not "user-valuably shippable" (the artifact has no direct use value without v0.3.0). I would amend the §Delivery Phases intro to say: "Each phase is internally coherent; end-user value accrues cumulatively across phases, not within each single phase." This is a one-sentence change that buys a lot of honesty. v0.5.0 lint against a never-ingested empty schema is moot, but that's a hypothetical — Jan won't ship v0.5.0 without v0.3.0 and v0.4.0 having landed per the dependency graph.

### Check 8: Roadmap coherence and deferred items
**Coherent.** The big-ticket deferrals (multi-space federation, ASMR, LLM Wiki v2, PDF) each have stated rationale. One small concern: `wiki_status` per R1 CTO ADV #5 — reconsideration trigger depends on community issues that may never fire for a low-traffic early OSS project. Adding Jan's daily-operator signal (R1 CTO ADV #26) addresses this. Endorse.

### Check 9: Jan's "phases of delivery" feedback
**Strongly answered.** The per-version Scope/MoSCoW/AC/Deliverables/Dependencies/Risks/Pre-release backbone is the right structural response. It would be strengthened marginally by a cross-phase traceability matrix (one table: requirement → v0.2.0 AC → v0.3.0 AC → ...), but this is polish, not a gap. The current structure is above the bar Jan named.

### Check 10: Anything R1 CPO should have caught but didn't
**One item.** R1 CPO did not flag that the currently-committed `README.md:3` line already makes a broader positioning claim than the spec's "to our knowledge, the first Anytype-native" statement. That line exists without the verification having been run. Captured as part of **ADV-CPO-R2-3.**

---

## R1 Delta — agreement, disagreement, missed items

**Read after independent assessment.** R1 CPO verdict was SIGN OFF WITH CONDITIONS with six conditions (R1 ADV #1 CSO-forwarded threat-model, R1 ADV #2 200-threshold validation, R1 ADV #3 prior-art reproducibility, R1 ADV #4 Keep-a-Changelog, R1 ADV #6 v0.2.0 publishing framing, R1 ADV #10 OQ #3 relabel, R1 ADV #11 CHANGELOG format, R1 ADV #12 prior-art queries, R1 ADV #26 wiki_status trigger).

### Agree

- **R1 ADV #6 (v0.2.0 PyPI strategy)** — my ADV-CPO-R2-1 agrees strongly and strengthens the framing to "must be in the pre-release checklist." R1 framed it as a concern to reconsider; R2 frames it as a concrete checklist-item gap.
- **R1 ADV #10 (OQ #3 relabel)** — my ADV-CPO-R2-4 adopts this verbatim and extends it into a README-level product decision rather than just labelling.
- **R1 ADV #12 (prior-art verification recording)** — my ADV-CPO-R2-3 adopts and strengthens to "sequence the verification *first,* before README prose lands."
- **R1 ADV #2 (200-threshold default empirical validation)** — agree this matters at v0.4.0; not raised as an independent finding because it's a v0.4.0 pre-release concern, not a spec-phase blocker.
- **R1 ADV #11 (Keep-a-Changelog)** — agree; low-cost credibility signal. Uncontroversial.

### Disagree — none

No R1 CPO advisory is wrong. The R1 CPO assessment was substantively correct; the calibration question was whether it was *complete* and whether it *exercised independent judgment* vs. rubber-stamping.

### R1 missed items (caught in R2)

- **ADV-CPO-R2-2 (15-minute quick-start temporal honesty).** R1 CPO raised the "15-minute bootstrap-to-value" in the context of v0.2.0 framing (R1 ADV #6) but did not note that the promise appears in **two separate places** in the spec (user story line 63 and success criterion line 1684), both of which span versions. The v0.2.0 README will need explicit version-stamped language — this is more than a framing fix for v0.2.0; it's a multi-version documentation consistency issue.
- **ADV-CPO-R2-3 extension: the `README.md:3` line already makes a broader claim than the spec.** R1 CPO did not audit the committed README against the spec's positioning statement. The committed README says "first open-source LLM wiki that uses a typed knowledge-graph store" — which is broader than "first Anytype-native LLM wiki." This line exists today without the verification having been run. It is a live product-strategy inconsistency that v0.2.0 implementation inherits.
- **ADV-CPO-R2-4 extension: the 16 GB default-extraction-model tension is a README product decision, not just a doctor warning.** R1 Infra flagged the doctor WARN (R1 ADV #19); R1 CPO endorsed generally. Neither framed the problem as a first-ingest disappointment conversion risk or specified a README-level two-default-recommendation pattern.
- **ADV-CPO-R2-5 (OQ #5 must close before implementation starts).** R1 CPO did not note that OQ #5 is flagged "must resolve by v0.2.0 README update" but the v0.2.0 README update IS part of the v0.2.0 deliverable — so the OQ must close before, not during, that deliverable. Minor sequencing issue but it would block implementation start if left.
- **Per-version shippability claim honesty.** R1 CPO endorsed the per-version structure strongly ("strongest structural response in the spec"). I agree — but R1 did not note the slight overstatement ("internally shippable — freeze development after any tag and have a coherent artifact") is more true for v0.3.0+v0.4.0+v0.5.0 than for v0.2.0. Small honesty-tuning gap.

### R1 items I'd reprioritize

- **R1 ADV #2 (200-threshold default)** was filed as "v0.4.0 pre-release concern." I agree — but the spec already tests the boundary mechanically (AC v0.4.0 #3 and the 199/200/201 test). The **default** question and the **mechanics** question are complementary; R1 correctly separated them. No reprioritization.

## Calibration Verdict on R1

**R1 CPO was substantively correct but incomplete.** The R1 CPO caught the biggest single product concern (v0.2.0 standalone release weakness, R1 ADV #6) and flagged the five conditions that matter most for OSS-grade release discipline. R1 did **not** miss a category of product risk; every advisory above is in a dimension R1 also examined.

However, R1 CPO review was **one layer too shallow** in three specific places:
1. **Did not audit the committed README** against the spec positioning statement. ADV-CPO-R2-3 extension.
2. **Did not trace the 15-minute promise** across the two places it appears in the spec. ADV-CPO-R2-2.
3. **Framed the 16 GB extraction default as a labelling issue** rather than a first-ingest conversion risk. ADV-CPO-R2-4 extension.

Each of these would have been catchable by grep-ing the spec for the promise text and reading `README.md:3`. The R1 architectural defect (specialist fallback to general-purpose with role prompts) plausibly explains the shallowness — a real CPO reads the committed README, a prompt-injected generalist likely does not.

**None of the misses rise to a BLOCKING level in R2.** R1 would not have changed its recommendation (proceed to test/impl) if these had been caught. The calibration finding is that **the R1 CPO verdict was correct, the reasoning was directionally correct, but the review missed product artifacts a real CPO would have inspected.**

**R2 verdict on R1:** Not a BLOCKING miss. An ADVISORY-level shallowness. R1's "SIGN OFF WITH CONDITIONS" stands; R2 adds three specific advisories on top.

## Sign-off statement

**Chief Product Officer signs off on the spec, with conditions.** The spec advances to the next SDLC phase. The five R2 advisories (plus the R1 CPO advisories already recorded) must be resolved before v0.2.0 is tagged — specifically:
- ADV-CPO-R2-1: PyPI publish decision made and recorded in v0.2.0 pre-release checklist.
- ADV-CPO-R2-2: v0.2.0 README version-stamps the quick-start; 15-minute promise deferred to v0.4.0.
- ADV-CPO-R2-3: Prior-art verification is v0.2.0 implementation task #1; `README.md:3` reconciled against the spec's positioning statement.
- ADV-CPO-R2-4: v0.3.0 README config table shows two recommended extraction defaults (32 GB and 16 GB) with a quality note; doctor warning anchors here.
- ADV-CPO-R2-5: OQ #5 closed in the spec before v0.2.0 README work begins.

No BLOCKING findings. No dissent.
