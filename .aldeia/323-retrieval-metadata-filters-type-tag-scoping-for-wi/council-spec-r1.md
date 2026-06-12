# Council Meeting — Post-spec (Round 1)

**Date:** 2026-06-12
**Ticket:** aldeia-box#323 — Retrieval: metadata filters + type/tag scoping for `wiki_query` / `semantic_search`
**Phase reviewed:** spec
**Client:** anytype-llm-wiki (internal — fleet wiki-memory tool; domains: infrastructure, agent-operations)
**Epic:** aldeia-box#140

## Attendance

| Role | Present | Reason |
|------|---------|--------|
| Council Chair | Yes | moderator / verdict synthesis |
| Chief Security Officer | Yes | minimum roster |
| Chief Product Officer | Yes | minimum roster |
| Chief Technology Officer | Yes | minimum roster |
| Infrastructure Lead | Yes | chair decision — forced re-embed migration + payload-schema change = real ops/deployment risk |
| Legal Counsel | No | not needed — local-first, no egress, no PII, internal tool, no licensing change |
| QA Director | No | not in minimum; a full in-phase QA review (`review-r1-qa.md`) already ran |
| Client Advocate | No | not a client project (internal infra) |

## Context Presented

The ticket asked to expose metadata filters (type, date, source_type, domain_tags) on two
retrieval MCP tools, premised on the belief that Qdrant already stores all four in the chunk
payload. Spec-phase investigation (lead + research + 3-specialist R1 review, cross-verified
against source) found the premise is **factually wrong**: the chunk payload holds only 6 fields
(`object_id, space_id, object_name, type_key, heading, text`). Three of the four requested
dimensions are **not deliverable as a filter-only change**:

- **type** — largely already built; gap is exposing it on `wiki_query` + indexing/validation/tests.
- **date** — deliverable, but only via an additive `last_modified_date` payload field + a forced
  one-time re-embed migration (the incremental reindex would otherwise never backfill history).
- **source_type** — `wiki_source` objects are body-less, never chunked, never reach Qdrant → an
  inert filter that silently returns nothing. **Deferred.**
- **domain_tags** — `wiki_domain_tags` is never persisted onto objects (validate-only) → inert.
  **Deferred.**

The spec ships **type + date** in v1 and defers source_type + domain_tags to a single follow-up
(D6), surfacing two Open Decisions for Jan: **OD-1** (accept the date payload field + forced
re-embed) and **OD-2** (accept the de-scope + create the follow-up ticket). Pipeline:
research → draft → R1 (NEEDS REVISION, 4 BLOCKING) → fix → R2 (APPROVED w/ conditions resolved
inline). The council reviewed `spec.md`, `spec-scope.md`, both review rounds, and the phase summary.

## Discussion

All four members independently verified load-bearing claims against source rather than taking the
spec's word.

- **CTO** spot-checked the four highest-stakes technical claims against the live codebase and the
  pinned qdrant-client 1.18.0: (a) the 6-field payload (`indexer.py:161-168, 218-225`); (b) the
  forced-backfill `_payload_schema_version` marker does **not** collide with space-id state keys
  (top-level key; space state read per-space via `state.get(sid,{})`; deletion loop iterates
  `space_state.keys()`); (c) `DatetimeRange` (not `Range`) coerces ISO-8601 and rejects bad dates;
  (d) the #289-trap is closed — `MatchAny` absent, nested-`should` shape, `FieldCondition` has no
  `.should` so the AC-F2 discriminator isolates the type group. **Judged the in-phase reviews
  genuinely diligent** (R1 cited specific source lines; R2 executed wire shapes against the real
  client and surfaced a *new* gap rather than rubber-stamping).
- **Infra Lead** verified the migration is fail-safe (version marker stamped only after the loop →
  interruption re-attempts; idempotent upserts on deterministic point IDs) and that the S4 hot-path
  concern is fully resolved (index creation moved to `_ensure_payload_indexes` on the `reindex`
  path only, locked by a negative test). Confirmed the "~seconds on ~500 chunks" claim is realistic
  (single Ollama call, 120s timeout). **Hunted the concurrency question** and found the state file
  has no atomic-write/locking and the launchd cron has no overlap guard — but classed it as a
  pre-existing weakness this ticket inherits, not introduces.
- **CSO** confirmed no new egress, no new auth surface, no PII; filter inputs reach Qdrant only as
  parameterized `MatchValue`/`DatetimeRange` (no injection vector); dates validated at the MCP
  boundary. Cross-referenced Infra's state-file finding as an integrity (not security) concern to
  avoid double-counting.
- **CPO** weighed the de-scope and judged it the **correct product call** (shipping an inert filter
  is the worse outcome), but flagged that `.aldeia/context/product.md` still advertises "tag"
  filtering as a capability, and that follow-up-ticket creation must be *guaranteed*, not merely
  recommended, so "deferred" cannot silently become "dropped."

## Findings

### BLOCKING
**None.** All four members signed off. The spec is approved and implementable; zero blocking
findings at the governance level.

### ADVISORY

1. **[CPO]** `product.md` still lists "Metadata filtering — Filter by space, object type, **tags**"
   as a capability the product will not have after v1. The §15 release note mentions only the
   date backfill, not that tag/source filtering remains unavailable. → Soften the capability line
   (or have the release note explicitly state tag/source filtering is not yet available + link the
   follow-up).
2. **[CPO]** The source_type + domain_tags deferral (OD-2) must be **gated on the follow-up ticket
   actually being created** — make follow-up creation a *condition* of accepting OD-2, inheriting
   #323's tag-scoping intent and linking the #140 epic. The two DEFERRED rows in spec §12 should be
   tied to that ticket's existence.
3. **[CPO]** Endorse the spec's recommendation to **not** take OD-2's "opt-in `wiki_excerpt`
   indexing now" path in v1 — it silently changes `semantic_search` retrieval semantics (source
   excerpts entering results) with no opt-out. If pursued in the follow-up it needs explicit
   product sign-off.
4. **[CTO / CSO]** **Tier-2 test harness must ship runnable.** R2's one SHOULD-FIX (AC-F1b /
   AC-F10b `...` placeholders) was resolved inline by the lead against real seams
   (`query_mod.config.index_threshold → 1`, `anytype_enum_fixture`, capture on
   `query_mod.indexer.semantic_search_core`, `synthesize` sentinel) — but the referenced
   `anytype_enum_fixture` was not found pre-existing in `tests/wiki/test_query.py`. The test phase
   MUST enforce AC-F1b ships as a genuinely runnable test (stand up the enumeration fixture if
   absent); it is the only guard against the §8.1 `effective_types` refactor silently regressing
   default-types behavior. This was R2's explicit approval condition — carry it to test/impl.
5. **[CSO]** Add one **cross-tier date-filter equivalence** assertion in the test phase (same
   object + same bounds → Tier-1 and Tier-2 agree at the inclusive edge). AC-F10 tests each
   predicate in isolation but not Tier-1↔Tier-2 equivalence; timezone-normalization and bound
   inclusivity are implemented by two independent code paths.
6. **[CSO]** (defense-in-depth) Date validation is enforced per-call-site, not at
   `semantic_search_core` (which by design does not validate). Not exploitable today; consider a
   follow-up to centralize validation at the core. Also add a one-line §14 cross-reference to the
   D3/§15 migration data-integrity analysis (the one state-mutating operation, currently only
   covered in §15).
7. **[Infra]** **State file has no atomic write / no lock; launchd cron has no overlap guard**
   (`StartInterval 1800` + `RunAtLoad=true`, no `ThrottleInterval`). A manual post-upgrade
   `reindex` can overlap a cron-fired one. Worst realistic outcome is one redundant forced
   re-embed or a lost `_payload_schema_version` stamp → one extra reindex (self-healing, no Qdrant
   corruption — upserts are idempotent). Pre-existing weakness #323 inherits. → Deployment note
   should sequence manual-vs-cron reindex (unload the cron for the manual run, or just let the cron
   do the migration). File a hardening follow-up (atomic `_save_state` via temp+`os.replace`, PID/
   flock guard on `reindex`).
8. **[Infra]** Single-call embedder + fixed 120s timeout is the **scaling ceiling** on the forced
   backfill — fine at ~500 chunks, latent risk at 10× growth. Note in the D6/backlog. No v1 action.
9. **[Infra]** No positive **migration-success signal**. A persistently failing forced reindex
   (e.g. Ollama down each cron fire) silently under-returns the date filter — the B2 symptom via a
   different cause, unpaged. → Make the §15 post-deploy verification explicit (confirm
   `_payload_schema_version == 2` + spot-check a chunk carries `last_modified_date`); longer term,
   an ntfy alert on non-zero reindex exit on the cron wrapper.
10. **[CTO]** Cosmetic: deferral source citations drop the `wiki/` directory (`ingest.py:924-936`
    is actually `src/anytype_llm_wiki/wiki/ingest.py`). Underlying claims correct. Fix for
    navigability at impl.
11. **[CTO]** The `multi_select` GET response shape remains UNVERIFIED (correctly fenced behind the
    D6 follow-up). v1 code must not touch it; the follow-up must verify against a live space before
    implementing `domain_tags` chunker extraction.

## Resolutions

No findings were withdrawn during discussion — the council converged cleanly. CSO and Infra
explicitly de-duplicated the state-file finding (Infra owns it as an integrity concern; CSO
defers to that framing). CTO and CSO independently arrived at the same Tier-2-harness /
cross-tier-consistency concern from different lenses (reviewer-diligence vs data-correctness),
consolidated here as findings 4 and 5.

## Recommendation

**Recommended target:** `decide`
**Confidence:** high
**Rationale:** The spec is APPROVED with **zero BLOCKING council findings** — it is technically
accurate (load-bearing claims independently re-verified against source), implementable (test plan
satisfiable, #289-trap closed), operationally sound (fail-safe idempotent migration, trivial
rollback), and secure (no new egress/auth/PII). What gates an autonomous advance to `test` is not
a quality defect but the **two Open Decisions that are explicitly Jan's to ratify**: OD-1 (accept
the `last_modified_date` payload field + a forced one-time re-embed — a payload-schema change that
deviates from the ticket's stated non-goal) and OD-2 (accept de-scoping the epic-linked ticket's
*titled* "tag" feature to type+date, and create the single follow-up ticket for
source_type + domain_tags). The council cannot ratify a material de-scope of an epic ticket or a
schema migration on Jan's behalf. At Decide, Jan should ratify OD-1 + OD-2, **create the D6
follow-up ticket as a condition of OD-2** (CPO finding 2), and reconcile `product.md`'s "tag"
capability claim (CPO finding 1). If ratified, this advances to `test` as a clean, low-risk
implementation; the ADVISORY items above are carried forward as authoritative acceptance criteria
for the test/impl phase via `spec-addendum-post-spec-r1.md`.
**Dissent:** None.
