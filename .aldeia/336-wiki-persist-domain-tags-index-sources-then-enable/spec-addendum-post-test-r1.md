# Spec Addendum — post-test council (R1)

**Source:** [`council-test-r1.md`](council-test-r1.md)
**Date:** 2026-06-13
**Target phase:** implement
**Status:** Authoritative — the implement phase MUST honor these items as spec requirements, in addition to the prior [`spec-addendum-post-spec-r1.md`](spec-addendum-post-spec-r1.md) (whose items 1–9 remain in force).

The post-test council unanimously signed off (0 BLOCKING). These advisories carry actionable requirements into the implement (and deploy) phase. They supplement, not replace, the post-spec addendum.

## Additional acceptance criteria for the implement phase

1. **[CTO/CPO] Verify `FakeWikiClient.update_object` matches the real client.** `test_create_source_writes_source_type_on_reuse_path` uses an inline fake whose `update_object(data=...)` signature must match the real `WikiClient.update_object`. Before marking the reuse-path AC green, confirm the fake's signature against the real method (repo #287 rule: "verify against the real client"). If they differ, fix the fake (or the test seam) so the guard remains meaningful — do not let a signature mismatch turn a real guard into a no-op.

2. **[QA/CPO/Client Advocate] AC-V-WARN typo warning — implement unless latency-prohibitive.** AC-V-WARN (`test_wiki_query_out_of_taxonomy_filter_warns`) is `xfail(strict=False)` per D11. The mandatory invariant (AC-V-ZERO: out-of-taxonomy value → zero results, no raise) is already required. The council recommends the implementer ALSO emit the out-of-taxonomy warning (XPASSing the deferred test) so a confused agent learns its `domain_tags`/`source_type` value isn't in the taxonomy — UNLESS fetching the taxonomy on the hot query path adds material latency, in which case keep it deferred and note the decision. Not a hard blocker; document the choice either way.

3. **[QA/CTO] Rename the stale `test_wiki_property_heading_maps_all_eight_keys`.** The test now iterates a 9-entry constant; rename to reflect nine keys (cosmetic, opportunistic — no logic change).

## Deployment / ship obligations (carried, must not be dropped)

4. **[Infra-carry] Migration reindex state-file isolation** (post-spec addendum item 7, reaffirmed). For the one-time v2→v3 manual reindex, set `WIKI_AUTO_REINDEX=false` (or `launchctl unload` the reindex job) during the manual pass, then re-enable. #342 (atomic state-file write + overlap guard, now on main) partially mitigates the concurrent-writer hazard but does not remove this step.

5. **[Infra-carry/Client Advocate] Post-deploy negative verification** (post-spec addendum item 8, reaffirmed). After the migration reindex, confirm `state.json` `_payload_schema_version == 3` AND that a second immediate `reindex` re-embeds nothing (proves the marker stamped and incremental behavior resumed). This is an operational check, not a unit test — ensure it is in §15 deployment steps.

6. **[QA/CPO/Client Advocate] Ship the OD-A forward-only release note.** OD-A (forward-only tagging) is ratified. Ensure the §15 release-note paragraph stating that existing pre-#336 objects are NOT retroactively tagged actually reaches Jan/operators — the empty-`domain_tags`-filter experience on the legacy corpus is a foreseeable "is it broken?" moment and must be set as an expectation, not discovered.

## Rationale

Item 1 is a genuine new impl-phase acceptance item the prior addendum did not cover and would otherwise be lost in a review file. Item 2 converts a deferred-but-valuable UX guard into an explicit implementer decision. Items 4–6 reaffirm deploy/ship obligations from the post-spec addendum that are not test-gated and are therefore at risk of being dropped once the tests go green. All are next-phase requirements that free-text comments carry unreliably — hence this addendum, which the implement lead reads during Task Intake.
