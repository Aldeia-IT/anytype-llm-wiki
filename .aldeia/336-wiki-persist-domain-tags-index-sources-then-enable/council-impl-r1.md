# Council Meeting — Post-impl (Round 1)

**Date:** 2026-06-13
**Ticket:** aldeia-box#336 — wiki: persist domain_tags + index sources + enable filters
**Phase reviewed:** impl (final delivery gate)
**Client:** anytype-llm-wiki (the agent fleet's own shared wiki memory tool)

## Attendance

| Role | Present | Reason |
|------|---------|--------|
| Council Chair | Yes | moderator |
| Chief Security Officer | Yes | minimum; data-handling change (excerpts now reach Qdrant) |
| Legal Counsel | Yes | minimum; confirm no new data-flow/licensing exposure |
| Chief Product Officer | Yes | minimum; verify scope discipline + forward-only UX |
| QA Director | Yes | minimum; AC coverage, regression risk, suite-green verification |
| Chief Technology Officer | Yes | minimum; technical accuracy + reviewer diligence on final gate |
| Infrastructure Lead | Yes | chair decision — v2→v3 payload-schema migration is the central operational risk |
| Client Advocate | Yes | chair decision — non-aldeia-box fleet tool; represents agents/operators as users |

Full attendance: this is the final delivery gate before merge, and the migration carries the highest operational risk of the ticket.

## Context Presented

The impl phase turned 33 test-first reds green with zero regressions, implementing spec §11 steps 1–8: persist `wiki_domain_tags` + `wiki_source_type` on Anytype objects; index source-document excerpts into Qdrant (OD-B Option 2: indexed but default-excluded from `semantic_search` unless explicitly requested); add `source_type`/`domain_tags` MatchAny filters to `semantic_search` + `wiki_query`; bump payload schema v2→v3. Three in-phase review lenses (security+correctness, DRY+simplification, spec-compliance+performance) returned CLEAN; two MINOR test-only findings were fixed inline by the impl lead.

All three ratified Decide decisions were in scope to honor: **OD-A** (forward-only tagging — no retroactive backfill), **OD-B Option 2** (index excerpts but default-exclude `wiki_source` from `semantic_search`), **OD-C** (SET/replace semantics on `wiki_domain_tags` update).

Final suite (independently reproduced by QA and CTO): **698 passed, 29 skipped, 8 deselected, 2 xfailed, 1 xpassed (AC-V-WARN), 0 failures** (baseline 33 failed / 664 passed).

## Discussion

The seven specialists reviewed in parallel and converged on sign-off. Cross-cutting threads:

- **CTO resolved the three-dot-diff red herring.** The spec-compliance reviewer had flagged that `git diff main...HEAD` includes #342's `_reindex_lock`/atomic-write hunks. CTO verified the branch is correctly rebased onto `origin/main` (`676bd1c`, which already merged #323 PR#47, #324 PR#46, and #342 PR#48); against the real merge target `origin/main...HEAD` the indexer delta is 24 lines with **zero** #342 lock code. The local `main` ref is stale at `6281f5e`. **No double-merge risk.** This is the kind of integration check a final gate exists to perform.
- **QA independently re-ran the suite twice** (698 passed / 0 failures, exact match to the debrief) and confirmed the AC-V-WARN XPASS is a genuine non-strict coverage gain (no `xfail_strict` config exists, so an XPASS cannot flip the suite red), with the mandatory AC-V-ZERO invariant asserted independently.
- **CTO + QA + spec-compliance all confirmed the §9-vs-AC-T1-ST-NOOP conflict resolution.** The spec §9 prose says apply/thread `source_type` in `wiki_query`, but D10/§6.2/AC-T1-ST-NOOP make it a permanent no-op (applying it would zero all entity/concept results, which lack `wiki_source_type`). The worker implemented both predicates but does NOT apply/thread `source_type` in `wiki_query` — consistent across both tiers; `domain_tags` IS applied in both. Unanimously judged the only defensible reading. Spec §9 prose remains stale and should be corrected on a future touch.
- **CTO confirmed his prior spec-council integration flags are honored:** the `lint.py:33` third caller of `_resolve_select_tag` still resolves (live import check passed) via the re-export from `remember.py`; the #324 neighbour fan-out coexists cleanly with the #336 filter must-list.
- **CSO accepted the data posture (CSO-A1) but surfaced an asymmetry:** ingested document excerpts (`ingest.py:1019`) are persisted to local Qdrant with control-char sanitization only — NOT routed through `scrub_credentials` (unlike the remember-path note at `remember.py:296`). Because #336 is what puts `wiki_excerpt` on the chunking allowlist, this is a newly-material (low-risk, local-first single-tenant) exposure. Accepted; recommended a follow-on to route the ingest excerpt through `scrub_credentials` for symmetry.
- **Legal confirmed no material exposure:** `git diff main...HEAD -- pyproject.toml uv.lock` is empty (no new dependencies/licenses); local-only store of the fleet's own knowledge; no data-subject processing; forward-only carries zero regulatory weight.
- **Infra (domain owner for the migration) found the two most failure-preventing migration steps are NOT in durable operator-facing docs.** §15/CHANGELOG document the migration in substance but omit the explicit `WIKI_AUTO_REINDEX=false` quiesce step and the negative re-embed verification — those specifics live only in the spec addenda. #342's atomic write + flock guard prevent a *torn* state file but do NOT prevent a scoped auto-reindex grabbing the lock and causing the manual full pass to skip-via-`LOCK_NB`, leaving the migration half-done. Infra rated this ADVISORY-with-hard-precondition (not BLOCKING), supplied the exact operator checklist, and recommended folding the two lines into §15/CHANGELOG as cheap belt-and-suspenders.
- **CPO + Client Advocate converged on the forward-only footgun.** OD-A is the right call (the `domain_hint` is recoverable nowhere). Mitigations (AC-V-WARN warning now enabled; CHANGELOG/§15 disclosure) soften but don't close it: the legacy corpus returns empty for `domain_tags` filters until re-touched. Client Advocate's sharpest point: the disclosure reaches the *human* (CHANGELOG) but not the *agent at call time* (the tool docstring only mentions unknown values, not untagged-legacy objects). Both recommend tracking the manual bulk re-tag as a real follow-on ticket so the feature's value actually lands.

## Findings

### BLOCKING
None. All seven specialists signed off.

### ADVISORY

1. **[Infra/QA/CTO/Client Advocate — DEPLOY, must not be dropped] Fold the two migration steps into durable docs + execute them.** The one-time v2→v3 reindex MUST run with `WIKI_AUTO_REINDEX=false` (and the launchd reindex job unloaded) during the manual pass, then re-enable; followed by negative verification (`state.json _payload_schema_version == 3` AND a second immediate `reindex` re-embeds nothing). These specifics are currently durable only in the spec addenda — promote them into §15/CHANGELOG so the operator cannot miss them. Captured authoritatively in `spec-addendum-post-impl-r1.md`.

2. **[CPO/Client Advocate — SHIP] Ensure the OD-A forward-only expectation reaches Jan/operators, and track the bulk re-tag follow-on.** The PR body (not just the CHANGELOG) should carry the forward-only expectation. File the manual bulk re-tag as a real ticket with an owner so `domain_tags` filtering delivers value on the legacy corpus rather than waiting on incidental re-touches.

3. **[CSO — FOLLOW-ON] Route the ingest document excerpt through `scrub_credentials`.** `ingest.py:1019` applies control-char sanitization only; the remember path (`remember.py:296`) scrubs credentials. One-line symmetry fix; low risk under the local-first single-tenant trust model. Also add the explicit "no secret/PII redaction of document prose" sentence to spec §14.

4. **[CTO/QA — FUTURE TOUCH] Correct the stale spec §9 prose** to match the implemented (and binding) `source_type` no-op on `wiki_query`, so a future reader does not "fix" the code to match the wrong prose.

5. **[Client Advocate — FOLLOW-ON] Pin AC-V-WARN.** It currently passes as an XPASS on an `xfail(strict=False)` test; flip to a normal passing assertion so the enabled behavior can't silently regress. Also add the untagged-legacy caveat to the `domain_tags` tool docstring (the agent's moment of confusion).

6. **[CTO — DOC, defer] Document the neighbour-fan-out filter semantics.** `wiki_query`'s `domain_tags` scopes seed selection, not the #324 1-hop neighbourhood — a neighbour can enter context without a matching tag (consistent inherited #323/#324 behavior, not a regression). One-line docstring/CHANGELOG note.

7. **[QA — TOOLING] Restore `ruff` in the venv** so the next phase's lint gate is enforceable (the worker leaned on the suite + import-regression tests).

## Resolutions

- The two in-phase MINOR findings (stale `test_..._eight_keys` rename; missing OD-B "source_type-suppresses-default-exclude" regression test) were confirmed fixed inline by the impl lead (commit 2418f78) and independently re-verified by QA (`test_wiki_property_heading_maps_all_nine_keys`, `test_semantic_search_source_type_filter_suppresses_default_exclude` both present and green).
- The spec-compliance reviewer's three-dot-diff #342 caveat was confirmed correct by CTO and shown to be a stale-local-`main` artifact, not a real contamination — no action needed on the diff scope.
- No specialist downgraded another's concern; no finding was withdrawn. All advisories are deploy/ship/follow-on items, none gate the engineering merit of the merge.

## Recommendation

**Recommended target:** done (approve PR / merge)
**Confidence:** high
**Rationale:** The implementation is spec-faithful, all three ratified Decide decisions (OD-A/B/C) are honored exactly, the suite is genuinely green (698 passed / 0 failures, independently reproduced), the #323 data-integrity invariant is intact, and reviewer diligence was genuine (file:line citations verified, three-dot-diff red herring correctly resolved). Zero BLOCKING findings from any of seven specialists. The advisories are deploy-time operator obligations, ship-communication, and follow-on polish — none impugn the code. The deploy obligations are carried authoritatively in `spec-addendum-post-impl-r1.md` and the handoff comment so they reach Jan at merge/deploy.
**Dissent:** None.
