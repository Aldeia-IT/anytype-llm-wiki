# Spec Addendum — post-spec council (R1)

**Source:** [`council-spec-r1.md`](council-spec-r1.md)
**Date:** 2026-06-13
**Target phase:** test → implement (after Jan's Decide ratification of OD-A/B/C)
**Status:** Authoritative — the test and implement phases MUST honor these items as spec requirements.

The post-spec council unanimously signed off (0 BLOCKING). These advisories carry actionable requirements into the next phases. Items conditioned on a Jan decision are marked; honor them per the ratified option.

## Additional acceptance criteria for the test / implement phases

1. **[CTO-A1] Rebase onto current `origin/main`, not "wait for #323".** #323 is already merged to main (`6281f5e`, PR #47). The dependency gate is MET. The implement phase begins by rebasing this branch onto current main. Update the spec's "CRITICAL: Hard Dependency on #323" framing and §15 step 1 to "rebase onto current main" during implementation.

2. **[CTO-A1] Absorb #324 (relationship-aware retrieval, `6aa320a`, PR #46) in the rebase.** #324 is on main and modifies the exact files #336 edits (`query.py`, `indexer.py`, `server.py`, `chunker.py`, `test_chunker.py`, `test_indexer.py`, `test_query.py`). Before writing code, re-anchor §11's step line-numbers against the **post-#324** tree and re-verify the `semantic_search_core` filter-build and Tier-1 dispatch seams still hold where #324's neighbour fan-out now coexists with #323's filter `must`-list. This is a spec-anchoring refresh, not a re-spec — but it is mandatory and must be done before the test phase runs (see item 4).

3. **[CTO-A2] `_resolve_select_tag` has a THIRD caller — do not break it.** `lint.py:33` imports `_resolve_select_tag` from `remember.py` (verified). D1 relocates the resolver helpers to `ingest.py`. Implementation MUST keep all three call sites green: define `_resolve_select_tag`/`_resolve_multi_select_tags` in `ingest.py` and **re-export `_resolve_select_tag` from `remember.py`** (or re-point `lint.py`'s import). Add an import-regression test asserting `from anytype_llm_wiki.wiki.remember import _resolve_select_tag` still resolves and `lint.py` imports cleanly post-refactor.

4. **[QA-A1] The test phase is GATED on the rebase (items 1–2).** The entire §10 plan targets #323/#324 seams absent on this pre-rebase branch; running it now yields false reds (missing machinery, not test-first red). Do not start the test phase against this branch — rebase onto current main first, then author/verify tests against the rebased tree.

5. **[QA-A2] Distinguish the two fail-first modes in the test-writer brief.** The five §10.2 contract-inversions are currently GREEN on the upstream branch and must be *flipped* to encode the new behavior (green→flip→green); the §10.3 new ACs are red→green (assert behavior that does not yet exist). The test-writer must not mistake an inverted-but-still-green assertion for a finished test.

6. **[QA-A3 / OD-B, conditional] If Jan selects OD-B Option 2 (index but default-exclude `wiki_source`), add a default-semantics regression test:** `semantic_search` with no `types` param returns results EXCLUDING `wiki_source` excerpts (today's default semantics preserved), while `types=["wiki_source"]` or a `source_type` filter retrieves them. No such AC exists in the current §10 plan.

7. **[Infra-A2] Migration reindex must isolate the state file.** The index state file is written non-atomically with no lock and has three concurrent writers (launchd cron, manual reindex, `WIKI_AUTO_REINDEX` default-true). For the one-time v2→v3 migration reindex, set `WIKI_AUTO_REINDEX=false` (or `launchctl unload` the reindex job) for the manual pass, then re-enable. Add this to §15 deployment steps.

8. **[Infra-A7] Add a post-deploy negative verification:** after the migration reindex, confirm `state.json` `_payload_schema_version == 3` AND that a second immediate `reindex` does NOT re-embed (proves the marker stamped and incremental behavior resumed). Catches a half-completed/clobbered-state migration.

9. **[CSO-A1] Document the source-excerpt redaction posture in §14.** Add a one-line note that indexed source excerpts are persisted to local Qdrant as-is — control-character sanitization only, no PII/secret redaction of prose — so the data-flow is explicit. (No code change; pre-existing local behavior #336 re-routes.)

## Items requiring Jan's ratification at the Decide gate (not implementation tasks)

- **OD-A (formal AC waiver):** the ticket's literal "backfill existing objects where derivable" is unachievable — the `domain_hint` is recoverable nowhere (verified discarded at `ingest.py:660`). Jan must explicitly supersede that AC with forward-only. The §12 AC set is already re-baselined to forward-only.
- **OD-B:** Option 1 (surface by default) / Option 2 (index, default-exclude — drives item 6 above) / Option 3 (defer — ships an inert filter, not recommended).
- **OD-C:** SET (recommended, lossy for multi-domain re-ingest) vs MERGE (follow-on).

## Rationale

Items 1–3 are integration realities the spec could not have known at authoring time (#323/#324 merged after the branch point) or that the technical reviewers missed (the `lint.py` third caller); honoring them prevents a broken rebase and a broken unrelated module. Items 4–6 ensure the test phase produces meaningful test-first reds against the correct tree and full AC coverage under whichever OD-B option Jan picks. Items 7–9 harden the migration and document the data posture per Infra and CSO. All are next-phase requirements that free-text comments are too easily missed to carry reliably — hence this addendum, which the next lead reads during Task Intake.
