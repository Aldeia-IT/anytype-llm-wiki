# Council Meeting — Post-test (Round 1)

**Date:** 2026-06-13
**Ticket:** #336 — wiki: persist domain_tags + index sources + enable filters
**Phase reviewed:** test
**Client:** anytype-llm-wiki (the agent fleet's own shared wiki memory tool)

## Attendance

| Role | Present | Reason |
|------|---------|--------|
| Council Chair | Yes | moderator |
| QA Director | Yes | minimum (config) — test coverage, AC traceability, fail-first integrity |
| Chief Technology Officer | Yes | roster — technical accuracy of test seams + reviewer diligence (central to a test phase) |
| Chief Product Officer | Yes | verify tests encode the ratified Decide decisions (OD-A/B/C) without scope creep |
| Client Advocate | Yes | anytype-llm-wiki is a non-aldeia-box repo; represents the fleet as users of the memory tool |
| Chief Security Officer | No | test phase introduces no new attack surface; CSO-A1 (excerpt redaction) is a §14 doc note already in the spec addendum — cleared at spec council |
| Legal Counsel | No | no new legal/compliance surface in a failing-tests phase |
| Infrastructure Lead | No | addendum migration items 7–8 are impl/deploy-time, not testable now; #342 (atomic state-file write) already merged. Carried forward as impl-phase obligations |

## Context Presented

The test phase authored failing-first tests for all of spec §10 + §12 acceptance criteria plus the post-spec addendum, then carried them through one review-fix round (R1 NEEDS CHANGES → fix → R2 APPROVED, within the 2-round cap, no escalation). The branch was correctly rebased onto current main (#323 PR#47, #324 PR#46, #341, #342 present), so the QA-A1 rebase gate was met before any test ran.

Final pre-impl suite state (independently reproduced by QA, CTO, CPO, and Client Advocate): **33 failed, 664 passed, 37 skipped, 3 xfailed**. All 33 failures are #336 tests failing for missing-behavior reasons; the inherited #323 `test_no_filter_regression` still passes.

Jan's ratified Decide decisions the tests had to encode:
- **OD-A** — domain_tags backfill is forward-only (literal "backfill where derivable" AC superseded; no backfill test).
- **OD-B Option 2** — index `wiki_excerpt` so `source_type` filter is live, but default `semantic_search` must EXCLUDE `wiki_source` (regression at the `server.py` seam); explicit `types=["wiki_source"]` retrieves it.
- **OD-C** — SET (not MERGE) for `wiki_domain_tags` on update.

## Discussion

The four specialists reviewed in parallel and converged. Cross-cutting threads:

- **All four independently ran the suite** rather than trusting the debrief. The reproduced count (33/664/37/3) matches R2 exactly — strong evidence the R2 reviewer actually executed the suite, not a document review. Failure types are all behavioral (`TypeError` for params not yet accepted, `AssertionError` for absent behavior, `KeyError`, one intentional in-test `ImportError`); **zero collection errors, zero module-level import failures** — i.e. the reds are "missing behavior" reds, not "broken rebase" reds.
- **CTO verified the B1 seam against production code:** `server.py:8` imports `semantic_search_core` at module level and `semantic_search` (line 58) passes `types` straight through, so the R2 rewrite's `monkeypatch.setattr(_server_mod, "semantic_search_core", fake_core)` genuinely intercepts the real call path. Ran B1 and `test_no_filter_regression` together: B1 fails (`assert None is not None`), regression passes — the R1 mutual-exclusion contradiction is genuinely gone because the two tests now hit different layers (server vs. core).
- **QA and CPO both confirmed the OD-C SET discriminator is real** in both `test_ingest.py` (seeds `old-tag-id`) and `test_remember.py` (seeds `old-rem-id`): a MERGE impl producing `["old-tag-id", "tag-id-ai"]` fails; SET passes.
- **CPO and Client Advocate independently confirmed OD-A fidelity:** no backfill test is smuggled in (the two `backfill` matches in `test_indexer.py` are inherited #323 space-scoping tests), the forward-only "empty-until-re-touched" limitation is disclosed honestly in the spec/release note (stated three times, labelled "material gap, not a footnote"), and the tests never overclaim legacy-corpus coverage.
- **CTO confirmed the integration realities he flagged at the spec council are honored:** the #324 collision (post-#324 seams verified in `query.py`/`indexer.py`) and the `lint.py:33` third caller of `_resolve_select_tag` (import-regression trio present: 1 RED for `_resolve_multi_select_tags`, 2 GREEN guards for the re-export — ran in isolation, `1 failed, 2 passed` as designed).
- **Client Advocate framed the fleet-impact stakes:** had B1 shipped unfixed, the implementer would have faced two contradictory tests and could have "resolved" them by weakening the regression guard — the precise way a silent default-behavior change (raw source excerpts polluting every caller's top-k) sneaks in. The fix relocating the assertion to the `server.py` seam closes that path.

## Findings

### BLOCKING
None. All four specialists signed off.

### ADVISORY

1. **[CTO/CPO] `FakeWikiClient.update_object` signature drift (impl-phase).** `test_create_source_writes_source_type_on_reuse_path` instantiates an inline fake whose `update_object(data=...)` signature should be re-confirmed against the real `WikiClient.update_object` during impl, per the repo's #287 "verify against the real client" rule. Cannot cause a false pass now (the test fails for the correct reason), but the impl reviewer must confirm the fake matches the real method so the reuse-path guard stays meaningful post-impl.

2. **[QA/CPO/Client Advocate] AC-V-WARN is xfail (D11 deferral).** The mandatory invariant AC-V-ZERO (out-of-taxonomy filter value → zero results, no raise) is asserted RED; only the optional typo *warning* on top is `xfail(strict=False)`. Acceptable, bounded gap — not a coverage hole. Client Advocate notes the warning would genuinely help the fleet's "I set a filter and got nothing, why?" footgun; recommend the implementer enable it unless taxonomy-fetch latency on the hot query path proves material.

3. **[Infra-carry / CTO/Client Advocate] Migration deploy obligations (impl/deploy-phase).** Spec addendum items 7–8 — set `WIKI_AUTO_REINDEX=false` (or pause launchd) for the one-time v2→v3 manual reindex, and a post-deploy negative verification (`state.json _payload_schema_version == 3` AND a second immediate reindex re-embeds nothing). These are deployment-step checks, not executable tests; correctly out of test-phase scope but must not be dropped from §15. #342 (atomic state-file write + overlap guard, now merged) partially mitigates the concurrent-writer hazard.

4. **[QA/CPO/Client Advocate] OD-A forward-only decision visibility (ship-phase).** Already ratified by Jan at the Decide gate. The product/client concern is purely that the release-note forward-only paragraph actually reaches Jan/operators — the entire pre-#336 corpus returning nothing for a `domain_tags` filter is a foreseeable "is it broken?" support moment. No test/code change.

5. **[QA/CTO] Cosmetic: stale docstring/name `test_wiki_property_heading_maps_all_eight_keys` ("8 keys").** Logic iterates the now-9-entry constant and is correct; name is misleading. Rename opportunistically during impl. Zero functional impact.

## Resolutions

- The two R1 BLOCKING findings (B1 fails-forever OD-B test on the wrong seam; B2 unguarded `PAYLOAD_SCHEMA_VERSION=3` deliverable) and the one SHOULD-FIX (OD-C SET vs MERGE indistinguishable) were all confirmed genuine and genuinely resolved by independent source-level cross-checks from QA, CTO, and CPO. No specialist downgraded another's concern; no finding was withdrawn.
- CSO/Legal/Infra non-attendance was accepted as appropriate scope for a failing-tests phase; their relevant items are either already in the spec addendum (CSO-A1 §14 note, Infra items 7–8) or carried forward as impl/deploy obligations (advisory 3).

## Recommendation

**Recommended target:** impl
**Confidence:** high
**Rationale:** The test suite is a trustworthy gate — RED for the right reasons (missing behavior, not broken machinery), satisfiable by a spec-faithful implementation without breaking the inherited #323 regression, and it faithfully encodes all three ratified Decide decisions plus the addendum. The in-phase review demonstrably caught the two failure modes the test phase exists to prevent (an unsatisfiable/conflicting regression test and an unguarded version-constant deliverable) and resolved both in one round. The next phase is implementation: turn the 33 reds green by following §11 steps 1–8, honoring the impl-phase advisories captured in `spec-addendum-post-test-r1.md`. The watcher enforces autonomy policy; if impl is not yet autonomous it will route to Decide instead — the council simply recommends impl on the merits.
**Dissent:** None.
