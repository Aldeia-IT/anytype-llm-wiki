# Council Meeting — Post-spec (Round 2) — Legal Counsel Independent Assessment

**Date:** 2026-04-22
**Ticket:** #140 — Wiki Library Module: Port LLM Wiki Pattern onto Anytype
**Phase reviewed:** spec (R2 calibration re-review)
**Reviewer:** Legal Counsel (native specialist — R2 calibration)
**Scope of this document:** independent legal/compliance assessment of `spec.md` as it stands on 2026-04-22, followed by delta against the Round 1 Legal Counsel assessment (`council-spec-r1.md` lines 48-58) and a calibration verdict.

> Process note: this re-review exists because the R1 council was run under an architectural defect where specialist subagents fell back to `general-purpose` with role prompts injected. A parallel ticket (#172) showed real specialists caught BLOCKING findings that the impersonators missed. My mandate is to form my own view on #140 first, then calibrate.

---

## Verdict

**SIGN OFF WITH CONDITIONS.**

Zero BLOCKING findings. The legal/compliance posture of the spec is sound: MIT license integrity holds, the dependency license matrix is compatible, the privacy and content-rights notices cover the substantive points, and the "first Anytype-native LLM wiki" claim is adequately hedged with a verification gate and a ready-to-swap fallback line. Hosted-LLM consent via endpoint-hash ack file is proportionate for a single-operator tool.

Conditions are advisory follow-ups — each is low-cost documentation work landed on pre-release checklists, not a design change. None gate implementation start.

---

## Summary

I confirm the core legal posture the R1 Legal Counsel reached. After independent review I also agree with R1's direction on the "to our knowledge" qualifier, the data-controller framing, and the endpoint-hash ack being proportionate. I do raise five additional items R1 did not explicitly surface (LGPD-specific citation detail, CRA free-software exemption preconditions, LICENSE year check, CONTRIBUTING.md inbound-license clarification, hosted-LLM provider ToS pass-through wording precision). None is BLOCKING. The most consequential independent finding is that the CRA open-source exemption (Recital 18 / Art. 13 as enacted 2024-10) is conditional on **non-commercial development**; Aldeia-IT uses this repo partly as a reputation/marketing signal (per `.aldeia/context/business.md`), which complicates but does not defeat the exemption. This should be documented and monitored, not blocked today.

---

## Independent Findings

### BLOCKING

None.

### ADVISORY

#### A1. [Legal] Dependency license audit confirms compatibility; add a NOTICE file at v0.2.0 tag.

**Description.** I verified the spec's license claims against the actual repo state:

- **Runtime deps (current `pyproject.toml`):** `fastmcp>=2.0.0` (Apache-2.0), `httpx>=0.27.0` (BSD-3-Clause), `qdrant-client>=1.12.0` (Apache-2.0). All three are permissive and MIT-compatible. No GPL/AGPL contamination.
- **v0.3.0 additions per spec line 748, 1622:** `markdownify>=0.11.0,<0.12.0` (MIT), `pydantic>=2.6,<3.0` (MIT). Both MIT. No incompatibility.
- **Model assets, not distributed but transitively invoked:** `bge-m3` (MIT), Ollama runtime (MIT). Neither is vendored in the wheel, so the MIT license of the distributed artifact is unaffected. The user brings Ollama + models at runtime.
- **Transitive chain.** I did not audit every transitive dep programmatically; the spec delegates this to `pip-audit` in CI (line 1626). `pip-audit` covers CVE advisories but does **not** enforce license-compatibility. That is an unstated gap.

**Legal basis.** Attribution requirements of Apache-2.0 (§4) and BSD-3-Clause (§2) require reproducing copyright notices for redistributed software. MIT-only does not technically require an aggregated NOTICE, but when an Apache-2.0 dep ships inside the wheel, its NOTICE provisions propagate.

**Recommended action.**
1. Add a **license-scan step** to CI (`pip-licenses --format=json --with-urls` or `license-check`) that fails on any copyleft (GPL*/AGPL*/SSPL/EUPL) in the full transitive closure, on top of `pip-audit`. This is stronger than R1's "pip-audit clean" claim, which does not cover license compatibility.
2. At v0.2.0 tag, add a top-level `NOTICE` file (or `THIRD_PARTY_NOTICES.md`) enumerating: (a) direct deps with SPDX identifier and URL, (b) any Apache-2.0 deps' upstream NOTICE contents concatenated, (c) model attribution (bge-m3, any LLM used). Generated from `uv export` + `pip-licenses`; <1 hour work.

#### A2. [Legal] LICENSE file integrity — year and copyright holder both present; inbound-license default is ambiguous.

**Description.** `LICENSE` (read directly) is a clean MIT with `Copyright (c) 2026 Aldeia IT`. The year matches today (2026-04-22) and the holder is consistent with `pyproject.toml` author and `.aldeia/context/business.md`. No defect. Git log reference in R1 (`72dca07 Fix company name in LICENSE`) is consistent.

However, `CONTRIBUTING.md` (read directly, 55 lines) contains no inbound-license policy. There is no CLA, no DCO sign-off requirement, and no "by submitting you license your contribution under the MIT License" clause. Under US law and Brazilian copyright law, the default is that contributors retain their copyright; absent an express grant, the project has an implied license that is narrower than the MIT license it redistributes under. GitHub's Terms of Service §D.6 provide a **licensing inbound=outbound** default when contributing to a public repo, which partially mitigates this, but that's GitHub's ToS, not a contract between Aldeia-IT and contributors directly.

**Legal basis.** 17 U.S.C. §201 (US copyright authorship default), Brazilian Law 9.610/98 Art. 11 (authorship retention). GitHub ToS §D.6 (inbound=outbound default). Standard OSS practice: SFLC, Apache, and most mature OSS projects either require CLA/DCO or embed an explicit "by contributing you agree to license under [X]" clause in CONTRIBUTING.md.

**Recommended action.** Add one paragraph to `CONTRIBUTING.md`:

> By submitting a pull request, you agree that your contribution is licensed under the MIT License (the project's license) and that you have the right to make the contribution. For substantial contributions we may request a Developer Certificate of Origin (DCO) sign-off (`git commit -s`).

This is the minimum defensible inbound-license posture for an MIT project without a full CLA. Land on the v0.2.0 pre-release checklist.

#### A3. [Legal] GDPR/LGPD "user-as-controller" framing is defensible, but the LGPD phrasing could be tightened.

**Description.** README additions (spec lines 649, 651):

> Content rights and PII: you are responsible for ensuring you have the right to ingest and store the content you provide. [...]
>
> This module is a tool, not a data controller under GDPR/LGPD. Operational responsibility for data protection rests with the operator (you).

The substance is correct under both regimes — a locally-executed OSS tool without telemetry where Aldeia-IT does not determine purposes or means of processing is not a controller under GDPR Art. 4(7) or LGPD Art. 5(VI). The phrasing "This module is a tool, not a data controller" is slightly imprecise: software cannot *be* a controller under either regime — the controller is always a natural or legal person. What the sentence means is "Aldeia-IT, as the publisher of this tool, is not a controller of data you process with it." That is correct, but the current phrasing could be read by a lay reader as disclaiming the user's controller status too, which is the opposite of the intended allocation.

**Legal basis.** GDPR Art. 4(7) ("'controller' means the natural or legal person... which, alone or jointly with others, determines the purposes and means of the processing of personal data"). LGPD Art. 5(VI) ("controlador: pessoa natural ou jurídica, de direito público ou privado, a quem competem as decisões referentes ao tratamento de dados pessoais"). Both regimes attach controllership to persons, not software.

**Brazilian AI framework note.** Brazilian Law 14.533/2023 (the AI framework pilot law, sectoral application) is not yet broadly applied to end-user developer tooling. There is also PL 2338/2023 (the draft comprehensive AI bill, still in legislative process as of April 2026). Neither imposes enforceable obligations on Aldeia-IT as a publisher today. Monitoring is appropriate; no action needed at v0.2.0.

**Recommended action.** Minor phrasing revision — replace the closing two sentences with:

> Aldeia IT, as the publisher of this open-source module, does not determine the purposes or means of data processing that you perform with it, and is therefore not a controller of your data under GDPR Art. 4(7) or LGPD Art. 5(VI). You are the controller — operational responsibility for data protection (lawful basis, consent where required, data-subject rights, retention, security) rests with you.

Same substance, tighter legal precision, no liability change.

#### A4. [Legal] Hosted-LLM consent flow via endpoint-hash ack file is proportionate; document its limits.

**Description.** Spec lines 1631-1637 describe a first-run banner that warns when `WIKI_EXTRACT_ENDPOINT` is non-localhost, plus an ack file keyed by `sha256(endpoint)[:8]`. This re-prompts on endpoint change but, as the CSO already noted in R1 Advisory #17, does NOT re-prompt when the same hostname resolves to a new provider (CDN repoint, MITM, hostile DNS).

From a legal perspective: informed-consent norms under GDPR (Art. 7) and LGPD (Art. 8) require consent to be "freely given, specific, informed, and unambiguous." A first-run banner + persisted ack satisfies the form requirement for a technically savvy operator configuring a tool on their own machine. The 8-character SHA-256 truncation does not meaningfully increase collision risk for the consent purpose (you would need a targeted preimage attack on a specific endpoint hash to suppress re-prompting — a threat model that is not credible for this use case).

**Legal basis.** GDPR Art. 7 (conditions for consent); LGPD Art. 8 (same). ICO guidance on "specific and informed" consent.

**Recommended action.** None at this layer — the CSO already flagged the DNS/CDN caveat as Advisory #17 for README documentation. From Legal's perspective, the ack flow is sufficient for the publisher's compliance posture. No publisher-side obligation to notify an operator of processor flow exists here because the operator, not the publisher, determines the processor (by setting the env var).

#### A5. [Legal] "First Anytype-native LLM wiki" claim is adequately hedged; require the verification record to ship *with* the v0.2.0 tag.

**Description.** Spec lines 36, 175-179, and pre-release checklist line 729 address this. The mechanism: "to our knowledge" qualifier + documented pre-release search of Anytype forum + anytype-mcp repo + GitHub + committed fallback one-liner. R1 Legal called this sufficient.

I agree this is sufficient **if executed**. The risk is execution drift: "claim verified — result documented inline in the PR description" is convention, not a CI-enforced artifact. A future tagger could forget, or could document weakly ("I searched and didn't find anything"). The legal defensibility depends on reproducibility.

**Legal basis.** US Lanham Act §43(a) (false advertising requires falsity + materiality + likelihood of consumer deception); Brazilian CDC Art. 37 (publicidade enganosa — deceptive advertising; stricter than Lanham in that intent is not required for civil liability). Brazilian law is the higher bar for an Aldeia-IT-published project. Reasonable diligence (search + qualifier + fallback) is a defense, but only if documented.

This also aligns with CPO Advisory #12 on reproducibility.

**Recommended action.** Harden the verification step: require the PR description to include (a) verbatim search queries used, (b) dates, (c) zero-or-nonzero finding count, (d) URLs of any near-matches reviewed. The `patch-decision.md` pattern (spec line 727) is the right analog — a committed artifact lives with the repo. Extend the spec to require a `positioning-verification.md` committed alongside `patch-decision.md` at v0.2.0 tag. This makes future "was this claim diligenced?" questions answerable from git alone.

#### A6. [Legal] Copyright of ingested content — the module's secondary role is adequately disclaimed; no further action.

**Description.** Spec lines 655-657 tell the operator they are responsible for the copyright status of content they ingest. The module stores extracted fragments in the operator's own Anytype space and, if configured, transmits them to a third-party LLM provider.

The module does not itself create a secondary copyright issue: the operator is the one fixing copies, the operator is the one transmitting to the provider, and the module is an instrumentality. Under US fair-use analysis (17 U.S.C. §107), LLM extraction for internal note-taking is likely transformative research use; this is precisely the scenario *Authors Guild v. Google* (2nd Cir. 2015) and *Bartz v. Anthropic* (N.D. Cal. 2025, pre-settlement) frame as defensible for the end user. Brazilian copyright (Law 9.610/98 Art. 46) has narrower fair-dealing exemptions, but private-study use is enumerated.

The existing notice is sufficient. The only practical gap is that the notice does not call out paywalled-content-specific scenarios (e.g., arxiv preprints vs. Elsevier PDFs the user downloaded); the current wording ("Paywalled content, proprietary documents you do not have rights to redistribute, and third-party material you only have read access to should be treated carefully") handles this adequately.

**Legal basis.** 17 U.S.C. §107, §106; Brazilian Law 9.610/98 Art. 46. The operator's terms-of-use compliance with source platforms (e.g., arxiv.org terms, publisher terms) is the dominant exposure, and that is correctly placed on the operator.

**Recommended action.** None.

#### A7. [Legal] SECURITY.md + coordinated disclosure — CRA preconditions mean this is higher priority than R1 framed.

**Description.** `SECURITY.md` does not exist in the repo today. R1 Legal flagged it as an advisory follow-up for the v0.2.0 pre-release checklist (R1 Advisory #2).

The EU Cyber Resilience Act entered into force on 2024-12-10. Key dates:
- **2026-06-11 (approaching):** product manufacturers' vulnerability-disclosure reporting obligations begin (Art. 14).
- **2027-12-11:** full applicability of conformity assessment.

CRA Art. 2(5) and Recital 18 carve out **free and open-source software** — but the exemption is conditional. Specifically, Recital 18 (as enacted) says OSS developed "outside the course of a commercial activity" is out of scope. The Commission's interpretation (and industry legal analysis through 2025-2026) is that "commercial activity" includes:
- Monetization (obvious cases: paid support, SaaS offering).
- **Use as a promotion / reputation signal for a commercial entity** (less obvious; actively debated).

Per `.aldeia/context/business.md` line 21: "*Published as an open-source tool for the Anytype community. Builds reputation and serves as marketing for Aldeia IT's AI pipeline tooling.*" This explicit marketing purpose could, under a strict Commission interpretation, pull the project into CRA scope — it is not the clean "individual contributor scratching an itch" case the exemption most comfortably covers.

The Open Source Stewards concept (CRA Art. 24) is a softer alternative regime for entities that facilitate OSS development; that is not directly available to Aldeia-IT.

**Legal basis.** EU Regulation 2024/2847 (CRA). Art. 2(5), Recital 18, Art. 14, Art. 24. Industry legal analysis (Eclipse, Linux Foundation, OpenForum Europe) through 2025-2026.

**Recommended action.** Upgrade R1 Advisory #2 priority:
1. `SECURITY.md` on the **v0.2.0 pre-release checklist** (aligned with R1, but reframed as CRA-preparation not community-norms).
2. Contents: supported-version statement, private disclosure channel (GitHub Security Advisories + `security@aldeia-it.br` or equivalent), response-time expectation (e.g., "acknowledge within 72 hours, triage within 14 days"), public advisory format.
3. Begin monitoring the "commercial activity" interpretation in late 2026 as CRA Art. 14 effective date approaches. If Aldeia-IT continues to frame this repo as marketing, consider either (a) softening the marketing framing, or (b) preparing for CRA obligations.

This is advisory because no CRA obligation is enforceable today (pre-2026-06-11 for vuln reporting, pre-2027-12-11 for full conformity), but the posture work should start at v0.2.0.

#### A8. [Legal] SBOM generation at tag time — aligned with R1; no new delta.

**Description.** R1 Advisory #3. I agree. `uv export --format cyclonedx` (if supported) or `cyclonedx-py` against the resolved `uv.lock` produces a CycloneDX 1.5+ SBOM attached to each GitHub Release. This aligns with CRA Art. 13 requirements (software bill of materials) once they become effective.

**Legal basis.** US EO 14028 §4(e) (federal supply chain SBOM baseline); EU CRA Art. 13; NIST SP 800-218.

**Recommended action.** Adopt as R1 framed (tier-2 — can land v0.2.x if not v0.2.0).

#### A9. [Legal] Trademark nominative-use footer — adopt at v0.2.0, check Anytype brand guidelines first.

**Description.** R1 Advisory #4. I agree with R1's advisory framing. My independent read:

- **Nominative fair use test (New Kids on the Block v. News Am. Publ'g, 9th Cir. 1992):** (1) the product or service in question must not be readily identifiable without use of the trademark; (2) only so much of the mark may be used as is reasonably necessary; (3) the use must not suggest sponsorship or endorsement. The positioning "Anytype-native LLM wiki" passes all three: "Anytype" is the only way to identify the target platform, usage is minimal, and no endorsement is implied. A footer disclaimer strengthens point (3) further.
- **Brazilian trademark law (Lei 9.279/96 Art. 132):** recognizes analogous nominative use, typically more restrictively interpreted. Disclaimer footer is prudent.

I have not been able to confirm whether Anytype has a public community-integration / trademark-use policy. The spec already flags this as "Jan's call" at line 1746 ("Community branding"). A pre-v0.2.0 check of `anytype.io/legal` or equivalent is recommended; if Anytype publishes a community-use policy, follow it.

**Whether to BLOCK on this.** The CRA/PyPI-publish question is: if v0.2.0 publishes to PyPI using "Anytype-native" positioning before Jan confirms Anytype's brand policy, and Anytype subsequently raises a concern, the remediation (rename positioning, re-tag) is inexpensive. This does not rise to BLOCKING given the minimal trademark claim and the ready nominative-use defense.

**Recommended action.** Adopt R1 Advisory #4 with one extension: before PyPI publish of v0.2.0, Jan (or whoever tags) should have a one-paragraph record in the pre-release checklist noting "Anytype trademark guidelines checked at [URL]; nominative use policy [exists/not found]; footer language drafted [here]." Reproducible due-diligence record, analogous to A5.

#### A10. [Legal] Hosted-LLM provider ToS pass-through reminder — R1 #5, with more precise wording.

**Description.** R1 Advisory #5 proposed one sentence. I agree this belongs in the README's "Privacy and data flow" section. My suggested precise wording:

> When you configure `WIKI_EXTRACT_MODEL` to point at a hosted LLM API, your ingested source content is processed under that provider's Terms of Service and data-handling policies — including their training-on-input, data-retention, and data-residency terms. Review those terms before configuring a hosted endpoint, and prefer providers that offer opt-out-from-training or enterprise no-train defaults when your ingest content is sensitive. The anytype-llm-wiki maintainers have no visibility into or control over third-party provider policies.

Two-sentence version; lands on v0.2.0 README (before v0.3.0 actually ships hosted-LLM flow is strictly a config option; better to land the warning pre-emptively).

#### A11. [Legal] Export controls — not applicable to this distribution.

**Description.** The module ships Python source that depends on `httpx` (which provides TLS via system OpenSSL) and interfaces with LLMs (which may or may not exceed encryption thresholds). Per US EAR §742.15 and the mass-market software exemption (§740.17(b), ECCN 5D002), pure source distribution of general-purpose cryptography via PyPI qualifies for License Exception ENC with no filing required, and the TSU exception (§740.13(e)) covers publicly-available source.

No Anatel registration applies (the module doesn't ship radio/telecom hardware).

**Legal basis.** US EAR 15 CFR Parts 730-774, specifically §740.13(e), §740.17, §742.15. Brazilian Anatel Resolution 242/2000 (hardware scope).

**Recommended action.** None. Note for the record — this is not a live exposure.

---

## R1 Delta

| R1 Legal finding | R2 calibration | Notes |
|---|---|---|
| MIT license integrity clean; all deps MIT-compatible | **Agree — verified independently.** httpx (BSD-3), fastmcp (Apache-2.0), qdrant-client (Apache-2.0), markdownify (MIT), pydantic (MIT), bge-m3 (MIT) all confirmed. | R1 was correct. I extend with A1 (NOTICE file) and a license-scan CI step — gap R1 missed. |
| "First Anytype-native" claim hedging is sufficient | **Agree with extension.** Qualifier + fallback + verification step are defensible under Lanham and CDC Art. 37. | A5 tightens the verification record to a committed artifact. R1 relied on the spec's "documented inline in the PR description" phrasing, which I find marginal. |
| Privacy notice addresses all five product-council points | **Agree.** | A3 refines LGPD phrasing precision; A10 refines hosted-LLM provider ToS wording. Both are polish, not substance. |
| Aldeia-IT not a controller under GDPR/LGPD | **Agree.** | Confirmed under Art. 4(7) / Art. 5(VI). A3 fixes the "module is a tool, not a controller" phrasing which is technically imprecise. |
| Endpoint-hash ack is proportionate for single-operator tool | **Agree.** | A4 confirms the legal sufficiency of the consent form. No change. |
| SECURITY.md + SBOM + trademark footer + ToS reminder + LGPD phrasing + embedding-inversion wording — all advisory | **Agree on SBOM/trademark/ToS/LGPD phrasing/embedding-inversion. Partial disagreement on SECURITY.md priority.** | A7 upgrades SECURITY.md rationale — R1 framed as "community expectation"; the stronger rationale is CRA Art. 14 preparation given Aldeia-IT's marketing framing of this repo (per `.aldeia/context/business.md`). Not BLOCKING, but higher-priority than R1 conveyed. |

### Items R1 Missed

1. **CONTRIBUTING.md has no inbound-license clause (A2).** R1 did not surface this. MIT-only repos without CLA/DCO rely on GitHub ToS §D.6 as an implicit license; mature OSS practice adds an explicit inbound=outbound statement. One paragraph fix.
2. **License-scan CI step, separate from pip-audit (A1).** R1 noted pip-audit clean in CI; pip-audit covers CVE advisories, not license-compatibility. A transitive GPL/AGPL could sneak in between pins and not trip pip-audit. `pip-licenses` or `license-check` fills this gap.
3. **Aggregated NOTICE file at v0.2.0 tag (A1).** R1 did not address Apache-2.0 NOTICE-propagation obligations (fastmcp, qdrant-client).
4. **LGPD phrasing precision (A3).** The R1-endorsed text "module is a tool, not a data controller" is technically imprecise under Art. 4(7) / Art. 5(VI). R1 did call out "LGPD-specific phrasing refinement" as a conditional follow-up but did not specify the change.
5. **CRA "commercial activity" exemption conditionality (A7).** R1 treated CRA SBOM requirements as future trending; R1 did not examine whether Aldeia-IT's marketing framing per business.md complicates the free-software exemption itself. This is the most consequential independent finding — not because it creates a current obligation, but because the posture work should start at v0.2.0 rather than post-hoc.

### Items R1 Got Right That Are Worth Restating

- The "to our knowledge" + fallback + search gate **is** sufficient diligence against false-advertising theories. I agree.
- The GDPR/LGPD analysis for Aldeia-IT-as-publisher is correct. I agree.
- Hosted-LLM ack flow is legally sufficient. I agree.
- No publisher exposure absent a hosted-instance offering. I agree.

R1 was directionally correct on every substantive legal question. The R1 assessment does not appear to have suffered from the subagent-fallback defect in its legal reasoning — the analysis reads as legally coherent, not generic-LLM-impersonating-Legal. My deltas are precision refinements and two genuinely missed items (A2 CONTRIBUTING.md inbound-license; A7 CRA framing), not opposing-direction defects.

---

## Calibration Verdict on R1

**R1 Legal Counsel assessment: SUBSTANTIALLY SOUND.**

- **Direction:** correct on every substantive question.
- **Completeness:** missed A2 (CONTRIBUTING.md inbound license) and A7 (CRA commercial-activity conditionality). Both are advisory, not BLOCKING.
- **Precision:** LGPD phrasing in the endorsed README text is technically imprecise (A3); endorsed without the refinement it needs.
- **Executional rigor:** the "to our knowledge" verification step was endorsed as sufficient. I narrowly agree — but flag that R1 did not push for a committed verification artifact (A5), leaving reproducibility to convention.

**Relative to the #172 calibration finding** (where real specialists caught 3 BLOCKING items R1 impersonators missed): for #140 Legal, I identify **zero BLOCKING items** R1 missed. The R1 Legal assessment does not exhibit the failure mode the #172 calibration surfaced. The spec's legal posture was competently reviewed in R1, and this R2 re-review finds refinements, not reversals.

---

## Sign-off Statement

**Legal Counsel SIGNS OFF on spec #140 with 11 ADVISORY conditions** (A1-A11 above). Zero BLOCKING. The spec may proceed to the next SDLC phase. The advisories should be tracked in the v0.2.0 and v0.3.0 pre-release checklists; none blocks implementation start. I recommend the council-chair synthesize A1 (NOTICE + license-scan), A2 (CONTRIBUTING.md inbound-license), A5 (verification-record committed artifact), A7 (SECURITY.md with CRA framing) onto the v0.2.0 pre-release checklist explicitly — these four items are the highest-leverage legal hygiene for an OSS tag publication.

— Legal Counsel (R2 calibration reviewer)
