# Spec Addendum — post-spec council (R1)

**Source:** [`council-spec-r1.md`](council-spec-r1.md)
**Date:** 2026-06-04
**Target phase:** test (then impl — this addendum auto-chains forward to both)
**Status:** Authoritative — the test and impl phases MUST honor these items as spec requirements.

The post-spec council signed off with zero BLOCKING findings. The advisories below are the subset
that act as additional acceptance/exit criteria for the downstream phases. Each is attributed to its
source specialist. Items are grouped by the phase that owns them; the lead of each phase reads this
file during Task Intake.

## Additional acceptance criteria for the TEST phase

1. **[QA-12]** Add a test for the **Tier-2 candidate-fetch failure** path — a Tier-2 candidate's
   `get_object` failing, which is distinct from a *neighbor* `get_object` failing (already covered by
   `test_partial_neighborhood_downgrades_to_partial`) and from total enumeration failure. Either add a
   sibling test or assert in a comment/test that candidate and neighbor fetch share one code path so
   one test demonstrably covers both. The `status`/`sources_consulted` outcome of a failed Tier-2
   candidate must be pinned.
2. **[QA-13]** Parametrize the Qdrant-down test at the exact threshold boundary — `count=199` (below →
   silent Tier-1 fallback, `status: ok`) and `count=200` (at threshold → `[API ERROR] qdrant_unavailable`,
   `status: error`) — reusing the boundary-matrix fixture, so the `count >= threshold` comparator is
   pinned on the failure path, not only on the mode-selection path.
3. **[CSO-1]** `test_synthesis_content_injection_neutralized` must assert non-obedience against at
   least one **realistic multi-vector** injection payload embedded in object CONTENT, not only the
   literal "ignore previous instructions" string. The test must confirm the payload lands inside the
   `<context>` fence under the DATA preamble and the synthesized answer does not obey it.
4. **[CTO-6 / QA-6 / Client-19]** The 1-hop relation read-back element shape is the one unverified wire
   contract. The test suite must keep `test_relation_readback_accepts_both_shapes` (dual-shape parser)
   AND the skip-gated live smoke test (`SF5` — pin the real shape from a live `get_object`). If the
   live shape differs from both mocked forms during impl, the real shape MUST be added to the mocked
   fixture so `test_reciprocal_relation_read_merge_write` exercises the real shape (otherwise the
   read-merge could merge an empty prior set and silently re-introduce the N1 clobber).

## Additional acceptance/exit criteria for the IMPL phase

5. **[Client-18]** Reconcile the config-var inconsistency: Files Changed (spec.md:656-657) says
   "three new vars" but Configuration (spec.md:503-512) adds **six**. The implementation MUST ship all
   six resolvers (`index_threshold`, `file_back_min_sources`, `file_back_min_words`,
   `synth_max_input_tokens`, `synth_max_objects`, `synth_max_object_tokens`) and the corresponding six
   `.env.example` entries in sync. `test_config_validators_reject_zero_and_negative` should cover the
   `WIKI_SYNTH_MAX_*` validators too.
6. **[CPO-15 / Client-15 / Client-17]** Add a **documentation acceptance criterion**. The README
   quick-start must demonstrate an end-to-end `bootstrap → ingest → query` run; the "How it works"
   section must explain (a) tiered retrieval (why Tier 1 vs Tier 2 + the threshold rationale), (b) the
   compounding loop (file-back → reindex → future retrieval), and (c) the **reindex-then-retrievable
   latency caveat** (a filed answer surfaces in Tier-2 only after the next `reindex_anytype`). Update
   `docs/known-limitations.md` (named in the scope brief, absent from Files Changed) with the
   reindex-cadence limitation. Treat the README as a reviewed deliverable, not a footnote.
7. **[CPO-16]** The README quick-start should demonstrate `file_back=True` explicitly so a first-time
   user *sees* the compounding loop close during onboarding — the default gate (≥3 sources AND
   ≥100 words) will rarely fire on a fresh small wiki.
8. **[Infra-8]** Resolve the synthesis timeout for an interactive tool: either introduce a separate
   `WIKI_SYNTH_TIMEOUT` (interactive default ~120s) instead of reusing the 600s `WIKI_EXTRACT_TIMEOUT`,
   OR document the 600s as a deliberate accepted ceiling and emit a slow-synthesis log signal when a
   synthesis call exceeds ~60s. (The `httpx` connect/read timeouts already prevent an indefinite hang.)
9. **[CSO-2]** Add one sentence to the spec/README Security Considerations naming the file-back loop as
   an injection amplifier (poisoned synthesis re-ingested as a future source), citing the SF1
   clean-synthesis gate + min-sources/min-words as the bound.
10. **[Infra-11 / Infra-9]** Ensure `error_category` (config_error/api_error) returns and the
    `filterexpression_fallback` >500-row warning are surfaced to operator logs, not buried only in the
    per-query `QueryResult`.
11. **[CTO-5]** Treat `embed_query` as imported from `embedder.py:22` (already imported by
    `indexer.py`) — there is no function to "move from server.py" as spec.md:116 implies. Cosmetic;
    avoids wasted impl effort.

## Release-gate criteria (record on the v0.4.0 release checklist)

12. **[Infra-10 / Client-19]** Run the live smoke test once against the **real Qdrant v1.17.0** and
    against **Aldeia's own vault** (internal dogfood) before any community release tag, to confirm the
    nested-`should`-in-`must` filter on that Qdrant version and to pin the live relation read-back
    shape. Internal-dogfood-first, community-tag-second.
13. **[QA-14]** Capture the maintainer-measured **p95 < 5s on Mac Mini M4** (master spec AC#7) as an
    explicit release-checklist item — the mocked `test_mocked_query_completes_under_5s` is a
    no-pathology gate, not the production SLO.

## Rationale

These items are recorded as authoritative because free-text ticket comments are easily missed by the
next lead, whereas inline spec addenda are read during Task Intake. None expands the v0.4.0 scope —
each refines test coverage, fixes a spec internal inconsistency, or hardens the highest-visibility
community surface (docs) and the highest-risk operational surface (the shared `semantic_search` tool
and the synthesis timeout). The relation-shape items (4, 12) are the most important to not lose: a
wrong shape guess could silently re-introduce the N1 relation-clobber the in-phase R2 review caught.
