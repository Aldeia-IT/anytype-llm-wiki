# Spec Addendum — post-impl council (R1)

**Source:** [`council-impl-r1.md`](council-impl-r1.md)
**Date:** 2026-06-13
**Target phase:** done / deploy / ship (post-merge operator actions + follow-on tickets)
**Status:** Authoritative — these are the deploy-time and ship-time obligations the merge of #336 carries. They supplement the prior [`spec-addendum-post-spec-r1.md`](spec-addendum-post-spec-r1.md) and [`spec-addendum-post-test-r1.md`](spec-addendum-post-test-r1.md), both of which remain in force.

The post-impl council unanimously signed off (0 BLOCKING, seven specialists). The engineering merit of the merge is not in question. These items are NOT test-gated and are therefore at risk of being dropped once the suite is green — hence this addendum.

## Deploy obligations (operator MUST execute at the v2→v3 migration)

1. **[Infra — hard precondition] Quiesce auto-reindex during the one-time v2→v3 manual reindex.** Before the manual pass: `launchctl unload` the reindex job AND export `WIKI_AUTO_REINDEX=false` for the migration shell (or pause worker sessions). Run the full unscoped `reindex` (no `space_id`). Then re-enable both. Rationale: three concurrent writers to `state.json` (launchd cron, manual reindex, default-true auto-reindex). #342's atomic write + non-blocking `flock` prevent a *torn* state file but do NOT prevent a scoped auto-reindex grabbing the lock first and causing the manual full pass to skip-via-`LOCK_NB`, leaving the migration half-done and the global marker un-advanced.

2. **[Infra — hard precondition] Post-deploy negative verification.** After the migration reindex: confirm `state.json` shows `_payload_schema_version == 3`, then run `reindex` once more and confirm the re-embed count is **0** (only skips). A non-zero second-pass re-embed means the first pass did not complete — investigate before declaring the migration done. The existing §15 positive checks pass even on a half-completed migration; this negative check is the only proof the marker stamped and incremental behavior resumed.

3. **[Infra/QA — durable-docs gap to close] Promote items 1 and 2 from this addendum into spec §15 and `CHANGELOG.md`.** They are currently durable only in the spec addenda. §15/CHANGELOG document the migration in substance but omit these two specific failure-preventing steps. Cheap one-line-each fix; do it as part of the merge or the deploy runbook so the operator cannot miss them.

## Ship obligations (must reach Jan/operators)

4. **[CPO/Client Advocate] The OD-A forward-only expectation must reach the operator via the PR body, not only the CHANGELOG.** The entire pre-#336 corpus returns empty for any `domain_tags` filter until re-touched — a foreseeable "is it broken?" support moment. The PR body should state this verbatim.

5. **[CPO/Client Advocate] File the manual bulk re-tag follow-on as a real ticket with an owner.** Until a meaningful fraction of the corpus is re-tagged, `domain_tags` filtering delivers thin value on historical knowledge. Track it so the capability lands rather than waiting on incidental re-touches. Announce the feature as "forward-only; bulk re-tag is the follow-on," not "domain filtering is now available."

## Follow-on items (next touch / separate tickets — not merge blockers)

6. **[CSO] Route the ingest document excerpt through `scrub_credentials`** for symmetry with the remember path (`ingest.py:1019` currently control-char-sanitizes only; `remember.py:296` scrubs). Add the explicit "indexed document excerpts are persisted to local Qdrant with control-char sanitization only — no secret/PII redaction of document prose; acceptable under the local-first single-tenant trust model" sentence to spec §14.

7. **[CTO/QA] Correct the stale spec §9 prose** to match the implemented (binding) `source_type` no-op on `wiki_query`, so a future reader does not "fix" the code to match the wrong prose.

8. **[Client Advocate] Pin AC-V-WARN** — flip the `xfail(strict=False)` test to a normal passing assertion so the now-enabled out-of-taxonomy warning can't silently regress. Add the untagged-legacy caveat to the `domain_tags` tool docstring (the agent's moment of confusion, distinct from the CHANGELOG which reaches the human).

9. **[CTO] Document the neighbour-fan-out filter semantics** — `wiki_query`'s `domain_tags` scopes seed selection, not the #324 1-hop neighbourhood (consistent inherited #323/#324 behavior). One-line docstring/CHANGELOG note.

10. **[QA] Restore `ruff` in the venv** so the next phase's lint gate is enforceable.

## Rationale

Items 1–3 are the central operational risk of this ticket and are not test-gated — exactly the class of obligation free-text comments carry unreliably. Items 4–5 ensure the ratified forward-only tradeoff is communicated and its value is scheduled to land. Items 6–10 are follow-on polish surfaced by the council that do not gate the merge but should not be lost. The deploy lead / operator reads this addendum (and the handoff comment) at merge/deploy time.
