# Research: Lexical / Hybrid Dense+Sparse Fusion (#327)

**Date:** 2026-06-25
**Researcher:** technical research worker
**Questions investigated:** sparse signal source, fusion mechanism, collection migration, filter interaction, contract preservation, evaluation methodology, fallback/robustness

---

## Research Questions

1. Sparse signal source — pick and justify
2. Fusion mechanism — Qdrant native vs app-level RRF
3. Collection migration — in-place vs recreate
4. Filter interaction with #323/#336
5. Contract preservation — `semantic_search_core` no-filter guarantee
6. Evaluation methodology
7. Fallback / robustness

---

## Findings

### Q1 — Sparse Signal Source

**Recommendation: app-level BM25 via `rank-bm25` (Option C). Runner-up: Qdrant native IDF with precomputed sparse vectors (Option B partial).**

Three options were evaluated:

#### Option A: Qdrant native server-side BM25 via `models.Document` + FastEmbed

The `Document(text=..., model="qdrant/bm25")` API exists in qdrant-client 1.18.0 (verified: `qdrant_client.models.Document.model_fields` shows `text`, `model`, `options`). However, resolving a `Document` to a sparse vector requires **client-side FastEmbed** (when not using Qdrant Cloud). The installed client raises `ImportError: fastembed is not installed. Please install it to compute embedding for document implicitly with pip install fastembed` when `Document` is passed without the package installed. Standard local Docker Qdrant does NOT do server-side BM25 computation; Qdrant Cloud Inference is required for that. Qdrant Edge has a built-in BM25 embedder, but that is a separate product.

FastEmbed (option A's dependency) pulls in **onnxruntime ~200MB** plus `huggingface-hub`, `tokenizers`, `filelock`, `fsspec`, and 14 other packages (verified via `uv pip install --dry-run fastembed`). It does NOT pull torch. However, adding onnxruntime is a significant dependency footprint for what amounts to a BM25 tokenizer, violating the spirit of the supply-chain cap posture. The `SUPPORTED_SPARSE_EMBEDDING_MODELS` dict in qdrant-client 1.18.0 is empty `{}` without fastembed installed, confirming this path is blocked without the extra install.

**Verdict: REJECTED.** Requires fastembed (onnxruntime), which is a heavy dep for a BM25 tokenizer. The benefit (server-side integration) is unavailable on local Docker Qdrant anyway.

#### Option B: Precomputed sparse vectors pushed as `SparseVector`

This is an app-side sparse vector producer: the application tokenizes text, computes IDF weights offline, and pushes `SparseVector(indices=[...], values=[...])` at index time. At query time, the query string is tokenized identically and a sparse vector is assembled for the Prefetch call.

This is exactly what `rank-bm25` enables. The distinction from Option C (pure app-level) is that the sparse vectors ARE stored in Qdrant and retrieved via the native `Prefetch` API.

`SparseVectorParams(modifier=Modifier.IDF)` enables Qdrant to apply IDF re-weighting at search time (server-side IDF over the sparse vectors stored in the collection). This uses `Modifier.IDF` (verified: `qdrant_client.models.Modifier` has values `NONE` and `IDF`). This means: store TF (term frequency counts as values), let Qdrant compute IDF. The alternative is to store pre-computed TF×IDF weights and use `Modifier.NONE`.

**This is the correct architecture for the Qdrant native sparse path.** The producer still runs in the app, but sparse vectors live in Qdrant.

#### Option C: App-level BM25 / keyword index over chunk `text` (pure app, no Qdrant sparse storage)

`rank-bm25` (v0.2.2) is 8.6 kB wheel, depends only on **numpy** (already a transitive dependency of qdrant-client). Zero additional package downloads confirmed via `uv pip install --dry-run rank-bm25` (resolves `rank-bm25==0.2.2` only, numpy already present). No onnxruntime, no torch.

The app holds an in-memory BM25 index over chunk texts, queried separately to produce a ranked list of chunk IDs, then fused with the dense ranked list via app-level RRF.

**Verdict: RECOMMENDED for implementation.** Lightest dependency addition, fully offline, no Qdrant collection schema change required for the BM25 signal itself. The only non-trivial cost is keeping the BM25 index in memory (a Python dict + BM25Okapi object). At ~500 chunks (current corpus), this is negligible.

**Why not Option B (native sparse in Qdrant)?** Option B is strictly better at scale (IDF computation is server-side, persistent, filtered-search-aware). However, it requires storing sparse vectors — either via `create_vector_name` migration (found to work in-place, see Q3) and upsert backfill, or a full recreate. The BM25 index build at query time in Option C requires loading all chunk texts from Qdrant payload (already in memory via `with_payload=True`) or a separate pre-build step. At the current 500-chunk scale, app-level BM25 is simpler to implement and to test (no Qdrant schema delta for this alone).

**However**: if the spec writer wants to get the full Qdrant-native RRF path (FusionQuery) as the eventual end-state, combining Option B (precomputed TF-count sparse vectors stored in Qdrant) with the native `Fusion.RRF` is more robust at scale and avoids maintaining an in-memory BM25 index. The two sub-recommendations are:

- **Ship v1 as:** app-level BM25 (`rank-bm25`) + app-level RRF. Zero schema migration. Proves the retrieval improvement.
- **Defer to v2:** native Qdrant sparse (`create_vector_name` in-place migration, TF-count sparse vectors, `Modifier.IDF`, native `FusionQuery(Fusion.RRF)`). Full stack alignment.

**Evidence for recommendation:**
- `uv pip install --dry-run rank-bm25` → resolves exactly 1 package, 8.6 kB
- `from rank_bm25 import BM25Okapi` → imports math, numpy, multiprocessing only
- Tested on sample corpus: `BM25Okapi(corpus).get_scores(["contradiction", "detection"])` returns highest score for the matching text (1.86 vs 0.0 for unrelated texts)

---

### Q2 — Fusion Mechanism

**Answer: App-level RRF for v1 (if app-level BM25 is chosen); Qdrant native `FusionQuery(Fusion.RRF)` for v2 native sparse path.**

#### Qdrant native fusion API (verified against installed 1.18.0)

All imports confirmed present in `qdrant_client.models`:

```python
from qdrant_client.models import Fusion, FusionQuery, Prefetch, SparseVector
```

- `Fusion` enum: `Fusion.RRF` (`'rrf'`), `Fusion.DBSF` (`'dbsf'`) — verified via `list(Fusion)`
- `FusionQuery.model_fields`: `{'fusion': FieldInfo(annotation=Fusion, required=True)}`
- `Prefetch.model_fields`: has `query`, `using`, `filter`, `limit`, `score_threshold`

The native call shape (verified end-to-end with in-memory client):

```python
results = client.query_points(
    collection_name=config.QDRANT_COLLECTION,
    prefetch=[
        Prefetch(query=dense_vector, using=None, filter=search_filter, limit=prefetch_limit),
        Prefetch(query=SparseVector(indices=..., values=...), using='sparse', filter=search_filter, limit=prefetch_limit),
    ],
    query=FusionQuery(fusion=Fusion.RRF),
    limit=limit,
    with_payload=True,
)
```

This requires a **named sparse vector** in the collection, but the unnamed dense vector can remain unnamed (`using=None`). Verified via in-memory client test.

**Critical: filter must go on each Prefetch, NOT at top-level `query_filter` for FusionQuery.** Verified by inspection of `local_collection.py:814-848`: when `query` is a `FusionQuery`, `_merge_sources` fetches fused results by ID and does NOT apply `query_filter` from the outer `query_points` call. The top-level `query_filter` is only applied in the re-scoring path (non-FusionQuery). This is confirmed by the live test: top-level filter returned both documents; Prefetch-level filter correctly returned only the matching one.

**Note on real Qdrant server behavior:** The local in-memory client may differ from the real Qdrant server. However, the Qdrant documentation states "whenever a query has at least one prefetch, Qdrant will: 1) Perform the prefetch query (or queries), 2) Apply the main query over the results." This implies filters applied at the prefetch level are the semantically correct placement for filtering the candidate pool before fusion.

#### RRF formula

The standard academic RRF formula (Cormack et al. 2009):

```
score(d) = sum over retrievers r: 1 / (k + rank_r(d))
```

Standard `k=60` (academic default). Qdrant's implementation uses `k=2` by default (found in `qdrant_client.hybrid.fusion.DEFAULT_RANKING_CONSTANT_K = 2`). Their formula is `1 / ((pos+1)/weight + k - 1)` which at `weight=1, k=2` equals `1/(pos+2)`, i.e. standard RRF with `k=2` not `k=60`. This gives much stronger differentiation between ranks: rank-1 score `0.5` vs `0.0164` at `k=60`. For app-level RRF, use `k=60` (the academic standard that works well empirically) rather than Qdrant's `k=2`.

#### App-level RRF

```python
def _rrf_fuse(
    dense_results: list[dict],
    bm25_results: list[dict],
    k: int = 60,
) -> list[dict]:
    scores: dict[str, float] = {}
    chunks: dict[str, dict] = {}
    for rank, r in enumerate(dense_results):
        cid = r["_chunk_id"]
        scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank + 1)
        chunks.setdefault(cid, r)
    for rank, r in enumerate(bm25_results):
        cid = r["_chunk_id"]
        scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank + 1)
        chunks.setdefault(cid, r)
    ordered = sorted(scores, key=lambda cid: scores[cid], reverse=True)
    return [chunks[cid] for cid in ordered]
```

---

### Q3 — Collection Migration

**Answer: In-place addition IS possible via `create_vector_name` (verified in qdrant-client 1.18.0). Full collection recreation is NOT required.**

This is the single most important finding of this research, resolving the "central architectural decision" from the spec-scope.

#### Verified API (qdrant-client 1.18.0)

```python
from qdrant_client.models import SparseVectorNameConfig, SparseVectorConfig

client.create_vector_name(
    collection_name=config.QDRANT_COLLECTION,
    vector_name='sparse',
    vector_name_config=SparseVectorNameConfig(
        sparse=SparseVectorConfig(modifier=None)  # or Modifier.IDF for server-side IDF
    )
)
```

Signature verified: `create_vector_name(self, collection_name: str, vector_name: str, vector_name_config: Union[DenseVectorNameConfig, SparseVectorNameConfig], wait: bool, ordering: WriteOrdering | None, timeout: int | None, **kwargs)`.

The Qdrant documentation states "Named vectors can be added to or removed from an existing collection without having to recreate the collection. Available as of v1.18.0." The project pins `qdrant-client>=1.18.0,<2.0.0`, so this is available by guarantee.

**End-to-end test result (in-memory client):**
1. Created collection with unnamed dense vector (`VectorParams(size=4, distance=COSINE)`)
2. Called `create_vector_name('sparse', SparseVectorNameConfig(sparse=SparseVectorConfig()))` → returned `operation_id=0 status=COMPLETED`
3. Collection now has `sparse_vectors: {'sparse': SparseVectorParams(index=None, modifier=None)}`
4. Upserted point with `vector={'': [0.1,...], 'sparse': SparseVector(indices=[1,5], values=[0.9,0.5])}`
5. Called `query_points(..., prefetch=[Prefetch(using=None, ...), Prefetch(using='sparse', ...)], query=FusionQuery(Fusion.RRF))` → succeeded, returned results

The unnamed dense vector is referenced as `using=None` in `Prefetch`. The in-memory client confirms it resolves to the unnamed vector.

#### Naming the existing unnamed dense vector

**Not required for hybrid queries.** The Prefetch API accepts `using=None` to reference the unnamed (default) dense vector, while the sparse vector is named `'sparse'`. Upsert uses `''` (empty string) as the key for the unnamed vector when constructing a dict-format vector:

```python
vector={'': dense_list_float, 'sparse': SparseVector(indices=..., values=...)}
```

This avoids the need to rename the unnamed dense vector (which would require a full collection recreate).

#### Migration pattern for sparse backfill

The **existing `PAYLOAD_SCHEMA_VERSION` / `_payload_schema_version` marker pattern** (already in `indexer._run_reindex`) can be reused. Bump `PAYLOAD_SCHEMA_VERSION` from 3 to 4. The `force_full` flag will trigger a full pass over all objects. In that pass, instead of (or in addition to) the usual `client.upsert`, the indexer adds the sparse vectors.

The new migration step needed is:
1. `_ensure_collection` detects collection exists with unnamed dense only → calls `create_vector_name` to add `'sparse'` vector idempotently. The `create_vector_name` call is idempotent (safe to re-call; returns `COMPLETED` if already exists — confirmed from the Qdrant docs noting it "adds or updates").
2. On the forced full pass (triggered by version bump), every `PointStruct` is upserted with both `vector={'': dense_vec, 'sparse': SparseVector(indices=..., values=...)}`.

After the forced pass, old (dense-only) points have been re-upserted with their sparse vectors. New points from `reembed_object` also need the sparse vector added.

**Important caveat:** the in-memory local Qdrant client is used for tests. Tests that monkeypatch `_qdrant()` with a fake need their `FakeQdrantClientWithSearch` extended to handle the new `create_vector_name` call and the dict-format vector in `upsert`.

#### Exact `VectorParams` / `SparseVectorParams` config shape needed

```python
# Existing (do not touch):
client.create_collection(
    collection_name=config.QDRANT_COLLECTION,
    vectors_config=VectorParams(size=config.EMBED_DIMS, distance=Distance.COSINE),
)

# New in-place addition (idempotent, called from _ensure_collection):
client.create_vector_name(
    collection_name=config.QDRANT_COLLECTION,
    vector_name='sparse',
    vector_name_config=SparseVectorNameConfig(
        sparse=SparseVectorConfig(modifier=None)  # Modifier.IDF if server-side IDF weighting desired
    )
)
```

For the app-level BM25 (v1 recommendation), `modifier=None` is correct — the app pre-computes BM25 scores and stores them directly as float values in `SparseVector.values`. Server-side IDF (`Modifier.IDF`) is only needed when storing raw term counts and delegating IDF to Qdrant (the v2 native approach).

---

### Q4 — Filter Interaction (#323/#336)

**Answer: For Qdrant native fusion (v2), filters MUST go on each `Prefetch`, not the top-level `query_filter`. For app-level fusion (v1), filters pass to each underlying search as normal.**

#### Qdrant native fusion (verified)

The local client source at `local_collection.py:814-848` confirms: when `query` is a `FusionQuery`, `_merge_sources` does NOT apply `query_filter`. It fetches the fused point IDs by `retrieve()` with no filter. The top-level `query_filter` in `query_points` is only applied when `len(prefetches) == 0` (the base query branch at `local_collection.py:750-762`).

**Correct pattern for native fusion:**

```python
results = client.query_points(
    collection_name=config.QDRANT_COLLECTION,
    prefetch=[
        Prefetch(query=dense_vector, using=None, filter=search_filter, limit=prefetch_limit),
        Prefetch(query=bm25_sparse_vector, using='sparse', filter=search_filter, limit=prefetch_limit),
    ],
    query=FusionQuery(fusion=Fusion.RRF),
    limit=limit,
    with_payload=True,
    # do NOT put query_filter here for FusionQuery — it is ignored
)
```

The same `search_filter` (constructed from space_id, types, date, source_type, domain_tags) is passed to both Prefetches.

**Live test result:**
- Top-level `query_filter` with FusionQuery: returned 2 results (no filtering)
- Prefetch-level `filter` with FusionQuery: returned 1 result (correct filtering)

#### App-level fusion (v1)

Filters pass through to `semantic_search_core` as today. The BM25 search is app-level over already-retrieved chunks (or over a pre-built in-memory index filtered by space_id). The filter semantics do not change.

---

### Q5 — Contract Preservation

**Answer: Fusion logic lives in a new `hybrid_search_core` function that calls `semantic_search_core` internally. `semantic_search_core` is not modified. The no-filter regression test continues to pass unchanged.**

#### Current call path

```
server.py:semantic_search → semantic_search_core(...)   [test: test_no_filter_regression]
query.py:wiki_query Tier-2 → semantic_search_core(...)
```

#### Proposed call path (v1 app-level)

```
server.py:semantic_search → hybrid_search_core(...)   [calls semantic_search_core internally]
query.py:wiki_query Tier-2 → hybrid_search_core(...)
```

`semantic_search_core` contract is **unchanged**:
- Remains filter-free on bare call (no-filter regression test still passes — it calls `semantic_search_core` directly, bypassing `hybrid_search_core`)
- OD-B default-type-exclusion still lives in `server.py:semantic_search` (sets `effective_types`, passes to `hybrid_search_core`)
- `test_no_filter_regression` asserts `query_filter is None` when `semantic_search_core(query="test")` is called — this is still true because `semantic_search_core` is unchanged

**New function `hybrid_search_core` in `indexer.py`:**

```python
def hybrid_search_core(
    query: str,
    space_id: str | None = None,
    types: list[str] | None = None,
    ingested_after: str | None = None,
    ingested_before: str | None = None,
    source_type: list[str] | None = None,
    domain_tags: list[str] | None = None,
    limit: int = 10,
) -> list[dict]:
    """Hybrid (dense + BM25) search. Falls back to dense-only if BM25 unavailable."""
    try:
        bm25_results = _bm25_search(query, space_id=space_id, limit=limit * 2)
    except Exception:
        bm25_results = []

    dense_results = semantic_search_core(
        query=query,
        space_id=space_id,
        types=types,
        ingested_after=ingested_after,
        ingested_before=ingested_before,
        source_type=source_type,
        domain_tags=domain_tags,
        limit=limit * 2,
    )

    if not bm25_results:
        return dense_results[:limit]

    return _rrf_fuse(dense_results, bm25_results, k=60)[:limit]
```

**`server.py:semantic_search`** and **`query.py:wiki_query` Tier-2** both change their call from `semantic_search_core` to `hybrid_search_core`. All existing tests that monkeypatch `semantic_search_core` directly continue to work (they test `semantic_search_core` in isolation). Tests for the higher-level callers that monkeypatch `indexer.semantic_search_core` need to be updated to monkeypatch `indexer.hybrid_search_core` instead (or vice versa, depending on what the test is proving).

**Test fixture gotcha (from spec-scope.md):** Tests that monkeypatch `indexer.semantic_search_core` for Tier-2 behavior must be reviewed — if `hybrid_search_core` is the new Tier-2 call site, those tests need to monkeypatch `indexer.hybrid_search_core` instead, or `hybrid_search_core` itself must be monkeypatched.

---

### Q6 — Evaluation Methodology

**Answer: A fixed query→expected-object set (manually curated from known failures), Recall@k and MRR@k, run as a `pytest -m live` script against the live Qdrant+Ollama stack.**

#### Baseline problem

No labeled relevance data exists. The corpus is small (~294 objects, ~500-800 chunks). Standard IR eval datasets do not apply.

#### Proposed approach (cheapest credible)

1. **Manually curate 10–20 test queries** from known failure cases. The live reproduction comment on ticket #327 (2026-06-25) provides the first: `"What is the contradiction detection capability in the anytype-llm-wiki and its limitations?"` expected to surface objects with `contradiction` in their text. Additional candidates: any wiki object name that is a specific technical term (e.g., exact object names from the Anytype wiki).

2. **For each query, note the expected object_id(s)** — the objects that SHOULD appear in the top-k results.

3. **Metric:** Recall@k (did the expected objects appear in the top k results?) and MRR@k (mean reciprocal rank of the first expected result). At this corpus size, k=5 is appropriate.

4. **Implement as a `tests/eval/test_retrieval_quality.py`** marked `@pytest.mark.live`:

```python
@pytest.mark.live
@pytest.mark.parametrize("query,expected_ids", [
    ("contradiction detection limitations", ["<object_id_from_live>", ...]),
    ("BM25 sparse retrieval", ["..."]),
    # ... more
])
def test_recall_at_5(query, expected_ids):
    from anytype_llm_wiki.indexer import semantic_search_core, hybrid_search_core

    dense_results = semantic_search_core(query=query, limit=5)
    hybrid_results = hybrid_search_core(query=query, limit=5)

    dense_ids = {r["object_id"] for r in dense_results}
    hybrid_ids = {r["object_id"] for r in hybrid_results}

    dense_recall = len(set(expected_ids) & dense_ids) / len(expected_ids)
    hybrid_recall = len(set(expected_ids) & hybrid_ids) / len(expected_ids)

    # Assert hybrid is at least as good as dense:
    assert hybrid_recall >= dense_recall, (
        f"Hybrid recall ({hybrid_recall:.2f}) < dense recall ({dense_recall:.2f}) "
        f"for query {query!r}"
    )
```

5. **Run baseline before implementing hybrid** to capture the dense-only Recall@k numbers, then run again post-implementation to prove the improvement.

6. **Object IDs** need to be captured from a live `semantic_search` + manual inspection (the IDs are UUIDs in Anytype). A helper script can dump current search results for each test query, and the researcher/developer eyeballs which results are "correct" to populate `expected_ids`.

The cost is: one-time manual curation (30 min), then fully automated re-runs via `uv run python -m pytest tests/eval/ -m live`.

---

### Q7 — Fallback / Robustness

**Answer: BM25 failure degrades to dense-only silently; Qdrant failure propagates as today.**

#### App-level BM25 fallback

The `hybrid_search_core` function wraps the BM25 call in `try/except Exception` (broad catch). If the BM25 index is not yet built, fails to build, or raises for any reason, `bm25_results = []` is used, and the function returns `dense_results[:limit]` — identical to the current `semantic_search_core` behavior.

The BM25 index build requires loading chunk texts from Qdrant (on first query after server restart). If Qdrant is unavailable, the BM25 build fails and dense-only mode applies. This is graceful: the tool still works.

#### Qdrant unavailability

Unchanged from today: `semantic_search_core` raises `httpx.HTTPError` (Qdrant down), which `hybrid_search_core` does NOT catch (it would propagate). `wiki_query` Tier-2 catches this as `qdrant_unavailable` (existing `except Exception` at `query.py:682`).

#### BM25 index build strategy

Option A (lazy on first query): build the BM25 index on the first `hybrid_search_core` call by scrolling all Qdrant payloads. Cached in memory. Rebuilt on `reindex` completion.

Option B (eager on `reindex`): build and cache after each `reindex` call.

Recommendation: Option B (eager on reindex) is simpler to test and avoids cold-start latency on the first query. The BM25 index at 500 chunks is <1MB.

---

## Alternatives Considered

| Option | Pros | Cons | Verdict |
|--------|------|------|---------|
| (A) FastEmbed + Qdrant `Document`/BM25 | Native Qdrant integration, no app-side code | Requires `fastembed` (onnxruntime ~200MB), needs Qdrant Cloud for server-side or client-side onnx inference | Rejected — dep too heavy |
| (B) Precomputed sparse → Qdrant native RRF | Full stack in Qdrant, scales, filters on Prefetch, no app index to maintain | Schema migration (create_vector_name + reindex), more complex upsert, test fake changes | Deferred to v2 |
| (C) `rank-bm25` + app-level RRF | 8.6 kB dep (numpy only), no schema migration, fully offline, simple to test, fast on small corpus | In-memory index, no server-side IDF, slightly more app logic, doesn't scale to millions of chunks | **RECOMMENDED for v1** |
| Full collection recreate | Clean slate, all vectors aligned | Full re-embed (O(corpus)), user downtime, unnecessary given `create_vector_name` | Rejected — unnecessary |
| `bm25s` (alternative to rank-bm25) | Faster on large corpora, scipy optional | scipy dep (37MB) if used, same concept | Deferred — overkill at <1k chunks |

---

## Key Findings

1. **`create_vector_name` works in qdrant-client 1.18.0 to add a sparse vector to an existing unnamed-dense collection in-place.** Collection recreation is NOT required. This resolves the spec-scope's "central architectural decision." The unnamed dense vector can be referenced as `using=None` in `Prefetch`.

2. **For Qdrant native `FusionQuery(Fusion.RRF)`, the `query_filter` parameter on `query_points` is NOT applied to the fused results.** Filters MUST be placed on each `Prefetch` object. Verified by inspecting `local_collection.py:814-848` and confirmed by live test.

3. **FastEmbed is required for `models.Document` BM25 on local Qdrant** — there is no server-side inference in standard self-hosted Docker Qdrant. FastEmbed adds onnxruntime (~200MB), making it too heavy for this project's supply-chain posture.

4. **`rank-bm25` adds only numpy (already present) as a new dependency** — 8.6 kB wheel, no onnxruntime, no torch. The cleanest sparse signal for v1.

5. **Qdrant's RRF k constant is 2 (not the academic standard 60).** The formula `1/((pos+1)/weight + k - 1)` at k=2,weight=1 gives rank-1 score 0.5, rank-2 score 0.333. App-level RRF should use k=60 (academic standard, empirically validated) not Qdrant's k=2.

6. **`semantic_search_core` does not need to change.** Fusion logic goes into a new `hybrid_search_core` wrapper, preserving the `test_no_filter_regression` contract byte-identically.

7. **`update_collection` with `sparse_vectors_config` does NOT add new sparse vectors** to an existing collection (returns "Vector sparse does not exist in the collection"). Use `create_vector_name` instead.

---

## Recommendations

1. **v1 implementation:** `rank-bm25` app-level BM25 + app-level RRF (`k=60`). Add `rank-bm25>=0.2.2,<1.0.0` to `pyproject.toml` dependencies. No Qdrant schema change in v1.

2. **v2 (native Qdrant, future):** `create_vector_name('sparse', SparseVectorNameConfig(sparse=SparseVectorConfig()))` added to `_ensure_collection`, bump `PAYLOAD_SCHEMA_VERSION` to trigger backfill, upsert with `vector={'': dense, 'sparse': SparseVector(...)}`, use native `FusionQuery(Fusion.RRF)` with `filter` on each `Prefetch`.

3. **`hybrid_search_core` as the new public API.** Both `server.py:semantic_search` and `query.py:wiki_query` Tier-2 call `hybrid_search_core` instead of `semantic_search_core`. `semantic_search_core` stays unchanged (called internally by `hybrid_search_core`).

4. **Evaluation:** Curate 10–15 test queries from known failure cases (starting with the `contradiction detection` case from the live reproduction). Implement as `@pytest.mark.live` tests with `Recall@5` metric. Run before and after to prove improvement.

5. **Fallback:** BM25 index build or query failure silently degrades to dense-only (no error surfaced to the caller). Qdrant unavailability propagates as today.

---

## Open Questions

1. **BM25 index persistence across restarts.** The in-memory BM25 index must be rebuilt on server restart. At 500 chunks this is fast (< 1 second). Is a cold-start latency acceptable, or should the index be serialized to disk (e.g., pickle, or a JSON file alongside `state.json`)?

2. **Tokenizer for BM25.** `rank-bm25` defaults to whitespace tokenization. Should stopword removal, stemming, or lowercasing be applied? For technical wiki content (object names, code terms), simple lowercased whitespace split is probably sufficient. Needs a decision before implementation.

3. **BM25 index scope (chunks vs objects).** BM25 operates at chunk level (matching `semantic_search_core` granularity). Dedup of object_ids from chunk-level results mirrors the existing `wiki_query` Tier-2 dedup. This should be the correct approach.

4. **Prefetch limit sizing for native RRF (v2).** For a `limit=10` final result, each Prefetch should fetch `limit * 2 = 20` candidates to give RRF enough input to fuse. This is already accounted for in the `hybrid_search_core` design above (`limit * 2` for each signal).

5. **`create_vector_name` behavior on real Qdrant Docker server.** Tested on in-memory client only. The Qdrant docs confirm it is available from v1.18.0, and the REST API endpoint `PUT /collections/{name}/vectors/{vector_name}` exists. But real-server behavior (especially for unnamed-dense + sparse mix) should be tested against the running local Docker Qdrant before the v2 implementation.

---

## Sources

- `src/anytype_llm_wiki/indexer.py` — `semantic_search_core`, `_ensure_collection`, `_run_reindex`
- `src/anytype_llm_wiki/config.py` — `PAYLOAD_SCHEMA_VERSION = 3`
- `src/anytype_llm_wiki/chunker.py` — `WIKI_TEXT_PROPERTY_KEYS`, chunk shape
- `src/anytype_llm_wiki/server.py` — `semantic_search`, `_SEMANTIC_SEARCH_DEFAULT_TYPES`
- `src/anytype_llm_wiki/wiki/query.py:638-694` — Tier-2 `semantic_search_core` call
- `.aldeia/327-retrieval-lexical-hybrid-dense-sparse-fusion/spec-scope.md` — verified code reality
- `.aldeia/323-retrieval-metadata-filters-type-tag-scoping-for-wi/spec.md` — migration pattern D3
- `.venv/lib/python3.13/site-packages/qdrant_client/local/local_collection.py:814-848` — `_merge_sources` FusionQuery implementation (filter not applied at top level)
- `.venv/lib/python3.13/site-packages/qdrant_client/hybrid/fusion.py` — `reciprocal_rank_fusion`, `DEFAULT_RANKING_CONSTANT_K = 2`
- `uv run python -c "from qdrant_client.models import Fusion, FusionQuery, Prefetch, SparseVector, SparseVectorParams, SparseVectorNameConfig, SparseVectorConfig; ..."` — verified imports
- `uv run python -c "client.create_vector_name(...)"` — in-place sparse add confirmed
- `uv run python -c "client.query_points(prefetch=[...], query=FusionQuery(Fusion.RRF))"` — end-to-end fusion verified
- `uv pip install --dry-run rank-bm25` → "Would install 1 package: rank-bm25==0.2.2"
- `uv pip install --dry-run fastembed` → 19 packages including onnxruntime
- [Qdrant Hybrid Search Revamped](https://qdrant.tech/articles/hybrid-search/)
- [Qdrant Hybrid Queries documentation](https://qdrant.tech/documentation/search/hybrid-queries/)
- [Qdrant Vectors management — add named vector](https://qdrant.tech/documentation/manage-data/vectors/)
- [Qdrant Text Search / BM25](https://qdrant.tech/documentation/search/text-search/)
- [rank-bm25 on PyPI](https://pypi.org/project/rank-bm25/)
