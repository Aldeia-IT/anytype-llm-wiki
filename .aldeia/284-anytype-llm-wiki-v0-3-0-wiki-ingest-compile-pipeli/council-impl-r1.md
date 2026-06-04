# Council Meeting — Post-impl (Round 1)

**Date:** 2026-06-03
**Ticket:** #284 — anytype-llm-wiki v0.3.0 wiki_ingest compile pipeline
**Phase reviewed:** impl
**Client:** anytype-llm-wiki (open-source, dual-purpose: internal Aldeia KB + public PyPI release)

## Attendance

| Role | Present | Reason |
|------|---------|--------|
| Council Chair | Yes | moderator |
| Chief Technology Officer | Yes | minimum |
| Chief Security Officer | Yes | minimum (off-machine data flow + SSRF surface) |
| Legal Counsel | Yes | minimum (first public release; privacy disclosure) |
| Chief Product Officer | Yes | minimum |
| QA Director | Yes | minimum (green-suite-masks-broken-promise history) |
| Infrastructure Lead | Yes | chair decision — Qdrant backup + deployment pre-publish gates |
| Client Advocate | Yes | chair decision — client project + first public release reputation |

Full council seated: this is the final governance gate before PR for a first public open-source release with an off-machine data flow.

## Context Presented

v0.3.0 adds the "compile step" end-to-end: fetch a URL/file (SSRF-guarded) → LLM-extract entities/concepts (local Ollama by default; opt-in remote endpoint) → create typed wiki objects (Entity/Concept) in Anytype with property-based bidirectional relations → close the v0.2.0 indexer gap (empty-body objects yielded 0 chunks → invisible to `semantic_search`) via chunker property-embedding. 7,641 lines added; `pytest -m "not live"` → 366 passed / 20 skipped / 0 failed; bandit + pip-audit clean.

The lead impl review found two spec violations the green suite masked (BLOCKING-A: every candidate created as `wiki_entity`, never `wiki_concept`; BLOCKING-B: relations created against a non-existent `wiki_relation` type), fixed both in a fix round, and re-verified (impl-review-r2: APPROVED). The lead flagged three items for council adjudication: (1) ratify the rewrite of one approved test (`TestBidirectionalRelationRollback`) to the spec's property-based relation model; (2) adjudicate heading-derivation as primary candidate path vs the spec's "LLM-extraction-primary" prose; (3) confirm deferral of live gates (AC#1/AC-P2/AC-P7/V3) to the pre-PyPI-tag gate.

## Discussion

**Independent verification, not prose-trust.** CTO, CSO, QA, and Infra each ran the suite themselves and read the production code. QA performed five falsification experiments — temporarily breaking each wiring point (consent, lock, body-PATCH invariant, empty-body create) and confirming the corresponding test goes red, then reverting — proving the previously-vacuous guards now bite. CTO independently confirmed `wiki_relation` is absent from `WIKI_TYPES` and that the property-based bidirectional model is the master-spec-authoritative mechanism (technical-research.md:165).

**The privacy-disclosure error — cross-functional convergence.** Legal and Client Advocate independently landed on the same finding: README.md:46-47 (and its frozen Legal-gated verbatim fixture) tell users that configuring `WIKI_EXTRACT_MODEL` transmits source content to a hosted provider. Verified false in code: `WIKI_EXTRACT_MODEL` (config.py:32-34) only selects the model-name string; `WIKI_EXTRACT_ENDPOINT` (extraction.py:126) is the actual off-machine switch and the sole trigger for the consent banner and scrubbed endpoint log. CSO and CTO had flagged the same variable mismatch as advisory and explicitly deferred the disposition to Legal. Legal — the authority on disclosure accuracy — ruled it BLOCKING-in-branch: an inaccurate statement, in a published privacy notice on a local-first-branded tool, about *which knob causes personal data to leave the machine*. The `.env.example`, CHANGELOG, MIGRATIONS, and the newer local-first README callout all name the correct variable; the error is isolated to the single most reputation- and legally-load-bearing paragraph, and is frozen behind a Legal-sign-off gate (which is why impl logged it as a follow-up rather than fixing it in-branch).

**Live gates — unanimous deferral, unanimous insistence.** Every member affirmed that AC#1 (≥1 Entity AND ≥1 Concept, discoverable), AC-P2, AC-P7, and V3 are proven only in mocks and are the *only* end-to-end proof that the property-indexing gap is closed and the rewritten relation/concept-routing paths work against live Anytype. CTO, CPO, QA, Infra, and Client Advocate all stressed: the two most contract-sensitive paths (entity/concept routing, property-based relations) were rewritten *after* the spec/test phases and have never run live. The deferral to pre-tag is spec-authorized (§10.1; addendum item 9) and acceptable for *merge* — nothing is published at merge — but the tag MUST NOT permit a `-m "not live"` shortcut. Client Advocate framed this as the literal "don't repeat v0.2.0" line: v0.2.0 broke because it shipped on a guessed write contract.

**Heading-derivation.** CTO and CPO accepted it for this increment (forced by approved non-live tests that drive `wiki_ingest` without mocking Ollama yet expect deterministic candidates; LLM extraction still enriches on the live path). Both noted AC#1's "≥1 Concept" rests entirely on the live LLM `concepts[]` path (heading candidates are always `kind="entity"`), so the pre-tag live run must include a concept-producing AND a headingless source to actually exercise the full promise. Flagged as a v0.4.0 product item (LLM-extraction-primary derivation = the real differentiator).

## Findings

### BLOCKING

1. **[Legal-L1 / CA-B1] Privacy disclosure names the wrong environment variable for off-machine transmission.** README.md:46-47 and `tests/wiki/fixtures/readme_privacy_notice_verbatim.md:5-6` state `WIKI_EXTRACT_MODEL` causes source content to be transmitted to a hosted provider; the actual off-machine switch and consent-banner trigger is `WIKI_EXTRACT_ENDPOINT` (extraction.py:126, 214-233, 259-277; config.py:32-34). A user following the notice literally transmits nothing and sees no consent banner, while the real switch is never named in the privacy section — and the page contradicts itself (line 159 correct, line 46 wrong). This is an accuracy defect in a published privacy notice (GDPR Art. 13/14, LGPD Art. 6 transparency) that will merge into the default branch and is frozen into a test fixture. **Required fix (Legal has pre-blessed the wording):** (a) README.md:46-47 — replace `WIKI_EXTRACT_MODEL` with `WIKI_EXTRACT_ENDPOINT` as the off-machine switch; describe `WIKI_EXTRACT_MODEL` only as the model-name selector; (b) update `tests/wiki/fixtures/readme_privacy_notice_verbatim.md:5-6` in lockstep so the verbatim fixture test stays green; (c) confirm consistency with the already-correct README.md:159-164 and .env.example:7-10. Surgical, no architectural impact.

### ADVISORY

1. **[All members] Live gates AC#1 / AC-P2 / AC-P7 / V3 are tag-blocking, not merge-blocking.** Run green against live Anytype + Qdrant + Ollama before the `v0.3.0` PyPI tag; the runbook MUST treat a *skipped* live test as a failure (they `pytest.skip()` when `ANYTYPE_SPACE_ID` is unset). The live run must include a concept-producing source and a headingless source so AC#1's "≥1 Concept" half is actually exercised. Already recorded: spec §10.1, addendum item 9. (CTO BLOCKING-PRE-TAG-1; CPO ADVISORY-1; QA tag-time gate; Infra gate 2; CA A-1.)
2. **[Infra] Qdrant backup rotation + TESTED restore for the v0.3.0 data volume — NOT done, at risk of being silently dropped.** No backup script, snapshot config, or restore procedure exists in-repo. Reconstructable-from-Anytype lowers severity but does not waive the gate (no tested RTO). Remains a recorded pre-publish blocker (addendum item 10, Infra-ADV). Re-seat Infra at the tag gate.
3. **[Legal] NOTICE / dependency-licensing gate.** New runtime deps `markdownify` + `pydantic` (both MIT, compatible). Regenerate NOTICE from the resolved venv via `pip-licenses --from=mixed` + manual vendored-Rust check before tag. Properly recorded (spec §10.1, addendum item 10).
4. **[CSO] Consent is notify-and-proceed (spec-designed, accepted).** First off-machine ingest transmits before the user can act on the one-time warning. Defensible for a deliberately-set opt-in env var; README must state plainly that first-run transmission occurs (folds into the addendum item-10 README-prominence eyeball). ADV-2: `0.0.0.0` in `_LOCAL_HOSTS` is semantically odd (harmless). ADV-3: `_is_model_not_pulled` 404-breadth — robustness nit.
5. **[CTO/CPO/CA] Heading-derivation under-delivers for headingless sources** (single URL-named entity, zero concepts). Accepted for v0.3.0 (forced by approved tests); track LLM-extraction-primary derivation as a named v0.4.0 product item; ensure public README/CHANGELOG "LLM-driven extraction" language doesn't over-promise for headingless inputs.
6. **[CPO/QA] AC#18 partial-state-idempotency disposition** must be a recorded product decision in release notes before tag (§10.1/§12) — its duplicate-Source workaround visibly weakens AC#2 idempotence under partial failure.
7. **[QA] Stale `xfail` marker.** `test_wiki_ingest_returns_error_on_missing_patch_decision` (test_bootstrap.py) now xpasses because v0.3.0 is implemented; remove the obsolete marker so a future regression surfaces as a real fail. Non-blocking, address in the rework pass if convenient.

## Resolutions

- **AC#13 relation-model test correction — RATIFIED.** The standalone-`wiki_relation`-object model in the original approved test was factually wrong against both the codebase (`WIKI_TYPES` has no such type) and the master spec (bidirectional property writes). The rewrite is spec-faithful, the assertion is strengthened and non-vacuous (verified by CTO read + QA falsification: the rollback PATCH must carry the reverted `objects:[]` list), and it touches exactly one test, surfaced transparently. Council ratifies the test-contract correction.
- **Heading-derivation as primary candidate path — ACCEPTED for v0.3.0** as an advisory with a v0.4.0 follow-up (see Advisory 5).
- **Two previously-vacuous loop guards + both HARD-GATE integration tests (consent, lock) — CONFIRMED biting** by QA falsification. No action.
- **CSO/CTO variable-mismatch advisories — escalated to Legal**, who dispositioned them as the BLOCKING finding above. Consolidated; highest severity preserved.

## Recommendation

**Recommended target:** impl (narrow rework — resolve BLOCKING-L1 only)
**Confidence:** high
**Rationale:** Six of seven members sign off to advance to PR; the engineering, security, and test contracts are sound and independently verified. The single BLOCKING item is a surgical, Legal-pre-blessed two-location documentation/fixture correction — it does not reopen the implementation. Route to impl to apply the fix (README.md:46-47 + verbatim fixture in lockstep), re-run the verbatim-fixture test, then proceed to PR. The numerous tag-time gates (live AC#1/P2/P7/V3, NOTICE/pip-licenses, Qdrant backup-restore, AC#18 disposition, README-prominence eyeball) are NOT merge blockers — they are already recorded as release-blocking in spec §10.1 and spec-addendum-post-test-r1 (items 9-10); re-seat Legal + Infra at the post-PR/pre-tag gate to execute them.
**Dissent:** None. The single BLOCKING was reached by two members independently and concurred-with by two more; no member opposed advancing once it is fixed.
