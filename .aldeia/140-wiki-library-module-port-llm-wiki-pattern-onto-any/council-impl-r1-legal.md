# Council Meeting — Post-implementation (Round 1) — Legal Counsel Assessment

**Date:** 2026-05-22
**Ticket:** #140 — Wiki Library Module: Port LLM Wiki Pattern onto Anytype
**Phase reviewed:** impl (v0.2.0 tranche — final delivery gate before PR open / merge to `main`)
**Reviewer:** Legal Counsel (native specialist)
**Repo:** `anytype-llm-wiki` — PUBLIC, MIT-licensed OSS (formerly `anytype-rag`; already public)
**Scope:** Governance/strategic legal review of the merge-to-`main` decision — NOT line-by-line code review. The dispositive legal question is which deferred Legal items are *merge-gating* vs *tag-gating*.

---

## Verdict

**SIGN OFF WITH ADVISORIES.**

Zero BLOCKING. Six ADVISORY (all tag-gating, none merge-gating).

The code is complete and the test suite is green. From the Legal/compliance angle, **the act of merging this code onto an already-public `main` branch creates no new legal exposure that must be cured first.** Every deferred Legal item I authored in prior rounds (NOTICE, license-scan CI, CONTRIBUTING DCO paragraph, SECURITY.md/CRA, README Trademarks footer, README hosted-LLM ToS, positioning-verification reconciliation) is gated on the **v0.2.0 release event** — `git tag v0.2.0` and/or a PyPI publish — not on the commit landing on `main`. Merging is not releasing. The legally operative events (a consumer-facing version release, the "making available on the market" that triggers CRA, the redistribution that triggers Apache-2.0 NOTICE duties) all happen at tag/publish time, which is a separate, documented maintainer step.

I sign off on advancing to `done` / opening the PR / merging to `main`, **conditioned on** the maintainer-local pre-release checklist (spec.md:760–794) being walked in full before `git tag v0.2.0` is cut. The tag is the legal gate; the merge is not.

---

## Summary

The brief poses four questions. My answers:

1. **Merge-gating vs tag-gating.** *None* of my deferred Legal items are merge-gating. All are tag-gating. The reasoning is uniform: each item cures exposure that arises from *releasing/distributing a versioned product* (PyPI metadata, Apache-2.0 redistribution, CRA market-placement, consumer-facing advertising claims). Landing the source on a public branch that is already public — and already carries the hedged claim, the LICENSE, and the privacy notice — adds no new distribution or market-placement event. See the per-item dispositions below.

2. **Hedged "first" claim.** Acceptable interim state to merge. The README.md:3 claim is qualified ("To our knowledge…"), carries an inline note (README.md:7) disclosing that the verification artifact is pending and naming a pre-committed fallback that drops "first". That qualification + disclosure closes the reasonable-diligence gap under Lanham §43(a) and Brazilian CDC Art. 37. The claim is already live today; the merge does not change it. The *absence* of `positioning-verification.md` is tag-gating (the search record must be committed before the v0.2.0 README prose is finalized), not merge-gating. (See ADV-1.)

3. **CRA Art. 14 proximity (2026-06-11, ~3 weeks out).** The proximity raises the *urgency* of SECURITY.md but does **not** convert it from tag-gating to merge-gating. CRA obligations attach to "products with digital elements made available on the market" — the triggering event is the v0.2.0 *release*, not a commit on a branch. The proximity does mean: if Aldeia-IT intends to tag/publish v0.2.0 on or after 2026-06-11, SECURITY.md (with the Art. 14 rationale and a working vulnerability-reporting channel) should land in the *same* tag, and the tag work should not slip past the effective date without it. Flagged to CSO (joint owner). (See ADV-4.)

4. **Licensing posture.** The MIT posture is sound for what is being merged. The current dependency set (`fastmcp` Apache-2.0, `httpx` BSD-3-Clause, `qdrant-client` Apache-2.0, `psutil` BSD-3-Clause) contains no copyleft (no GPL/AGPL/SSPL/EUPL) — no MIT-incompatibility. The absence of a `NOTICE` file does **not** create a license-compliance defect *on `main`*: Apache-2.0 §4(d) attribution-redistribution duties are triggered by *distributing* the work (a release artifact / sdist / wheel), not by the source sitting in a public Git tree. NOTICE is tag-gating (must exist before the v0.2.0 release artifact is built/published). (See ADV-2 and ADV-3.)

---

## Spot-checks performed

- **README.md:3** — confirmed the hedged claim: *"To our knowledge, the first Anytype-native LLM wiki — combining Karpathy's pattern, Hermes' battle-tested operational policies, and Anytype's typed knowledge graph…"*
- **README.md:7** — confirmed the inline "Positioning-verification note" disclosing that the verification file may not yet exist and naming the pre-committed fallback that drops "first".
- **README.md:40–55** — confirmed the "Privacy and data flow" section is present, including the hosted-LLM ToS paragraph (README.md:47) and the GDPR Art. 4(7) / LGPD Art. 5(VI) controller disclaimer (README.md:51), and the "Source content and copyright" subsection (README.md:53–55). The hosted-LLM ToS paragraph (Legal #15) **landed** as the impl summary claimed.
- **README.md (full)** — grep for `Trademark|nominative|Any Association Zug|Supply-chain posture` returned **no matches**. The Trademarks footer (Legal #16) and the supply-chain posture section (CSO #7) are **NOT** in the README. Confirmed absent.
- **CONTRIBUTING.md (full, 55 lines)** — grep for `inbound|outbound|Developer Certificate|DCO` returned no matches. The inbound=outbound MIT paragraph (Legal #11) is **NOT** in it. Confirmed absent.
- **pyproject.toml:4** — description now reads *"An Anytype-native LLM wiki combining Karpathy's pattern with Anytype's typed knowledge graph…"* The broader "first … typed knowledge-graph store" claim that I flagged in R3 (ADV-R3-LEGAL-1) is **resolved** — no longer the broader claim, no longer says "first". Good.
- **pyproject.toml:9–14** — dependency set: `fastmcp>=2.0.0` (Apache-2.0), `httpx>=0.27.0` (BSD-3-Clause), `qdrant-client>=1.12.0` (Apache-2.0), `psutil>=5.9` (BSD-3-Clause). No copyleft. MIT-compatible.
- **LICENSE** — clean MIT, "Copyright (c) 2026 Aldeia IT". Standard text, no modification.
- **Repo root** — `ls` confirms **`NOTICE`, `SECURITY.md`, `CHANGELOG.md`, `MIGRATIONS.md` are all ABSENT.**
- **`.github/workflows/`** — directory **does not exist**. There is no CI at all. The license-scan CI step (Legal #10), `pip-audit`, `bandit`, `gitleaks` gates are net-new infrastructure, not modifications to existing CI. (Flagged to Infra below.)
- **`.aldeia/140…/positioning-verification.md`** and **`patch-decision.md`** — both **ABSENT**.
- **`.aldeia/context/business.md:21,31`** — confirmed the repo is explicitly framed as *"marketing for Aldeia IT's AI pipeline tooling"* with value as a *"reputation + marketing funnel."* This is the load-bearing fact for the CRA "commercial activity" analysis (Recital 18).
- **`.aldeia/context/compliance.md`** — confirms local-only, no telemetry, no cloud, "No PII handling beyond what users put in their Anytype notes." Consistent with the README controller disclaimer.

---

## Findings

### BLOCKING

_None._

The central governance question — does merging this code to a public `main` create legal exposure that must be cured before the merge — resolves **no** on every axis I am responsible for. There is no merge blocker from the Legal angle.

### ADVISORY

#### ADV-IMPL-LEGAL-1 — [Legal / CPO-overlap] `positioning-verification.md` is TAG-gating, not merge-gating. Hedged claim is mergeable as-is.

**Description.** README.md:3 carries "To our knowledge, the first Anytype-native LLM wiki…" with the README.md:7 note disclosing the pending `positioning-verification.md` and the pre-committed fallback. The verification artifact does not yet exist. This claim is **already public** on the live repo and has been since the R2/R3 reconciliation; merging v0.2.0 changes nothing about it.

**Legal basis.** US Lanham Act §43(a) (false advertising — requires falsity + materiality + likelihood of deception); Brazilian CDC Art. 37 (*publicidade enganosa* — stricter civil liability). The "to our knowledge" qualifier converts an unqualified factual assertion into a qualified, good-faith representation; the inline pending-verification note demonstrates reasonable diligence in progress; the pre-committed fallback demonstrates the maintainer will retract the "first" claim if the search does not substantiate it. This posture is defensible for an interim/pre-release public state.

**Recommended action.** Merge as-is. Before `git tag v0.2.0`, commit `positioning-verification.md` (per spec.md:768 — verbatim search queries, dates, finding count, near-match URLs with one-line notes, committed conclusion) and finalize the README prose to either keep "first" (if substantiated) or adopt the fallback. **Merge-gating: NO. Tag-gating: YES.** Positioning strategy is CPO-owned; I have messaged CPO to confirm alignment.

#### ADV-IMPL-LEGAL-2 — [Legal] `NOTICE` file is TAG-gating, not merge-gating. No license-compliance defect created on `main`.

**Description.** No `NOTICE` file exists at repo root. Spec.md:773 (Legal #10) requires one enumerating direct deps with SPDX IDs + the concatenated Apache-2.0 upstream NOTICE contents for `fastmcp` and `qdrant-client` + model attribution.

**Legal basis.** Apache License 2.0 §4(d): the attribution / NOTICE-propagation obligation is triggered by **distributing** the Work or Derivative Works (a redistributable artifact). A public Git source tree is not a §4(d) "distribution" of a compiled/packaged derivative in the sense that triggers the NOTICE-bundling duty; the operative trigger is building and shipping the sdist/wheel (PyPI publish) or a release artifact. MIT §(the copyright-notice-inclusion clause) is satisfied by the in-tree LICENSE. There is therefore **no license-compliance defect on `main`** from the missing NOTICE.

**Recommended action.** Merge as-is. Generate `NOTICE` (from `uv export` + `pip-licenses`) and commit it before the v0.2.0 release artifact is built/published. **Merge-gating: NO. Tag-gating: YES** (and hard-required before any PyPI publish).

#### ADV-IMPL-LEGAL-3 — [Legal / Infra-overlap] License-scan CI step is TAG-gating. Note: no CI exists at all.

**Description.** Spec.md:774 (Legal #10) requires a `pip-licenses` CI step that fails on any GPL/AGPL/SSPL/EUPL in the transitive closure, separate from `pip-audit`. I verified there is **no `.github/workflows/` directory** — the repo has no CI whatsoever. So this is net-new infra, as are the `pip-audit`/`bandit`/`gitleaks` gates.

**Legal basis.** The license-scan is a *preventive control*, not a present-defect cure. The current dependency set is already copyleft-clean by manual inspection (see Summary Q4). The CI step protects against a *future* PR introducing a GPL/AGPL transitive dependency that would contaminate the MIT distribution. Its absence does not make today's tree non-compliant.

**Recommended action.** Merge as-is. Stand up the CI (including the license-scan) before the v0.2.0 tag — this is the natural moment, since the tag is also gated on `pip-audit`/`bandit`/`gitleaks` being green (spec.md:785–788). **Merge-gating: NO. Tag-gating: YES.** CI mechanics are Infra-owned; messaged Infra below.

#### ADV-IMPL-LEGAL-4 — [Legal / CSO-overlap] SECURITY.md (CRA Art. 14 rationale) is TAG-gating. CRA effective date 2026-06-11 raises tag-time urgency.

**Description.** No `SECURITY.md` exists. Spec.md:776 (Legal #14 / CSO) requires it with five sections including the CRA Art. 14 rationale paragraph (EU Reg 2024/2847, effective 2026-06-11). Today is 2026-05-22 — the effective date is ~3 weeks out (my R3 estimate of "7 weeks" was as of 2026-04-23; the window has tightened).

**Legal basis.** CRA Art. 14 vulnerability-reporting obligations attach to manufacturers of "products with digital elements made available on the market." The "making available" trigger is the v0.2.0 *release/tag/publish*, not a commit on a public branch. Critically, `business.md:21,31` frames this repo as a "reputation + marketing funnel" — under a strict Commission reading of Recital 18 ("commercial activity"), that framing is the factor that could pull an otherwise-exempt free-software project into CRA scope. This is precisely why SECURITY.md is preparedness Aldeia-IT should not skip at tag time.

**Recommended action.** Merge as-is. SECURITY.md must land before `git tag v0.2.0`. **If the tag is cut on/after 2026-06-11, SECURITY.md (with a working vulnerability-reporting channel — GitHub Security Advisories + backup email) must be in that tag.** I recommend Aldeia-IT either (a) land SECURITY.md now as cheap insurance regardless of tag timing, or (b) treat 2026-06-11 as a hard deadline for the posture work. **Merge-gating: NO. Tag-gating: YES (with date-driven urgency).** Security content + reporting channel are CSO-owned; messaged CSO.

#### ADV-IMPL-LEGAL-5 — [Legal] CONTRIBUTING.md inbound=outbound MIT paragraph is TAG-gating; cheap to land early.

**Description.** `CONTRIBUTING.md` (55 lines) has no inbound-license paragraph. Spec.md:775 (Legal #11) pre-commits the verbatim text (MIT inbound=outbound + optional DCO `git commit -s` for substantial contributions).

**Legal basis.** 17 U.S.C. §201; Brazilian Law 9.610/98 Art. 11; GitHub ToS §D.6 (inbound=outbound default for public repos). Between merge and the eventual CONTRIBUTING edit, any inbound PR relies on GitHub ToS §D.6 as the sole basis for the contribution being MIT-distributable. That is the *minimum-defensible baseline*, not a gap — so the missing paragraph is not a merge blocker. But it is cheap to land and eliminates the inbound-contribution window risk entirely.

**Recommended action.** Merge as-is. Land the paragraph before the v0.2.0 tag; consider landing it in the merge PR itself (single paragraph, minutes of cost) since the repo will plausibly attract community PRs the moment v0.2.0 lands and is announced. **Merge-gating: NO. Tag-gating: YES (recommend early).**

#### ADV-IMPL-LEGAL-6 — [Legal] README Trademarks footer (nominative-use) + Anytype brand-policy check are TAG-gating.

**Description.** No "Trademarks" footer in README. Spec.md:777 / spec.md:664–670 (Legal #16) pre-commits the nominative-fair-use disclaimer ("Anytype is a registered trademark of Any Association Zug… not affiliated with or endorsed by… nominative-fair-use doctrine, New Kids on the Block v. News Am. Publ'g, 9th Cir. 1992") and requires a dated check of `anytype.io`/`anytype.io/legal` brand policy before commit.

**Legal basis.** Nominative fair use (Lanham; New Kids three-prong test). The repo *already* uses "Anytype" nominatively throughout the live README (title, prose, links) without the disclaimer — so the merge does not increase trademark exposure relative to the already-public state. The disclaimer is risk-*reduction* that should be in place before the project is actively marketed to the Anytype community at the v0.2.0 announcement.

**Recommended action.** Merge as-is. Add the Trademarks footer before the v0.2.0 tag, after the dated brand-policy check (record URL + date in pre-release notes per spec.md:777). **Merge-gating: NO. Tag-gating: YES.**

---

## Items I am NOT flagging (and why)

- **GDPR/LGPD controller disclaimer** — already landed verbatim at README.md:51 with a verbatim fixture test gating it. No action.
- **Hosted-LLM ToS paragraph (Legal #15)** — landed verbatim at README.md:47. No action.
- **Source content / copyright notice (Legal A6)** — landed at README.md:53–55. Confirmed sufficient in R2/R3; still sufficient.
- **pyproject.toml description (R3 ADV-1)** — resolved; the broader "first … typed-KG store" claim is gone. No action.
- **Export controls (R2 A11)** — still N/A; v0.2.0 introduces no new crypto footprint (TSU exception + mass-market exemption continue to apply).
- **CHANGELOG.md / MIGRATIONS.md** — product/process artifacts, not Legal-owned. Tag-gating per the impl summary; I defer their classification to CPO/CTO.
- **CycloneDX SBOM (R2 A8, Tier 2)** — docketed; eligible for v0.2.x. Not a v0.2.0 gate.

---

## Cross-thread coordination

- **CSO** (messaged): SECURITY.md is jointly owned (Legal #14 / CSO). I've classified it tag-gating and asked CSO to confirm the no-CI state doesn't break their supply-chain merge sign-off, and flagged the 2026-06-11 CRA date as the tag deadline.
- **CPO** (messaged): positioning claim strategy is CPO-owned. I've confirmed the hedged claim is mergeable-as-is and `positioning-verification.md` is tag-gating, and asked CPO to confirm pyproject.toml:4 will not be re-broadened.
- **Infra** (will message): license-scan CI mechanics are Infra-owned, and the repo has no `.github/workflows/` at all — the entire CI suite (license-scan + pip-audit + bandit + gitleaks) is net-new and tag-gating.
- **CTO/QA**: no Legal overlap this round.

---

## Recommendation

**Target: `done`.** Advance to `done` / open the PR / merge to `main`. The merge creates no Legal exposure requiring a pre-merge cure. Zero BLOCKING.

**Hard condition on the SEPARATE tag step (not the merge):** before `git tag v0.2.0` is cut, the maintainer must walk the OSS-hygiene pre-release checklist (spec.md:772–793) — at minimum NOTICE (ADV-2), license-scan CI (ADV-3), SECURITY.md (ADV-4), CONTRIBUTING DCO paragraph (ADV-5), README Trademarks footer (ADV-6), and `positioning-verification.md` + README claim finalization (ADV-1). If the tag is cut on/after 2026-06-11, SECURITY.md is non-negotiable for that tag (ADV-4).

**Pipeline-improvement note (flag-early mandate):** the merge-vs-tag distinction held up cleanly this round only because the prior spec councils scoped every Legal item as a *checklist item with pre-committed verbatim text*, not as in-tree edits. That foresight is why none of these became merge blockers. Recommend the council preserve that pattern: for OSS-hygiene items, pre-commit the verbatim text in the spec checklist so the tag-time maintainer step is mechanical, not a re-litigation.

---

## Sign-off Statement

**Legal Counsel SIGNS OFF WITH ADVISORIES on impl #140 R1 (the v0.2.0 merge-to-`main` gate).** Zero BLOCKING. Six ADVISORY, all tag-gating, none merge-gating. The MIT posture is sound for what is being merged; no copyleft contamination; the missing NOTICE creates no license-compliance defect on `main` (Apache-2.0 §4(d) triggers on distribution, not on a public source tree). The hedged "first" positioning claim is an acceptable interim public state. The CRA Art. 14 effective date (2026-06-11) raises the *tag-time* urgency of SECURITY.md but does not gate the merge. Advance to `done`; the v0.2.0 *tag* remains gated on the maintainer-local pre-release checklist, which Jan should walk in full before tagging — and SECURITY.md must be in any tag cut on or after 2026-06-11.

— Legal Counsel (impl R1 governance reviewer)
