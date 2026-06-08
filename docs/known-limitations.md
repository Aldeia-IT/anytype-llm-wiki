# Known limitations (v0.2.0)

This document records behaviors that are understood, accepted for the v0.2.0
internal/foundation tranche, and tracked for reconciliation before the public
release and/or v0.3.0. Each item notes the source (a live verification run on
Anytype local API `2025-11-08`, or the post-implementation review
`impl-review-r2.md`).

## 1. Cross-host bootstrap dedup relies on Anytype-side `type_key`, not the file lock

`wiki_bootstrap` serializes concurrent runs **on a single host** with an
`fcntl.flock` advisory lock under `WIKI_LOCK_DIR`. `fcntl.flock` is **local to
one machine** — two different hosts bootstrapping the *same shared vault* at the
same time will not see each other's lock.

The cross-host safeguard is therefore **Anytype-side idempotency**, not the
file lock:

- **Types** are keyed by a space-unique `type_key`; creating an existing key
  links/returns the existing type rather than duplicating (verified live).
- **Domain tags** are de-duplicated by name within the `wiki_domain_tags`
  property before creation.
- **Root "Wiki" collection** is detected by name and reused.

What is **not** cross-host safe: the **WikiLog** audit entries (one is appended
per run by design — see §2) and any genuinely concurrent first-create race
window on the Anytype server. In practice the recommended operating model is to
bootstrap a shared vault from **one** host. A true two-host concurrent probe was
not run (requires two machines sharing one vault).

**Status:** accepted for v0.2.0. Re-evaluate if multi-host concurrent bootstrap
becomes a supported workflow.

## 2. The schema-version marker lives on the WikiLog, and WikiLog entries accumulate

(`impl-review-r2.md` SHOULD-FIX-1 / ADVISORY-1.)

- The spec (§Schema Compatibility, AC #13) specifies that the **root Collection**
  carries `wiki_schema_version`. The current implementation stamps the version on
  the per-run **WikiLog** object instead, because the system `collection` type
  did not reliably persist a custom property (and the create-type `layout` enum
  has no `collection` option for a wiki-owned collection type).
- Consequently every `wiki_bootstrap` run appends a **new** WikiLog entry, and
  each carries the version marker. Upgrade detection (`_max_version` across all
  objects) is **correct** regardless (it selects the highest version), but:
  - the "idempotent / zero duplicates" property does **not** apply to the WikiLog
    marker object itself; and
  - this diverges from the spec's "marker on the root Collection" wording.

**Status:** **Resolved in v0.3.0** (ticket #284) via option (a): `wiki_bootstrap`
now PATCHes `wiki_schema_version` onto the long-lived root Collection
(`_patch_schema_version_on_collection`), and `_read_schema_version` returns
`max(collection_value, wikilog_max)` so a stale Collection marker cannot mask a
newer WikiLog (SF7). The per-run WikiLog stamp is retained as an informational
fallback; WikiLog accumulation is unchanged but no longer the authoritative marker.

## 3. `wiki_action` is not written on the bootstrap WikiLog entry

(`impl-review-r2.md` SHOULD-FIX-2.)

`wiki_action` is a `select` property. Writing a select value requires a
pre-existing tag (option) id; the bootstrap WikiLog write omits it rather than
fail. The spec defines `wiki_action` as the primary WikiLog discriminator
(grouped on by the v0.5.0 lint). No v0.2.0 consumer depends on it.

**Status:** **Resolved in v0.3.0** (ticket #284): `wiki_bootstrap` now creates all
five `wiki_action` tag options (`ingest`/`query`/`lint`/`bootstrap`/`archive`,
idempotent/union-only via `_ensure_wiki_action_tags`) and stamps the bootstrap
WikiLog with `wiki_action = bootstrap`; `wiki_ingest` stamps `wiki_action = ingest`
(degraded-but-written if tag resolution fails).

## 4. Anytype ignores PATCH of an object `body` (returns 2xx, does not persist)

(verify-anytype-writes.sh → `patch-decision.md`: `patch_body_updates:
silently_ignored`.)

A `PATCH /v1/spaces/{id}/objects/{id}` with a `body` field returns success but
the re-read does not reflect the change on API `2025-11-08`. The module's
recorded `implementation_path` is therefore `fallback_properties_only`: durable
content must be written via **properties** (or the object's initial create
`body`), never via a `body` PATCH. PATCH of a **property** (e.g. `name`) works.

## 5. Anytype search ignores the `type_key` FilterExpression

(verify-anytype-writes.sh → `patch-decision.md`: `filter_expression: no_op`.)

`POST /v1/spaces/{id}/search` with
`filter={"condition":"and","filters":[{"key":"type_key","condition":"eq",...}]}`
returns the **same** result set as an unfiltered query (an impossible type also
returned the full set). Type-scoped server-side search is therefore **not**
effective with the current filter shape on API `2025-11-08`.

This does **not** affect the v0.2.0 MCP `semantic_search` tool, which queries
**Qdrant** vectors (with optional client-side filtering), not Anytype's search
endpoint. `WikiClient.search(... filter={"type_key": X})` should not be relied
on for type scoping until the correct filter contract is confirmed.

**Status:** tracked for the version that uses Anytype-native filtered search.

## 6. Re-ingest idempotency depends on deterministic extraction

`wiki_ingest` is idempotent on re-ingest of the **same** source — a second ingest
creates 0 new objects and reuses the existing Source — **because extraction uses
deterministic decoding** (`temperature: 0` + fixed seed), so the same source
yields the same entity titles, which entity resolution (exact + fuzzy title
match) then resolves to the existing objects. Verified live and pinned by
`tests/wiki/test_ingest.py::TestReingestIdempotency`.

Residual caveats:
- If `WIKI_EXTRACT_ENDPOINT` points at a non-deterministic remote model, re-extraction may vary and produce near-duplicate entities on re-ingest.
- Resolution is title-based (exact + fuzzy ≥ 0.92; the embedding sweep is not yet implemented), so genuinely different surface forms of the same concept across *different* sources can still create separate objects.
- Resolution is also **type-scoped**: the same normalized title as both a `wiki_entity` and a `wiki_concept` (a cross-kind twin) is never merged, and an abbreviation/expansion pair like "AXE" vs "AXE token" falls below the 0.92 threshold.

These are now **detected** by the lint potential-duplicate sweep, which runs an
embedding-independent **title pass** (identical normalized titles incl. cross-kind,
plus token-subset pairs) alongside the vector pass, scoped to entity/concept
objects so Query objects are never flagged. **Prevention at write time** (an
embedding nearest-neighbour check inside `resolve_entity`) remains the deferred
follow-up (aldeia-box#286); see
[architecture §5](./architecture.md#5-entity-resolution--duplicate-handling).

## 7. Filed `wiki_query` answers surface only after the next reindex (compounding latency)

(v0.4.0, ticket #285 — `wiki_query` file-back.)

`wiki_query` can file a synthesized answer back as a typed **Query Object**
(`file_back=True`, or the default gate of ≥ 3 cited sources AND ≥ 100 words on a
clean answer). This closes the compounding loop: a filed answer becomes a
retrieval candidate for future queries. However, it does **not** become
retrievable immediately.

- A filed Query Object is written to the Anytype vault synchronously, but its
  `wiki_answer` is embedded into the Qdrant index only on the **next**
  `reindex_anytype` run. Until that reindex, Tier-2 (vector-augmented) retrieval
  cannot surface the filed answer.
- If you rely on the scheduled background reindex (`WIKI_AUTO_REINDEX` / launchd
  cadence), the compounding latency is bounded by that cadence. A slow cadence
  delays when a filed answer starts helping future queries; it does **not** add
  per-query latency (the count/enumerate/synthesis path is unaffected).
- Meaningful Tier-2 compounding also depends on the v0.3.0+ indexer
  property-embedding behavior (#284): wiki content stored in text properties
  (`wiki_answer`, `wiki_question`, …) must be embedded for filed Query Objects to
  appear as candidates.

**Status:** accepted for v0.4.0. A filed answer is durable in the vault
immediately; only its *vector retrievability* waits for the next reindex.
Verified by the mocked CI backstop
`tests/wiki/test_query.py::TestCompoundingBackstop::test_filed_query_retrievable_after_reindex`.

## 8. `wiki_query` candidate/neighbor objects are sourced from the enumeration snapshot when a permissive mock or partial fetch occurs

(v0.4.0, ticket #285.)

`wiki_query` fetches each candidate and 1-hop neighbor via
`AnytypeReadClient.get_object` (one fetch per unique id, via a per-run cache).
When a `get_object` call returns a non-object response (a list envelope from a
permissive test mock) rather than the `{"object": …}` shape, the implementation
falls back to the object as it appeared in the initial `list_objects`
enumeration snapshot. A genuine HTTP error (404 / connection failure) is treated
as a real fetch failure (the object is dropped and the result is downgraded to
`partial`), not masked by the snapshot. This fallback exists for resilience and
is exercised by the CI suite; live behavior (where `get_object` returns the real
object shape) is pinned by the skip-gated live smoke test
(`tests/wiki/test_query.py::TestQueryLive`).

## 9. `wiki_query` enumerates the whole wiki on every call — O(N) scaling cliff

(v0.4.0, ticket #285.)

Every `wiki_query` calls `list_objects` to enumerate the entire wiki on **both**
tiers — Tier 1 navigation reads the full object set, and Tier 2 still enumerates
to compute the count that selects the tier (`WIKI_INDEX_THRESHOLD=200`). Cost is
therefore O(N) in the number of wiki objects, per query. Compounding this, the
optional file-back of a synthesis as a reusable Query Object monotonically grows
N over time, so sustained dogfooding trends the per-query latency toward the p95
ceiling over months.

This is correct and acceptable at the current dogfooding scale (hundreds of
objects). The fix is deferred to **v0.5.0**: cache the object count / index size
(invalidated on write) so the tier decision and Tier 1 navigation avoid a full
re-enumeration on every call. Tracked here rather than as a separate ticket
(per maintainer decision); raised by the post-impl council and prior #285
councils.

## 10. `wiki_remember` holds the per-space lock for the whole (uncapped) drain

`wiki_remember` no longer caps or drops subjects — every extracted subject is
processed and durably logged (see [architecture §7](./architecture.md#7-the-no-drop-work-log-wikiworklog)).
The per-space write lock is held for that whole drain, and it is **fail-fast**
(`LOCK_EX | LOCK_NB`): a concurrent same-space `wiki_remember`/`wiki_ingest`
gets `[DATA ERROR] ingest_in_progress` rather than queuing. For a large narration
this hold can last as long as N sequential consolidations (each an LLM call).

This is accepted: on a single-user / single-agent vault, concurrent same-space
writes are rare, and the contender gets a clear, retryable error (no data is at
risk — the no-drop work-log makes any interrupted drain resumable). The complete
fairness fix — a **blocking-with-timeout** acquire plus **chunked lock release**
(release every K subjects so writers interleave; K as a fairness boundary, not a
data ceiling) — is **deferred on purpose**: it is an invasive refactor of the
most critical path for marginal single-user benefit, and the work-log already
makes mid-drain release safe to add later. See
[architecture §6](./architecture.md#6-concurrency-model--the-per-space-lock).

**Status:** accepted; revisit if multi-writer concurrency on one space becomes a
real workload.

## 11. Duplicate prevention is detect-only; cross-kind merges are deliberately not automatic

The lint duplicate sweep now *detects* cross-kind twins and abbreviation/expansion
pairs (§6 above), but `resolve_entity` does not yet *prevent* them at write time
(the embedding-resolve step is the deferred aldeia-box#286 follow-up). Note that
automatic merging across the entity↔concept boundary is intentionally **not**
done even once embedding-resolve lands — consolidating a concept's definition
into an entity (or vice-versa) changes meaning — so cross-kind twins will always
be surfaced for human/agent merge rather than merged silently.

**Status:** detection shipped; write-time prevention for same-kind near-dupes
tracked (aldeia-box#286); cross-kind auto-merge intentionally out of scope.
