# CSO Council Assessment — Post-Spec R1 — #426

## Sign-off: APPROVE WITH CONDITIONS

## BLOCKING findings
None.

## ADVISORY findings

1. **The carried-forward `get_type` read-side probe must be a hard gate on the impl/test phase, not a soft "should."**
   The central data-integrity risk in this ticket is silent graph corruption: under `update-type`'s
   replace-not-merge contract, any live user property omitted from the union PATCH is destroyed for
   every object of that type. The write contract is empirically verified; the *read* contract
   (`GET /v1/spaces/{id}/types/{type_id}` — exact per-property field set, and whether `properties[]`
   ever paginates) is NOT. The spec carries this as a non-blocking impl/test precondition (Open
   Questions / BL-6.4). I accept that disposition at the strategic level because the design is
   safe-by-construction (see Rationale), but the *acceptance of risk* must be made explicit: if the
   live probe is silently skipped, the safety guards still hold by construction, but the team loses
   the one empirical confirmation that the guards are matching reality. **Recommended action:** the
   impl/test phase MUST treat the live probe as a blocking entry condition for shipping §3, and the
   recorded transcript (field set + pagination behavior) must land in `research.md` before the
   reconcile PATCH path is enabled against any real space. No code in §3 may merge without it.

2. **`get_type` is a single GET with no pagination loop, unlike every other list helper — the pagination guard is the sole defense and must be tested as the destructive-path gate.**
   Per the spec, `get_type` does not route through `_paginated_get`. The BL-6.3 pagination/shape
   guard (`pagination.has_more is True` or missing `properties` → abort, never PATCH) is therefore
   the only thing standing between a truncated read and destruction of the omitted properties. This
   is architecturally sound (fail-closed: a partial read aborts rather than PATCHes), but it places
   the entire data-integrity guarantee on one conditional. **Recommended action:** ensure the test
   plan includes an explicit "paginated/partial read → no PATCH issued" test case, not only the
   monotonic-union and never-drops cases already listed. The current Test Plan covers union/no-op/
   never-drops/partial-failure-recovery but does not enumerate a has_more=True abort test. Add it.

3. **No new trust boundary, but confirm the audit log is durable enough to reconstruct a destructive event.**
   SG-e adds an INFO-level log of the computed union before each PATCH. Given the blast radius
   (whole-type property-set replacement), this is the right instinct. **Recommended action (accepted
   risk if not done):** confirm the deployment captures INFO-level logs for `wiki_bootstrap` runs
   durably enough that, in the event of a real corruption, the exact union sent can be reconstructed
   post-hoc. If bootstrap runs only emit to ephemeral stdout, the audit value is reduced. This is an
   operational note, not a spec defect.

4. **Out-of-scope format-mismatch correction (SG-c) is the right call — flagged only so the risk is consciously owned.**
   Reconcile only ADDS missing keys; it never corrects a format mismatch on an already-present
   property. This is the correct scope decision (format migration is higher-risk and distinct). No
   action required — recorded here so the council owns the accepted residual: a `wiki_concept` whose
   live `wiki_last_reviewed` ever existed under a wrong format would not be repaired by this path.
   That scenario is not reachable from this change set.

## Rationale
The security posture is sound. No new trust boundary, credential, or secret-handling surface is
introduced — `get_type`/`update_type` reuse the existing Anytype API key and transport, and the
data is internal fleet wiki content, not regulated PII. The one genuine risk — silent graph
corruption via replace-not-merge — is contained by a defense-in-depth stack that is fail-closed by
construction: union-send (never delta), the monotonic-union guard (never shrink the live user set),
empty/None-payload refusal, the pagination/shape guard (partial read aborts rather than PATCHes),
name/format sourced from the declared schema rather than the untrusted live echo, an audit log
before each PATCH, and a never-drops regression test. I verified the load-bearing code claims
directly (lint gate entity-only at `lint.py:490`, the `types_skipped` append in the existing-types
branch at `bootstrap.py:281-285`, the tolerant accessor at `:273-277`, both version markers stamped
post-loop at `:422`/`:458`, `_empty_result` lacking `types_reconciled`); they are accurate. The
unverified read contract does NOT constitute a blocking gap because the guards make the reconcile
correct even against a sparse or paginated echo — but the empirical probe and the explicit
has_more-abort test (Advisories 1 and 2) are the conditions under which I sign off.

---
Relevant files:
- `/Users/Shared/development/anytype-llm-wiki-worktrees/426-surface-concept-contradictions-in-wiki-lint/.aldeia/426-surface-concept-contradictions-in-wiki-lint/spec.md`
- `/Users/Shared/development/anytype-llm-wiki-worktrees/426-surface-concept-contradictions-in-wiki-lint/src/anytype_llm_wiki/wiki/bootstrap.py`
- `/Users/Shared/development/anytype-llm-wiki-worktrees/426-surface-concept-contradictions-in-wiki-lint/src/anytype_llm_wiki/wiki/wiki_client.py`
- `/Users/Shared/development/anytype-llm-wiki-worktrees/426-surface-concept-contradictions-in-wiki-lint/src/anytype_llm_wiki/wiki/lint.py`
