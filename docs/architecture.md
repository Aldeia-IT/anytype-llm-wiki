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
3. **LLM alias adjudication** (v0.7.3, **EXPERIMENTAL — off by default**, entity/
   concept only) — when (1) and (2)
   miss, ask a local LLM whether the candidate denotes the *same real-world
   entity* as one of the same-type lexical search hits (alias / abbreviation /
   rename). Conservative (returns null unless confident; a part-of or related
   entity stays distinct — `Gnosis Safe` ≠ `Gnosis`), hallucinated-id-filtered,
   and **best-effort** (any LLM/transport failure → create; never blocks ingest).
   Same posture as contradiction detection. `wiki_source` dedup stays exact/fuzzy.
   **Off by default and model-gated:** a small model over-merges, so it runs only
   when `WIKI_ALIAS_ADJUDICATION` is on *and* the extraction model is **vetted**
   (prefix match; built-in `qwen3.5-mlx`, extend via `WIKI_ALIAS_VETTED_MODELS` —
   no force flag). Enabled-on-an-unvetted-model is an *unapproved config*: the MCP
   server **refuses to start** (exit 2, loud `[CONFIG ERROR]`), with the same guard
   at `wiki_ingest`/`wiki_remember` entry for one-shot CLI use.
   **⚠️ Known limitation (why it's experimental):** even the vetted model
   **over-merges distinct entities** on real, messy data — a real-graph eval saw
   ~7–10% over-merges (person→eponymous project, testnet→mainnet, collection→member).
   Because a merge is destructive, **leaving this off and using the non-destructive
   `wiki_lint --include-duplicates` suggestions (human-reviewed) is the recommended
   curation path.** A future revision will route the adjudicator's judgment into
   those `potential_duplicate` *suggestions* rather than auto-merging at write time.
4. otherwise → create.

Consequences (and where dupes come from):

- **Cross-kind twins** — the same normalized title as a `wiki_entity` *and* a
  `wiki_concept` are never merged, because resolution only looks within one type.
- **Abbreviation/expansion** — "AXE" vs "AXE token" sits below the 0.92 fuzzy
  threshold; step (3) now catches the true-alias cases the LLM is confident about,
  while genuinely distinct near-matches still create.

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

## 6. Concurrency model — queue-submit, single drainer

`wiki_remember` is built for a **fleet**: independent agents on separate PIDs /
terminals (each running `/wiki-learn`) write the *same* space concurrently. The
model is **submit + drain**, so concurrent submitters never block and never lose
writes — read-after-write is explicitly not guaranteed (the knowledge is for the
*next* agent on that client/project).

**Submit (lock-free).** `wiki_remember` does `extract` (read-only LLM, no lock)
→ `worklog.begin` (a durable, fsync'd, **lock-free append** of the extracted
subjects to the per-space work-log, §7). Once `begin` returns, the subjects are
durable. This is the "submit."

**Drain (single holder, drain-until-dry).** The per-space `fcntl.flock`
(`space_ingest_lock`) now guards only *draining*. After submitting, a caller
tries to become the drainer via a **bounded non-blocking retry**
(`_acquire_and_run`, a few NB attempts over ~0.3 s):

- **Acquired** → it runs **drain-until-dry**: re-read `load_pending` each pass and
  apply every pending batch, until the queue is empty, then `compact`. Because it
  re-reads each pass, subjects another PID appended *during* the drain are swept
  up by this same holder.
- **Not acquired** → another writer holds the lock and is draining; the caller
  returns `queued_for_drain`. Its append is durable and the current holder's
  drain-until-dry applies it.

Why the lock exists at all: `resolve_entity` does read-candidates → decide-create,
which is **not atomic**; serializing the drain is load-bearing for dedup
correctness (§5).

**Who drains a queued submitter's work — the holder, not a future agent.** This
is the crux. If B can't acquire while A is draining, A's drain-until-dry loop sees
B's append (B appended before retrying) and applies it. The one microsecond race —
B appends in the gap between A's final empty-check and A's release — is closed by
B's bounded retry: B keeps trying NB-acquire, and A's release is imminent, so B
grabs the lock and drains its *own* work. `compact()` is gated on an empty queue,
so even in that race B's record is never deleted, only delayed. We do **not**
depend on the next organic submit. The only fall-through is true pathology (a PID
crashes between `begin` and draining), for which there is an explicit
`wiki-drain --space-id` CLI backstop (`remember.drain_pending`) — runnable on
demand or via cron, never an unbounded wait on traffic.

**`wiki_ingest` participates.** Holding the lock obligates draining the queue:
`wiki_ingest` acquires with the same bounded retry (waits politely instead of
fail-fast) and **drains pending `wiki_remember` subjects first**, then does its
own work — so a long ingest never starves queued learnings. It stays synchronous
(the operator wants its result inline); if the lock stays held for the whole
retry budget it returns `ingest_in_progress` for the operator to retry.

**Extraction is lock-free.** Since submit appends and only draining holds the
lock, the long extraction LLM call never holds it — the per-space critical
section is just resolve → write → relations, kept short.

**Cross-host caveat (important for fleets).** `fcntl.flock` is **host-local** —
it serializes processes on the *same* machine that share `WIKI_LOCK_DIR` (the
common fleet case: several agents/terminals on one host, default `~/.local/share`,
sharing one `WIKI_WORKLOG_DIR`). It does **not** cover writers on *different*
hosts (or containers without a shared lock-dir volume) writing the *same* vault:
flock gives them no mutual exclusion, so their `resolve→create` genuinely
interleaves → duplicate entities and clobbered relation arrays (same limitation
`wiki_bootstrap` notes in known-limitations §1). **Operating constraint: write a
shared vault from a single host.** A cross-host guard needs an Anytype-side
compare-and-set, not a file lock.

## 7. The no-drop work-log (`wiki/worklog.py`)

**The guarantee: a `wiki_remember` run never silently drops an extracted
subject, even across a crash.**

History: `wiki_remember` used to truncate its subject list to a hard
`_MAX_SUBJECTS = 8` ("fan-out cap") and discard the rest with only a
`subject_cap_exceeded` warning — unbounded, irrecoverable data loss, applied
inconsistently (`wiki_ingest` had no such cap). The cap's only purpose was to
bound how long the per-space lock was held; it paid for that with dropped
knowledge.

The work-log is also the **submission queue** for the concurrency model (§6): a
lock-free `begin` append is how a fleet submitter durably hands off its subjects
to whichever PID drains.

The replacement is a **write-ahead log**:

- A JSONL file per space under `WIKI_WORKLOG_DIR` (stdlib only — `json`/`os`/
  `uuid`/`hashlib`/`re`; no database, no service, no new dependency).
- `begin()` records **every** extracted subject (with stable ids) and an
  `fsync` **before** the drain starts; `mark_done()` per subject; `compact()`
  deletes the file once all subjects are done.
- Records are append-only single lines, each `flush + fsync`; the **first** write
  to a new log also fsyncs the parent directory so the new directory entry is
  durable (an fd fsync flushes file data, not the metadata that makes the file
  findable after a crash). Replay skips **any** unparseable line — a torn
  trailing write is the common case, but a mid-file partial is skipped the same
  way. Once `begin` returns, its subjects are durable.
- The drain-until-dry loop (§6) `load_pending()`s the log and applies every
  pending subject, finishing any left by an interrupted run. Consolidation is
  best-effort idempotent (it relies on the LLM returning equal text for an
  already-applied subject — cf. known-limitations §6), so re-processing converges
  to a no-op in the normal case.
- **Locking contract:** `begin` (append) is **lock-free** — that is what lets a
  fleet submitter hand off without blocking. Everything else — `load_pending`,
  draining, `mark_done`, `compact` — **must hold the per-space lock** (it
  serializes drainers and makes `compact`'s read-then-remove atomic against a
  concurrent `begin`). The call sites enforce this.

All work-log calls in `remember.py` are guarded: a work-log failure degrades to
in-process processing with a warning — never a dropped subject, never a broken
run. **Scope of the no-drop guarantee:** it covers process death
(crash/kill/timeout) and work-log I/O failure. A *per-subject* API error during a
subject's write is reported (`status=partial`, `action="error"`) and that subject
is marked done — it is surfaced, not silently dropped, and not retried forever.

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

Older versions *did* write that reverse edge, so a space with pre-existing
file-back history carries **stale citation edges** (query ids inside entity
relation arrays). `wiki_lint` flags these as `stale_citation_edge` (High), and
the one-time `prune-citations` CLI command (`query.prune_stale_citation_edges`)
removes them idempotently — see [known-limitations §12](./known-limitations.md)
and [MIGRATIONS](../MIGRATIONS.md).

Injection note: the file-back loop is an amplifier (a poisoned synthesis,
re-ingested, becomes future retrieval material). The structural bounds are the
clean-synthesis precondition and the file-back gate — see
[security-and-data-flow](./security-and-data-flow.md).

## 9. Structural health (`wiki_lint`)

A read-only battery over a bootstrapped space (mutates nothing but one WikiLog
receipt):

- `asymmetric_relation` (High) — an outbound relation `A → B` whose reverse is
  not **reachable** from `B`. A directed `A → B` written only on `A`'s forward
  array still produces an Anytype backlink on `B`, so reciprocity holds when
  **any** of: `B`'s `backlinks` list `A` (the auto-reverse — the authoritative
  signal), `B`'s symmetric outbound contains `A`, or `A`'s `backlinks` list `B`.
  Only a genuinely dangling edge (target gone / no reverse at all) is reported.
  *(v0.7.2: was Critical, and the pre-v0.7.2 check read the **source's** backlinks
  instead of the target's, false-flagging every backlink-only directed edge.)*
- `stale_citation_edge` (High) — an entity/concept relation pointing at a
  `wiki_query` object (a leftover from old file-back); remove with the
  `prune-citations` command (§8).
- `contradiction_unresolved` (Critical, #287) — a `wiki_entity` carrying
  unresolved `wiki_contradictions` with no `wiki_last_reviewed`. *(v0.7.2:
  reranked from High — a semantic conflict outranks structural checks.)*
- `orphan` / `pipeline_orphan`, `staleness`, oversized descriptions,
  `empty_type`, unreviewed/stale `needs-review`, and the opt-in
  `potential_duplicate` sweep (§5).

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
