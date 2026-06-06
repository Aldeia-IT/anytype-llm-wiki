# Council Impl Review R1 — Legal / Compliance

**Ticket:** #287 — anytype-llm-wiki v0.6.0 "Automated Cross-Object Contradiction Detection"
**Phase:** POST-IMPL final delivery gate (governance sign-off, pre-PR)
**Reviewer:** General Counsel (Legal)
**Date:** 2026-06-06
**Diff basis:** `git diff 81b54d3..HEAD` (README.md, CHANGELOG.md, fixture, extraction.py consent banner) — read directly, not taken from summary.

## Verdict

**SIGN OFF WITH ADVISORIES**

The transparency/disclosure obligation I co-flagged as Legal-ADV-1 (post-spec addendum items 2/3/4; post-test addendum item 1) is **actually met in the shipped artifacts**, verified by reading the diff. No residual legal/compliance blocker.

## BLOCKING findings

None.

## ADVISORY findings

### Legal-ADV-1 (CARRIED, now SATISFIED) — Widened peer-fact egress disclosure
- **Status:** Resolved in shipped docs. Verified across four lockstep surfaces:
  - README "Privacy and data flow" (line ~46): hosted-LLM extraction bullet now states the endpoint "**also receives the `wiki_facts` of already-linked peer entities** — content distilled from *earlier* ingests, not just the current source." Consent-banner sentence updated to "before any source **or previously-stored wiki content** is transmitted."
  - README §5 security/extraction note: discloses the broadened off-machine data class and states the existing consent gate governs all of it; no separate gate added.
  - CHANGELOG v0.6.0: dedicated "Widened off-machine egress disclosure" entry; explicitly confirms the consent gate "continues to govern **all** off-machine egress including this new peer-fact class; no new gate is added and no re-consent is forced."
  - Verbatim privacy fixture (`tests/wiki/fixtures/readme_privacy_notice_verbatim.md`): updated in lockstep — byte-consistent with the README at the NEW peer-fact wording, not the stale v0.3.0 "source content you ingest" text. This closes the masking risk the post-test council flagged (substring test could have passed against stale wording).
  - Consent banner copy (`extraction.py` `_default_emit_banner`): now reads "transmit source **and previously-stored wiki content** off-machine ... includes the wiki_facts of already-linked peer entities (distilled from earlier ingests)."
- **Legal basis:** Transparency obligation under the operator-as-controller / self-hosted model (LGPD art. 9 / GDPR arts. 13–14 information duties run to the operator, who is controller; the maintainer is tooling-provider, not processor of operator data). My prior position holds: the existing consent gate is the sufficient *control*; the remedy was *disclosure copy as a gated deliverable*. That deliverable landed.
- **Recommended action:** None required for sign-off. The version-bumped consent ack key (forced re-consent) was RECOMMENDED, not legally required; impl chose banner-copy-only and documented that choice in the CHANGELOG, which is the legally acceptable path under operator-as-controller. Acceptable as-is.

### Legal-ADV-2 — Over-trust / scope-limitation disclosure (operator reliance risk)
- **Description:** Activating `contradiction_unresolved` and removing the in-product "PASSIVE" caveat makes the check read as fully active, while detection is bounded to linked-entities-only (DI-3) and entity-only (DI-1). Without scope disclosure, an operator could treat a green contradiction column as a guarantee — a reliance/adequacy concern.
- **Status:** Resolved. README contradiction/lint section carries both limitations in plain operator language ("Linked entities only", "Entity-only; concept scope deferred", "do not over-trust a clean contradiction column"); CHANGELOG carries the same; the lint-table row label changed from "passive" to "active in v0.6.0; scoped". Per the in-phase completeness review, `test_docs_disclosure.py` asserts the replacement copy is present, so it cannot silently regress.
- **Legal basis:** Fitness-for-purpose / no-misrepresentation. For an MIT-licensed, no-warranty, free OSS tool the exposure is low, but disclosed scope limits reduce any reliance-based claim.
- **Recommended action:** None. Acceptable.

### Legal-ADV-3 — Third-party provider terms remain operator's responsibility (unchanged, noted)
- **Description:** Peer `wiki_facts` now flow to whatever hosted LLM the operator configures, processed under that provider's ToS (training-on-input, retention, residency). The README "Hosted-LLM provider terms" bullet already places this duty on the operator and disclaims maintainer visibility/control. v0.6.0 widens the *data class* under that same clause; the clause text did not need to change because it already speaks to "ingested source content ... under that provider's Terms of Service." The new privacy bullet now makes the broadened class explicit upstream of it.
- **Legal basis:** Third-party ToS compliance; controller obligation sits with the operator.
- **Recommended action:** None blocking. ADVISORY-only nit for a future docs pass: the "Hosted-LLM provider terms" bullet still says "your ingested source content is processed under that provider's terms" — it would read more precisely as "ingested source content and previously-stored peer wiki content." Not required for this release; the adjacent privacy bullet and §5 note already disclose the broadened class.

### Legal-ADV-4 (CROSSOVER → CSO) — Platform assumption is a data-correctness, not legal, gate
- **Description:** The one carried pre-tag risk (CTO-ADV-1: no-target-GET assumes POST `/search` hydrates objects-format arrays) is an engineering/data-integrity verification, not a legal/privacy gate. It does not affect the disclosure obligations, which are satisfied regardless of whether detection fires. Flagging to the CSO only because security and I share the data-flow surface: if the fallback `get_object` is added pre-tag, it is a read-plane call within the same space — no new egress class, no disclosure delta. No legal action required either way.
- **Recommended action:** None from Legal. Defer to CSO/CTO pre-tag runbook.

## Rationale

My mandate was narrow: confirm the transparency obligation was actually shipped (not summary-claimed) and decide residual legal risk. I read the `81b54d3..HEAD` diff directly. All four disclosure surfaces — README privacy bullet (~line 46), README §5 security note, CHANGELOG v0.6.0, and the verbatim fixture — carry the widened peer-fact egress disclosure at consistent, byte-matched wording, and the consent banner copy in `extraction.py` was updated in lockstep. The scope-limitation (over-trust) disclosure also landed with a CI presence gate.

The legal posture is unchanged from my post-spec position and is correct: self-hosted, operator-as-controller, MIT/no-warranty, no PII handling by the tool beyond what the operator places in their own space, no telemetry, off-machine egress remains opt-in behind an unchanged first-run consent gate. v0.6.0 broadens the *data class* transmitted under that gate but adds no new collection, no new recipient the operator did not configure, and no change of legal role. The obligation this triggered was transparency, and transparency was delivered as a gated deliverable. The choice to update banner copy without forcing re-consent is legally acceptable under operator-as-controller and was documented. No GDPR/LGPD DPA, retention-policy, cookie, or erasure obligation is newly implicated (no maintainer-side processing). Residual items (platform assumption, live smoke) are non-legal. I sign off.
