# Spec Addendum — post-spec council (R2)

**Source:** [`council-spec-r2.md`](council-spec-r2.md)
**Date:** 2026-06-03
**Target phase:** test (then impl / pre-publish)
**Status:** Authoritative — the test phase MUST honor these items as spec requirements. They are the council's R2 ADVISORY items, precise enough to serve as a test-phase brief. The spec body (§8/§9/§10/§11) already pins the substantive contracts; this addendum captures execution constraints the test/impl lead must not lose.

## Additional acceptance criteria for the test phase

1. **[CTO-R2-A1] Place the AC-P9 seam test where the indexer is patchable.** `test_property_only_reindex_upserts_payload` MUST live where it can monkeypatch the `indexer` module-level symbols (`_qdrant`, `get_object`, `list_objects`, `list_spaces`, `embed`) — i.e. `tests/test_indexer.py`, not under an assumed `tests/wiki/` home. The seam test MUST drive the real `chunk_object → embed → upsert` path (fake `_qdrant()` spy client + fake embedder) and assert on the captured `points[].payload` carrying the property chunk's `text` and `heading` (e.g. `heading == "Facts"`, `wiki_facts` text). It must not stub `chunk_object` itself.

2. **[CTO-R2-A2 / CTO-A3] Verify the `markdown`-key assumption during V1, before trusting the chunker body path.** The chunker reads `obj.get("markdown", "")` (`chunker.py:14`) and `get_object(format=md)` returns the `["object"]` dict with no proof the rendered body lands under a `markdown` key. V1 MUST inspect the actual `get_object(format=md)` response shape and confirm the key before the body path (and V3's implicit validation of it) is relied upon. If the key differs, fix the chunker accordingly.

3. **[QA-ADV-1] Keep the AC-P7 ↔ test mapping explicit.** AC-P7's update-path end-to-end retrieval is verified by `test_reingest_reembeds_updated_facts`. Preserve this mapping explicitly in the test docstring so traceability stays mechanical (AC-P2 gets a same-named row; AC-P7's coverage must remain discoverable).

4. **[QA-ADV-2 / CPO-ADV-R2-1] Retrieval assertions are `object_id`/`name` membership, and V3's fixture is pinned.** Both AC-P2's `test_create_side_named_entity_retrieval` and gate V3's named-entity check MUST assert top-K membership on the created/known entity's `object_id` (or `name`), NOT a loose name-substring match that can pass spuriously. Additionally, pin one named fixture entity + its query string for V3 in the pre-release notes so V3 is reproducible run-to-run rather than a self-graded check at tag time.

5. **[QA-ADV-3] Honor V4 marker-home sequencing.** Run V4 (Option-a vs Option-b-1 marker-home selection) — or its `test_exactly_one_marker_mechanism_ships` guard — BEFORE authoring marker tests/impl. Author only the V4-selected Option's test body; do not ship both Option-a and Option-b-1 mechanisms. AC-M1a/M1b/M5 are gated on V4 PASS.

6. **[CSO-ADV-1] Confirm the consent banner is wired into the live ingest path.** AC-S2.2's unit test mocks the ack-file path. During test/impl, confirm the consent-banner call actually sits on the live `wiki_ingest` code path ahead of the first `fetch`/transmit to a non-local endpoint — not only inside an isolated helper that the production path may bypass.

## Pre-publish (tag-time) gates — not test-phase, recorded so they are not lost

7. **[CA-ADV] Human-eyeball the README data-flow callout for prominence** at test-phase sign-off (visual conspicuousness is not test-assertable).

8. **[Legal-ADV] Execute the NOTICE gate at publish time.** Generate `NOTICE` from the resolved venv via `pip-licenses --from=mixed` and diff it against the corrected expected tree (`typing-extensions` PSF-2.0; `pydantic-core`/`annotated-types` MIT; markdownify's beautifulsoup4+six; "all OSI-permissive (MIT/PSF/BSD)"); manually verify `pydantic-core`'s vendored Rust crate licenses. This is the §10.1 (~L1061) item and MUST NOT be silently skipped before the PyPI push.

9. **[Infra-ADV] Confirm Qdrant collection is in the backup rotation** (and restore tested for the v0.3.0 data volume) before the long-running internal deployment accumulates an unrecoverable corpus. Fold into the pre-release ops notes alongside the §12 collection-size / Colima-RSS watch.

## Rationale

The council reached unanimous sign-off with zero BLOCKING findings; the spec body already pins every substantive contract (V3 MUST, AC-P2/P7/P9, AC-S2, the corrected NOTICE tree, the V2-fail reconciliation). What remains are **execution constraints** that are easy to lose between phases: where a test file lives (so it actually exercises the real seam rather than a mock), how an assertion is written (membership vs substring), the ordering dependency around V4, and three tag-time gates that no test run will trigger. Capturing them inline as authoritative test-phase acceptance criteria — rather than leaving them in the meeting summary the next lead must remember to re-read — ensures the defense-in-depth the council verified actually lands in the test artifacts and the release checklist.
