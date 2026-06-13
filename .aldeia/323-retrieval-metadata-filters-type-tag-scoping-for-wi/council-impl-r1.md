# Council Meeting — Post-impl (Round 1)

**Date:** 2026-06-13
**Ticket:** #323 — Retrieval metadata filters: type + date scoping for `wiki_query` / `semantic_search`
**Phase reviewed:** impl
**Client:** anytype-llm-wiki (Aldeia-IT/anytype-llm-wiki)
**Gate:** final delivery gate (PR / pre-merge)

## Attendance

| Role | Present | Reason |
|------|---------|--------|
| Council Chair | Yes | moderator |
| Chief Security Officer | Yes | minimum; trust-boundary input validation + the only state-mutating op (forced re-embed) |
| Legal Counsel | Yes | minimum; OSS licensing + public-doc claims + privacy surface of date filtering |
| Chief Product Officer | Yes | minimum; owns the CPO-1 Decide-gate finding (product.md overclaim) + de-scope integrity |
| QA Director | Yes | minimum; final test-suite verification + addendum exit-criteria coverage |
| Chief Technology Officer | Yes | minimum; C1 fix correctness, migration design, rebase integrity, reviewer diligence |
| Infrastructure Lead | Yes | forced one-time re-embed migration is the highest operational risk; infra/agent-ops domain |
| Client Advocate | Yes | final gate — dual-purpose OSS + internal tool; user-expectation + upgrade-burden lens |

Full council convened — per the post-impl policy of aiming for full attendance at the last gate before release.

## Context Presented

The impl phase delivered optional **type + date** metadata filters for the two retrieval tools,
exactly per the ratified spec (Jan's Decide adjudication: **OD-1 ACCEPTED** — ship date filtering via
an additive `last_modified_date` payload field + a forced one-time re-embed migration; **OD-2 ACCEPTED
as de-scope** — `source_type`/`domain_tags` deferred in full to follow-up **#336**).

Delivered diff (true #323 scope, `git diff origin/main...HEAD`): 5 src + 3 test files (~1122 lines):
`chunker.py` (inject `last_modified_date`), `config.py` (`PAYLOAD_SCHEMA_VERSION = 2`), `indexer.py`
(shared `_chunk_to_payload`, `_ensure_payload_indexes`, `DatetimeRange` filter, forced-backfill marker),
`server.py` + `wiki/query.py` (date/type params, ISO-8601 validation, Tier-1 predicates), plus docs
(product.md reconciliation, CHANGELOG release note, README params + Roadmap, technical.md). In-phase impl
review: **R1 NEEDS CHANGES** (1 CRITICAL data-integrity finding, C1) → fixed → **R2 APPROVED**. Full suite
**661 passed, 0 failed** (post-rebase onto the already-merged #324).

> **Diff-reading note for the record:** local `main` is stale (lacks the merged #324), so
> `git diff main...HEAD` is inflated and shows #324's code/work-folder. The authoritative #323 diff is
> `git diff origin/main...HEAD`. The branch is a clean descendant of `origin/main`. All members were
> briefed on this and reviewed the correct diff; CTO independently confirmed the rebase integrity
> (`git merge-base --is-ancestor 6aa320a origin/main`).

## Discussion

All seven members reviewed the correct (`origin/main`-relative) diff and converged on sign-off
independently. The verification was substantive, not a rubber-stamp:

- **QA ↔ CTO** both ran the test suite. QA: `.venv/bin/python -m pytest -q` → **661 passed, 37 skipped,
  2 xfailed**, matching the impl claim exactly (the R1/R2 640/641 counts predate the #324 rebase; +20 is
  #324's tests). CTO ran the three #323 test modules → **121 passed, 11 skipped**. Both confirmed the
  mandated addendum exit criteria ship as **genuinely-runnable, non-vacuous** tests: AC-F1b
  (`test_wiki_query_default_passes_full_type_keys`) and AC-F10b
  (`test_wiki_query_mixed_types_silently_narrowed`) drive `wiki_query` through the real Tier-2 path; the
  CSO-5 cross-tier date-equivalence test asserts Tier-1 `_passes_date_filter` ↔ Tier-2 `DatetimeRange`
  agree on inclusive-edge + timezone normalization; the C1 regression
  (`test_scoped_reindex_does_not_stamp_schema_marker`) asserts a scoped reindex backfills its space but
  does NOT advance the global marker.
- **CTO ↔ Infra** independently traced the **C1 fix** in `indexer.py`: `force_full` is computed from the
  stored schema version independent of `space_id`, the unchanged-skip bypass uses `force_full`, and the
  global `_payload_schema_version` marker stamp is gated `if space_id is None`. Verdict: a scoped reindex
  (auto-fired after every `wiki_ingest`/`wiki_remember` under default `WIKI_AUTO_REINDEX=true`) still
  re-embeds its own space but cannot prematurely advance the marker and strand other spaces on the old
  6-field payload. Correct and complete. CTO judged the in-phase review diligent: it cited exact lines,
  traced the auto-reindex call chain, re-ran the suite at three checkpoints, and correctly identified C1
  as a latent flaw in the spec's own §3 D3 pseudocode — a catch *beyond* the literal spec.
- **Infra** confirmed migration self-healing + interrupt-safety at the persistence boundary (`_save_state`
  called once after the space loop; marker never persists on an aborted run → next reindex re-attempts;
  re-upsert is idempotent). Payload indexes are created on the reindex path only, never the
  `reembed_object` hot path (AC-F7). Resource cost trivial (~500 chunks). Infra surfaced two **new**
  operational-durability advisories (below) — both pre-existing conditions the migration now leans on, not
  regressions introduced by #323.
- **CPO** verified the Decide-gate findings landed: `.aldeia/context/product.md:15` is reconciled
  ("Filter by space and object type, with date-range filtering; tag/source filtering planned (see #336)")
  — the "tags" overclaim is gone; **#336 exists** (OPEN, client anytype-llm-wiki, P1, epic #140) and
  faithfully inherits the full tag/source intent with ACs forbidding inert filters; CHANGELOG/README are
  documentation-honest. Zero `source_type`/`domain_tags` leakage in the src diff — the MCP surface adds
  only `types`, `ingested_after`, `ingested_before`.
- **CSO** confirmed input validation short-circuits before client construction (`wiki_query` →
  `config_error`; `semantic_search` raises `ValueError`); malformed dates rejected, not ignored; no new
  egress, no unsafe interpolation, local-first posture preserved; `_chunk_to_payload` writes only the 6
  base fields + optional `last_modified_date`.
- **Legal** found no legal surface: no new PII/retention/cross-border flow (date derived from existing
  object metadata, evaluated in the local Qdrant container), no new third-party dependency
  (`pyproject`/`.env.example` unchanged; new code uses only stdlib `datetime` + bundled `qdrant_client`),
  public docs *narrowed* claims to match reality (no overpromise). Praised the pipeline for catching the
  inert-filter footgun at spec stage rather than shipping silent no-ops.
- **Client Advocate** judged type+date a coherent, self-contained capability (not a confusing
  half-feature), docs honest for the OSS audience, backward-compatible (all params optional, no-filter
  path byte-identical), and the forced re-embed painless (auto-triggered, seconds-scale) for a
  self-hoster.

## Findings

### BLOCKING
None.

### ADVISORY

1. **[Infra-A1] State-file write is non-atomic (`_save_state` → `write_text`).** A crash/power-loss
   *during* the single terminal state write could truncate/corrupt `state.json` and block all future
   reindexes (`json.loads` raises on next load). Likelihood low; pre-existing condition the migration now
   leans on. **Recommend a follow-up:** atomic temp-file + `os.replace`. → tracked in operational-hardening
   follow-up (see Resolutions).

2. **[Infra-A2] Sample reindex cron has `RunAtLoad` + 1800s interval and no overlap guard.** During the
   one-time migration window, an operator reloading the cron mid-migration or running a manual reindex can
   race the single `_save_state` write (compounds A1). Mitigation already documented (spec §15
   sequencing). **Operationally safer option:** let the cron perform the migration; run no concurrent
   manual reindex. → same follow-up.

3. **[CSO-A1 / CTO-A2 / QA-2 — merged] Date-grammar divergence between MCP-boundary probe and Tier-1
   parser.** `DatetimeRange(gte=...)` (pydantic) vs `_parse_iso` (`datetime.fromisoformat`) accept slightly
   different *exotic* inputs (e.g. bare `"2026"`); both no-op safely and agree on full ISO-8601 (the
   documented usage). Spec §9.1 deliberately pins the probe. No injection/exposure path (structured Qdrant
   conditions, never string interpolation). Documented risk, accepted.

4. **[CTO-A1 / QA — merged] Date-validation block duplicated in `server.py` + `wiki/query.py`** with
   divergent error contracts (raise vs error-dict). Justified for now; centralizing at
   `semantic_search_core` is correctly tracked as a **#336** item (CSO-6 longer-term). Accepted.

5. **[Legal-A1 / Client-A1 — merged] `ingested_after`/`ingested_before` param names vs the underlying
   `last_modified_date` field.** Minor user-expectation/doc-accuracy nuance; docstrings are honest. Spec
   §D2 chose `last_modified_date` deliberately for universal coverage (sound trade-off). Consider a
   one-line README clarification in a follow-up. Not blocking.

6. **[QA-1] No dedicated CI-runnable assertion for a `space_id`-only filter `must`-clause.** Covered only
   indirectly (live-gated `test_reindex_specific_space` is CI-skipped; rest is regression-by-green-suite).
   Logic unchanged from pre-existing code → low risk. Fold a one-line assertion into a future touch.

7. **[Client-A3] README Roadmap / CHANGELOG cite internal ticket numbers (#327, #336)** an OSS reader
   cannot see. Pre-existing repo convention; sets correct directional expectations. Long-term, describe
   deferred features in prose or use publicly-visible references. Not blocking.

## Resolutions

- The one finding that could have been BLOCKING — the C1 scoped-reindex marker-stamp data-integrity bug —
  was caught by the in-phase review, fixed (`space_id is None` gate), regression-guarded, and independently
  re-confirmed fixed by CTO and Infra during this meeting. Cleared.
- No member withdrew a finding under discussion; all seven arrived at sign-off independently and converged.
  **No dissent, no contradictions.**
- Infra-A1 and Infra-A2 are genuinely new operational-durability observations, but they are **pre-existing
  conditions** surfaced (not introduced) by #323 and are low-probability on this corpus. They do not block
  delivery. The chair will record them in a single operational-hardening follow-up ticket so "surfaced"
  does not become "dropped."
- All carried-forward addendum exit criteria (post-spec R1: Infra-7/9, CSO-6, CTO-10; post-test R1: CPO-1,
  CTO-ADV1, CPO-traceability, QA-A1/A2) were verified shipped by the owning specialists.

## Publish precondition (operational — MUST happen before the PR is built)

**The local rebased branch is not yet on the remote.** Local HEAD `a6e35b0` is a clean descendant of
`origin/main` (correctly rebased onto the merged #324); the remote feature branch is still at the
pre-rebase `d058fc3`. The impl worker and this council session were both **denied `git push
--force-with-lease` at the permission layer**, and the impl phase's intended `abs-pr-ready.md` signal was
**not actually written** (confirmed absent). The chair has written `abs-pr-ready.md` to close that gap.

**Required action by the watcher / Jan before / at PR creation:**
```
git -C <worktree> push --force-with-lease origin aldeia/323-retrieval-metadata-filters-type-tag-scoping-for-wi
```
Without this, the PR would be built from un-rebased history that conflicts with `main`. `--force-with-lease`
is safe here — remote is confirmed at `d058fc3` (the expected lease base). This is a publish-mechanics gate,
not a code or quality defect, and it does not affect any member's sign-off.

## Recommendation

**Recommended target:** `done` (approve PR / proceed to merge)
**Confidence:** high
**Rationale:** Unanimous full-council sign-off, zero BLOCKING findings. The delivered diff is a faithful,
well-engineered realization of the ratified spec; the one CRITICAL (a real spec-pseudocode gap) was caught,
correctly fixed, and regression-guarded; the test suite is green and independently re-verified by two
members; the migration is self-healing, interrupt-safe, and rollback-trivial; de-scoped filters are cleanly
absent with #336 tracking the deferral; and the public claims are documentation-honest. The seven advisory
items are accepted risks or low-priority follow-ups, none gating. **One operational precondition must be
satisfied before merge:** force-push the rebased local branch (see Publish precondition).
**Dissent:** None.
