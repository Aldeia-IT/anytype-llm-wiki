# Council Impl R1 — Chief Security Officer

**Ticket:** #287 — anytype-llm-wiki v0.6.0 Automated Cross-Object Contradiction Detection
**Gate:** POST-IMPL final delivery (strategic security sign-off, not line review)
**Date:** 2026-06-06
**Reviewer:** CSO (council seat)

## Verdict

**SIGN OFF WITH ADVISORIES**

## BLOCKING findings

None.

## ADVISORY findings

### ADV-1 — Pre-v0.6.0 remote users are not re-prompted for the widened peer-fact egress class

**Risk:** LOW (accepted). The consent ack is keyed by `sha256(endpoint)[:8]`
(`extraction.py:415`) and persists per endpoint. An operator who already acked a
remote `WIKI_EXTRACT_ENDPOINT` under the v0.3.0 "source content" model will NOT see
a new banner on upgrade, even though the off-machine data class has broadened to
include peer `wiki_facts` distilled from earlier ingests. The updated banner copy
(`extraction.py:_default_emit_banner`) only reaches operators who configure a *new*
endpoint or clear the ack.

This is a deliberate, Legal-confirmed decision (post-spec addendum item 4:
operator-as-controller; transparency obligation, not a new consent gate; re-consent
"RECOMMENDED but NOT legally required"). The implementer chose banner-copy-only and
disclosed it in CHANGELOG, which is within the sanctioned option set.

**Recommended action:** None required for this release. Note the accepted risk in
the release runbook. If future scope widens further (e.g., DI-3 Qdrant pre-filter
shipping *unlinked* peer facts off-machine), reconsider a version-bumped ack key to
force re-consent. Not a blocker now.

### ADV-2 — Prompt-injection controls are defense-in-depth, not a hard guarantee

**Risk:** LOW (accepted). Peer `wiki_facts` are attacker-influenceable
LLM-summarized source text flowing into the contradiction prompt. The controls are
sound and layered: (a) anti-injection preamble present verbatim in both
`prompts/contradiction.md` and the `_load_contradiction_prompt()` OSError fallback;
(b) rendering via `str.replace` + `json.dumps` (never `.format`), so candidate JSON
braces cannot break out; (c) the hallucinated-ID filter (SG-2) caps the blast radius
— even a fully successful injection cannot write a `wiki_contradictions` link to any
object outside the pipeline-supplied candidate set (`candidate_set` membership check
at `ingest.py` `detect_contradictions`), and the worst achievable outcome is a
spurious or suppressed link between two already-linked in-space entities, which a
human resolves (no auto-merge, facts never overwritten).

The residual risk is inherent: a preamble is not a cryptographic boundary, and a
determined injection could bias the contradiction verdict (false positive/negative)
within the candidate set. Because the output is advisory (lint flags for human
review, `wiki_last_reviewed` stays null) and the write surface is bounded, this is
an acceptable posture for a passive-but-active detection feature.

**Recommended action:** None required. The SG-2 filter is the load-bearing control
and it is present and tested (AC-11). Accept the residual.

### ADV-3 — No-target-GET platform assumption is a correctness gate with a security-adjacent failure mode

**Risk:** LOW (accepted; tracked as pre-tag verification). The no-target-GET design
assumes POST `/search` returns hydrated `properties[].objects` arrays. If wrong,
the candidate set is empty and detection silently never fires — "green-in-CI,
dead-in-prod." This is primarily a correctness/efficacy issue (CTO/QA owned), but it
has a security adjacency: a contradiction-detection feature that silently no-ops
recreates the *over-trust* failure mode this release exists to eliminate. The
fallback (one `get_object`, +1 call) is pre-identified and the AC-1 fixture is
honestly annotated as proving only the parsing contract.

**Recommended action:** Confirm against a live Anytype search response before tag,
per the existing pre-tag runbook. Already owned by CTO/QA seats; flagged here only
because a silent no-op undermines the security narrative of the feature. Not a CSO
blocker.

## Rationale

The strategic security posture is acceptable. I evaluated the four security-relevant
dimensions that this release actually moves:

1. **Widened egress / data handling.** The new peer-fact data class (`wiki_facts`
   distilled from earlier ingests) is correctly governed by the existing
   `check_remote_endpoint_consent` gate, which fires at the ingest entry path
   (`ingest.py:602`) *before* `_run_ingest` is reachable, whenever
   `WIKI_EXTRACT_ENDPOINT` is set. The contradiction path derives the same endpoint
   and is only reached inside `_run_ingest`, so no egress escapes the gate. Peer
   reads use `read_client.get_object(space_id, peer_id)` with the same `space_id` —
   no cross-space data access is introduced. Disclosure is shipped in lockstep
   (README privacy notice, the `contradiction_unresolved` lint section, CHANGELOG,
   consent-banner copy, and the verbatim privacy fixture), closing the
   transparency gap four council seats flagged at spec time. This is the right
   control model for operator-as-controller.

2. **Prompt-injection surface.** Adequately mitigated in depth (ADV-2). The
   hallucinated-ID filter is the decisive control: it converts a prompt-injection
   from a potential arbitrary-write into, at worst, a bounded advisory false signal
   between already-linked in-space entities. No auto-merge, facts never overwritten,
   `wiki_last_reviewed` untouched.

3. **Credential/secret handling.** Rollback notes are scrubbed via
   `{type(exc).__name__}: {scrub_credentials(str(exc))[:120]}` at both note sites
   (`_write_contradiction_links`); no raw httpx body reaches `wiki_notes`. No
   hardcoded secrets, no new config variables, no new credential surface. Prompt
   path is a fixed module constant — no traversal.

4. **Attack surface / blast radius.** No new network listener, no new auth
   boundary, no schema change (`WIKI_SCHEMA_VERSION` stays 0.4.1). The feature only
   adds outbound LLM calls (already consent-gated) and in-space PATCH writes bounded
   to the candidate set. The A/B rollback degrades safely (status=partial, entity
   fact-write not rolled back) and detection failure is non-blocking by design.

No pattern of minor issues suggesting a systemic problem. The in-phase security
review was clean, and my independent read of the consent-gate ordering, the
cross-space boundary, the SG-2 filter, and the scrubbing confirms it. The three
advisories are accepted risks with clear owners and runbook tracking, none rising to
a release blocker.

**Sign-off:** I sign off on the security posture of #287 v0.6.0 for advancement to
PR, subject to the three advisories above being acknowledged (not resolved) in the
release record. ADV-3 (no-target-GET live verification) and the AC-8/AC-9 live smoke
remain pre-tag runbook items owned by CTO/QA; they are not security blockers.
