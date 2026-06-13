# Spec Addendum — post-test council (R1)

**Source:** [`council-test-r1.md`](council-test-r1.md)
**Date:** 2026-06-12
**Target phase:** impl
**Status:** Authoritative — the impl phase MUST honor these items as spec requirements,
in addition to the impl-phase ACs already recorded in
[`spec-addendum-post-spec-r1.md`](spec-addendum-post-spec-r1.md) (Infra-7/Infra-9, CSO-6,
CTO-10), which remain in force.

> Context: the council signed off the test phase with **zero BLOCKING findings** (unanimous
> advance test → impl). The items below are the council's ADVISORY findings that translate
> into concrete acceptance/exit criteria for the implementation phase. They do not reopen the
> approved design — they ensure the feature ships documentation-honest and that the test-enforced
> ordering/coverage requirements are met in the right place.

## Additional acceptance criteria for the impl phase

1. **[CPO-1] Reconcile the product.md "tags" overclaim and ship the release note.** This is Jan's
   explicit Decide-gate finding 1.
   - Soften `.aldeia/context/product.md:15` ("Metadata filtering — Filter by space, object type,
     **tags**") so it does not advertise a capability v1 does not deliver. Suggested:
     "Filter by space and object type, with date-range filtering; tag/source filtering planned
     (see #336)."
   - Ship the §15 release note stating tag/source filtering is **not** available in v1, linking
     **#336**. The product-truth fix must ship **with** the feature, not drift.

2. **[CTO-ADV1] `wiki_query` validation must short-circuit before client construction.** Insert
   the date-format and empty-type-intersection validation as an **early return ahead of**
   `AnytypeReadClient` / `WikiClient` construction (current code constructs clients at
   ~`src/anytype_llm_wiki/wiki/query.py:371-372` before any validation). The F6b/F6c tests
   enforce this — a non-short-circuiting impl returns `api_error` instead of the required
   `config_error` and the tests fail. Place validation per spec §9.2.

3. **[CPO-traceability] Cite #336 literally in the spec.** Backfill the follow-up ticket id
   "#336" into spec §12 DEFERRED rows and §3 D6, which currently refer to the deferral
   generically ("D6 / single follow-up ticket"). Low effort, durable traceability so "deferred"
   cannot become "dropped." Low priority but bundle with the impl commit.

4. **[QA-A1/A2] Confirm two regression/threshold behaviors go genuinely green post-impl.**
   - Confirm the pre-existing space_id-scoping test (AC-F3 coverage) still passes after the
     §6.2 `must`-list refactor touches the space_id clause; add a one-line space_id-in-`must`
     assertion if cheap.
   - Confirm `test_no_bump_keeps_incremental_skip` (AC-F11b) reaches and passes its
     `objects_indexed == 0` assertion after `config.PAYLOAD_SCHEMA_VERSION` is added — i.e. goes
     genuinely green, not merely non-erroring.

## Carried-forward impl exit criteria (from post-spec R1 addendum — still in force)

- **[Infra-7/Infra-9]** Deployment note MUST sequence manual-vs-cron reindex to avoid the
  overlap window (state file has no atomic write/lock; cron plist has no overlap guard), and add
  a post-deploy verification step: after the first reindex confirm `_payload_schema_version == 2`
  and spot-check that a dated chunk carries `last_modified_date`.
- **[CSO-6]** Add a one-line cross-reference in spec §14 (Security) to the D3/§15 migration
  data-integrity analysis.
- **[CTO-10]** Cosmetic: correct the deferral source citations to include the `wiki/` directory
  (`_create_source` / `wiki_excerpt` live in `src/anytype_llm_wiki/wiki/ingest.py`).

## Rationale

The council's verification was substantive: all four members ran the suite, reproduced the
15/101/11 split, traced failures to missing-impl artifacts, and independently re-confirmed the
one previously-flagged operational hazard (real-state-file mutation) is fixed (c88218e). The
only carried risks are documentation honesty (item 1 — Jan's explicit finding), a non-obvious
validation-ordering requirement the tests already enforce (item 2), traceability (item 3), and
post-impl green-confirmation of two tests (item 4). None changes the approved design; they ensure
the (already-approved, well-tested) feature ships verified and documentation-honest.
