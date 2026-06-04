# Review R1 — Infrastructure & Operations (wiki_query v0.4.0, #285)

**Verdict:** CHANGES REQUESTED — the spec is operationally sound on config and the
happy path, but the failure-mode taxonomy is under-specified and partially
contradicts the master spec; the WikiLog-on-error-path guarantee is not stated; and
synthesis-context bounding (the only OOM/stall risk on the 32GB box) is entirely absent.

**Severity counts:** BLOCKING 3 · SHOULD-FIX 6 · SUGGESTION 4

Reviewer scope: Infrastructure & Operations checklist only. Spec under review:
`.aldeia/285-anytype-llm-wiki-v0-4-0-wiki-query-tiered-retrieva/spec.md`.

---

## BLOCKING

### B1 — Synthesis context is unbounded; Tier 2 can OOM/stall Ollama on the 32GB box
`spec.md:256-260` (Synthesis) and `spec.md:403-410` (Resource Impact).

The spec passes `context_objects` = "both candidates and their 1-hop neighbors" into
`synthesize()` with **no cap on object count, no cap on per-object text length, and no
total-token budget**. Tier 2 fetches 10 candidates (`limit=10`), but each candidate can
fan out to an arbitrary number of 1-hop neighbors via `wiki_relations` / `wiki_related` /
`wiki_drew_from` / `wiki_subjects`. A densely-linked wiki can expand 10 candidates into
dozens or hundreds of full `get_object(...?format=md)` bodies, all concatenated into one
Ollama prompt. The extraction path it copies (`extraction.py`) bounds input via
`WIKI_EXTRACT_MAX_INPUT_TOKENS=8192` (`.env.example:11`); the synthesis path inherits the
model and timeout but **drops the input cap**. On a 32GB box running bge-m3 (~2.2GB) +
chat model (~5GB+) resident, an unbounded prompt is the single most likely cause of an
OOM or a 600s-timeout stall.

The Resource Impact section (`spec.md:405-410`) only counts *API calls*, never *prompt
size*, and explicitly hand-waves: "Synthesis: 1 Ollama call. Timeout governed by
WIKI_EXTRACT_TIMEOUT (default 600s)." A 600s timeout is a stall budget, not a guard.

**Fix:** Specify a synthesis context budget: (a) cap total context objects (e.g.
candidates + neighbors truncated to N, N≈20–30); (b) per-object truncation of the md body
and text properties (reuse `WIKI_EXTRACT_MAX_INPUT_TOKENS` or add an explicit budget); (c)
state that 1-hop neighbor count per candidate is capped. Add a `synthesis_context_truncated`
warning to `QueryResult.warnings` when the cap trips. Add an AC and a test asserting the
prompt size is bounded.

### B2 — `wiki_query` failure taxonomy contradicts the master spec; Ollama-down maps to the wrong category and string
`spec.md:127` (Decision 3) and `spec.md:233-236` (Qdrant fallback) vs. master spec
`spec.md:1644` (Failure modes per tool) and `spec.md:1655`, and codebase
`wiki/extraction.py:184` / `wiki/ingest.py:495`.

Two concrete defects:

1. **Wrong error string for model-not-pulled.** Decision 3 (`spec.md:127`) specifies the
   synthesis helper returns `[CONFIG ERROR] model_not_pulled: {model}`. The entire
   codebase uses the literal token `ollama_model_not_pulled` (extraction.py:184, 201, 256;
   ingest.py:495; and the master-spec AC at master `spec.md:831` / `spec.md:1655`). Inventing
   `model_not_pulled` (no `ollama_` prefix) breaks the documented operator-facing
   convention and any grep/troubleshooting recipe keyed on it. The remediation hint
   ("run `ollama pull {model}`") is also missing from the spec'd string.

2. **Ollama-down (reachable host, transport/connection error, NOT model-missing) has no
   specified disposition.** The master spec failure-modes row (`spec.md:1644`) is explicit:
   "Ollama unreachable | Only blocks synthesis; `[API ERROR]`." The v0.4.0 spec never
   states what happens when Ollama is *down* (connection refused / read timeout) as
   opposed to *model not pulled*. Decision 3 only addresses model-not-pulled. There is no
   `[API ERROR]` path, no `status` value, and no test for "Ollama process down during
   synthesis."

**Fix:** Align the model-not-pulled string to
`[CONFIG ERROR] ollama_model_not_pulled: run \`ollama pull {model}\` and retry`. Add an
explicit Ollama-unreachable branch → `[API ERROR]` with `status: "error"` (per master
`spec.md:1644`), and add ACs/tests for both. Decide and state whether the answer is
returned with `status: "partial"` when retrieval succeeded but synthesis failed — the
master spec's "only blocks synthesis" wording implies synthesis failure is terminal
(`error`), so make that explicit.

### B3 — Anytype 500 / timeout during retrieval has no specified failure path and no status
`spec.md` (whole) — no Anytype-down branch; master spec `spec.md:1644` row says
"Anytype 500 | `[API ERROR]`; no Query object created."

The spec pins the four Anytype endpoints it calls (`spec.md:334-340`) but never specifies
what `wiki_query` returns when any of them fails:
- `list_objects` failing mid-pagination during Tier 1 enumeration (partial neighborhood /
  partial candidate set).
- `get_object` failing for a candidate or a neighbor during the 1-hop fetch (the checklist
  "partial neighborhood fetch" case).
- `create_object` / `update_object` failing during file-back.

`_read_schema_version` "raises httpx.HTTPError on network failure (callers must catch)"
(research.md:166) — the spec reuses this helper at `spec.md:300-307` but never says the
caller catches it. There is no `[API ERROR]` mapping, no `status` assignment, and no
distinction between "synthesis ran on a partial neighborhood → `status: partial`" vs.
"could not enumerate candidates at all → `status: error`."

**Fix:** Add a Failure-modes subsection for `wiki_query` mirroring master `spec.md:1644`:
schema-read / list_objects / get_object transport failure → `[API ERROR]` with
remediation ("Ensure the Anytype desktop app is running"). Specify that a *partial*
neighborhood fetch (some get_object calls fail but synthesis still runs) yields
`status: "partial"` + a `neighborhood_fetch_failed: {object_id}` warning, while total
enumeration failure yields `status: "error"`. Specify that a file-back write failure does
NOT lose the answer (return `status: "partial"`, `filed_back: false`, warning). Add tests.

---

## SHOULD-FIX

### S1 — WikiLog-on-error-path is not guaranteed; spec only writes it "success or partial"
`spec.md:282` ("After every `wiki_query` invocation (success or partial)") vs. master spec
`spec.md:1516` ("Both are always written at terminal events (success or failure), except
when Anytype is unreachable") and master `spec.md:342`.

Checklist item 3 asks: "Is a WikiLog written even on the error path?" The spec's WikiLog
section header explicitly scopes it to "(success or partial)" and omits the error path.
The master spec requires a WikiLog receipt at *every* terminal event including failure
(except when Anytype itself is unreachable, in which case `wiki_log_id` is `null` and the
failure lives only in the stderr JSON log). The pre-check error paths (`spec.md:300-316`,
schema-outdated / patch-decision-missing) and the Qdrant-at-threshold error
(`spec.md:236`) return before reaching the WikiLog write at `spec.md:282`, so no WikiLog is
written for them.

**Fix:** State that `wiki_query` writes a WikiLog on the error path too (when Anytype is
reachable), recording the failure category in `wiki_notes`, and that `wiki_log_id`/
`wiki_log_deeplink` are `null` only when Anytype is unreachable. Note the schema-outdated/
patch-decision pre-checks fire *before* Anytype reachability is known — clarify whether a
WikiLog is attempted for those (master spec implies yes, best-effort). Add a test.

### S2 — Unbounded `list_objects` pagination in Tier 1 with no page cap or hard ceiling
`spec.md:64` / `spec.md:221` ("paginate while `pagination.has_more == True`").

Tier 1 paginates with no upper bound. The `filterexpression_fallback` warning at
`spec.md:67` only *warns* above 500 rows — it does not *stop*. If FilterExpression is a
no-op (the LOCKED canonical path) and the space has unrelated non-wiki objects (Sources,
WikiLogs, and any user content in the same space), the pre-filter row count is the *entire
space*, not just the ≤199 wiki objects the threshold implies. A space with thousands of
non-wiki objects forces thousands of `list_objects` rows + client-side filtering on every
sub-threshold query. The "≤ 4 paginated GETs" estimate at `spec.md:407` assumes the space
contains only ~200 wiki objects, which is not guaranteed.

**Fix:** State a page-size and a hard pagination ceiling (e.g. stop after K pages and emit
a warning), or document the assumption that wiki spaces are dedicated. At minimum,
acknowledge that object_count_at_decision counts only wiki types while pagination scans all
object types, and bound the latter.

### S3 — No latency budget stated for the realistic path; AC#15's 5s is mock-only
`spec.md:476` (AC#15: "mocked query completes within 5s. Maintainer-measured p95 < 5s on
Mac Mini M4").

Checklist item 4 asks for a latency budget. AC#15 ties p95<5s to a Mac Mini M4, but the
target machine for this review is a 32GB box and the dominant cost (Ollama synthesis) is
explicitly *excluded* from the 5s mocked figure. The master spec (`spec.md:1624`) already
concedes Ollama latency is 10–40s for extraction; synthesis on a large unbounded context
(see B1) can be far worse. The "< 5s" budget is therefore not a real-world budget — it
measures everything except the slow part.

**Fix:** State a realistic end-to-end budget that includes synthesis (or explicitly mark
synthesis latency as out-of-budget and dominated by model choice), and reconcile the
Mac Mini M4 reference with the actual 32GB target. Note the 600s timeout as the worst-case
stall bound and tie it to B1's context cap.

### S4 — Compounding / reindex-coupling warning to the operator is not specified in the response
`spec.md:318-326` (Compounding) and AC#7 (`spec.md:468`).

Checklist item 5 asks whether the operator is *told* that filed queries are retrievable
only after the next reindex, mirroring the v0.3.0 "rerun reindex" guidance (master
`spec.md:435`). The spec documents the compounding mechanism and makes #284 a prerequisite,
but when `file_back` actually creates a Query object, **nothing is added to
`QueryResult.warnings`** telling the operator "this answer is filed but will not be
retrievable until the next reindex_anytype." v0.3.0 emits a `reindex_failed:` warning and
README guidance for exactly this lag; v0.4.0 should mirror it. The launchd reindex cadence
assumption (30 min per master `spec.md:1980`) is also not stated as the freshness bound.

**Fix:** When a Query object is filed, add a warning such as
`filed_back_pending_reindex: this answer is retrievable by future queries only after the
next reindex_anytype (auto-reindex cadence ~30 min via launchd)`. State the launchd
cadence assumption in the spec and README known-limitations. (Note: `wiki_query` does NOT
auto-reindex — unlike `wiki_ingest`/`wiki_remember` which call `_maybe_reindex` — so this
lag is unavoidable and must be surfaced.)

### S5 — Negative / zero config values pass the validators silently (threshold=0, min=-1)
`spec.md:358-374` (config resolvers) vs. existing pattern in `wiki/config.py:48-65`
(`extract_timeout` rejects non-positive: `return val if val > 0 else DEFAULT`).

Checklist item 1 explicitly asks about "negative, threshold=0." The three spec'd resolvers
only guard `(ValueError, TypeError)` — they accept any integer-parseable value including
`0` and negatives. The existing `extract_timeout()` resolver in the real config
(`config.py:65`) sets the precedent: it adds a `val > 0` guard. The spec's resolvers
diverge from that established pattern. Consequences:
- `WIKI_INDEX_THRESHOLD=0` → every query (count ≥ 0) takes Tier 2, defeating Tier 1
  entirely and forcing Qdrant dependence even on tiny wikis; negative threshold has the
  same effect.
- `WIKI_FILE_BACK_MIN_SOURCES=-1` / `=0` → file-back fires on every query (an empty answer
  with 0 sources passes `>= 0`), polluting the wiki.
- `WIKI_FILE_BACK_MIN_WORDS=0` → same.

**Fix:** Mirror `extract_timeout`'s positivity guard. `index_threshold()` should reject
`< 1` (a threshold of 0 is meaningless) and the two file-back resolvers should reject
`< 0` (0 may be intentionally permissive but negative is not; pick and document). Add a
test for each (`threshold=0`, negative, non-int). The call-time resolution is otherwise
correct and matches the documented Mem0 lesson (`config.py:1-9`) — good.

### S6 — `[API ERROR]` strings from Qdrant/Ollama must be credential-scrubbed; not restated
`spec.md:236` (`[API ERROR] qdrant_unavailable`), `spec.md:398-399` (credentials).

The master spec carries an explicit AC (CSO#5, master `spec.md:745`, and
`spec.md:1809`) that `[API ERROR]` strings triggered by a Qdrant or Ollama failure must not
leak `QDRANT_API_KEY` / endpoint userinfo. The v0.4.0 spec introduces *new* `[API ERROR]`
emission sites (qdrant_unavailable, and per B2/B3 Ollama/Anytype-down) but does not restate
that these new error strings are scrubbed. New emission points are exactly where regressions
hide.

**Fix:** Add a line that all new `[API ERROR]` strings route through the existing logger
mask, and add (or reference) a scrubbing regression test for the qdrant_unavailable path.

---

## SUGGESTION

### G1 — Config/env-var declarations and call-time resolution are otherwise correct
`spec.md:351-383`, `.env.example`, `wiki/config.py`.

Confirmed for the record (checklist item 1): the three vars are declared in both
`wiki/config.py` (resolvers + `DEFAULT_*` constants) and `.env.example`, defaults match
(200/3/100), and resolution is call-time (`os.environ.get` per call) — matching the
documented monkeypatch/testability requirement at `wiki/config.py:1-9`. Only the
validation gap (S5) needs fixing. `.env.example` should also gain a one-line comment per
var (the existing file documents every var with a comment block; the three new entries at
`spec.md:380-382` are bare).

### G2 — Schema-compatibility reuse and the "no MIGRATIONS.md entry" call are correct
`spec.md:146-147`, `spec.md:300-307`, `spec.md:494`.

Confirmed (checklist item 6): `wiki_answer` already exists (`types_schema.py:134`),
`WIKI_SCHEMA_VERSION` stays `"0.3.1"`, no new property, so no MIGRATIONS.md entry is
required — consistent with the master spec's MIGRATIONS policy (only bump-and-append when
`WIKI_SCHEMA_VERSION` changes, master `spec.md:1607`). The QA#25 pre-check reuse of
`_read_schema_version` + `_cmp_versions` is correct. One nit: the spec hard-codes the
schema floor implicitly via the live-vs-code compare; state explicitly that the floor is
`>= 0.3.1` so an operator on an older space gets the outdated error (research.md:421 flagged
this).

### G3 — Docs/rollout enumeration is mostly complete; add the two operator-facing items
`spec.md:492-494` (README/CHANGELOG), AC#7 (`spec.md:468`).

Confirmed (checklist item 7): README query section, CHANGELOG v0.4.0, and the Tier-2
freshness known-limitation are enumerated in the Files-Changed table. Missing: (a) the
`filed_back_pending_reindex` operator guidance from S4 belongs in the README troubleshooting
section (master spec seeds README H3s from failure-mode rows, `spec.md:1537`); (b) the new
failure modes from B2/B3 (Ollama-down, Anytype-down) should each get a README H3 per that
same convention. Enumerate them in the spec's docs list.

### G4 — Live smoke test gate is correct but under-specifies the multi-service requirement
`spec.md:442-456`, `pyproject.toml:44-45`.

Confirmed (checklist item 8): the live test is `@pytest.mark.live` + `pytest.skip` when
`ANYTYPE_SPACE_ID` is unset, mirroring `test_ingest.py`, and the `live` marker already
exists in `pyproject.toml`. CI runs `-m 'not live'`, so absence of services does not fail
CI. Gap: the skip gate keys only on `ANYTYPE_SPACE_ID`, but the test exercises the full
stack (Qdrant + Ollama + Anytype, per the marker description at `pyproject.toml:45`). If
`ANYTYPE_SPACE_ID` is set but Qdrant or Ollama is down, the test will hard-fail rather than
skip. `conftest.py` has an `anytype_available` guard (research.md:466) — consider gating on
service reachability, not just the env var, or document that the operator must bring all
three up before running `-m live`.

### G5 — Per-run object cache is correct; note it does not bound total fetches
`spec.md:248-251`.

The per-run `dict[str,dict]` cache correctly prevents duplicate `get_object` calls for the
same id (checklist item 4 — good, and AC#8/test covers it). But de-duplication is not the
same as bounding: a query touching many *distinct* neighbors still makes many distinct
fetches. This reinforces B1/S2 — the cache caps *redundant* work, not *total* work. Worth a
one-line note so a reader does not mistake the cache for a fetch budget.

---

## Summary table

| ID | Sev | Item | One-line fix |
|----|-----|------|--------------|
| B1 | BLOCKING | Unbounded synthesis context (OOM/stall on 32GB) | Cap object count + per-object text + token budget; add warning + test |
| B2 | BLOCKING | Ollama failure taxonomy wrong/incomplete | Use `ollama_model_not_pulled`; add `[API ERROR]` Ollama-down branch + tests |
| B3 | BLOCKING | Anytype-down / partial-neighborhood path unspecified | Add `wiki_query` failure-modes subsection mirroring master spec:1644 |
| S1 | SHOULD | WikiLog not guaranteed on error path | Write WikiLog at every terminal event (Anytype reachable); test |
| S2 | SHOULD | Unbounded Tier-1 pagination | Page ceiling + warning; clarify count counts only wiki types |
| S3 | SHOULD | No real latency budget | State end-to-end budget incl. synthesis; reconcile M4 vs 32GB |
| S4 | SHOULD | No filed-back reindex-lag warning | Add `filed_back_pending_reindex` warning; state launchd cadence |
| S5 | SHOULD | Config validators accept 0/negative | Add positivity guards like `extract_timeout`; tests |
| S6 | SHOULD | New `[API ERROR]` scrub not restated | Route new errors through mask; regression test |
| G1 | SUGG | Config/call-time resolution correct | Add per-var comments in .env.example |
| G2 | SUGG | Schema-compat/no-migration correct | State `>= 0.3.1` floor explicitly |
| G3 | SUGG | Docs enumeration nearly complete | Add README H3s for new failure modes + reindex-lag |
| G4 | SUGG | Live gate correct | Gate on service reachability, not just env var |
| G5 | SUGG | Object cache correct | Note cache bounds redundant, not total, fetches |
