# Spec Addendum — post-test council (R1)

**Source:** [`council-test-r1.md`](council-test-r1.md)
**Date:** 2026-06-05
**Target phase:** impl
**Status:** Authoritative — the impl phase MUST honor these items as spec requirements. This addendum
SUPPLEMENTS and, where noted, CORRECTS [`spec-addendum-post-spec-r1.md`](spec-addendum-post-spec-r1.md).
The impl lead reads both addenda during Task Intake.

The post-test council signed off with zero BLOCKING findings (advance to impl). The items below are the
subset of advisories that act as additional acceptance/exit criteria for the impl phase, plus one
correction to the prior addendum that was caught by independent source verification.

## Correction to the post-spec addendum

**C1. [CTO-5 — CORRECTED] `embed_query` is NOT currently imported by `indexer.py`.**
Post-spec addendum item-11 stated `embed_query` is "imported from embedder.py:22 (already imported by
indexer.py)." This is factually wrong and was verified against real source by the CTO and the council
chair:
- `src/anytype_llm_wiki/indexer.py:13` imports only `embed` (`from .embedder import embed`).
- `embed_query` is imported by `src/anytype_llm_wiki/server.py:9`, not by `indexer.py`.

**Impl requirement:** When extracting `semantic_search_core` into `indexer.py`, the impl MUST add
`from .embedder import embed_query` to `indexer.py`. The behavioral multi-type test
(`TestMultiTypeSemanticSearch`, `tests/wiki/test_query.py:1844`) monkeypatches `_idx_mod.embed_query`;
if that name is not present in `indexer.py`'s namespace, the monkeypatch raises `AttributeError` and the
test fails for the wrong reason. Item-11's "no function to move" conclusion still holds — `embed_query`
is imported, not moved — but the "already imported by indexer.py" premise is false and is corrected here.

## Additional acceptance/exit criteria for the IMPL phase

1. **[CTO] `semantic_search_core` MUST construct its Qdrant client via the `_qdrant()` factory.**
   The in-memory behavioral tests patch `_idx_mod._qdrant` to return a seeded `QdrantClient(":memory:")`.
   If `semantic_search_core` builds its client with an inline `QdrantClient(...)` (as the *current*
   `semantic_search` in `server.py` does) instead of calling `_qdrant()`, the monkeypatch will not bind
   and the multi-type / single-type / Qdrant-down boundary tests will not exercise the real code path.

2. **[CTO-6 / QA / CSO / Client — live relation-shape pin, BINDING] Honor post-spec addendum item-4.**
   The 1-hop relation read-back element shape is the one wire contract with no existing read-side code to
   mirror. During impl, run a live `get_object` (against Aldeia's own vault) and confirm the actual
   relation-element shape. If it differs from BOTH mocked forms used by the dual-shape parser test, the
   real shape MUST be added to the mocked fixture so `test_reciprocal_relation_read_merge_write` exercises
   a NON-EMPTY prior set. Rationale: if the merge test only ever sees a shape the parser cannot read, it
   merges an empty prior set and the test passes vacuously while the real code silently re-introduces the
   N1 relation-clobber — i.e. silent relation-data loss in the user's own Anytype vault. This is the
   single most important item in this addendum.

3. **[QA / Infra / Client] Doc + operational ACs have NO automated test backstop — verify by manual
   review at the impl gate.** These cannot be asserted by the test suite and must not be assumed covered:
   - **Docs (post-spec addendum items 6, 7):** README quick-start demonstrating end-to-end
     `bootstrap → ingest → query` AND an explicit `file_back=True` demo; a "How it works" section
     covering (a) tiered retrieval + threshold rationale, (b) the compounding file-back loop, and (c) the
     **reindex-then-retrievable latency caveat**; create `docs/known-limitations.md` with the
     reindex-cadence limitation. NOTE: `docs/known-limitations.md` is still absent from the spec's Files
     Changed table (spec.md:649-661) — this addendum is authoritative over that table; the impl must
     create the file and the impl review must check for its existence, not only README edits.
   - **Synthesis timeout (post-spec addendum item 8):** land EITHER a separate `WIKI_SYNTH_TIMEOUT`
     (interactive default ~120s) OR a documented 600s accepted ceiling PLUS a slow-synthesis log signal
     when a synthesis call exceeds ~60s. The `httpx` connect/read timeout must be finite (never `None`)
     as the true anti-hang backstop.
   - **Operator-log surfacing (post-spec addendum item 10):** `error_category` (config_error/api_error)
     and the `filterexpression_fallback` >500-row warning must reach the operator log stream, not only the
     per-query `QueryResult`.

4. **[CSO-2] File-back injection-amplifier security note (post-spec addendum item 9) still owed.**
   Add one sentence to the spec/README Security Considerations naming the file-back loop as an injection
   amplifier (a poisoned synthesis re-ingested as a future source), citing the SF1 clean-synthesis gate +
   min-sources(3)/min-words(100) as the structural bound.

## Release-gate criteria (record on the v0.4.0 release checklist — re-affirmed)

5. **[Infra / Client — post-spec addendum items 12, 13] Transcribe onto the actual release checklist**,
   not only the addenda: run the live smoke test once against **real Qdrant v1.17.0** and **Aldeia's own
   vault** before any community tag (internal-dogfood-first), to confirm the nested-`should`-in-`must`
   filter on that Qdrant version and to pin the live relation read-back shape (feeds item 2 above);
   capture the maintainer-measured **p95 < 5s on Mac Mini M4** as an explicit checklist item (the mocked
   `test_mocked_query_completes_under_5s` is a no-pathology gate, not the production SLO).

## Rationale

The test phase is review-clean and the suite is a faithful, strict TDD-red gate. These items are recorded
as authoritative because (a) C1 corrects a factual error in the prior addendum that would otherwise cost
the impl-worker a confusing `AttributeError` debug cycle, (b) items 1-2 are the binding conditions under
which the suite's strongest behavioral assertions actually exercise the real code (otherwise they pass
vacuously), and (c) items 3-5 are doc/operational/release obligations with no automated backstop that the
impl and release gates must verify by hand. None expands v0.4.0 scope.
