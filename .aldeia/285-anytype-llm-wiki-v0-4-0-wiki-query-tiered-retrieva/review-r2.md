# Spec Review — R2 (post-fix): wiki_query v0.4.0 (#285)

**Date:** 2026-06-04
**Spec:** `.aldeia/285-anytype-llm-wiki-v0-4-0-wiki-query-tiered-retrieva/spec.md` (732 lines, 20 ACs)
**Scope:** verify R1 findings (B1–B11, SF1–SF11) resolved CORRECTLY against the real codebase; flag new defects.

## Verdict: APPROVED WITH CONDITIONS

**Severity totals (new/unresolved only):** BLOCKING 1 · SHOULD-FIX 1 · SUGGESTION 4

All eleven R1 BLOCKING items (B1–B11) are correctly resolved and code-verified. The one BLOCKING
condition below is a NEW defect the SF11 fix introduced: the spec asserts a behavior of
`_write_bidirectional_relations` that the real helper does not have, which would silently regress
existing relation arrays during file-back. Fix that one claim and the spec is approvable.

---

## (a) R1 findings NOT correctly resolved

None. **All B1–B11 verified resolved** (code-checked where applicable):

- **B1** — nested AND-of-OR confirmed: a `Filter(should=[...])` group appended to `must`
  (spec.md:96-101); `min_should=1` explicitly rejected as a type error (spec.md:84-89);
  `types is None` → no filter (spec.md:104); both regression tests present
  (`test_multi_type_semantic_search_returns_results`, `test_single_type_semantic_search_unchanged`,
  spec.md:568-569). Matches the real bug at `server.py:51-55` (`Filter(must=conditions)`).
- **B2** — NEW `_call_ollama_synthesis` omits `format:json` and reads raw text (spec.md:138-139);
  reuse table claims only `_DETERMINISTIC_OPTS` + `_is_model_not_pulled` + config resolvers, and
  does NOT claim reuse of the JSON parser. Verified all reused pieces exist: `_DETERMINISTIC_OPTS`
  (`extraction.py:42`), `_is_model_not_pulled` (`extraction.py:92`); `_call_ollama_prompt` does
  hardcode `format:json` at `extraction.py:120,139` as stated.
- **B3** — search-core LOCKED to `indexer.py` (spec.md:108-115); no "server.py (or indexer.py)"
  ambiguity remains. Verified `indexer.py` imports only `config/anytype_client/chunker/embedder`
  (indexer.py:10-13) — no `server` import, nothing under `wiki/` imports it → import-safe. Note
  `embed_query` lives in `embedder.py:22` (not `server.py`); `embedder` is already imported by
  `indexer.py`, so "moved into the core" works.
- **B4** — fences ALL content + "DATA not INSTRUCTIONS" preamble (spec.md:152-158); AC#11 tests a
  CONTENT injection (`wiki_description`), not just a name (spec.md:625, test spec.md:573). The
  `WIKI_TEXT_PROPERTY_KEYS` set named in the spec exactly matches the real frozenset
  (`chunker.py:13-16`).
- **B5** — synth budget present: `WIKI_SYNTH_MAX_INPUT_TOKENS` (default = extract value),
  `_MAX_OBJECTS` (24), `_MAX_OBJECT_TOKENS` (1024), per-object head-truncation, trim order
  (neighbors first, then lowest-scored candidates), Resource Impact accounts for prompt size
  (spec.md:318-327,538-540). The `extract_max_input_tokens()`/`WIKI_EXTRACT_MAX_INPUT_TOKENS`
  addition is coherent: verified it is NOT implemented in code today (only a commented line in
  `.env.example:11`, no resolver in `config.py`), and the spec adds it with the `_positive_int`
  guard (spec.md:494-496). See SUG3 for one wording nit.
- **B6** — `ollama_model_not_pulled` used verbatim (spec.md:145,234); matches `extraction.py:184`
  and `ingest.py:495`. Ollama-down `[API ERROR] ollama_unavailable` path present (spec.md:146).
- **B7** — Anytype-down (`status: error`, no WikiLog) vs partial-neighborhood (`status: partial`,
  `neighbor_fetch_failed` warning) rows present and consistent (spec.md:389-395).
- **B8** — status-determination table present, first-match-wins, unambiguous (spec.md:380-387).
- **B9** — `error` + `error_category` added to QueryResult with a population table (spec.md:222-236).
- **B10** — mocked CI backstop `test_filed_query_retrievable_after_reindex` present (spec.md:581),
  AC#7 keeps live as additive (spec.md:621).
- **B11** — count==0 / zero-candidate path specified end-to-end (spec.md:282-288) with AC#15
  (spec.md:629) and `test_zero_candidate_returns_no_sources` (spec.md:575).

SF1–SF11 spot-checked and resolved, EXCEPT SF11's append claim — see BLOCKING below. (SF1
spec.md:337-340; SF2 spec.md:315-316; SF3 spec.md:329-333; SF4 spec.md:352; SF5 spec.md:298-302;
SF6 spec.md:533-534; SF7 spec.md:150,350,517; SF8 spec.md:240,362; SF9 spec.md:356-361; SF10
spec.md:465-473 with `_positive_int` guard mirroring real `extract_timeout()` at config.py:48-65.)

---

## (b) NEW findings introduced by the fixes

### BLOCKING

**N1 — SF11 misdescribes `_write_bidirectional_relations`; reuse as-spec would OVERWRITE existing
relation arrays (spec.md:353).**
The spec states: *"That helper appends to the union of existing relation ids (does not overwrite);
the reciprocal target's prior relation array is read first so the Query id is added, not replacing
existing links."* This is **factually wrong about the code**. `_write_bidirectional_relations`
(`ingest.py:296-351`) seeds `prior_from`/`prior_to` from an **in-run** dict (`linked.get(id, [])`,
ingest.py:321,333) that starts **empty** for the call — it never reads the target's
already-persisted relations from Anytype. `_patch_relation` (`ingest.py:287-293`) then does a full
**overwrite**: `update_object(..., {"properties": [{"key": rel_key, "objects": list(ids)}]})`. In
the ingest pipeline this is safe only because every relation for an object is written in one batched
call so `linked` accumulates them all. In the proposed file-back reuse, an entity that already has
persisted `wiki_relations` from a prior ingest would have that array **clobbered** down to just
`[query_id]`. This directly violates the SF11 "append-not-overwrite" guarantee and the AC#16 promise
(spec.md:630). The `test_reciprocal_relation_append_not_overwrite` test (spec.md:583) — "target
entity with a prior `wiki_relations` array → PATCH carries prior ids ∪ Query id" — would FAIL against
the helper as it exists.
**Fix (pick one):** (a) before reciprocal write, `get_object` each surviving target, parse its
current relation array (the parser already exists per SF5), and pass `prior ∪ [query_id]` — i.e.
do NOT rely on the helper to read prior state; OR (b) spec a small new helper / explicit
read-merge-write step and stop attributing append semantics to `_write_bidirectional_relations`.
Either way, correct the false statement at spec.md:353 and make the read-merge step explicit so the
AC#16 test is actually satisfiable.

### SHOULD-FIX

**N2 — AC#19 (CLI + server registration) has no mapped test in the Test Plan (spec.md:633 vs
spec.md:558-589).**
New-problem check #2: every AC must map to a CI-runnable test. AC#19 asserts `wiki-query` in
`SUBCOMMANDS` and `wiki_query` registered as an MCP tool, but the Test Plan table contains no entry
for it — it leans on the prose "full test suite green." A registration test pattern already exists
(`tests/wiki/test_server_registration.py`, which asserts tool presence + no-shadowing). Add an
explicit row (extend `test_server_registration.py` for `wiki_query` and a `SUBCOMMANDS`/`wiki-query`
CLI-routing assertion) so AC#19 is independently verifiable. (AC#20's "mocked query < 5s" likewise
has no named test row — fold a timing assertion into an existing CI test or add a row.)

### SUGGESTION

- **SUG1 — Pagination is over-described; the helper already hides it.** The spec repeatedly tells
  the implementer to "paginate while `pagination.has_more == True`" at the call site (spec.md:64-65,
  265, wire-contract 437). Both `WikiClient.list_objects` (wiki_client.py:136-140 → `_paginated_get`)
  and `AnytypeReadClient.list_objects` (anytype_client.py:23-42) already paginate internally and
  return a flat accumulated `list[dict]`. Net behavior is correct (the returned list is complete, so
  the `filterexpression_fallback` >500 count works), but the call-site pagination instruction is
  misleading. Reword to "call `list_objects(space_id)` (it paginates internally)".

- **SUG2 — `_safe_name` is a new inline helper but not flagged as new.** spec.md:350 defines
  `_safe_name = strip_control_chars(question)[:100]` inline; it does not exist in the codebase and is
  not listed in the Reused-Helpers table (correctly, since it's new), but neither is it explicitly
  marked "(new)". It is defined where used, so low risk — just mark it new for clarity.

- **SUG3 — B9 slightly overstates the `error_category` convention.** spec.md:227 says
  `error`/`error_category` align "with the existing tools' convention." Verified `error_category`
  is used ONLY by `bootstrap.py` today (ingest/remember do not emit it). The choice is reasonable
  (aligns with the richest precedent), but "existing tools' convention" implies uniformity that
  doesn't exist. Trim to "aligns with `wiki_bootstrap`'s error_category convention."

- **SUG4 — Size (732 lines) is justified.** The growth over R1 (538→732) is normative: the status
  table, failure taxonomy, error population table, synthesis budget, config block, and the expanded
  test/AC lists are all load-bearing. The only restatement is the pagination instruction (SUG1).
  Not bloat — no action required beyond SUG1.

---

## New-problem coherence checks (results)

1. **Schema vs status table vs taxonomy vs ACs vs Test Plan vs pipeline:** Coherent. The QueryResult
   `status`/`error`/`error_category` fields (spec.md:220-224), the population table (spec.md:229-236),
   the status-determination table (spec.md:380-387), and the Anytype taxonomy (spec.md:389-395) all
   agree (e.g. Anytype-down → error/api_error/no-WikiLog appears identically in all three). No drift
   found.
2. **AC→test mapping:** 18 of 20 ACs map cleanly to CI-runnable (non-live) tests; no core promise is
   gated behind `@pytest.mark.live` only (B10's compounding promise has the required mocked backstop).
   Gaps: AC#19 and AC#20 (see N2).
3. **No contradiction with prior fixes:** The status table, error-category table, and WikiLog-on-error
   rule (SF9) are mutually consistent. No conflict found — except N1, which is an internal
   spec-vs-code contradiction, not a spec-vs-spec one.
4. **Helper reality:** `_DETERMINISTIC_OPTS`, `_is_model_not_pulled`, `_call_ollama_prompt`
   (extraction.py), `_read_schema_version` (bootstrap.py:486), `_cmp_versions` (ingest.py:447),
   `_object_deeplink` (bootstrap.py:83), `read_patch_decision` (util.py:229), `_resolve_wiki_action_tag`
   (ingest.py:212), `_write_wikilog` (ingest.py:241), `_write_bidirectional_relations` (ingest.py:296),
   `WikiClient.{list,create,update}_object`, `AnytypeReadClient.get_object` (with `?format=md`),
   `wiki_answer`/`wiki_question`/`wiki_drew_from`/`wiki_asked_at` (types_schema.py:133-136),
   relation keys `wiki_relations`/`wiki_related`/`wiki_subjects`/`wiki_drew_from` — ALL verified
   present at the cited lines. `extract_max_input_tokens` correctly flagged as not-yet-present and
   added. New helpers `semantic_search_core`, `_call_ollama_synthesis`, `synthesize`, `_positive_int`
   are marked new. Only `_write_bidirectional_relations`'s *behavior* is misdescribed (N1).

---

## Disposition
Resolve N1 (correct the relation-write append claim so AC#16 is satisfiable) and N2 (map AC#19/#20
to tests). The four suggestions are optional. No scope expansion required. All R1 BLOCKING/SHOULD-FIX
items are correctly resolved.
