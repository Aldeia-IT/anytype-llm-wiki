# Implementation Review R2 — wiki_remember (#289)

**Verdict: APPROVED**

**Date:** 2026-06-04
**Reviewer:** lead (re-review of R1 fixes, commit b392230)

## R1 findings — disposition (all lead-verified in source, not just via green tests)
- **C1 (CRITICAL) — RESOLVED.** Fabricated space-level `/v1/spaces/{id}/tags` caller is gone (grep confirms no non-property-scoped `/tags` caller in `src/`). `remember.py` now resolves select tags via `_resolve_select_tag` doing the spec D6 two-step (`list_properties` → match property key → `client.list_tags(space_id, prop_id or property_key)`), mirroring `ingest._resolve_wiki_action_tag` incl. SF12 degraded-read symmetry. The 16 tag route mocks in `test_remember.py` were re-pointed to the property-scoped path via `url__regex=r".*/properties/[^/]+/tags(\?.*)?$"` — assertions unchanged. **Proof the fix is real, not mock-papered:** the tag-absent degrade tests (`test_conflict_status_tag_absent_degrades`, `test_source_created_without_source_type_when_tag_absent`, `test_wikilog_action_tag_absent_degrades`) all pass against the corrected endpoint (3 passed).
- **M1 (MAJOR) — RESOLVED.** Hand-rolled `_resolve_remember_action_tag` deleted; action-tag call site (remember.py:596) now calls the imported `_resolve_wiki_action_tag(client, space_id, action_name="remember")`. Dead import cleared. Stale ingest docstring fixed.
- **M2 (MINOR) — RESOLVED.** Local `_object_deeplink` removed; now `from .bootstrap import _object_deeplink` (remember.py:29).
- **Schema guard — RESOLVED.** `@pytest.mark.skip` removed; `test_wiki_schema_version_is_031` positively asserts `WIKI_SCHEMA_VERSION == "0.3.1"`.
- **m1 (MINOR) — ACCEPTED (no change).** `sources_overwrite_on_conflict` over-warning on the PATCH-skipped path is a benign, non-destructive audit signal; addendum item 2 accepts the warning as the surfacing mechanism. Documented in the fixer debrief.

## Test state (lead-run)
- `tests/wiki/` → **368 passed, 4 skipped, 2 xfailed**.
- 4 named regression guards (`default_name_is_ingest`, `default_is_ingest`, `payload_unchanged`, `model_not_pulled_detection_unchanged`) → 4 passed.
- Full repo (fixer-run) → 454 passed, 23 skipped, 2 xfailed. No cross-module regression.
- Branch pushed; in sync with origin.

## Outcome
0 open BLOCKING / SHOULD-FIX. The single accepted MINOR (m1) carries documented rationale. The production-correctness defect (C1) — which a green suite alone did not surface — is fixed and proven against the real Anytype property-scoped endpoint. Approved to proceed to docs check + PR.
