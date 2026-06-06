# Council Meeting — Post-test (Round 1)

**Date:** 2026-06-06
**Ticket:** Aldeia-IT/aldeia-box#287 — anytype-llm-wiki v0.6.0 Automated Cross-Object Contradiction Detection
**Phase reviewed:** test
**Client:** anytype-llm-wiki (open-source, MIT, local-first; infrastructure + agent-operations)

## Attendance

| Role | Present | Reason |
|------|---------|--------|
| Council Chair | Yes | moderator |
| QA Director | Yes | minimum; quality gates, AC↔test adequacy, regression risk |
| Chief Technology Officer | Yes | reviewer diligence + the CTO-ADV-1 platform-assumption gate elevated at spec council; wire-contract fidelity is locked at the test phase |
| Chief Security Officer | Yes | security-relevant ACs realized this phase (AC-10 anti-injection, AC-11 hallucinated-id blast-radius filter, AC-12 self-reference); widened peer-fact egress disclosure |
| Chief Product Officer | Yes | over-trust failure mode is product-central; the disclosure-presence test (item 5a) realizes CPO-A-1 |
| Client Advocate | Yes | non-aldeia-box OSS; Jan's pre-queue direction fidelity (#289↔#287 boundary, addendum honoring, wire contracts) |
| Legal Counsel | No | chair decision — Legal's spec-phase concern (off-machine egress) was resolved as a transparency obligation satisfied by README disclosure; the disclosure copy is an impl-phase docs deliverable, covered here via CSO/Client/CPO. No new legal surface at the test phase. |
| Infrastructure Lead | No | chair decision — Infra's spec-phase findings (fan-out cap, degraded-warning monitoring) are noted-not-gated ops follow-ups, post-merge. No operational-readiness surface at a test-first, pre-impl gate. |

## Context Presented

The test phase produced 15 new/modified failing tests encoding all 14 spec §7 acceptance criteria plus the post-spec council addendum item 5 (the test-phase deliverable). The internal test-reviewer returned **APPROVED** (zero BLOCKING/SHOULD-FIX, two SUGGESTIONs, both addressed: dead-code removal committed in `ed7db7a`; AC-8 OR-assertion deliberately retained as a live-LLM flakiness guard). Lead-verified non-live suite: **15 failed, 557 passed, 25 skipped, 8 deselected, 2 xfailed** — the 15 failures are exactly the new v0.6.0 tests, failing test-first for genuine missing-symbol / wrong-value reasons (`detect_contradictions`, `_call_ollama_prompt`, `_CONTRADICTION_PROMPT_PATH` absent; README disclosure copy absent), with no collection/import error masking the suite.

The council was asked to confirm, at the governance level, that: (a) every AC has a real gate that fails for the right reason; (b) the security controls (AC-10/11/12) are non-hollow; (c) the over-trust guard ships both halves — PASSIVE-removal AND replacement-disclosure presence; (d) CTO-ADV-1 (the "no target GET" platform assumption) is kept honestly OPEN as an impl gate rather than silently closed by a green fixture; and (e) Jan's pre-queue direction (cross-object `wiki_contradictions` bidirectional, distinct from #289's `wiki_status`; POST-search wire contract) is upheld.

## Discussion

Each seat read the test source directly (not just the reviewer summary); QA and CTO independently re-ran the suite and reproduced the 15/84/6 counts; CSO, CPO, and Client cross-checked the disclosure gates against the live README. Three themes converged across seats:

1. **CTO-ADV-1 — "no target GET" platform assumption (QA, CTO, CPO, Client).** The spec's §3.3/§3.4/§4 no-target-GET design assumes POST `/search` returns *hydrated* `properties[].objects` arrays for the objects-format relations. CTO verified against source that every existing objects-format reader operates on a `get_object` result, never a `search` result — no code path today reads `prop.get("objects")` off a search response. The council unanimously confirmed the test phase handled this **honestly**: the AC-1 fixture (`_make_objects_shaped_search_response`, test_ingest.py:1205-1238) carries the addendum-5b honesty comment verbatim (it proves the *parsing* contract only and explicitly says "Do NOT treat this fixture passing as evidence"), and no green test entrenches the assumption as validated. The gate remains OPEN as a mandatory impl-phase exit criterion (post-spec addendum item 1). This is the single highest residual risk in the ticket — green-in-CI, dead-in-prod if real search returns lean objects — but it cannot be CI-tested without a real backend, so deferring it to impl with the pre-identified one-`get_object` fallback is correct.

2. **Widened-egress disclosure is ungated and masked by an existing verbatim fixture (CSO, Client — NEW this round).** The strongest new finding. `tests/wiki/test_bootstrap.py:575` (`test_readme_contains_verbatim_privacy_notice`) pins the README privacy notice to `tests/wiki/fixtures/readme_privacy_notice_verbatim.md`, which currently discloses ONLY the v0.3.0 "source content you ingest" egress model. The post-spec addendum items 2/4 (disclose that enabling a remote `WIKI_EXTRACT_ENDPOINT` now egresses already-stored peer `wiki_facts` from earlier ingests; update the consent-banner copy) are impl-phase deliverables with **no CI gate** — and because the verbatim test asserts substring presence, impl can keep it green while leaving the incomplete v0.3.0 wording in place, silently dropping the peer-fact disclosure. The test-phase `phase-summary-test.md` "Risks and Open Items" omitted items 2 and 4. Unlike the *detection-scope* copy (item 3), which item 5a correctly gated via `test_docs_disclosure.py`, the *egress* copy has no regression protection. Four spec-council seats converged on this disclosure originally; the council records it as a named impl-phase exit criterion so it is not lost behind the green verbatim test.

3. **Security controls are genuinely gated, but two impl-coupling traps could turn a correct impl red (QA, CTO, CSO).** CSO confirmed AC-10 (anti-injection preamble) asserts BOTH the prompt-file preamble AND the OSError-fallback preamble; AC-11 (hallucinated-id filter, SG-2 — the blast-radius bound) exercises the REAL `detect_contradictions` filter feeding a ghost id, not a hollow mock; AC-12 (self-reference skip) asserts no self-GET and own-id absence. However, AC-11/AC-12 monkeypatch `anytype_llm_wiki.wiki.ingest._call_ollama_prompt`, and `ingest.py` does not currently import that helper into its namespace. If impl calls it qualified (`extraction._call_ollama_prompt`) rather than importing it module-locally (`from .extraction import _call_ollama_prompt`), the security test stays red against a functionally correct impl — risking pressure to weaken a security gate. This is a legitimate constraint on impl (consistent with spec §3.3), not a test bug, and must be a named impl obligation.

Reviewer-diligence verdict (CTO): the internal test-reviewer did real verification, not rubber-stamping — its per-test failure-mechanism table and its AC-11 tuple-return type claim both reproduce against source. One stale line reference (test-review-r1.md:130 cites a dead variable already removed in `ed7db7a`) is a doc-freshness nit, not a defect.

## Findings

### BLOCKING
None. (Unanimous across all five voting seats.)

### ADVISORY

1. **[CTO-ADV-1 / QA-A2 / CPO-ADV-1 / Client-A1 — carried forward, reaffirmed]** The "no target GET" platform assumption is NOT CI-covered and must not be treated as discharged by this phase. Impl MUST validate against a *real* Anytype POST `/search` response that `_relation_ids(target, "wiki_relations")` yields linked peer ids; if the arrays are absent, add a single target `get_object` fallback (+1 call) and correct §4's "NO target GET" claim. The AC-1 objects-shaped fixture proves parsing only; the 5b honesty comment is present and correct. → post-spec addendum item 1; reaffirmed as a hard impl-phase exit criterion.

2. **[CSO-ADV-1 / Client-A1 — NEW]** The widened peer-fact egress disclosure (post-spec addendum item 2) and consent-banner copy update (item 4) have no CI gate and are masked by `test_bootstrap.py:575` `test_readme_contains_verbatim_privacy_notice`, which pins the README privacy notice to a fixture describing only the v0.3.0 egress model. Impl MUST update both `README.md:46` and the verbatim fixture `tests/wiki/fixtures/readme_privacy_notice_verbatim.md` in lockstep to disclose the peer-fact egress class, and SHOULD add a presence assertion (mirroring `TestReadmeDetectionScopeDisclosure`) for the peer-fact / "previously-stored wiki content" copy so items 2/4 cannot regress silently. The test-phase risk handoff omitted items 2/4. → new impl-phase exit criterion (see spec addendum post-test).

3. **[QA-A3 / CTO-ADV-1]** Monkeypatch namespace coupling: AC-11/AC-12 patch `ingest._call_ollama_prompt`, which `ingest.py` does not yet import. Impl MUST `from .extraction import _call_ollama_prompt` (and surface `detect_contradictions`, `_CONTRADICTION_PROMPT_PATH`) into the `ingest` namespace and call module-locally, or the SG-2 security test stays red against a correct impl. Consistent with spec §3.3. → named impl-phase exit criterion.

4. **[QA-A4]** `_create_source` tuple-return (spec §3.6 BL-6): impl MUST unpack `(str, bool)` at BOTH call sites in `ingest.py` (do NOT store the raw tuple in `result["source_object_id"]`), or the pre-existing green `TestReingestIdempotency::test_reingest_same_source_creates_zero_and_reuses_source` breaks. No test change needed; an impl obligation. → impl-phase verification point.

5. **[QA-A5 / CPO-ADV-2]** AC-8 live smoke uses OR (contradictions written OR lint High finding) rather than AND. Accepted as a non-deterministic-LLM flakiness guard; the deterministic CI seam tests (AC-1/3/13/14) cover both halves. No action required; optionally tighten to AND at impl time if the live LLM proves reliable. Live-only observation, not a CI gate.

6. **[CTO-ADV-2 / CSO-ADV-2 / CPO-ADV-3 / Client-A2]** The item-5a disclosure tests assert document-wide substring presence, not section placement. Low risk given the discriminating tokens have zero current README hits, but the impl reviewer should confirm the disclosure copy lands in the operator-facing contradiction/lint section and reads legibly — not buried.

7. **[QA-A1]** Three negative/absence assertions (AC-2 not-called, AC-5 contrast warning-absent, AC-12 compound `not called or all(...)`) currently fail at the `monkeypatch.setattr` line *before* reaching their absence assertion, so the negatives have never executed and could be vacuously satisfiable post-impl. Impl-phase QA should confirm these pass for the right reason (a deliberate fault injection flips them red), with attention to AC-12's compound at test_ingest.py:1769.

8. **[CTO-ADV-3]** Stale line reference in `test-review-r1.md:130` (cites a dead `linked_entities_disclosed` variable already removed in `ed7db7a`). Doc-freshness nit; already actioned in code. No action.

## Resolutions

- All five voting seats independently reached "advance to impl" with zero BLOCKING. The verbatim-fixture egress-disclosure gap (Finding 2) was the only genuinely new finding; the council resolved it cross-functionally as an **impl-phase exit criterion** (not a test-phase rework) because the post-spec addendum had scoped only the detection-scope copy (item 3) to the test phase via item 5a — items 2/4 were always impl deliverables. The remedy is to gate them in impl and update the verbatim fixture in lockstep.
- CTO's reviewer-diligence audit cleared the test-review chain as genuine. The honest-fixture comment (5b) was confirmed present, resolving the spec-council concern that a green objects-shaped fixture might create false validation of the no-target-GET assumption.
- No seat pressed any advisory to BLOCKING. Legal and Infra were excused with recorded rationale; neither has a live surface at a test-first gate.

## Recommendation

**Recommended target:** impl
**Confidence:** high
**Rationale:** Unanimous sign-off, zero BLOCKING findings. The test phase meets all quality gates: complete AC↔test traceability (14 ACs + addendum item 5), independently reproduced test-first failures for the right reasons, spec-faithful wire contracts (search = POST, get_object = GET-with-`?`, no target GET / BL-3 asserted, no `respx.patterns.M`), non-hollow security gates (AC-10/11/12), and a genuinely-failing docs-disclosure gate for the detection-scope copy. CTO-ADV-1 is kept honestly OPEN. The next phase per the SDLC order is `impl`. The advisories impose concrete impl-phase exit criteria — captured authoritatively in `spec-addendum-post-test-r1.md`. None rises to a test-phase blocker.
**Dissent:** None.

> Note: the council recommends `impl` on the merits. The watcher enforces autonomy policy and will route to `decide` if the impl phase is not yet autonomous for this project; the council does not read or enforce that policy.
