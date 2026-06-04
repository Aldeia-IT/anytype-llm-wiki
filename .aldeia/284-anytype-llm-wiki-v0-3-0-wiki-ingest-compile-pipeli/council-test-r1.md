# Council Meeting — Post-Test (Round 1)

**Date:** 2026-06-03
**Ticket:** #284 — anytype-llm-wiki v0.3.0 — `wiki_ingest` compile pipeline
**Phase reviewed:** test (suite APPROVED in-phase: test-review-r1 NEEDS CHANGES → fix → test-review-r2 APPROVED, 0 BLOCKING; 81 failing / 279 passing / 22 skipped / 3 xfailed, 0 regressions)
**Client:** anytype-llm-wiki (open-source MIT; **v0.3.0 is the first public PyPI release**)

## Attendance

| Role | Present | Reason |
|------|---------|--------|
| Council Chair | Yes | moderator |
| QA Director | Yes | minimum; test-phase quality gate owner (QA-ADV-1/2/3 carry-forwards) |
| Chief Technology Officer | Yes | technical accuracy of test seams; reviewer diligence; CTO-R2-A1/A2 carry-forwards |
| Chief Security Officer | Yes | heavy security-AC surface (SSRF, DNS-rebind, prompt-injection, consent, scrub); CSO-ADV-1 |
| Chief Product Officer | Yes | core v0.3.0 retrievability promise must be tested (the v0.2.0 failure mode); CPO-ADV-R2-1 |
| Client Advocate | Yes | client project + first public release; local-first honesty, README callout (CA-ADV) |
| Legal Counsel | No | NOTICE/dependency gate is publish-time (addendum item 8), not test-phase; carried to post-impl/PR gate |
| Infrastructure Lead | No | Qdrant-backup / ops-watch gates are pre-publish (addendum item 9), not test-phase; carried to post-impl/PR gate |

Focused six-seat council: the test phase is pre-impl and changes no deployed surface, so the publish-time Legal/Infra gates (already captured as authoritative addendum items 8–9 from the spec council) are deferred to the post-impl/PR final gate rather than re-litigated here.

## Context Presented

The test phase wrote a comprehensive failing-test suite for the v0.3.0 `wiki_ingest` compile pipeline, traceable to every spec §8 acceptance criterion and §9 Test Plan row. v0.3.0 exists to close the v0.2.0 defect where curated wiki facts live in **properties** of empty-body objects → the markdown-body indexer produced **0 chunks** → objects were invisible to `semantic_search`. The prior spec council (post-spec R2, unanimous) made the retrievability proof a release-blocking tested invariant (gate V3 MUST + AC-P2 live retrieval + AC-P9 CI seam test) and the local-first promise an honest tested invariant (AC-S2.1 local-by-default + AC-S2.2 consent banner). Those contracts, plus the post-spec-r2 addendum's execution constraints, were the bar this test phase had to meet.

The in-phase review loop did real work: it caught a silent false-coverage defect (AC#5 concurrent-lock tests used unpicklable nested closures that would error under macOS `spawn` before exercising anything), two tautological `isinstance(result, dict)` assertions (AC#3 partial-failure, AC#13 relation rollback), and one forbidden substring scan (AC-P7). All were genuinely fixed and re-verified in R2.

## Discussion

Each member independently re-ran the suite and verified the disposition of their own carry-forward items against the real test files and source tree. Multiple members converged on the same two structural observations, which were debated and consolidated:

**The "passes-against-helper/primitive, but no test gates the live wiring" pattern (raised by CSO, CPO, CA, QA, CTO).** Two distinct instances:
- **Consent banner (CSO-ADV-1):** `test_remote_endpoint_consent_banner_fires` exercises the isolated `check_remote_endpoint_consent` helper; `test_local_default_no_offmachine_call` correctly drives the real `extract()` entry and forbids any non-local call when the endpoint is unset. But no test fails if impl writes the banner helper and forgets to call it on the live `wiki_ingest` path ahead of the first off-machine transmit. For a tool whose headline promise is "local-first / no cloud," this is the single most important user-trust guarantee. The council judged this NOT a test-phase blocker (the test phase cannot prove wiring; the spec body + addendum item 6 explicitly hand it to impl) but elevated it to a **hard impl-phase gate**.
- **Lock acquisition (AC#5):** the concurrent-lock tests exercise the already-implemented `space_ingest_lock` primitive directly via `multiprocessing.Process` (satisfying spec §9.6, which mandates exercising the kernel flock, not wrapping `wiki_ingest`). No test fails if impl forgets to acquire the lock on the `wiki_ingest` entry path. The CTO noted the R2 reviewer's claim that "AC#1/AC#2 integration tests would surface the gap" is weak — those use respx HTTP mocks and would not detect a missing `space_ingest_lock` call. Consolidated as an impl-phase wiring obligation; the phase summary already flags it.

No member dissented on the verdict. The disagreement surface was only on *severity framing* (whether the two wiring gaps are test-phase blockers), resolved unanimously to ADVISORY-with-hard-impl-gate because the spec/addendum already pin them as impl obligations and the test phase structurally cannot close them.

The CTO independently traced the AC-P9 seam test (`tests/test_indexer.py:121-239`) against real `indexer.py` symbols and confirmed it monkeypatches the genuine I/O boundaries (`_qdrant`, `list_spaces`, `list_objects`, `get_object`, `embed`), does NOT stub `chunk_object`, and asserts on the captured upsert `payload["heading"]=="Facts"` + text — the precise CI backstop the v0.2.0 regression lacked. The CPO concurred this, plus the CI-runnable empty-body-invariant guards, structurally closes the "green CI but invisible objects" path independent of the live gates. All members confirmed the 81 failures are `ModuleNotFoundError`/`ImportError`/genuine-assertion-against-unimplemented — no malformed test code.

## Findings

### BLOCKING
None.

### ADVISORY

1. **[CSO-ADV-1 / CPO-ADV-1 / CA-1] Consent-banner live-path wiring is not test-enforced.** No test fails if impl places the consent check in a helper the production `wiki_ingest` path bypasses → silent off-machine transmission of source content before consent. **Elevated to hard impl-phase gate.** Impl MUST add an integration test driving the real `wiki_ingest` entry with a non-local `WIKI_EXTRACT_ENDPOINT` + no ack file, asserting the banner/ack check fires BEFORE the first off-machine transmit. (Source: CSO, CPO, Client Advocate.)

2. **[CTO-ADV-1 / QA-ADV-3 / CSO-ADV-3 / CPO-ADV-2] AC#5 lock acquisition not gated at the `wiki_ingest` integration boundary.** Primitive-level coverage is complete (kernel flock via `multiprocessing.Process`, satisfying §9.6); the `wiki_ingest`→`space_ingest_lock` wiring is untested. Impl MUST wire the lock on the entry path and add a CI-runnable assertion that `wiki_ingest` raises `[DATA ERROR] ingest_in_progress` when the space lock is held. (Source: QA, CTO, CSO, CPO.)

3. **[QA-ADV-1] Vacuous-loop risk in two spy-guard tests.** `test_update_path_no_body_key` (AC-L1, `tests/wiki/test_ingest.py:721`) and `test_create_wiki_object_empty_body` (AC-P7 create-side, `:763`) iterate captured payloads with no prior non-empty assertion → would pass vacuously if impl never reaches the path. Impl (or a fast test touch-up) MUST add `assert <payloads>` (and a type-key membership check) before the loop so the AC-L1 body-PATCH-deprecation and empty-body invariant guards cannot pass without firing. (Source: QA.)

4. **[CSO-ADV-2] SSRF bypass-encoding coverage gap.** Required cases (302-redirect-to-loopback, port 31012, RFC1918, DNS-rebind tripwire) are covered substantively, but alternate loopback/private encodings are untested: IPv6 `[::1]`, `0.0.0.0`, decimal/hex/octal IP forms, link-local metadata `169.254.169.254`. Impl SHOULD validate the **resolved `ipaddress` object** (reject non-global categorically) rather than string-matching the host, and add fetch tests for `[::1]`, `0.0.0.0`, and one numeric-encoded loopback. (Source: CSO.)

5. **[CTO-ADV-2] AC#16/SF2 sanitizer placement over-constrains impl.** `test_property_value_sanitized` asserts on `chunk_object` output, pinning sanitization to the chunker, while spec §4.1 SF2's canonical home is "on write." Defensible (chunker is the embedding chokepoint) but impl must either sanitize in the chunker to satisfy the test OR relax the test to assert on the written value — decide explicitly, don't let it surface as a surprise red. (Source: CTO.)

6. **[CTO-ADV-3] `force_reembed_object` is a test-invented signature.** `tests/test_indexer.py:262` imports `force_reembed_object(space_id, object_id, obj)` from `wiki.ingest` — not named in spec §7.2. Acceptable test-driven contract for the V2-fail object-scoped re-embed, but impl is bound to that name/signature or must update the test. Traceability flag. (Source: CTO.)

7. **[QA-ADV-2] AC#14 (schema-newer→warn+continue) has no behavioral assertion.** Covered indirectly via `_max_version`/read-order tests; the warn-and-continue branch is never directly exercised. Optional: impl may add a one-line test seeding a synthetic `"9.9.9"` marker asserting warn-level log + continued execution. Acceptable to ship without per spec rationale. (Source: QA.)

8. **[QA-ADV-4] Disjunctive `or "[CONFIG ERROR]" in result` assertions weaken specificity** in several error-path tests (e.g. `test_malformed_patch_decision`, `test_invalid_domain_hint`, AC#9's `or "ok" in result_str`). Low severity; the strongest cases also assert the specific code. Impl may tighten once exact codes are pinned. (Source: QA, Client Advocate.)

9. **[Process — pre-tag, not test-phase] Non-skippable live gates AC-P2/AC-P7/V3 remain unverified.** These `@pytest.mark.live` end-to-end retrieval proofs (the only full proof the v0.2.0 indexer gap is closed) skip in CI and MUST be run green against live Anytype+Qdrant+Ollama before the PyPI tag (spec §10.1). The publish runbook must not allow a `-m "not live"` shortcut at tag. (Source: QA, CPO, Client Advocate.)

10. **[Process — pre-publish, carried from spec council] README data-flow callout prominence (CA-ADV), NOTICE/dependency gate (Legal-ADV, addendum 8), Qdrant backup rotation (Infra-ADV, addendum 9), and the AC#18 + V4 release-blocking recorded decisions** all remain pre-publish gates. Captured in addendum items 7–9 and spec §10.1/§12; re-seat Legal + Infra at the post-impl/PR final gate. (Source: Client Advocate, CPO; carried from post-spec-r2.)

## Resolutions

No findings were withdrawn. The only debated point — whether the two "live-wiring" gaps (consent banner, lock acquisition) are test-phase blockers — was resolved unanimously to ADVISORY-with-hard-impl-gate: the spec body and the post-spec-r2 addendum already pin both as impl obligations, the test phase structurally cannot prove live wiring, and the CI backstops (AC-P9 seam test, empty-body-invariant guards, default-case egress guard) plus pinned non-skippable pre-tag live gates provide defense-in-depth. Every member verified their own carry-forward items as honored; the sign-offs cover distinct surfaces (test adequacy/traceability, technical accuracy/reviewer diligence, security posture, product promise, community/client trust) with no gap and no contradiction.

## Recommendation

**Recommended target:** impl
**Confidence:** high
**Rationale:** Unanimous sign-off, zero BLOCKING findings. The test suite is comprehensive, mechanically traceable to every §8 AC and §9 row, substantively asserted (the R1→R2 loop removed a silent-false-coverage defect and two tautological assertions), and correctly failing for the right reasons with zero regressions. The core v0.3.0 retrievability promise is protected in CI by a real seam test that drives the genuine `chunk_object→embed→upsert` path plus empty-body-invariant guards, and end-to-end by pinned named-entity live gates. The local-first promise is pinned by a real default-case egress guard. The advisories are precise impl-phase acceptance criteria (consolidated into `spec-addendum-post-test-r1.md`) and pre-publish gates — none gates advancement out of test.

**Dissent:** None.

*Note (training wheels):* `config/council.yaml` `autonomous: []` — this recommendation routes to Decide for Jan's ruling regardless of target. The watcher enforces autonomy policy; the council records its honest recommendation (impl).
