# Council Meeting — Post-impl (Round 1)

**Date:** 2026-06-06
**Ticket:** #287 — anytype-llm-wiki v0.6.0: Automated Cross-Object Contradiction Detection
**Phase reviewed:** impl (final delivery gate)
**Client:** anytype-llm-wiki

## Attendance

| Role | Present | Reason |
|------|---------|--------|
| Council Chair | Yes | moderator / synthesis |
| Chief Security Officer | Yes | minimum; widened off-machine egress + new LLM prompt-injection surface |
| Legal Counsel | Yes | minimum; widened peer-fact data egress, disclosure obligation |
| Chief Product Officer | Yes | minimum; over-trust failure-mode is the product's reason to exist; #289/#287 boundary |
| QA Director | Yes | minimum; AC coverage, non-vacuous negative assertions, live-test deferral |
| Chief Technology Officer | Yes | minimum; owns the no-target-GET platform-assumption finding (CTO-ADV-1) |
| Infrastructure Lead | Yes | post-impl full-attendance; per-update LLM+IO cost, release/deployment risk |
| Client Advocate | Yes | client project (non-aldeia-box); privacy-first positioning, operator trust |

Post-impl is the last gate before release, so the chair convened the full council.

## Context Presented

v0.6.0 adds automated **cross-object** contradiction detection to the wiki ingest pipeline:
at entity-update time, `detect_contradictions()` compares new facts against already-linked peer
entities (via `wiki_relations`) using a dedicated LLM prompt, and `_write_contradiction_links()`
writes `wiki_contradictions` **bidirectionally** with `wiki_last_reviewed` left null (so the
re-activated `contradiction_unresolved` lint check flags it for review). The hook is entity-only,
update-branch-only, and MUST-NOT-block-ingest (LLM/IO failure → `contradiction_detection_degraded`
warning, ingest still succeeds). Schema unchanged at 0.4.1.

Per Jan's pre-queue guidance, this is a **distinct surface from #289**: #289 `wiki_remember` does
intra-entity (same-subject) conflict flagging via `wiki_status`; #287 does cross-object detection via
`wiki_contradictions`. The two signals are kept separate.

The impl was APPROVED in-phase (1 round, zero BLOCKING) across three independent reviews
(security/code-quality/completeness). Full non-live suite: **572 passed, 25 skipped, 8 deselected,
2 xfailed** — all 15 previously-red target tests green, zero regressions. Both binding spec addenda
(post-spec items 1–5, post-test items 1–5) were honored.

## Discussion

The council's scrutiny converged on three themes, each independently verified against the code (not
the phase summary):

1. **The no-target-GET platform assumption (CTO-ADV-1).** CTO confirmed in code that `_relation_ids`
   reads `prop.get("objects")` off a raw `client.search` result (util.py:152, fed from ingest.py:192),
   with no fallback — if a real Anytype search response does not hydrate objects-format arrays, the
   candidate set is always empty and detection silently never fires ("green-in-CI, dead-in-prod"). CTO,
   QA, Infra, CPO, and Client all independently landed on the same disposition: this **cannot** be
   resolved headless (it needs a live Anytype response), is honestly disclosed in four places, and has
   a cheap pre-identified fallback (one target `get_object`, +1 call, plus a §4 correction). The
   unanimous position: **defer to a release-blocking pre-tag runbook gate, do not block the PR.**

2. **Widened off-machine egress + disclosure.** CSO confirmed the existing `check_remote_endpoint_consent`
   gate fires before any contradiction-path transmit (ingest.py:602, same space_id — no cross-space
   leak) and that the SG-2 hallucinated-ID filter bounds the prompt-injection blast radius to the
   pipeline-supplied candidate set. Legal read the `81b54d3..HEAD` diff directly and confirmed the
   widened peer-fact disclosure landed at consistent wording across all four required surfaces (README
   privacy bullet, README §5 security note, CHANGELOG v0.6.0, byte-matched verbatim fixture) with the
   consent banner updated in lockstep — Legal-ADV-1 satisfied. Operator-as-controller model unchanged;
   transparency obligation met, no new gate required.

3. **#289/#287 signal boundary + over-trust.** CPO and CTO both verified at code level that
   `remember.py` writes only `wiki_status`/`wiki_last_reviewed` (never `wiki_contradictions`) and
   `ingest.py` writes only `wiki_contradictions` bidirectionally and never touches `wiki_last_reviewed`
   — no conflation. The scope-limitation disclosure (linked-entities-only, entity-only) landed legibly
   in the operator-facing README section and is CI-gated by `test_docs_disclosure.py::TestReadmeDetectionScopeDisclosure`,
   directly addressing the over-trust failure mode this release exists to fix. QA fault-injection-proved
   AC-5 non-vacuity and confirmed both disclosure regression gates exist and pass.

## Findings

### BLOCKING
None.

### ADVISORY
1. **[CTO / QA / Infra / CPO / Client — convergent] Pre-tag platform-assumption gate.** The
   no-target-GET design must be verified against a real Anytype POST `/search` response before the
   v0.6.0 tag. If arrays are not hydrated, add the pre-identified single `get_object` fallback and
   correct §4. **Release-blocking pre-tag, not PR-blocking.** Owner: release/infra.
2. **[QA / Infra / Client] AC-8/AC-9 live smoke + SLO** are skip-gated and unexecuted headless; run
   them in the same pre-tag runbook (AC-9 is informational-only by spec). Capture AC-9 wall-clock SLO
   at tag.
3. **[CTO] `pyproject.toml` still at 0.5.0** while CHANGELOG declares 0.6.0 — consistent with the
   project's prior `chore(release)` cadence; bump as a release-runbook step.
4. **[CPO / QA] #289↔#287 lint-semantics interaction:** a #289 clean-consolidation `wiki_last_reviewed`
   timestamp can mask a later #287 contradiction finding (lint predicate `contradictions and not
   last_reviewed`, lint.py:410). Pre-existing schema-semantics gap, **out of #287 scope** — track for
   v0.6.x.
5. **[CSO]** Pre-v0.6.0 remote users who already acked are not re-prompted for the new peer-fact data
   class — deliberate, Legal-confirmed (operator-as-controller); banner-copy-only is within the
   sanctioned option set.
6. **[QA] AC-12 vacuous first clause:** the self-filter (ingest.py:411) empties the candidate set so
   the `get_object`-not-called clause is trivially true; the result-side assertion is the real guard and
   is adequate. Optional future hardening only.

## Resolutions

- Legal-ADV-1 (widened-egress disclosure) and Client-ADV-1 (operator trust / honest disclosure):
  **resolved** — verified landed across all four surfaces with CI regression gates.
- CSO prompt-injection concern: **resolved to advisory** — defense-in-depth preamble + SG-2
  hallucinated-ID filter; residual bounded to advisory false signals between already-linked in-space
  entities (no auto-merge, facts never overwritten).
- The platform-assumption finding was deliberately **not** escalated to BLOCKING: blocking cannot
  resolve an assumption that by definition requires a live environment to verify, and would forfeit a
  complete, green, CI-verified baseline. The correct control is a release-blocking pre-tag gate.

## Recommendation

**Recommended target:** done (open PR via watcher; merge strategy "Rebase and merge")
**Confidence:** high
**Rationale:** Unanimous sign-off, zero BLOCKING from all seven seats. The CI-runnable scope is
complete, traceable, regression-clean, and the two deferred items are environmental (need live
Anytype/Ollama), honestly documented, and carry pre-identified fallbacks — not implementation gaps.
The PR body and release runbook MUST carry Advisories 1–3 as **release-blocking pre-tag checklist
items** so green-in-CI is never mistaken for green-in-prod.
**Dissent:** None.
