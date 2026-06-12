# Spec Scope: relationship-aware-retrieval (#324)

**Client:** anytype-llm-wiki · **Ticket:** Aldeia-IT/aldeia-box#324 · **Epic:** aldeia-box#140
**Branch:** aldeia/324-relationship-aware-retrieval-follow-anytype-relati

## One-line
Complete and harden the 1-hop neighbour traversal already present in `wiki_query` (added in v0.4.0 / spec #285) so that linked neighbours are **cited**, the relation set matches the product intent, the get_object fan-out is **bounded + measurable**, and the over-budget trim is deterministic by seed rank then relation priority.

## This is NOT greenfield — critical framing
`src/anytype_llm_wiki/wiki/query.py` **already** fetches each top-k seed's 1-hop neighbourhood (`_neighbor_ids_of`, `_fetch_cached` per-run cache, `_build_context` trim). #324 is a **modification of that existing path**, not a new feature. The spec MUST describe the *delta* against the locked #285 design and reference #285's locked invariants (SF5 dual-shape relation parser, per-run object cache, candidate/neighbor fetch sharing one `_fetch_cached` code path, error/partial status table) **by reference**, not recopy them. (Mem0 #289 lesson: append-only specs bloat and lower review fidelity.)

## Domains touched
- agent-operations / conventions (retrieval pipeline internals)
- product (citation correctness — answers must cite what they used)
- performance/infra (API fan-out, latency, call budget — the #287 constraint)

## The precise gap (current → desired)
| # | Current behaviour (v0.4.0) | #324 desired | AC |
|---|----------------------------|--------------|----|
| 1 | Neighbours feed synthesis CONTEXT but are NOT in `sources_consulted` (`contributing` = surviving **candidates only**, query.py:738-740). | Surviving neighbours that fed synthesis are **cited** in `sources_consulted`. | AC#1 |
| 2 | `_RELATION_KEYS = (wiki_relations, wiki_related, wiki_drew_from, wiki_subjects)` — **missing `wiki_sources`** (the entity/concept→Source "citations" edge), **has `wiki_subjects`** (not in #324's four). | Follow the four: `wiki_relations`, `wiki_related`, `wiki_sources`, `wiki_drew_from`. Decide explicitly whether to retain `wiki_subjects` (real comparison→subject edge). | AC#2 |
| 3 | Neighbour get_object fan-out is **unbounded** (every neighbour id fetched); only `synth_max_objects` caps the *context*, after fetching. | **Configurable cap** on neighbour fan-out BEFORE fetching; added get_object calls **logged/measurable**. | AC#5 |
| 4 | Over-budget trim drops neighbours first then weakest candidates; neighbours kept in **discovery order** (no relation priority). | Deterministic trim: **seed rank, then relation priority**. | AC#4 |
| 5 | Dedup vs seed set: already done (query.py:521,525). | Keep — no Object embedded twice. | AC#3 |

## Cross-cutting decisions the spec MUST make (flag, don't hand-wave)
1. **File-back interaction.** `_maybe_file_back` writes `sources_consulted` ids into the filed Query's `wiki_drew_from` and counts them toward the min-sources(3) gate. If neighbours now enter `sources_consulted`, do they enter `wiki_drew_from` and the gate? This touches the documented injection-amplifier bound. **Pick one** and justify: (a) cite neighbours in the result but keep file-back seed-only; (b) full provenance incl. neighbours. Recommend (a) unless research shows otherwise — keeps the #285 file-back invariant intact.
2. **`wiki_subjects` retention** — keep (5 keys) or strictly scope to the four (drop it)? State the call.
3. **Fan-out cap semantics** — per-seed cap, global cap, or both? New env knob name (e.g. `WIKI_QUERY_MAX_NEIGHBORS`) with default. Honor `_positive_int` SF10 guard pattern in config.py.
4. **Relation priority order** — define the total order over the four relation keys used for deterministic trim.

## Known prior learnings to inject (verified this session)
- **#287 (HIGH):** Anytype SEARCH responses do NOT hydrate objects-format relation arrays — `get_object` is the proven path. Reading a seed's relations needs a get_object per seed; each neighbour's content a further get_object. Fan-out is real → bound + document latency/call budget.
- **#289 spec-bloat:** reference inherited constraints by ID; keep prompts/schemas in separate files; fixer consolidates; ≥8 BLOCKING in R1 = scope/altitude signal.
- **#289 wire-contract:** pin verb+path+test-mock-to-mirror per endpoint. Here: `get_object` → `GET /v1/spaces/{space_id}/objects/{object_id}?format=md`, mirror `tests/wiki/test_query_fetch_paths.py`.
- **respx route-ordering:** new fetch-count/hydration tests belong in `test_query_fetch_paths.py` (single-dispatcher pattern), NOT `test_query.py` (catch-all GET shadows specific routes).
- **Test traceability:** every AC → named test(s).

## Estimated complexity: moderate
High reuse of the existing #285 traversal scaffolding. The risk is altitude, not volume — keep the spec a focused delta. Target: well under #289's bloat (aim ≤ ~600 lines, ≤ ~15 ACs).

## Files at risk of staleness if implemented
- `src/anytype_llm_wiki/wiki/query.py` (core change)
- `src/anytype_llm_wiki/wiki/config.py` (new fan-out knob)
- `tests/wiki/test_query_fetch_paths.py`, `tests/wiki/test_query.py` (coverage)
- `.env.example` (document new knob)
- `README.md` (roadmap line 236 → ship; tool description if behaviour changes)
- No CLAUDE.md (absent in this repo) — `.aldeia/context/technical.md` is the equivalent.
