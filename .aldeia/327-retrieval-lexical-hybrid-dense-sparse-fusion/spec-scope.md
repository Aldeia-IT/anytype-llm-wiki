# Spec Scope: retrieval-lexical-hybrid-dense-sparse-fusion (#327)

**Epic:** aldeia-box#140 | **Depends on:** #323 (metadata filters), #336 (source_type/domain_tags) — both MERGED on this branch.

## Problem (verified)
Dense (bge-m3, 1024-dim, Ollama) retrieval underperforms on name/keyword-precise queries: exact lexical match is invisible to pure cosine similarity. #327 adds a lexical/sparse signal and fuses it with the existing dense ranking so keyword-precise queries recall the right Objects.

## Verified code reality (must anchor the spec — do not re-derive from the ticket)
- **`indexer.semantic_search_core`** (`indexer.py:71-161`) is the single dense retrieval path. It embeds the query (`embed_query`), builds a conjunctive Qdrant `Filter` (space_id, types, date `DatetimeRange`, source_type/domain_tags `MatchAny`), calls `client.query_points(collection, query=vector, query_filter=..., limit, with_payload=True)`, returns `list[dict]` (object_name, object_id, type, heading, text[:500], score).
- **Collection** (`_ensure_collection`, `indexer.py:164-170`) is created with a **single UNNAMED dense vector**: `VectorParams(size=EMBED_DIMS, distance=COSINE)`. **No named vectors, no sparse vector config today.** Adding native Qdrant sparse vectors requires either named-vector migration (collection recreate + full re-embed) OR an app-level fusion that does not touch the collection schema. THIS IS THE CENTRAL ARCHITECTURAL DECISION.
- **Embedding** is Ollama `/api/embed` with bge-m3 — **dense only**. bge-m3 *can* emit sparse/ColBERT vectors via FlagEmbedding, but the Ollama path does not. A sparse signal needs a separate producer (Qdrant server-side BM25/IDF, FastEmbed SPLADE/BM25, or app-level BM25 over chunk `text`).
- **Migration pattern already exists**: `config.PAYLOAD_SCHEMA_VERSION` + `_payload_schema_version` state marker drives a one-time forced full re-embed in `_run_reindex` (`indexer.py:263-338`), marker advanced only on full (unscoped) reindex. A sparse-vector backfill can reuse this exact pattern.
- **`wiki_query` Tier-2** (`query.py:646-694`) is the only fused-candidate consumer: it calls `semantic_search_core(**_core_kwargs)` and dedupes candidate object_ids. Tier-1 (index_navigation, below `index_threshold`) does NOT hit Qdrant — fusion is a Tier-2 concern only. Metadata filters must apply to the fused candidate set (ticket open question #3).
- **Mem0 #336 OD-B constraint (load-bearing):** default-scoping / default-type-exclusion lives in `server.py:semantic_search`, NOT in `semantic_search_core`. `semantic_search_core` MUST stay filter-free on a bare call — inherited `test_no_filter_regression` asserts `query_filter is None`. Fusion logic must not break this contract.
- **Test fixture gotcha (Mem0):** tests that monkeypatch `indexer.semantic_search_core` for Tier-2 must also add the seeds as `wiki_entity`-typed objects to the `list_objects` response in `test_query.py` / `test_query_fetch_paths.py`.

## Domains touched
infrastructure (Qdrant collection schema, migration, resource), product (retrieval quality), conventions (test seams).

## Estimated complexity: **complex**
Central schema decision (named-vector migration vs app-level fusion) with a real migration cost, a new sparse-producer dependency, fusion-method choice (RRF weighting), and an evaluation methodology to prove before/after. High blast radius on the core retrieval path.

## Key open questions for Research
1. **Sparse signal source:** Qdrant native sparse vectors (server-side BM25/IDF via `models.Document` + FastEmbed, or precomputed) vs an external/app-level lexical index. Cost/complexity/dependency tradeoff (local-first constraint — no cloud, deps capped per supply-chain posture). Does it add a heavy dependency (FastEmbed/torch)?
2. **Fusion mechanism:** Qdrant native `query_points` prefetch + `FusionQuery(Fusion.RRF)` (requires both vectors in one named-vector collection) vs application-level RRF over two separate ranked lists. Weighting/k constant.
3. **Collection migration:** can sparse be added without recreating the collection? (Qdrant: adding a sparse vector to an existing single-unnamed-dense collection — feasible in-place, or recreate required?) Reuse the `PAYLOAD_SCHEMA_VERSION` forced-reembed marker for backfill.
4. **Filter interaction (#323/#336):** filters apply to the fused candidate set — confirm prefetch-level vs post-fusion filter placement in Qdrant's API.
5. **Evaluation:** how to measure retrieval quality before/after on this small local corpus (a fixed query/relevance set; metric — recall@k / MRR). What's the cheapest credible eval given no labeled data.
6. **`semantic_search_core` contract:** keep filter-free-on-bare-call; where does fusion live so the no-filter regression and #336 OD-B both hold.

## CLAUDE.md / context sections at risk of staleness
- `.aldeia/context/technical.md` — "Qdrant chunk payload schema" + collection vector config (single unnamed dense → +sparse named); `EMBED_*` config; new env vars if a sparse model is configurable.
- `.aldeia/context/product.md` — "Semantic search" capability description (→ hybrid).
- README tool docs + CHANGELOG release note (migration/backfill, as #323 did).

## Guard rails
Local-first (no cloud egress); supply-chain dependency caps (compatible-release policy in pyproject); preserve the existing dense path as a safe fallback if sparse is unavailable.
