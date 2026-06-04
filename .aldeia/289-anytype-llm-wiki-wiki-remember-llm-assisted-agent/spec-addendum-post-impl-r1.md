# Spec Addendum — post-impl council (R1)

**Source:** [`council-impl-r1.md`](council-impl-r1.md)
**Date:** 2026-06-04
**Target phase:** done (PR merge) + v0.3.1 release tag (downstream, e.g. #234 tag-prep)
**Status:** Authoritative. The PR is approved to merge. Items 1–2 are HARD GATES on the v0.3.1 **release tag** (not on the PR merge). Items 3–6 are recommended hardening / v0.3.2 follow-ups.

The post-impl council returned **0 BLOCKING / unanimous sign-off**. These items carry the council's non-blocking conditions and advisory recommendations forward so they are not lost between PR merge and release tagging.

## Release-tag gates (block the v0.3.1 tag, NOT the PR merge)

1. **[Unanimous] Live smoke run against a freshly re-bootstrapped space MUST pass before tagging v0.3.1.** Run `test_live_wiki_remember_end_to_end` (`@pytest.mark.live`) with `WIKI_TEST_SPACE_ID` set against a space that has been re-bootstrapped to schema 0.3.1 (`wiki-bootstrap --space-id <id>`). This is the only signal that proves (a) a `wiki_status`/`wiki_source_type`/`wiki_action` tag write actually succeeds against live Anytype's property-scoped endpoint — the exact path the C1 CRITICAL got wrong and that no CI test covers — and (b) AC-R7/AC-R24 (retrievable-after-reindex; real off-machine consent-on-transmit). CI "454 passed" does not cover either.

2. **[Infra] The live smoke run MUST include an Anytype export→import round-trip** on the re-bootstrapped space, confirming the new `wiki_status`/`wiki_source_type` tags, `wiki_source` provenance objects, and `wiki_log` entries survive restore. Backup coverage is *inferred* object-type-agnostic (Anytype native export) but has not been restore-tested for the new object types.

## Recommended hardening (address before tag if cheap; otherwise v0.3.2)

3. **[CSO-A1] Resolve the WikiLog sanitize gap vs. the B1 claim.** `_write_wikilog` (`ingest.py:241-269`) writes LLM-derived `notes` and `subject=knowledge[:50]` to Anytype `wiki_notes`/`wiki_subject` without `sanitize_property_value`, deviating from the spec §8.4 B1 "raw LLM output NEVER reaches Anytype" absolute. EITHER wrap `notes`/`subject` in `sanitize_property_value` inside `_write_wikilog` (one line; also hardens the #284 ingest path), OR correct the spec §8.4 wording to scope B1 to the fact properties (`wiki_facts`/`wiki_definition`) and record the WikiLog audit text as a knowingly-accepted residual. Do not ship the absolute B1 claim alongside the unsanitized audit path.

4. **[CA-A2] Require verbatim superseded text in the consolidation contract.** Add one RULE line to `consolidate.md` (the `supersedes` field, line ~37) requiring the model to emit the *complete verbatim* superseded text, not a paraphrase — so the supersede WikiLog audit note (CPO-A1/CA-A1, `remember.py:491-496`) is losslessly recoverable.

## v0.3.2 operational follow-ups (do NOT block v0.3.1)

5. **[Infra-A1 / CPO-A3] Write-rate advisory while auto-reindex is on.** `WIKI_AUTO_REINDEX` defaults `"true"`; reindex cost scales with total space size on the first repeated agent-write path. Docs disclose the `WIKI_AUTO_REINDEX=false` + batched mitigation. Add a one-time ntfy/log advisory when writes/hour to a space exceed a threshold while auto-reindex is on.

6. **[Infra-A2] WikiLog pruning tooling.** Monotonic WikiLog growth is disclosed but pruning is manual with no concrete procedure. Provide a `wiki-log prune --older-than <duration>` helper or document the manual deletion procedure concretely.

## Accepted residuals (no action; recorded for traceability)

- **[CSO-A2 / Legal-A2] Consent gate is notify-once / non-blocking / self-acking** — correct and disclosed for the single-operator autonomous-agent model. Any future move to multi-tenant/hosted MUST re-trigger security + legal review (re-opens LGPD/GDPR controller-vs-processor).
- **[Legal-2 / CSO] `knowledge` stored as-is** (only URL credentials scrubbed) — disclosed in README operating notes; proportionate to the single-operator MIT model.
- **[m1] `sources_overwrite_on_conflict` over-warns on the PATCH-skipped path** — non-destructive audit signal; documented rationale.

## Rationale

The council's verdict is ADVANCE with zero blocking defects: the recurring wire-contract defect class (test-council B-1, impl C1) is structurally closed (remember.py makes no raw HTTP calls), the two durable-audit trust findings landed in shipped code, and the operator docs landed in shipped README/CHANGELOG. The single concern every lens reached independently is that the one guarantee defining this product's trustworthiness — conflict review-flagging via live tag writes — was almost shipped silently inert and has been re-verified only against mocks. Gating the *release tag* (not the merge) on a live smoke run is the proportionate guardrail: it lets the code land while ensuring the documented contract is empirically confirmed against reality before operators receive it.
