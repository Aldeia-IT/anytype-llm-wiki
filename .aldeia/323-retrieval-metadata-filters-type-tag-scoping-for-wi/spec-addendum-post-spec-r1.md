# Spec Addendum — post-spec council (R1)

**Source:** [`council-spec-r1.md`](council-spec-r1.md)
**Date:** 2026-06-12
**Target phase:** test / impl (applies once Jan ratifies OD-1 + OD-2 at Decide and the ticket advances)
**Status:** Authoritative — the test and impl phases MUST honor these items as spec requirements.

> Context: the council signed off the spec with **zero BLOCKING findings**. The ticket is routed
> to `decide` only so Jan can ratify the two Open Decisions (OD-1 date payload + forced re-embed;
> OD-2 de-scope + follow-up ticket) — not because of any spec defect. The items below are the
> council's ADVISORY findings that translate into concrete acceptance/exit criteria for the work
> that follows ratification. They do NOT block the Decide gate.

## Additional acceptance criteria for the test phase

1. **[CTO-4 / CSO-4]** AC-F1b and AC-F10b MUST ship as **genuinely runnable** tests, not
   placeholders. The referenced `anytype_enum_fixture` (the Tier-2 enumeration harness that forces
   `count >= index_threshold()` and drives `wiki_query` through Tier 2) was NOT found pre-existing
   in `tests/wiki/test_query.py` — the test phase must stand it up if absent, anchored to the real
   seams: `monkeypatch query_mod.config.index_threshold → 1`, capture stub on
   `query_mod.indexer.semantic_search_core`, `query_mod.synthesize` sentinel. AC-F1b is the only
   guard against the §8.1 `effective_types` refactor silently regressing the default-types
   behavior — it was R2's explicit approval condition and must not ship as `...`.

2. **[CSO-5]** Add a **cross-tier date-filter equivalence** test: for the same object and the same
   `ingested_after`/`ingested_before` bounds (including the inclusive-edge case), assert Tier-1
   (`_passes_date_filter`) and the Tier-2 Qdrant `DatetimeRange` path agree. The existing AC-F10
   tests each predicate in isolation but not Tier-1↔Tier-2 equivalence; timezone-normalization and
   bound inclusivity are implemented by two independent code paths and could diverge.

## Additional acceptance criteria for the impl phase

3. **[Infra-7 / Infra-9]** Make the §15 operational story concrete in the implementation:
   - Deployment note MUST sequence the manual-vs-cron reindex to avoid the overlap window (run the
     manual `reindex` with the launchd cron unloaded, OR let the cron perform the migration and do
     not run a manual reindex concurrently). The state file has no atomic write / lock and the cron
     plist has no overlap guard.
   - Add an explicit **post-deploy verification step**: after the first reindex, confirm
     `_payload_schema_version == 2` in the state file and spot-check that a dated chunk carries
     `last_modified_date`.

4. **[CSO-6]** Add a one-line cross-reference in spec §14 (Security) to the D3/§15 migration
   data-integrity analysis (the forced re-embed is the only state-mutating operation and is
   currently only covered under §15 Operational).

5. **[CTO-10]** Cosmetic: correct the deferral source citations to include the `wiki/` directory —
   `_create_source` / `wiki_excerpt` live in `src/anytype_llm_wiki/wiki/ingest.py` (~924-936), not
   bare `ingest.py`. Underlying claims are correct; this is for navigability.

## Items for the D6 follow-up ticket (NOT this ticket)

These are recorded so they are not lost when the follow-up is written; they impose nothing on
#323's impl:

- **[Infra-8]** The single-call embedder + fixed 120s timeout is the scaling ceiling on the forced
  backfill (fine at ~500 chunks). Note as a latent risk in the follow-up/backlog.
- **[CTO-11]** The `multi_select` GET response shape is UNVERIFIED — the follow-up MUST verify it
  against a live space before implementing `domain_tags` chunker extraction. No v1 code may touch it.
- **[CSO-6, longer-term]** Consider centralizing date validation at `semantic_search_core` so the
  trust boundary is enforced in one place rather than per call-site.

## Decide-gate items for Jan (handled at Decide, not in test/impl)

- **[CPO-1]** `.aldeia/context/product.md` advertises "Metadata filtering — Filter by space, object
  type, **tags**", a capability v1 will not deliver. Soften the line, or make the §15 release note
  explicitly state tag/source filtering is not yet available + link the follow-up.
- **[CPO-2]** Accepting OD-2 MUST be conditioned on the D6 follow-up ticket actually being created
  (inheriting #323's tag-scoping intent, linked to epic #140), so "deferred" cannot become
  "dropped."
- **[CPO-3]** Do NOT take OD-2's "opt-in `wiki_excerpt` indexing now" alternative in v1 — it
  silently changes `semantic_search` retrieval semantics. Endorsed by CPO; needs explicit product
  sign-off if ever pursued.

## Rationale

The council's verification was substantive: all four members re-checked load-bearing claims against
source, and the only carried risks are test-harness concreteness (findings 1–2), operational
documentation precision (finding 3), and minor doc cross-references (findings 4–5). None changes the
spec's design — they harden the test plan and the deployment story so the (already approved) design
ships verified. Items 1–2 in particular elevate R2's residual SHOULD-FIX from "resolved on paper"
to an enforced test-phase exit criterion.
