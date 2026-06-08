# Architecture & internals

This document is the orientation map for anyone — human or agent — working *on*
anytype-llm-wiki (not just using it). It explains how the pipeline is wired, why
the load-bearing decisions are the way they are, and where the deliberate
trade-offs and deferred work live. Consumer-facing behavior is in the
[README](../README.md); data flow and threat model are in
[security-and-data-flow](./security-and-data-flow.md); accepted rough edges are
in [known-limitations](./known-limitations.md). This doc is the "why".

## 1. What it is

A local MCP server that turns an Anytype space into a typed, queryable knowledge
graph. Everything runs on `localhost`: **Anytype** (object store), **Qdrant**
(vector index), **Ollama** (local extraction/consolidation/embedding model).
Nothing leaves the machine unless an operator opts into a hosted
`WIKI_EXTRACT_ENDPOINT` (one-time consent gate).

## 2. The typed object model

The wiki is a small set of Anytype types created by `wiki_bootstrap`:

| Type | Holds | Key properties |
|------|-------|----------------|
| `wiki_entity` | a named thing (person, org, token, place) | `wiki_facts`, `wiki_relations`, `wiki_sources`, `wiki_status`, `wiki_contradictions` |
| `wiki_concept` | an idea/abstraction | `wiki_definition`, `wiki_related`, `wiki_open_questions`, `wiki_sources` |
| `wiki_query` | a filed Q&A from `wiki_query` | `wiki_question`, `wiki_answer`, `wiki_asked_at`, `wiki_drew_from` |
| `wiki_source` | provenance of an ingest/remember | source type tag, timestamps |
| `wiki_log` | append-only audit receipt per run | `wiki_action`, `wiki_notes`, `wiki_timestamp`, `wiki_schema_version` |
| `wiki_comparison` | (reserved) | — |

Objects carry **properties, not body text** — Anytype silently drops a `body`
PATCH (see known-limitations §4), so durable content lives in text properties.

## 3. The write pipeline (extract → resolve → consolidate → relate → log → reindex)

Both `wiki_ingest` (from a URL/file) and `wiki_remember` (from narration) run the
same backbone:

1. **Extract** — a local LLM turns the source/narration into candidate
   *subjects* (`{name, kind, facts}`) plus optional relations. Deterministic
   decoding (temp 0 + fixed seed) so re-runs converge (known-limitations §6).
2. **Resolve** — each subject's title is matched against existing objects
   (§5 below) to decide *update existing* vs *create new*.
3. **Consolidate** — on an update, an LLM merges the new facts into the existing
   `wiki_facts`/`wiki_definition` (§4 below). On a create, the object is created
   with properties only.
4. **Relations** — named `{from, to, label}` links are written **bidirectionally**
   between resolved subjects (`wiki_relations`/`wiki_related`).
5. **WikiLog** — one audit receipt per run, carrying the action and notes
   (supersede/conflict details).
6. **Reindex** — the new/updated objects are embedded into Qdrant
   (incremental). Until this runs, vector (Tier-2) retrieval can't see them.

## 4. Consolidation — how the wiki stays correct over time

There is **no crawler and no self-refresh**. Reality is corrected only by new
writes: `wiki_remember` (incl. `/wiki-learn`), `wiki_ingest`, or a human editing
in Anytype. The consolidation prompt (`wiki/prompts/consolidate.md`) classifies
each incoming fact as `merge | add | supersede | keep | conflict`:

- **supersede** → the old fact is replaced in the consolidated text (audited in
  the WikiLog).
- **conflict** → **both** facts are kept, the new one is inline-tagged
  `[CONFLICT: reason]`, and `wiki_status` flips to **`needs-review`**. Nothing is
  silently overwritten. `wiki_ingest` additionally writes `wiki_contradictions`
  links between the conflicting objects (cross-object detection, #287).

`wiki_lint` then surfaces unresolved contradictions and staleness; a human
resolves them. **Important nuance:** whether a correction lands as *supersede*
(clean replace) or *conflict* (both kept, needs-review) is the model's judgment.
Phrasing nudges it — "X replaced Y / Y is no longer true" leans supersede; "X,
but actually Y" leans conflict. So narrating a correction does not always reach
clean truth on its own; you may then need to review the flagged object and edit
out the stale clause. Re-asserting the *same* knowledge converges to a no-op.

## 5. Entity resolution & duplicate handling

`resolve_entity` (in `ingest.py`) is **type-scoped** and **title-based**:

1. exact match on the normalized title (NFC + dash-fold + casefold + whitespace
   collapse) among same-type candidates → update;
2. fuzzy `SequenceMatcher` ratio ≥ `0.92` among same-type candidates → update;
3. otherwise → create.

Consequences (and where dupes come from):

- **Cross-kind twins** — the same normalized title as a `wiki_entity` *and* a
  `wiki_concept` are never merged, because resolution only looks within one type.
- **Abbreviation/expansion** — "AXE" vs "AXE token" sits well below 0.92, so both
  are created.

These are *detected* (not yet prevented) by `wiki_lint`'s opt-in duplicate sweep,
which has two passes, both scoped to `_DEDUP_TYPES = (entity, concept)` so Query
objects are never candidates:

- **title pass** (embedding-independent) — flags identical normalized titles
  (incl. cross-kind) and token-subset pairs ("axe" ⊂ "axe token");
- **embedding pass** — Qdrant nearest-neighbours within a score band, candidate
  type re-checked defensively.

**Deferred:** prevention at write time via an embedding nearest-neighbour check
inside `resolve_entity` (the "Step 3 embedding sweep" stub) — tracked as the
dedup follow-up (aldeia-box#286). Auto-merging across the entity/concept kind
boundary is intentionally *not* done (it would consolidate a definition into an
entity), so cross-kind twins are surfaced for human merge rather than merged
automatically.

## 6. Concurrency model — the per-space lock

All writes to a space are serialized by an **advisory file lock**
(`fcntl.flock`, `LOCK_EX | LOCK_NB`) under `WIKI_LOCK_DIR`, one file per space
(`space_ingest_lock`). It is **non-blocking / fail-fast**: if another run holds
the lock, the new run does **not** queue — it raises
`[DATA ERROR] ingest_in_progress` immediately.

Why the lock exists: `resolve_entity` does read-candidates → decide-create, which
is **not atomic**. Two concurrent writers resolving the same name would both miss
and both create — the duplicate class in §5. The lock makes resolve→write
serial per space, which is load-bearing for dedup correctness.

**Why extraction runs *inside* the lock.** Extraction is a read-only LLM call
(no writes) and the single longest step — minutes on a large local model. It is
tempting to move it outside the lock to shrink the critical section. We don't,
and the trade-off is the reason: under the *fail-fast* lock, a contender that
extracted *before* checking the lock would pay for a multi-minute extraction and
*then* fail with `ingest_in_progress` — wasted work. Keeping extract under the
lock lets a contender fail fast without that waste. (This is asserted by
`test_space_lock_held_returns_ingest_in_progress`.)

### Deferred: blocking acquire + chunked release

The complete fairness fix — so a long drain neither rejects nor indefinitely
blocks a concurrent same-space writer — is:

1. a **blocking-with-timeout** acquire (wait your turn, don't hard-fail), and
2. **chunked lock release**: process subjects in chunks of K, releasing the lock
   between chunks so other writers interleave. K becomes a *fairness* boundary,
   not a data ceiling.

This is **deferred on purpose**. It is an invasive refactor of the most critical,
most-tested path, its real-world benefit is marginal on a single-user/single-
agent vault (concurrent same-space writes are rare), and the no-loss work-log
(§7) already makes mid-drain release *safe to add later* (an interrupted chunk
just resumes). The current fail-fast behavior is correct and bounded; the
contender gets a clear, retryable error. Revisit if multi-writer concurrency on
one space becomes a real workload.

## 7. The no-drop work-log (`wiki/worklog.py`)

**The guarantee: a `wiki_remember` run never silently drops an extracted
subject, even across a crash.**

History: `wiki_remember` used to truncate its subject list to a hard
`_MAX_SUBJECTS = 8` ("fan-out cap") and discard the rest with only a
`subject_cap_exceeded` warning — unbounded, irrecoverable data loss, applied
inconsistently (`wiki_ingest` had no such cap). The cap's only purpose was to
bound how long the per-space lock was held (§6); it paid for that with dropped
knowledge.

The replacement is a **write-ahead log**:

- A JSONL file per space under `WIKI_WORKLOG_DIR` (stdlib only — `json`/`os`; no
  database, no service, no new dependency).
- `begin()` records **every** extracted subject (with stable ids) and an
  `fsync` **before** the drain starts; `mark_done()` per subject; `compact()`
  deletes the file once all subjects are done.
- Records are append-only single lines, each `flush + fsync`. A crash can only
  corrupt the trailing line, which replay skips. Once `begin` returns, the
  subjects are durable.
- On the next run, `load_pending()` replays the log and **folds any unfinished
  subjects back into the current batch**, finishing them. Consolidation is
  idempotent, so re-processing a partially-applied subject converges to a no-op.

All work-log calls in `remember.py` are guarded: a work-log failure degrades to
in-process processing with a warning — never a dropped subject, never a broken
run. The lock is held for the whole (now uncapped) drain; bounding that hold is
the deferred §6 work, **not** a reason to cap or drop.

## 8. Retrieval & the compounding loop (`wiki_query`)

`wiki_query` enumerates the wiki, picks a **tier** by object count
(`WIKI_INDEX_THRESHOLD`, default 200): Tier 1 index-navigation below it, Tier 2
vector-augmented at/above. It fetches candidates + their 1-hop neighbourhood,
synthesizes a prose answer from that bounded context, and — when the answer is
clean and meets the file-back gate (≥ 3 cited sources **and** ≥ 100 words, or
`file_back=True`) — files the Q&A back as a `wiki_query` object so the next
reindex makes it retrievable. That is the **compounding loop**: a filed answer
becomes a source for future questions.

### Citation edges: `wiki_drew_from` + backlinks, one direction only

A filed Query object links to its sources via `wiki_drew_from`. It does **not**
write a reverse edge into each cited entity's `wiki_relations`. A citation is
*directional provenance*, not a *bidirectional semantic relation*; writing the
reverse edge conflated "relates to" with "was cited by", surfaced Query objects
as entity neighbours / duplicate candidates, and — because the reverse edge would
live under a different key than `wiki_lint`'s symmetry check reads — produced a
flood of false `asymmetric_relation` (Critical) findings. The reverse "cited by"
view is served for free by **Anytype backlinks**, auto-derived from
`wiki_drew_from`.

Injection note: the file-back loop is an amplifier (a poisoned synthesis,
re-ingested, becomes future retrieval material). The structural bounds are the
clean-synthesis precondition and the file-back gate — see
[security-and-data-flow](./security-and-data-flow.md).

## 9. Structural health (`wiki_lint`)

A read-only battery over a bootstrapped space (mutates nothing but one WikiLog
receipt):

- `asymmetric_relation` (Critical) — an outbound relation whose target doesn't
  reciprocate. Reciprocity is confirmed by **either** the target appearing in
  `backlinks` **or** the target's symmetric outbound containing the source
  (either signal suffices — neither is trusted alone).
- `orphan` / `pipeline_orphan`, `contradiction_unresolved` (#287),
  `staleness`, oversized descriptions, `empty_type`, unreviewed/stale
  `needs-review`, and the opt-in `potential_duplicate` sweep (§5).

The default (sweep-off) path targets ≤ 60 s / ≤ 500 objects; the opt-in duplicate
sweep embeds objects and can exceed that.

## 10. State, storage, and configuration

| State | Location | Notes |
|-------|----------|-------|
| Knowledge objects | Anytype (localhost) | the source of truth |
| Vectors | Qdrant (localhost) | rebuilt by reindex; treat as sensitive (embedding inversion) |
| Per-space write lock | `WIKI_LOCK_DIR` (`~/.local/share/anytype-llm-wiki/locks`) | `fcntl.flock`, host-local |
| Subject work-log | `WIKI_WORKLOG_DIR` (`~/.local/share/anytype-llm-wiki/worklog`) | JSONL, crash-resume (§7) |

Config is environment-driven, resolved per-call (not cached at import) so tests
can monkeypatch — see `wiki/config.py`. Notable knobs: `WIKI_INDEX_THRESHOLD`,
`WIKI_FILE_BACK_MIN_SOURCES`/`_MIN_WORDS`, `WIKI_EXTRACT_ENDPOINT`/`_MODEL`/
`_TIMEOUT`, `WIKI_LINT_DUPLICATE_MAX_SCORE`/`_MAX_OBJECTS`, `WIKI_LOCK_DIR`,
`WIKI_WORKLOG_DIR`.

## 11. Map for contributors

| Area | File |
|------|------|
| MCP tool surface | `wiki/server.py` |
| Bootstrap / schema | `wiki/bootstrap.py`, `wiki/types_schema.py` |
| Ingest pipeline, resolution, contradictions | `wiki/ingest.py` |
| Remember pipeline, no-drop drain | `wiki/remember.py` |
| Durable subject work-log | `wiki/worklog.py` |
| Query / file-back / compounding | `wiki/query.py` |
| Structural health | `wiki/lint.py` |
| Extraction/consolidation/synthesis prompts | `wiki/prompts/*.md` |
| Per-space lock, normalization | `wiki/util.py` |
| Config (env, per-call) | `wiki/config.py` |

When you change behavior here, update this doc, [known-limitations](./known-limitations.md),
and the `CHANGELOG`.
