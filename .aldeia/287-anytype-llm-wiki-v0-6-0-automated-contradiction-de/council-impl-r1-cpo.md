# Council — POST-IMPL R1 — Chief Product Officer (#287)

**Phase:** POST-IMPL final delivery gate (governance, not code review)
**Ticket:** anytype-llm-wiki v0.6.0 — Automated Cross-Object Contradiction Detection
**Reviewer:** Chief Product Officer
**Date:** 2026-06-06

## Verdict

**SIGN-OFF (product-ready to open PR).** 0 BLOCKING, 2 ADVISORY.

All three product questions I was charged to confirm resolve in favor of shipping:
(a) the #289/#287 signal boundary is respected at the code level, not just on paper;
(b) the CPO-A-1 scope-limitation disclosure actually landed, reads in operator
language, and is protected by a CI regression gate; (c) scope discipline held — the
two deferrals (DI-1 concept, DI-3 semantic pre-filter) are intact and honestly
disclosed, and no feature crept in beyond the ticket.

## BLOCKING findings

None.

## ADVISORY findings

### ADV-1 — Cross-signal masking: a #289 clean-consolidation timestamp can suppress a later #287 contradiction finding

**Description.** The #289 same-object path (`remember.py:516-520`) writes
`wiki_last_reviewed = now()` whenever a consolidation completes with no intra-entity
conflicts (`not n_conflicts`). The #287 lint predicate is `contradictions and not
last_reviewed` (`lint.py:410`). If an entity is cleanly consolidated by `wiki_remember`
(setting `wiki_last_reviewed`) and *subsequently* acquires a cross-object
`wiki_contradictions` link via `wiki_ingest` (which deliberately never re-nulls
`wiki_last_reviewed`, per spec §3.4), the lint check will NOT fire — the stale review
timestamp masks a genuinely unreviewed cross-object contradiction.

**Impact on product/users.** This is the exact over-trust failure class v0.6.0 exists
to fix, reachable via a signal-ordering edge case rather than the passive-check path.
It is narrow (requires a clean #289 consolidation to precede a #287 detection on the
same entity) and is a property of the shared-schema design that predates this ticket —
#287 did not introduce it and correctly stays within its boundary by not touching
`wiki_last_reviewed`. The two signals remain distinct as Jan mandated; the interaction
is a schema-semantics gap, not a conflation.

**Recommended action.** Do not block #287 on this. Track as a v0.6.x product item:
either (a) `wiki_remember` re-nulls `wiki_last_reviewed` when it writes a new
contradiction-relevant change, or (b) the lint predicate compares
`wiki_last_reviewed` against the contradiction-link write time. Flag to the QA Director
so the acceptance model for the over-trust fix records this known residual. Hand to the
council-chair for the durable insight (I do not write Mem0).

### ADV-2 — The headline value claim is gated behind an unrun pre-tag platform check (no-target-GET)

**Description.** The core user-visible deliverable — "ingest auto-detects cross-object
contradictions" — depends on POST `/search` returning hydrated objects-format
`properties[].objects` arrays so `_relation_ids(target, "wiki_relations")` yields a
non-empty candidate set. No existing code reads relation arrays off a *search*
response; the AC-1 fixture proves only the parser contract. If the assumption is wrong,
the feature ships green-in-CI but the candidate set is always empty and detection
silently never fires — delivering zero user value while the lint check reads as active.

**Impact on product/users.** This is the single risk that could turn a "ship" into a
hollow feature. It is honestly documented (impl debrief, phase summary item 1, both
addenda) with a pre-identified one-line fallback (a single target `get_object`, +1
call). It is environmental (needs live Anytype), not an implementation gap.

**Recommended action.** Bind this to the release runbook as a hard PRE-TAG product gate,
not just an engineering note: the live smoke (AC-8) MUST demonstrate a real
bidirectional `wiki_contradictions` write on two conflicting sources before the v0.6.0
tag is cut. If the search response is not hydrated, apply the get_object fallback and
re-verify. PR may open; tag may not cut until this passes.

## Rationale

**(a) Signal boundary — CONFIRMED at the code level.** `remember.py` (#289) writes only
`wiki_status` (`:655`, conflict) and `wiki_last_reviewed` (`:518`, clean consolidation)
— both on the *same* object; it never writes `wiki_contradictions`.
`ingest.py::_write_contradiction_links` (#287) writes only `wiki_contradictions`
bidirectionally (`:486`, `:501`) and explicitly never touches `wiki_last_reviewed`
(`:469`). The two surfaces populate distinct properties exactly as Jan specified. The
one interaction (ADV-1) is an ordering edge case, not a conflation, and is out of #287's
scope.

**(b) Over-trust disclosure (CPO-A-1) — LANDED and LEGIBLE.** I read the README/CHANGELOG
diff directly rather than trusting the summary. The README contradiction/lint section
header changed from "passive until v0.6.0" to "active in v0.6.0 — but scoped" and states
both limitations in plain operator language: "v0.6.0 detects contradictions between
linked entities only; contradictions between unlinked entities are not yet caught" and
"Entity-only; `wiki_concept` scope deferred," with the explicit operator warning "do not
over-trust a clean contradiction column." The widened-egress disclosure (peer
`wiki_facts`) landed in both the privacy notice and the ingest section, and the CHANGELOG
carries a dedicated "read before trusting a clean result" bullet. Critically, this is
not best-effort: `tests/wiki/test_docs_disclosure.py::TestReadmeDetectionScopeDisclosure`
gates both the "linked entities" and "entity-only" phrases in CI, so the disclosure
cannot silently regress. This is the gated deliverable I co-flagged at spec council, and
it is the strongest part of the delivery — the release correctly refuses to recreate the
over-trust problem it set out to fix.

**(c) Scope discipline — HELD.** DI-1 (concept) and DI-3 (semantic pre-filter) remain
deferred and are disclosed to operators rather than silently dropped. No schema bump
(`WIKI_SCHEMA_VERSION` stays 0.4.1), no new config vars, no new consent gate (existing
gate correctly reused for the widened data class). The only adjacent work folded in (E2
partial-resume, LD5 reader consolidation) is mechanical plumbing the spec scoped
explicitly, not gold-plating. Resource impact is proportional: 1 batch Ollama call plus a
handful of peer reads per entity update — cost matches the value. No cannibalization of
#289; the two features are complementary surfaces on a coherent contradiction-handling
story. Local-first principle preserved (detection runs on local Ollama by default; the
remote path is the existing opt-in, now honestly re-disclosed).

The product is ready. My sign-off is conditioned only on ADV-2 being enforced as a
pre-tag runbook gate — that is a release-management obligation, not a reason to hold the
PR.
