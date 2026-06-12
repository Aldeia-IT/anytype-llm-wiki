# Consolidated Spec Review — Round 1

**Spec:** `spec.md` (323 — Retrieval metadata filters + type/tag scoping)
**Date:** 2026-06-12 · **Reviewers:** CTO (technical accuracy), QA Director (completeness/testability), Infrastructure Lead (ops/migration), + Lead inline verification
**Source reviews:** `review-r1-cto.md`, `review-r1-qa.md`, `review-r1-infra.md`

## Verdict: **NEEDS REVISION**

Three independent reviews converged on the same structural problem: **filter params that are inert against the real corpus** (the exact footgun the spec rightly rejects for `domain_tags`), plus a **migration that never backfills**. The spec's Qdrant wire contract, no-filter regression design, and type-filter path were independently verified CLEAN. The fixes are coherent and achievable in one revision round; the spec's skeleton is sound. The core correction is a **scope tightening to `type` + `date` filters**, with `source_type` and `domain_tags` both deferred (each blocked by a distinct, now-verified upstream indexing gap).

---

## BLOCKING

### B1 — `source_type` is INERT: `wiki_source` objects are never chunked or indexed (Lead-verified; CTO-B2 + CTO-B1)
**Verified by the Lead directly.** `wiki_source` objects are created with **properties only, no markdown body** (`ingest.py:935-967` `_create_source`, `remember.py:188-195`; ingest comment line 822: "NEVER a body/markdown key — AC-L1"). The chunker emits property chunks only for keys in `WIKI_TEXT_PROPERTY_KEYS` (`chunker.py:13-16`), which does **not** include `wiki_excerpt` (the only text a source carries). Therefore `chunk_object` returns **zero chunks** for `wiki_source` objects → they never reach Qdrant → no payload ever carries `source_type`.
Consequence: the D2 `source_type` filter returns zero for ALL inputs on **both** `semantic_search` and `wiki_query` (compounded on `wiki_query` by CTO-B1: `wiki_source ∉ _WIKI_TYPE_KEYS`, `query.py:50`). AC-F3 / AC-F8 pass only because their fixtures hand-feed a markdown body that production sources never have.
**Fix:** Defer `source_type` (D2) in v1, mirroring the D4 domain_tags treatment, with the root cause documented (sources are body-less and not in the chunk allowlist). Present as an Open Decision the optional path to enable it (index `wiki_excerpt` by adding it to `WIKI_TEXT_PROPERTY_KEYS` — note this changes `semantic_search` retrieval semantics, so it needs Jan/product sign-off, not a silent inclusion). Remove `source_type` from the v1 API surface, filter build, chunker extension, payload writes, indexes, and tests unless Jan opts into the excerpt-indexing path at Decide.

### B2 — Migration is a no-op: incremental `reindex` never backfills new payload fields (Infra-B1; Lead-confirmed)
`reindex()` skips any object whose `last_modified_date` is unchanged (`indexer.py:134-136`). After upgrade, the vast majority of objects are unchanged, so their chunks keep the old 6-field payload **indefinitely**; the new `last_modified_date` payload field only lands for objects edited post-upgrade. The launchd cron (`docs/samples/com.aldeia.anytype-llm-wiki-reindex.plist:34`) runs plain `reindex()` and never backfills either. The date filter then silently under-returns against the historical corpus — the same footgun, via the back door.
**Fix:** Specify a forced/auto-healing repopulation path. Recommended: store a **payload-schema-version marker in the index state file** (`config.INDEX_STATE_FILE`); when the code's payload-schema version exceeds the stored one, force a full re-embed pass (ignore the unchanged-skip) on the next `reindex`, then stamp the new version. This auto-heals both the manual and the cron path. Document the one-time cost (full re-embed through Ollama). Update §15 deployment steps accordingly.

### B3 — domain_tags deferral is an unratified scope gap (QA-B1)
Technically airtight (research proved `wiki_domain_tags` is never persisted onto objects, `ingest.py`/`remember.py` validate-only). But the ticket is *titled* "type/**tag** scoping" and lists domain_tags as an AC. This requires Jan's explicit acceptance at Decide (OD-2) and a **linked follow-up ticket** before close.
**Fix:** Keep the deferral; ensure §4 Open Decisions states it crisply and the handoff/Decide path creates the follow-up. Combined with B1, the follow-up should cover BOTH domain_tags persistence AND source/excerpt indexing. (This is a Decide-gate ratification item, not a spec-prose defect — but the spec must present it for sign-off.)

### B4 — AC-F10 (Tier-1 filter test) is not implementable (QA-B2)
The spec literally says "full test setup omitted," and §8 Tier-1 predicates are inline lambdas inside `wiki_query` with no testable seam. The "consistent across Tier 1 and Tier 2" guarantee would ship unverified.
**Fix:** Extract the Tier-1 predicates (now only `type` and `date`, since `source_type` is deferred per B1) into **module-level pure functions** in `query.py` (e.g. `_passes_type_filter(obj, effective_types)`, `_passes_date_filter(obj, after_dt, before_dt)`), and write concrete unit tests against them. Rewrite AC-F10 with a full, runnable setup.

---

## SHOULD-FIX

### S1 — Pin ONE type-filter shape; remove unused `MatchAny` import (#289 trap) (CTO-S, QA-SF)
§6.1 imports `MatchAny` and the research recommends the flat `MatchAny` form, but §6.2 and AC-F2 use the nested `Filter(should=[FieldCondition(match=MatchValue)])`. If an implementer follows the "cleaner" `MatchAny` recommendation, AC-F2's `hasattr(c,"should")` assertion fails on day one. **Pin the nested-`should` form** (it is what the regression depends on and matches existing code), remove the `MatchAny` import and any `MatchAny` mention from §6/research-carryover.

### S2 — Strengthen the no-filter regression (AC-F1) (QA-SF)
AC-F1 only asserts `query_filter is None`. Also assert: (a) the `query_points` call kwargs are otherwise unchanged (collection, limit, with_payload), and (b) default `wiki_query` (no `types`) still passes the **full `_WIKI_TYPE_KEYS`** into the Tier-2 core call (not `types=None`) — guarding the §8.1 intersection refactor from accidentally widening/narrowing default behavior.

### S3 — Error-path & edge-case test coverage (QA-SF, CTO)
AC-F6 tests only 1 of 3 specified error paths. Add: the `wiki_query` never-raise **error-dict** path for a bad date (returns `error_category:"config_error"`), and the **empty-type-intersection** error on `wiki_query`. Add edge-case tests: empty-list filter param (treated as no-filter), both date bounds present, a filter matching zero results, and a mixed valid+invalid `types` list (silently narrowed) on `wiki_query`.

### S4 — Gate payload-index creation out of the `reembed_object` hot path (CTO-G1, Infra-S4)
§6.3 runs 4 synchronous `wait=True` `create_payload_index` calls inside `_ensure_collection`, which runs on every `reembed_object` (`indexer.py:197`) — the per-object update path. Idempotent but wasteful on a real Qdrant server. Move index creation to a function called only on the full `reindex` path (or a once-guard), keeping `_ensure_collection` to collection creation. Also decide CI handling for the in-memory-Qdrant `create_payload_index` `UserWarning` (explicit `filterwarnings` so a warnings-as-errors run doesn't break).

### S5 — Shared `_chunk_to_payload` helper + test `reembed_object` writes new fields (Infra-S3)
`reindex` and `reembed_object` hand-duplicate the `PointStruct` payload dict; drift desyncs bulk vs single-object update paths. Extract a shared `_chunk_to_payload(chunk) -> dict` and assert BOTH paths write the new field(s). No current test covers `reembed_object`'s payload for the new fields.

### S6 — Tier-1 `last_modified_date` extraction shape (CTO-SF)
Reconcile the date-read shape between `indexer._get_last_modified` (`indexer.py:108`) and the lint reader (`lint.py:508`); ensure the Tier-1 predicate and the chunker read the same property shape. Make the AC-F8/F9 fixtures representative of real `get_object` output (don't hand-feed a body to a type that never has one).

---

## SUGGESTION

- **SG1** — §3 uses a `wiki_source` example to illustrate chunking; replace with an entity/concept example since sources are not chunked (avoid implying sources are indexed).
- **SG2** — State the rollback story explicitly (the extra payload fields/indexes are inert under the prior code version → trivial rollback).
- **SG3** — Re-baseline the §13 resource wording: once B2 forces a full re-embed, the cost is a complete Ollama re-embed pass (still seconds on this corpus), not an incremental delta.

---

## Revised v1 scope (post-review, for the fixer)

| Filter | v1 status | Reason |
|---|---|---|
| `type` (type_key) | **SHIP** | Already in payload; expose on `wiki_query`, index, validate, test. |
| `date` (`last_modified_date`, `ingested_after/before`) | **SHIP** (needs B2 migration fix) | Universal across all chunked types; additive payload field + forced reindex. |
| `source_type` | **DEFER** (B1) | `wiki_source` objects are never chunked → inert. Optional enable path = index excerpts (needs Jan/product sign-off). |
| `domain_tags` | **DEFER** (B3/D4) | Never persisted onto objects → inert. Follow-up ticket. |

## Open Decisions for Jan (Decide gate) — updated
- **OD-1:** Accept the additive `last_modified_date` payload field + a **forced one-time re-embed** migration (schema-version-marker auto-heal)? Fallback: type-filter-only.
- **OD-2:** Accept deferring **both** `domain_tags` and `source_type` to a single follow-up ticket (which would persist domain_tags onto objects AND index source excerpts)? Or opt into indexing `wiki_excerpt` now to enable `source_type` on `semantic_search` (changes retrieval semantics)?

## Lead verification notes
- Independently confirmed B1 (sources body-less + `wiki_excerpt` not in allowlist) and B2 (incremental skip) against source — both real.
- Confirmed the reviewers' CLEAN findings are credible: Qdrant wire contract, AC-F2↔§6.2 agreement, no-filter regression. Did not re-verify every clean claim.
