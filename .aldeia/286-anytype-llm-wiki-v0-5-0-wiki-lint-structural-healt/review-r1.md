# Spec Review R1 — wiki_lint v0.5.0 (#286)

**Date:** 2026-06-05
**Reviewers:** Completeness, Architecture, Security, Infra/Ops (general-purpose agents w/ specialist personas) + lead inline checks
**Spec:** `.aldeia/286-anytype-llm-wiki-v0-5-0-wiki-lint-structural-healt/spec.md`

## Consolidated Verdict: **NEEDS REVISION**

Two BLOCKING findings, both clustered on the **potential-duplicates sweep** (band-correctness + perf/cap). The spec is otherwise well-grounded: every helper name, line ref, and wire contract in the Reuse table and D5 was independently verified accurate against source (the #285/#289 wire-contract lesson is well-applied). Anti-bloat discipline is respected (367 lines, master content referenced not restated). BLOCKING count is 2 (not ≥8) → no scope/altitude alarm; proceed to a fix cycle.

Resolve findings by **tightening**, not appending. Address ALL findings (BLOCKING, SHOULD-FIX, SUGGESTION) unless a suggestion would introduce a problem.

---

## BLOCKING

### B1 — Duplicate-sweep band uses an object-COUNT as a similarity score; band is empty/no-op (Architecture + Infra, independently; lead-confirmed)
Spec D4 §96, Lint-Checks §137, Config §183, AC8 §288, and tests `test_duplicate_sweep_*` (§239–240) use `config.index_threshold()` as the UPPER bound of the cosine band `[0.70, X)`.
**Evidence:** `wiki/config.py:67-69` → `index_threshold()` returns `WIKI_INDEX_THRESHOLD` default **200**, documented "Tier-1/Tier-2 **object-count** flip" (also `docs/known-limitations.md §9` line 165). `semantic_search_core` returns `score` = cosine in [0,1] (`indexer.py:79`). So `[0.70, 200)` accepts everything (no-op upper bound); the AC8/test `index_threshold()/1000` = 0.20 hack makes `[0.70, 0.20)` = **empty interval** → `test_duplicate_sweep_fires_in_band` (score 0.75) asserts a finding the impl can never produce → test phase unsatisfiable (exact #285/#289 failure mode, on a value).
**Correct value:** master spec §424c–d / §600 define the band as **0.70 → embedding auto-upsert threshold, default 0.85**. No config exists for it (`ingest.py:37` only has `_UPSERT_THRESHOLD_TITLE = 0.92`).
**Fix:** introduce a real float knob `WIKI_LINT_DUPLICATE_MAX_SCORE` (default **0.85**) guarded by a new `_positive_float`/`[0,1]` helper (`_positive_int` at config.py:45 is int-only — cannot express 0.85). Use band `[0.70, 0.85)`. Remove `index_threshold()` reuse and the `/1000` hack from D4 §96/§183, AC8, §137, and both duplicate tests. Reverse the Config §183 claim "No new threshold variable needed for duplicates."

### B2 — Perf budget not honest about the N-embedding duplicate sweep; uncapped pass shipped (Infra)
§Resource Impact §211 says "up to N `semantic_search_core` calls." Each runs `embed_query` (Ollama bge-m3) THEN a Qdrant query (`indexer.py:47-48`). For 500 objects that is 500 sequential bge-m3 embeddings + 500 Qdrant queries — plausibly 30–60s+ alone on the constrained box, BEFORE the `get_object` fan-out. The perf section (§156–164) credits D1 with removing the traversal pass but never costs the embedding sweep (the dominant cost). `WIKI_LINT_DUPLICATE_SAMPLE` is *deferred* (§365), so v0.5.0 ships an uncapped N-embedding pass with no timing guard.
**Fix (pick one, IN-SCOPE for v0.5.0):** (a) ship the sample cap now; OR (b) make the sweep opt-in / excluded from the default run since it is Informational — run it only when `severity_threshold == "all"` (or behind a default-off flag), and state the default run excludes it; OR (c) give an honest worst-case timing breakdown proving ≤60s including embeddings. Recommended: (b) + document, since the sweep is Informational-tier and the High/Critical findings must stay within budget regardless.

---

## SHOULD-FIX

### Perf / budget
- **SF1 (Infra S1):** `get_object` fan-out arithmetic omitted: ~N×100ms ≈ 50s for 500 objects alone nearly exhausts the budget. Add an explicit per-phase derivation (enumeration batched pages + N×get_object + WikiLog search + sweep), state sequential (no concurrency specified), and reconcile with the ≤60s claim. The budget is currently asserted, not derived.
- **SF2 (Infra S2):** No hard cap → runaway lint on a large wiki (10k objects = 10k fetches + 10k embeds, minutes, may saturate Ollama/Qdrant). Add a hard ceiling (`WIKI_LINT_MAX_OBJECTS`, abort with a clear error) or auto-disable the sweep above the budget threshold. The warn-and-continue string is fine; the unbounded behavior behind it is the concern.
- **SF3 (Infra S3):** State lint is single-space-per-run so the `_fetch_cached` `object_id`-only cache key (query.py:692) is sound (one sentence).

### Correctness / completeness
- **SF4 (Architecture S2 + Completeness):** QA#25 pre-check specifies only `live < code`. Source `query.py:424-433` also emits `[CONFIG ERROR] wiki_schema_missing` when `_schema_version_from_objects` returns `None` (never-bootstrapped/empty space) — without it lint crashes on such a space. Scope brief §65 also mandates the `_newer` (live > code) → **warn-and-continue** branch. Add both branches: `None → wiki_schema_missing` (abort, status error, no WikiLog); `live > code → warning in warnings[], continue`.
- **SF5 (Architecture S3):** `stale` check inputs are not co-located: `wiki_ingested_at` lives on `wiki_source` (types_schema.py:79), NOT on entity/concept. Lint must dereference the `wiki_sources` relation and fetch the linked source's property (an extra `_fetch_cached` hop). State this explicitly (else the check silently never fires by reading an absent property) and budget the extra source fetches in Resource Impact.
- **SF6 (Completeness):** LintReport `status` lifecycle (`ok|partial|error`) undefined. Define: `ok` = all checks ran on all objects; `partial` = ≥1 `get_object`/`semantic_search_core` failure (object skipped, counted in `warnings`); `error` = enumeration or pre-check failure that aborts. Add an AC + a mocked-`get_object`-5xx test for the `partial` path.
- **SF7 (Completeness):** `severity_threshold` ordering vs the sixth severity `informational`. Signature enum is `critical|high|medium|low|all` but `empty_type`/`potential_duplicate` are informational. State the total order (`critical > high > medium > low > informational`), that `low` excludes informational, that only `all` includes informational, and whether `potential_duplicates[]` (a separate array) is gated by the threshold (recommend: yes — suppress below `all`; this also dovetails with B2 option (b)). Add a `severity_threshold="low"` test.
- **SF8 (Completeness):** Duplicate sweep — specify (a) self-match exclusion (`object_id == candidate_id`), and (b) pair canonicalization (sorted id tuple) so each reciprocal pair (A→B, B→A) appears once in `potential_duplicates[]`. Add an assertion for single-emission of a reciprocal pair.
- **SF9 (Completeness):** Contradiction check on `wiki_concept`: `wiki_last_reviewed` exists on `wiki_entity` but NOT `wiki_concept` (research §C). Resolve: treat absent `wiki_last_reviewed` as null (check applies) OR scope the contradiction check to `wiki_entity` only. Pick one (low impact now — check is passive — but state it).
- **SF10 (Completeness):** `backlinks` malformed handling: D1 covers absent/empty → fallback, but not present-but-malformed (`null`, dict, non-list). State a non-list/unparseable `backlinks` is treated identically to absent (fallback to traversal) so the primary path never raises.

### Security
- **SF11 (Security S1):** §Security §201 overstates `scrub_credentials()` — `util.py:98-141` only strips URL userinfo (`user:pass@`) and query/fragment; it does NOT redact bearer tokens / API keys (those live in headers, low real risk). Correct the wording to "strips userinfo and query strings from URL-shaped fragments"; stop implying broader redaction. Confirm tokens are never concatenated into any `detail`/`notes`/error string.
- **SF12 (Security S2):** `detail` (and WikiLog `subject`/`notes`) may embed full object-controlled text — esp. the `oversized` finding naturally embeds the offending >2000-char description, written back into Anytype's WikiLog. Mandate: (a) `detail` carries a char-count/summary, not the raw oversized body; (b) any object title/description written into WikiLog `subject`/`notes` runs through `strip_control_chars(...)[:N]` (precedent: `query.py:347` truncates subject to `[:50]`). Bounds data exposure + log bloat.

---

## SUGGESTION
- **G1 (Completeness):** `elapsed_ms` (master schema) never asserted — add `elapsed_ms >= 0` assertion to `test_wikilog_receipt_written_on_clean_run`.
- **G2 (Completeness):** AC#5 says "All 9 check types" but the increment now has 10 (D2+D3 split). Relabel to 10 to match the enum list.
- **G3 (Completeness):** `pipeline_orphan` heuristic window unquantified ("near the WikiLog timestamp"). Pin a concrete tolerance (e.g. `wiki_ingested_at` within WikiLog `wiki_timestamp` ± `WIKI_LINT_PIPELINE_WINDOW_SECONDS`, or a fixed ±N) so `test_pipeline_orphan_check_fires` is deterministic. Acceptable to keep as documented heuristic, but the fixture needs a defined tolerance.
- **G4 (Completeness):** entity/concept lacking `wiki_status` (pre-schema object) → state neither needs-review check fires (treat as not-needs-review).
- **G5 (Security G5):** `error_category` field unspecified. Master conventions (§614) require `error_category` (`config_error`/`api_error`/`data_error`) in all errors; `query.py` sets it on pre-check failures. Have `lint.py` set `error_category` to match.
- **G6 (Architecture G1):** Check ordering (§348 puts empty-type last) deliberately differs from master data-flow (empty-type first). Harmless (checks independent, share cache) — call out the deliberate reorder to preempt a future reviewer flag.
- **G7 (Architecture G3):** Make the dual-client setup explicit: `AnytypeReadClient` (get_object/backlinks) + `WikiClient` (list/search/create/wikilog) — same pattern as `query.py:405-406` — so the WikiLog write isn't routed through the read client.
- **G8 (Infra G2):** `doctor` — no `wiki/doctor.py` change needed (run_doctor is a fixed preflight battery; lint adds no new external dependency). Add one line: "no doctor change; doctor remains green." Closes the ticket's "doctor green" AC cleanly.
- **G9 (Security G1):** Pre-check ordering is correct, but `list_objects` (a read) runs between QA#30 and QA#25; state explicitly that the enumeration read is intentionally between the two gates (header "before any write or Qdrant call" is accurate).

---

## Verified-correct (no action — recorded for the fixer's confidence)
- All 18 helpers in the Reuse table exist at the cited locations with compatible signatures (line refs off by ≤1 in two cases). `search` is POST `/v1/spaces/{id}/search`; `get_object` GET `…?format=md`; tag resolution is the property-scoped two-step (space-level `/tags` 404s — no such route in source). `lint` seeded in `_WIKI_ACTION_TAGS` index 2 (bootstrap.py:54). `_WIKI_STATUS_TAGS` has no `stub` (D2 justified). Tag resolution is read-only (no create-on-miss). No SSRF, no LLM/injection surface, no new credential surface. Test harness mirrors the respx + `@pytest.mark.live` conventions; `semantic_search_core` monkeypatched at the function boundary keeps the 22 mocked tests CI-runnable without live services.
