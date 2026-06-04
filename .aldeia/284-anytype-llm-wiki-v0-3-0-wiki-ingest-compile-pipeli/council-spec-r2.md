# Council Meeting — Post-Spec (Round 2)

**Date:** 2026-06-03
**Ticket:** #284 — anytype-llm-wiki v0.3.0 — `wiki_ingest` compile pipeline
**Phase reviewed:** spec (status SPEC; R1 council REWORK addressed in commits `edde82d` spec +142/−45, `2fda2c4` context docs)
**Client:** anytype-llm-wiki (open-source MIT; **v0.3.0 is the first public PyPI release**)

## Attendance

| Role | Present | Reason |
|------|---------|--------|
| Council Chair | Yes | moderator |
| Chief Security Officer | Yes | minimum; verify BLOCKING-2 security half + CSO advisories resolved; regression check |
| Chief Product Officer | Yes | minimum; raised R1 BLOCKING-1 (retrievability proof) — verify resolution |
| Chief Technology Officer | Yes | minimum; technical-accuracy gate on NEW spec text (seam test feasibility) |
| QA Director | Yes | drove the R1 REWORK (QA-B1/B2); verify verification-strength inversion is genuinely fixed |
| Client Advocate | Yes | raised R1 BLOCKING-2 (local-first honesty); first public release / community stakeholder |
| Legal Counsel | Yes | held the Legal-Adv1 hard pre-publish gate (NOTICE dependency tree) |
| Infrastructure Lead | Yes | R1 operational advisories (V2-fail reconciliation, reindex concurrency, ops watch) addressed |

Near-full council re-seated: a Round-2 re-review whose job is to verify that the two R1 BLOCKING clusters and the hard-gate advisories were genuinely (not cosmetically) resolved before a first public PyPI release.

## Context Presented

R1 council recommended **REWORK** (2 BLOCKING clusters + 13 advisories) while judging the design sound and the spec ~90% done — the findings were surgical amendments to §8/§9/§10/§11, not a redesign. A fresh spec-fixer addressed every finding; the spec lead verified each against the diff. This Round-2 meeting evaluated whether the rework actually closed the two BLOCKING clusters:

- **BLOCKING-1 (CPO-B1 / QA-B1 / QA-B2 / CA-B1):** the core retrievability promise was verified only by deferred/optional gates — V3 was a SHOULD, AC-P2 (create-side end-to-end retrieval) had no §9 test row, and no CI backstop protected the live-only `chunk_object → indexer → embed → upsert → semantic_search` path. The v0.2.0-class "ship before the core promise is verified" risk, one phase later.
- **BLOCKING-2 (CA-B2 / Legal-Adv3 / CSO-A2):** a tool marketed "local-first / no cloud" could silently send source content (and the operator's own local-file notes) off-machine via `WIKI_EXTRACT_ENDPOINT`, contradicting `product.md` / `compliance.md`.

## Discussion

The council reviewed by surface, each member verifying the disposition of their own R1 findings against the reworked spec text and (for CTO) the real source tree. The verdict was unanimous sign-off with no member dissenting and no contradiction between members.

**BLOCKING-1 — closed (CPO, QA, CTO concur).** The verification-strength inversion is genuinely corrected with defense-in-depth, not relabeling:
- **AC-P2** (§8.2 ~L796) now has its missing §9.2 live row `test_create_side_named_entity_retrieval` (~L983), asserting a **named entity** (`name`/`object_id` membership), not an aggregate count.
- **Gate V3** (§10.2 ~L1089) promoted **SHOULD → MUST/release-blocking** with a named-entity assertion on the exact 22-object `llm-wiki-test` repro space (the metric that was `objects_indexed: 0`); fail action "do not tag until this passes."
- **AC-P9** (§8.2 ~L832) adds a CI-runnable seam test `test_property_only_reindex_upserts_payload` (fake Qdrant + fake embedder) that backstops — does not replace — the live gates against a silent `indexer.py` refactor regression.
- **§10.1** (~L1047) names AC-P2/AC-P7 **non-skippable pre-tag gates**; AC-P9 a separate green-CI item.
The CTO independently traced the seam test against real code (`indexer.py` reindex call site ~L75, `chunk_object` L75, `embed` L85, `client.upsert` payload `heading`/`text` L96-103, `_delete_object_vectors` by `object_id` L121-130) and confirmed it exercises the **genuine** path and is implementable as written — not a mock-of-a-mock. No new technical inaccuracy introduced by the rework; file:line references in the new text are accurate.

**BLOCKING-2 — closed (CA, CSO, Legal concur).** Local-by-default is now a tested invariant (AC-S2.1, `test_local_default_no_offmachine_call` — no HTTP call to any non-local host when `WIKI_EXTRACT_ENDPOINT` unset). The first-run consent banner is pinned to **ship and fire before any source-content transmission** (AC-S2.2, `test_remote_endpoint_consent_banner_fires`; ack-file keyed `sha256(endpoint)[:8]`, re-prompts on endpoint change, stores hash+timestamp only). The README data-flow disclosure is promoted from a doc note to an AC-bound **conspicuous callout** (§11 ~L1147) and a §10.1 non-skippable pre-tag item, retaining the "and local-file notes" exfiltration phrasing. `product.md` and `compliance.md` were reconciled (commit `2fda2c4`) to "local-first by default, explicit opt-in remote-extraction exception."

**Hard pre-publish gate — closed (Legal).** The NOTICE/dependency tree (Legal-Adv1) is corrected and accurate: `typing-extensions` = **PSF-2.0 (not MIT)**, `pydantic-core`/`annotated-types` = MIT, markdownify's beautifulsoup4+six included; "all MIT" → "all OSI-permissive (MIT/PSF/BSD)"; NOTICE mandated generated from the resolved venv via `pip-licenses --from=mixed`; vendored-Rust manual-check caveat present (§10.1 ~L1061, §11 ~L1151).

**Operational advisories — closed (Infra).** §4.1-vs-§10.2 V2-fail contradiction reconciled (both now "release-blocking, NOT a deferred ticket"); object-scoped re-embed (delete + re-upsert by `object_id` payload filter, O(1) in corpus) preferred over whole-space sweep, pinned by `test_update_path_forces_reembed`; Ollama-OOM-mid-extraction failure-mode row added; G3 `wiki_facts` soft-cap ticket-filing obligation made binding; reindex concurrency safety (deterministic point IDs OR fcntl.flock) pinned as a §10.1 item. Rework lightens the steady-state resource profile; no new BLOCKING operational risk.

## Findings

### BLOCKING
None.

### ADVISORY

All advisories below are **test-phase / pre-publish execution notes** — none gates advancement out of spec. The actionable subset is consolidated into the spec addendum (`spec-addendum-post-spec-r2.md`) as test-phase acceptance criteria.

1. **[CTO-R2-A1] AC-P9 seam-test file placement.** §9 files the seam test alongside chunker tests, but it drives `indexer.reindex`; its natural home is `tests/test_indexer.py` where the `indexer` module-level symbols (`_qdrant`, `get_object`, `list_objects`, `list_spaces`, `embed`) are monkeypatchable. Placement precision, not a defect.
2. **[CTO-R2-A2 / CTO-A3 carry-forward] `markdown`-key assumption is a live unknown.** V1 must actually inspect the `get_object(format=md)` response key before the chunker's body path is trusted (`chunker.py:14` reads `obj.get("markdown","")`; `anytype_client.py` returns `["object"]` with no proof the body lands under `markdown`). Correctly bound to V1/V3 by the spec; restated for the test phase.
3. **[QA-ADV-1] AC-P7 traceability.** AC-P7's live coverage is via `test_reingest_reembeds_updated_facts` (row cites B2/AC-P7) rather than an AC-P7-named row. Coverage is genuine; keep the AC-P7 ↔ test mapping explicit in the test docstring.
4. **[QA-ADV-2 / CPO-ADV-R2-1] V3 / AC-P2 retrieval-strength bar.** Encode the named-entity assertion as `object_id`/`name` top-K membership, not a loose name-substring match. Pin one fixture entity + query string for V3 in the pre-release notes so the gate is reproducible run-to-run and not self-graded.
5. **[QA-ADV-3] V4 marker-home sequencing.** V4 (Option-a vs b-1 selection) must run before marker tests/impl; author only the V4-selected Option's test body, with `test_exactly_one_marker_mechanism_ships` guarding that exactly one mechanism ships. AC-M1a/M1b/M5 are gated on V4 PASS.
6. **[CSO-ADV-1] Consent-banner live wiring.** AC-S2.2's unit test mocks the ack-file path; confirm during test/impl that the banner call sits on the actual `wiki_ingest` code path ahead of the first `fetch`/transmit, not only in an isolated helper.
7. **[CA-ADV] README callout prominence.** A callout's value is visual conspicuousness, which a test cannot assert; a human should eyeball the rendered README data-flow callout at test-phase sign-off.
8. **[Legal-ADV] NOTICE gate is publish-time.** The corrected dependency tree is a check value; the binding `NOTICE` is generated from the resolved venv at tag time (§10.1 ~L1061). The gate must actually be executed and diffed against the expected tree before the PyPI push — it cannot be silently skipped. Placement (immediately above the tag/publish line) is correct.
9. **[Infra-ADV] Qdrant backup coverage.** Confirm the Qdrant collection is in the backup rotation (and restore is tested for the v0.3.0 data volume) before the long-running internal deployment accumulates an unrecoverable corpus. Fold into the pre-release ops notes alongside the A2 collection-size watch.
10. **[Legal process note]** For future content-ingesting features, source-usage-policy thinking should surface in the **product** phase, not at legal sign-off. Pipeline-improvement note, not a defect in this spec. Forwarded to the chair.

## Resolutions

No findings were withdrawn — there was nothing to withdraw. Every member verified the disposition of their own R1 findings as **RESOLVED** with specific spec evidence (AC id / § / line), and the CTO additionally cleared the new spec text on technical-accuracy grounds against the real source. The R1 split (four sign-offs vs three BLOCKING positions) has collapsed: the three members who held BLOCKING/veto positions (CPO, QA, Client Advocate) and the Legal hard-gate holder all confirm resolution. No member contradicts another; the sign-offs cover distinct surfaces (security, product, technical accuracy, test-gate strength, community honesty, legal, operations) with full coverage and no gap.

## Recommendation

**Recommended target:** test
**Confidence:** high
**Rationale:** Unanimous sign-off, zero BLOCKING findings. Both R1 BLOCKING clusters are genuinely closed with defense-in-depth: the retrieval gap v0.3.0 exists to close is now *provably* closed before ship (V3 MUST/release-blocking + named-entity assertion on the real repro space + AC-P2 live row + AC-P9 CI backstop + non-skippable pre-tag gating), and the local-first promise is honest (local-by-default tested invariant + AC-bound consent banner firing before transmission + reconciled context docs). The hard pre-publish legal gate (NOTICE tree) is corrected and accurate. The spec is now self-contained for the test phase. The remaining ADVISORY items are precise test-phase/pre-publish execution notes, consolidated into a spec addendum so the test lead honors them as acceptance criteria.

**Dissent:** None.

*Note (training wheels):* `config/council.yaml` `autonomous: []` — this recommendation routes to Decide for Jan's ruling regardless of target. The watcher enforces autonomy policy; the council records its honest recommendation (test).
