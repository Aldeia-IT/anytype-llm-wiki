# Council Meeting — Post-test (Round 1)

**Date:** 2026-06-04
**Ticket:** #289 — anytype-llm-wiki — wiki_remember: LLM-assisted agent memory write (extract → resolve → consolidate)
**Phase reviewed:** test
**Client:** anytype-llm-wiki

## Attendance

| Role | Present | Reason |
|------|---------|--------|
| Council Chair | Yes | moderator |
| QA Director | Yes | minimum — test coverage / AC traceability / regression risk |
| Chief Technology Officer | Yes | mock fidelity, reviewer diligence, refactor regression guard |
| Chief Security Officer | Yes | sanitize-on-write, hard-gate ordering, consent (security-critical tests) |
| Chief Product Officer | Yes | product-trust audit criteria (supersede/conflict/idempotency) |
| Legal Counsel | Yes | data-handling change (LLM-extracted content incl. possible PII), consent model |
| Client Advocate | Yes | self-hosted product — operators are the client; CA-originated audit/provenance items |
| Infrastructure Lead | No | item 9 (operational docs) is deferred to impl/docs phase; nothing test-gate-load-bearing to evaluate. Will attend impl/post-impl council. |

## Context Presented

The test phase authored the full failing-test suite (TDD) for `wiki_remember` — the first Anytype write path driven repeatedly by autonomous agents. 89 new tests across four files (`test_remember.py` new, `test_extraction.py`, `test_bootstrap.py`, `test_ingest.py`), committed `991af3e` + R1 fixes `2357b4a`. The suite traces 1:1 to spec §9/§10 and to the 8 post-spec council addendum items. In-phase test review ran R1 (NEEDS CHANGES — doctor-whitelist BLOCKING, ambiguous-mock SHOULD-FIX) → R2 (APPROVED).

**Chair independent verification (ran the suite):** `74 failed / 294 passed / 1 skipped / 3 deselected / 2 xfailed` on `-m 'not live'` — matches the lead's claim exactly. All 74 current failures are impl-absence (ModuleNotFoundError/ImportError/AttributeError). The 4 regression guards + 2 #284 forward-note tests PASS pre-impl (6 passed). Lead's phase-summary claims hold.

## Discussion

Five members (QA, CSO, CPO, Legal, Client Advocate) independently signed off: the AC↔test traceability is 1:1, the highest-stakes properties (byte-for-byte sanitize-on-write, the four hard gates driving the real entry point with `assert_not_called()` spies, twice-driven idempotency convergence, conflict-independence from the PATCH-skip gate, ambiguity-no-write with co-resident unambiguous-write proven, supersede/conflict durable audit notes) are all substantive and falsifiable rather than tautological. The B-R1 fix (before/after doctor FAIL-set diff) was judged the correct robustness call.

The **CTO dissented with a BLOCKING finding** none of the other lenses — nor the two in-phase test reviews — surfaced, because catching it required standing up a spec-faithful stub rather than reading the tests. The CTO stood up that stub and empirically proved the entity-resolution `search` route mock does not match the shipped client's wire contract. **The chair independently reproduced the CTO's evidence at the source level** (see Findings B-1). This is exactly the wire-level executability gap a governance review exists to catch; it overrides the otherwise-clean sign-offs.

## Findings

### BLOCKING

**B-1 [CTO, chair-verified] — Entity-resolution `search` route is mocked as GET; the shipped client POSTs. The test contract is not satisfiable by a correct implementation.**
- Shipped `WikiClient.search` issues `c.post("/v1/spaces/{space_id}/search", json=payload)` (`src/anytype_llm_wiki/wiki/wiki_client.py:113`). Verified.
- `tests/wiki/test_remember.py` registers the search route as **`router.get(".../search")` in 49 places; 0 POST registrations.** Verified.
- The established #284 convention (`tests/wiki/test_ingest.py:848`) correctly mocks search via `respx.post()`. Verified.
- Consequence: a spec-faithful `resolve_entity` calling `client.search()` (POST) will not match the GET-registered respx route → respx raises `AllMockedAssertionError` (a bare `AssertionError`). `resolve_entity` catches `httpx.HTTPError`, **not** `AssertionError`, so a *correct* impl crashes rather than resolving. The CTO confirmed this empirically with a stub.
- Why it is currently masked: with the `remember` module absent, imports fail before any HTTP call is made, so the mismatch cannot manifest yet. The "74 failures = all impl-absence" TDD state is therefore genuine **but incomplete as a correctness signal** — the suite will break the moment a correct impl lands, and risks misleading the impl-worker into "fixing" the tests by changing the shipped client GET-ward (which would break the #284 ingest contract).
- **Required fix (mechanical):** change every entity-resolution `search` route registration on `/v1/spaces/.../search` in `test_remember.py` from `.get(...)` to `.post(...)`, mirroring the `test_ingest.py` `respx.post()` convention. Re-verify with a minimal spec-faithful `resolve_entity` stub that the search-dependent tests fail ONLY on impl-absence and not on `AllMockedAssertionError`. The test-review must stand up such a stub this time (R1/R2 did real codebase verification but neither executed the contract, which is how the mismatch passed).

### ADVISORY (carry into impl; re-confirm at the next council round once B-1 is fixed)

1. **[QA-1] Audit-note property landing.** `test_supersede_recorded_in_wikilog_notes` and `test_conflict_path_surfaces_sources_overwrite` assert the recorded text via a `str(properties)` substring rather than the specific `wiki_notes` property. Impl must land those notes in `wiki_notes`; tighten or confirm at impl review.
2. **[QA-2 / nuance] Failure-class nuance.** ~6 of the 74 failures are `AssertionError` from bootstrap tag-seeding (because `wiki_bootstrap` pre-exists from #284), not pure ImportError — still correct test-first behavior-absence, not a test bug. Noted so it is not confused with B-1's `AllMockedAssertionError`.
3. **[CSO-1 / CPO-1 — live gate] AC-R7 / AC-R24 (retrievable-after-reindex, real off-machine transmit) have NO CI equivalent** — they live only in `test_live_wiki_remember_end_to_end` (`@pytest.mark.live`). The impl-worker MUST run the live smoke gate manually before PR; "294 passed" does not prove the user can retrieve what the agent remembered, nor that the consent banner fires on a real non-local transmit.
4. **[CSO-2] Consent-gate proxy.** `test_consent_banner_fires_on_live_path` proxies "non-local transmit" via the mocked `extract` spy and does not assert the ack file is written (AC-R-S1 item 2); the notify-once self-ack (G2) is the weakest control in the chain. Strengthen at impl + cover by the live gate.
5. **[Legal-1 / CA-1 — docs handoff] Addendum item 9 (operator-facing docs) is correctly DEFERRED to impl/docs but is NOT echoed in `phase-summary-test.md`'s handoff list.** For a self-hosted product the operator is the client. The five disclosures — per-space re-bootstrap runbook; auto-reindex cost model + `WIKI_AUTO_REINDEX=false` mitigation; monotonic WikiLog growth/pruning; `ingest_in_progress` fail-fast back-pressure; "knowledge stored as-is, only URL creds scrubbed" + notify-once non-blocking consent banner — and the Anytype-backup object-type-agnostic confirmation MUST be carried explicitly into the impl/docs brief or they risk being lost. The chair carries item 9 forward in this summary and the handoff comment.
6. **[Legal-2] Accepted residual is documented, not hidden:** `knowledge` stored as-is (arbitrary secrets not scrubbed beyond URL credentials) under the single-operator / sole-data-controller model of this MIT self-hosted tool. No copyleft contamination; test fixtures are synthetic (no real secrets/third-party content).
7. **[N-R1 — impl handoff, from the phase] When impl adds `"remember"` to `_WIKI_ACTION_TAGS` (5→6), the #284 tests `test_bootstrap_action_tags_idempotent` and `test_bootstrap_creates_all_five_action_tags` must have their counts updated 5→6. They MUST stay green pre-impl and must not be touched during the B-1 rework.**

## Resolutions

The five sign-offs are not withdrawn — their domains (coverage, security properties, product-trust guarantees, legal posture, client interests) are genuinely well-served by the suite. They are, however, **gated** behind B-1: until the search route is wire-faithful, none of those proven properties are actually executable against a correct impl. The council's collective position is therefore REWORK, not advance, driven solely by B-1. All advisory items survive into the next round / impl.

## Recommendation

**Recommended target:** `test` (rework)
**Confidence:** high
**Rationale:** A single, precise, chair-verified BLOCKING defect makes the test contract unsatisfiable by a correct implementation. The fix is mechanical and well-understood (GET→POST on the `search` route mocks in `test_remember.py`, mirroring the existing `test_ingest.py` convention) and does not require human adjudication, so rework-to-test is preferred over escalation. On return, the test-review must execute the contract against a spec-faithful `resolve_entity` stub (not only read it), then this council reconvenes (R2) to confirm B-1 closed and to fold the advisory items into a post-test spec addendum for the impl phase.
**Dissent:** None on the verdict. The CTO's BLOCKING is the controlling finding; the other five members' sign-offs are conditional on it and do not contradict the rework recommendation.
