# Council Meeting — Post-spec (Round 1)

**Date:** 2026-06-13
**Ticket:** Aldeia-IT/aldeia-box#336 — wiki: persist domain_tags + index sources, then enable source_type/domain_tags filters (#323 follow-up)
**Phase reviewed:** spec
**Client:** anytype-llm-wiki (internal Aldeia fleet tool; local-first, single-user)

## Attendance

| Role | Present | Reason |
|------|---------|--------|
| Council Chair | Yes | moderator |
| Chief Security Officer | Yes | minimum; data-handling change (source excerpts → Qdrant), new filter input boundary |
| Chief Product Officer | Yes | minimum; OD-B is a user-facing product decision |
| Chief Technology Officer | Yes | minimum; spec written as deltas to another branch's seams — accuracy + reviewer diligence |
| QA Director | Yes | chair decision; heavy test plan, cross-ticket test handshake (5 inverted assertions), forced re-embed regression |
| Infrastructure Lead | Yes | chair decision; corpus-wide migration, payload indexes, deployment-ordering / unlocked-reindex risk |
| Legal Counsel | No | near-zero legal surface — local-first, no new external egress, no new data store or PII category, no licensing change |
| Client Advocate | No | internal fleet tool, not a client engagement; CPO covers Jan-as-sole-user product value |

## Context Presented

The spec closes the two write-side gaps #323 deferred and exposes the `source_type` + `domain_tags` retrieval filters end to end: persist `wiki_domain_tags` (multi_select) in ingest + remember; fix a **confirmed** validate-then-discard bug (`wiki_remember` drops `domain_tags` before it reaches `meta`/the worklog); index `wiki_excerpt` so body-less `wiki_source` objects chunk and reach Qdrant; add `source_type`/`domain_tags` to the chunk payload + two KEYWORD payload indexes; bump `PAYLOAD_SCHEMA_VERSION` 2→3 (forced one-time re-embed, reusing #323's proven migration); add `MatchAny` filter clauses + Tier-1 predicates + MCP-boundary validation.

The spec reached status **SPEC / APPROVED** after R1 (NEEDS REVISION: 1 BLOCKING + 11 SHOULD-FIX) → fix → R2 (APPROVED), across three independent technical reviewers plus a lead-run **live Anytype prerequisite verification** of the multi_select/select GET+write shapes. It deliberately leaves three Open Decisions to Jan (OD-A forward-only backfill; OD-B source-excerpt surfacing default; OD-C SET vs MERGE) and states a hard upstream dependency on #323.

## Discussion

Five specialists reviewed in parallel and cross-flagged. The cross-cutting threads:

- **CTO + Infrastructure independently discovered the spec's central premise is now stale.** Both verified against `origin/main` that **#323 is already merged** (commit `6281f5e`, PR #47 — `PAYLOAD_SCHEMA_VERSION` and `_chunk_to_payload` present on main). The chair re-verified directly: #323 merged, the 336 branch was cut from `aa7fc00` (before the merge — which is why this worktree lacks the machinery, not because #323 is unmerged). The "CANNOT be implemented before #323 merges" framing is no longer the live risk; the live action is a mechanical rebase onto current main.
- **CTO surfaced a NEW upstream the spec is blind to: #324** (relationship-aware retrieval, `6aa320a`, PR #46), also now on main, touching the exact files #336 edits (`query.py`, `indexer.py`, `server.py`, `chunker.py`, `test_chunker.py`, `test_indexer.py`, `test_query.py`). The rebase conflict surface is real; §11 line anchors must be re-verified against post-#324 code. Infra and QA concurred this is an Implement/test-phase precondition, not a re-spec.
- **CTO found an integration trap the reviewers missed (A2):** `_resolve_select_tag` has a **third caller** — `lint.py:33 from .remember import _resolve_select_tag` (chair-verified) — that D1's "move/colocate to ingest.py" would break unless a re-export shim is left in `remember.py`. Flagged to QA for an import-regression test.
- **QA verified the cross-ticket test handshake is exact** — all five inverted assertions confirmed at the cited lines on the #323 branch — but flagged that the entire §10 test plan is unrunnable until the rebase, so the **test phase must be gated on the rebase**, and that **OD-B Option 2 would add a default-semantics regression test** with no current AC. QA also noted OD-A makes the ticket's literal "backfill where derivable" AC a **formal waiver** requiring Jan's explicit sign-off.
- **CPO confirmed all three Open Decisions are framed neutrally and completely**, that the OD-A forward-only coverage gap is surfaced honestly (stated three times, labelled "material gap, not a footnote"), and pushed on user value: `domain_tags` filtering is *technically live but practically empty* until the corpus is re-touched, while `source_type` becomes useful immediately after re-embed — asymmetric time-to-value the spec makes visible. CPO flagged the OD-A↔OD-C interaction (SET semantics overwrite multi-domain tags on re-ingest-based backfill).
- **CSO confirmed the no-new-egress / local-first claim is coherent and verified**, no injection surface in the Qdrant `MatchAny` path, trust boundaries respected, failure modes degrade fail-closed on retrieval scope. One data-handling advisory: source excerpts reach Qdrant without secret-scrubbing of prose (pre-existing behavior #336 merely re-routes locally; accepted risk).
- **Infrastructure confirmed the migration is safe and idempotent**, rollback clean and honestly characterized, resource impact correctly bounded (~seconds re-embed on ~500 chunks, sub-second index creation, one extra local API call pair per run). Refined the concurrency hazard: three concurrent state-file writers exist (cron + manual + `WIKI_AUTO_REINDEX` default-true), state file written non-atomically with no lock — self-healing via idempotency, but the migration reindex should set `WIKI_AUTO_REINDEX=false` / pause the launchd job.

## Findings

### BLOCKING
None. All five specialists signed off.

### ADVISORY
1. **[CTO/Infra] Stale dependency premise — #323 is already merged to main** (`6281f5e`, chair-verified). The spec's "hard dependency / not yet merged" framing and §15 step 1 are obsolete. Live action: rebase onto **current main**, do not wait. De-risks the dependency.
2. **[CTO] #324 (relationship-aware retrieval, `6aa320a`) is on main and collides with #336's files.** The spec is blind to it. Before Implement, rebase onto current main and re-anchor §11 against post-#324 code — particularly `query.py` Tier-1 dispatch and `semantic_search_core`, where #324's neighbour-fan-out now coexists with #323's filter build. Spec-anchoring refresh, not a re-spec.
3. **[CTO] `_resolve_select_tag` has a third caller (`lint.py:33`) unaddressed by spec/reviews.** D1's "move to ingest.py" would break `lint.py`'s import unless the symbol is re-exported from `remember.py`. Define in `ingest.py`, re-export from `remember.py`; keep all three call sites green. Add an import-regression test.
4. **[QA] The test phase must be gated on the rebase.** The entire §10 plan targets #323 seams absent on this branch; running it pre-rebase yields false reds. Distinguish §10.2 contract-inversions (flip the assertion) from §10.3 new red tests (assert intended behavior) in the test-writer brief.
5. **[QA/CPO] OD-A is a formal AC waiver.** The ticket's literal "backfill existing objects where derivable" is unachievable (the `domain_hint` is recoverable nowhere — chair/CTO verified discarded at `ingest.py:660`). Jan must explicitly supersede that AC at Decide; the spec's §12 AC set is correctly re-baselined to forward-only.
6. **[QA] OD-B decision changes test scope.** Option 2 (index-but-default-exclude `wiki_source`) adds a `semantic_search` default-types guard with no current AC test — a "default results unchanged" regression test must be added if Jan picks it.
7. **[CPO] The three Open Decisions interact and should be weighed as a set, not isolated toggles** — notably OD-A acceptance is more palatable paired with a backfill pass, on which OD-C's SET losiness then compounds. Recommend the Decide summary set the time-to-value expectation plainly (domain_tags filter delivers little until backfill/organic re-tagging).
8. **[Infra] Migration reindex should set `WIKI_AUTO_REINDEX=false` / pause launchd** for the one manual pass — closes the auto-reindex leg the spec's "manual vs cron" wording misses. Worst case absent this is a benign extra idempotent re-embed. Add a post-deploy negative check (a second immediate reindex does NOT re-embed).
9. **[CSO] Source excerpts persist to local Qdrant without secret-scrubbing of prose.** Pre-existing behavior #336 re-routes locally; accepted risk for a single-user local tool. Recommend a one-line §14 note documenting that excerpts are stored as-is (control-char sanitization only, no PII/secret redaction).

## Resolutions

- The spec's "#323 unmerged" hard-dependency, treated by the spec author as a live gate, was **resolved by the council as already-satisfied** — the gate is met; the residual is a mechanical rebase. This downgrades the dependency from "blocks Implement until an external merge" to "a routine rebase precondition," and simultaneously **raises** the #324 collision (Finding 2) as the actual rebase risk to manage.
- CSO routed its excerpt-redaction policy question to CPO; CPO accepted it as a product/data-classification call, non-gating for a single-user local tool.
- No specialist's finding was withdrawn; none was downgraded. All nine advisories are carried forward (the actionable next-phase ones into the spec addendum).

## Recommendation

**Recommended target:** decide
**Confidence:** high
**Rationale:** The spec is technically sound, faithful to the verified codebase, and the two review rounds were genuinely rigorous (CTO spot-checked every cited seam against `git show`; reviewer diligence affirmed). Zero BLOCKING findings — the council unanimously signs off on the spec's quality. It nonetheless routes to **Decide, not directly to test**, because three genuine product decisions require Jan and cannot be made by the pipeline: **OD-A is a formal waiver** of the ticket's literal backfill AC, **OD-B materially changes the test scope** (and default `semantic_search` semantics for existing agent callers), and **OD-C** sets lossy update semantics. Jan must also be told the dependency landscape shifted: #323 is merged (gate cleared) and #324 now sits in the rebase path. The actionable next-phase items (rebase onto current main incl. #324, the `lint.py` re-export fix, the OD-B-contingent regression test, the migration `WIKI_AUTO_REINDEX` step, the §14 redaction note) are captured in `spec-addendum-post-spec-r1.md` so the test/Implement lead honors them.
**Dissent:** None.
