# Council Review — Post-Impl (Round 1) — Legal Counsel

**Date:** 2026-06-24
**Ticket:** aldeia-box#325 — Contradiction Detection: Extend to Concepts
**Phase reviewed:** impl (post-implementation governance)
**Client/Project:** anytype-llm-wiki (Aldeia IT — Jan Scheufen's open-source, local-first MCP wiki)
**Reviewer:** Legal Counsel (General Counsel)

---

## Verdict

**SIGN-OFF (clean). No legal, privacy, licensing, regulatory, ToS, IP, or contractual obstacle to advancing #325 to `done`.**

At the spec phase Legal was excused on the basis of "no new data handling, PII, trust
boundary, or licensing surface." Post-impl verification of the actual diff confirms that
basis held: the implementation introduces **no new legal surface** relative to the
already-shipped entity contradiction detection (#287, v0.6.0).

---

## BLOCKING

None.

---

## ADVISORY

None requiring action. Two observations recorded for completeness only:

1. **Context file naming drift (process note, not a #325 defect).** My mandate directs me to
   read `.aldeia/context/engagement.md`; that file does not exist. The equivalent contractual
   context lives in `.aldeia/context/business.md` (project is Jan's own MIT-licensed
   open-source tool; internal + public dual purpose; no third-party client engagement, no
   external SLA). The substantive contractual question — "does this meet obligations to a
   client?" — is therefore moot: there is no external client contract in play. No action for
   the impl worker; flagging the path mismatch to the council-chair for pipeline hygiene.

2. **Disclosure honesty is already correct (endorsed, no change).** The README/CHANGELOG edits
   accurately disclose that concept contradictions are *detected and cross-linked* but *not yet
   surfaced by `wiki_lint`* (follow-up #426), and correct the prior `High`→`critical` severity
   wording. From a consumer-protection / no-misrepresentation standpoint this is exactly right:
   neither the agent fleet nor the OSS community is led to infer a closed integrity loop. The
   `test_docs_disclosure.py` change enforces this disclosure as a test invariant — a positive.

---

## Rationale (per evaluation criterion)

**Data Privacy (GDPR / LGPD).** No new privacy surface. Concept `wiki_definition` text is
already-stored local user content, reused through the *existing* LLM prompt path that entity
`wiki_facts` already traverses. No new data class, no new collection, no new external
destination or transport. The `WIKI_EXTRACT_ENDPOINT` remote-LLM opt-in (the only off-machine
data flow in the product, consent-gated) is untouched — `detect_contradictions` reads the same
`os.environ.get("WIKI_EXTRACT_ENDPOINT")` it already read for entities. No new retention,
erasure, portability, cookie, or tracking implication. Local-first, no-telemetry posture
(compliance.md) is preserved. There is no new processing of personal data, so no DPA, ROPA
update, or LGPD/GDPR lawful-basis analysis is triggered.

**Licensing / Attribution.** No new dependency added by #325 (confirmed: `uv.lock` churn in the
diff is an already-merged pytest bump, not this ticket; the source diff adds only first-party
logic). No OSS license-compatibility, GPL/AGPL-contamination, or attribution concern. Project
remains MIT. Nothing in the diff or docs copies third-party code, content, or media. No
Creative Commons or media-licensing surface.

**Regulatory.** Not applicable. The change is a local correctness improvement to a
knowledge-graph integrity check. No financial-services/DeFi, export-control, age-verification,
or accessibility (WCAG) trigger. No UI surface added.

**Terms of Service.** No external third-party service ToS is implicated — the only network
calls are to the local Anytype API and local Ollama (or the user's own opted-in endpoint),
unchanged in kind. No user-agreement, privacy-policy, liability, or indemnification change.

**Intellectual Property.** No third-party IP used. No trade-secret exposure (local-only,
no new transport). The novel mechanism (kind-discriminated peer-text dispatch) is incremental
and unremarkable from a patent standpoint; no IP-protection action needed.

**Contractual / SLA / Warranty.** No external client contract or SLA (open-source, no-revenue,
reputation-driven — business.md). The deliverable meets the three literal ticket ACs. The
honest "surfacing is a follow-up" disclosure correctly avoids over-promising a closed loop —
the only warranty-adjacent risk, and it is mitigated.

**Security/Legal crossover (CSO coordination).** The CSO's spec-phase finding — concept text
enters the same anti-injection-fenced prompt as DATA, behind the same hallucinated-id
allowlist, no new trust boundary — is the same fact that disposes of the data-protection
question for Legal. No new breach-notification or data-protection exposure. No crossover issue
needs escalation; I concur with the upheld CSO position.

---

## Sign-off Statement

As Legal Counsel I **sign off** on aldeia-box#325. The implementation creates no new privacy
(GDPR/LGPD), licensing, regulatory, terms-of-service, intellectual-property, or contractual
risk versus the already-shipped entity detection. There is no legal or compliance reason to
withhold advancement to `done`. A clean sign-off is the warranted verdict.
