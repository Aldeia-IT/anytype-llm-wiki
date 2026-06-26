# AC-EVAL — Live Retrieval-Quality Fixture: Curation Runbook

**Status: NOT YET CURATED — blocking pre-merge gate for #327.**

AC-EVAL is the feature's single CI-unverifiable, headline guard: proof that hybrid (dense+BM25)
retrieval beats dense-only. The council made it a **non-skippable, human-reviewed pre-merge gate**
(spec §10, addendum items 2 + 1-post-test). It cannot be satisfied in the headless SDLC sandbox:
curating `expected_ids` and running the eval require the **live production fleet wiki** (294 objects)
plus Qdrant/Anytype/Ollama credentials, none of which the `agent` user can access (Jan's `.env` is
mode 0600; Anytype is not running on the build host). It must be run by someone with the live stack
(Jan) and the result recorded on the PR **before merge**.

## What to produce
`tests/eval/fixtures/retrieval_quality_cases.json` — a ≥5-case fixture (schema in
`retrieval_quality_cases.example.json`). Replace every `<CURATE: ...>` placeholder with real values.

## Curation procedure (spec §10.2, Step 8)
1. Point at the live production fleet wiki; confirm `reindex_anytype` has run so Qdrant is populated.
2. For each case, run the live `semantic_search(query=..., types=[...], space_id=...)` MCP tool and
   inspect results in Anytype to capture the correct `expected_ids` (Anytype object UUIDs). For
   `repro-327`, derive `expected_ids` **independently** from
   `semantic_search("contradiction detection limitations linked entities")` + manual inspection —
   NOT by reverse-engineering from what BM25 happens to surface.
3. Each case carries production-shaped `types`/`space_id` (so the eval exercises the real
   `wiki_query` shape, not a no-filter shortcut).

## Hard requirements (council addendum — all four MUST hold)
1. **`repro-327` `expected_ids` traceable** to the ticket's 2026-06-25 reproduction comment and
   independently justified.
2. **Dense genuinely misses** repro-327 (`dense_recall < hybrid_recall`, strict `<`) — the
   committed per-case assertion in `test_retrieval_quality.py` already enforces strict `>`.
3. **≥1 case shows a strict `hybrid > dense` lift** (the aggregate `mean >=` assertions alone
   tolerate a no-op tie).
4. **`uv run python -m pytest tests/eval/ -m live` exits 0** against the live stack, and the result
   is **recorded on the PR**.

## Run
```
uv run python -m pytest tests/eval/ -m live -v
```
The aggregate test (`test_hybrid_recall_aggregate`) also prints a per-query diagnostic table
(`d_recall`/`h_recall`/`d_mrr`/`h_mrr`) regardless of pass/fail — paste it into the PR.

## Why it isn't committed as a real fixture here
A fixture with fabricated/placeholder UUIDs would give false confidence — the exact anti-pattern
the council's own memory (`0447e373`) and addendum item 2 warn against. The real
`retrieval_quality_cases.json` is intentionally absent so the live test errors-until-curated; CI
(`-m "not live"`) is unaffected. Curate, run, record, then merge.
