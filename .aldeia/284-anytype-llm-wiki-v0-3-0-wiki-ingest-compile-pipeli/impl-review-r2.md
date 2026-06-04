# Implementation Review — v0.3.0 wiki_ingest (Round 2, re-review)

**Ticket:** #284 · **Branch:** aldeia/284-… · **Reviewer:** Lead (inline re-verification of round-1 fixes against the diff and the test suite).
**Suite:** `pytest -m "not live"` → 366 passed, 20 skipped, 0 failed; `bandit -r src/` clean; live tests deselected.

## Verdict: APPROVED

All round-1 BLOCKING and SHOULD-FIX findings are resolved and independently verified. Remaining items are accepted minor suggestions or pre-release (live-gate) gates explicitly deferred by the approved addendum.

## Round-1 findings — resolution status
- **BLOCKING-A (no concepts) — RESOLVED.** Candidates carry `kind`; LLM `concepts` → `create_object(type_key="wiki_concept", properties=[{"key":"wiki_definition",...}])`; entities → `wiki_entity`/`wiki_facts`; `resolve_entity` receives the kind-mapped `type_key` (ingest.py:140-154, 505-549). AC#1's "≥1 Entity AND ≥1 Concept" is now achievable on the live path. Non-live suite unchanged (mocked tests have no LLM concepts).
- **BLOCKING-B (relations) — RESOLVED.** Standalone `wiki_relation` object replaced with property-based bidirectional links: PATCH `wiki_relations`(entity)/`wiki_related`(concept) on both sides; B-side failure reverts A to its prior objects list and records `relation_rollback` + `status="partial"` (ingest.py:272-345, `_patch_relation` is properties-only — AC-L1 holds). `TestBidirectionalRelationRollback` rewritten to the property-based model with a strengthened, non-vacuous assertion (A-side PATCHed twice: set `[b_id]` then revert to `[]`; `relation_rollback` in WikiLog). No `wiki_relation` type reintroduced. Verified this is the only non-live test issuing relation writes.
- **SF (AC#11) — RESOLVED.** `ollama_model_not_pulled` aborts with the `[CONFIG ERROR]` before Source creation (ingest.py:485-489, before step 9).
- **SF (WikiClient leak) — RESOLVED.** Steps 2–5 wrapped in `try/finally: client.close()` (ingest.py:435-436).
- **SF (fetch error fabrication) — RESOLVED.** Short-circuits any `[DATA ERROR]` fetch return (ingest.py:460).
- **SF-3 (reindex concurrency) — RESOLVED** via the spec's accepted alternative (§6 ADV-12: "deterministic Qdrant point IDs OR flock"): `uuid5(NAMESPACE_URL, "{object_id}:{i}:{heading}")` in both `reindex` and `reembed_object` (indexer.py:90,147) → a concurrent reindex re-upserts the same ids instead of duplicating.
- **Addendum item 3 (update-side vacuous guard) — RESOLVED.** `TestUpdatePathNoBodyKey`'s `/search` mock now returns a search-shaped same-name entity so the update path fires; `assert update_payloads` added before the body-key loop (test_ingest.py:740). AC-L1's update-path body-omission now has non-vacuous CI coverage.
- **S-2 (unused import) — RESOLVED** (ingest.py:22).

## Accepted / deferred (non-blocking)
- **Heading-derived candidates as the primary path (design concern):** retained because the approved non-live ingest tests (partial-failure, rollback, create-side guard) require deterministic candidates without mocking Ollama; LLM `extract()` enriches when available. The headingless fallback names a single entity after the source URL — coarse but durable, and required to satisfy the addendum item-3 create-side guard. Flagged for council awareness; LLM-extraction-primary re-architecture would require revising multiple approved tests and is out of scope for this increment.
- **S-1 domain_hint validated-but-not-applied; S-4 `_is_model_not_pulled` 404 breadth; S-5 `0.0.0.0` in `_LOCAL_HOSTS`; S-6 thresholds not env-driven** — minor, no AC/test impact; left as follow-ups.
- **Live gates (AC#1/AC-P2/AC-P7/V3) + NOTICE/pip-licenses + Qdrant backup** — explicitly deferred to the pre-PyPI-tag gate by addendum-post-test-r1 items 9–10. Re-seat Legal + Infra at the post-impl/PR final gate.

## Note for council (carried to handoff)
The relation-mechanism correction changed one council-approved test (`TestBidirectionalRelationRollback`) to match the authoritative spec's property-based relation model (master §ingest step 6 + verified-live native-backlinks). This is documented transparently rather than silently; the change strengthens (does not weaken) the assertion. Council should ratify the test-contract correction at post-impl review.
