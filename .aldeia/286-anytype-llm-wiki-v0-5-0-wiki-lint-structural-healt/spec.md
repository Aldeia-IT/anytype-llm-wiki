# wiki_lint v0.5.0 — Structural Health Check

**Status:** DRAFT
**Date:** 2026-06-05
**Author:** spec-writer agent
**Ticket:** #286 (Aldeia-IT/aldeia-box)
**Master spec:** `.aldeia/140-wiki-library-module-port-llm-wiki-pattern-onto-any/spec.md` (status: SPEC)
**Shipped dependencies (all merged):**
- v0.3.0 `wiki_ingest` (#284)
- v0.3.1 `wiki_remember` (#289)
- v0.4.0 `wiki_query` (#285 — per-run cache, `_qdrant()`, `semantic_search_core`)
- v0.4.1 schema rename (#303 — `Wiki …` display-name prefix)

---

## Nature of This Spec

INCREMENT spec. The master spec (#140) is the authoritative design baseline and already specifies `wiki_lint` (signature, LintReport schema, 9-check table, data-flow diagram, perf budget, OQ#7) at lines 519–618. This document does NOT re-derive that design. It:

1. References the master spec for the bulk of the lint design.
2. Locks five deltas discovered/shipped since the master was written (D1–D5 below).
3. Grounds every helper and wire contract against real function names in the post-#303 codebase.
4. Firms the v0.5.0 acceptance criteria into a single authoritative testable list.

---

## Problem Statement

After v0.4.0, agents can ingest, remember, and query a typed Anytype wiki. There is no tool to audit structural integrity: orphaned objects, broken relations, schema drift, and stale or unreviewed content accumulate silently. Without `wiki_lint`, the maintain loop of the Karpathy pattern is incomplete — operators have no automated way to find and fix structural decay. This release closes that gap.

---

## Research Summary

Research findings are in `.aldeia/286-anytype-llm-wiki-v0-5-0-wiki-lint-structural-healt/technical-research.md`. Key findings that drove the five locked decisions:

- **D1:** `get_object` returns `obj["backlinks"]` verbatim in the API response. No client code currently reads it. O(1) inbound-relation access is available now; the master spec's O(N) traversal-primary framing was written before this was confirmed (OQ#7).
- **D2:** `_WIKI_STATUS_TAGS = ["needs-review", "reviewed", "archived"]` (bootstrap.py:57). There is no `stub` tag. The master's `stale_stub` check (line 599) can never fire as written.
- **D3:** `_flag_conflict_status` (remember.py:659–673) sets `wiki_status=needs-review` on conflict but writes no separate conflict marker. Lint cannot distinguish conflict-flagged from other needs-review by reading the object alone; two checks keyed on `wiki_status == "needs-review"` are needed.
- **D4:** Per-run cache, `_fetch_cached`, `_qdrant()`, and `semantic_search_core` are all confirmed importable from their research-verified locations.
- **D5:** Schema v0.4.1 reads by KEY (`wiki_*`), unchanged. All wire contracts and the `lint` action tag are confirmed at the exact paths and mock patterns given below.

---

## Proposed Solution

### Locked Decisions

#### D1 — Native `backlinks` is PRIMARY; O(N) traversal is explicit FALLBACK

**Verdict (reverses master spec lines 595–606 / OQ#7):** The master spec shipped the O(N) reciprocal-traversal as the primary path and deferred `backlinks` to v0.6.x. That is now reversed.

**Primary path:** `obj.get("backlinks", [])` on the dict returned by `AnytypeReadClient.get_object`. Each element parsed via `_parse_relation_elements` (query.py:72–91), which handles both bare id strings and `{"id": ...}` dicts. This is O(1) per object relative to the already-fetched object — no additional API call required.

**Fallback path:** when `backlinks` is absent or empty in the API response (field may be missing on older API versions), lint falls back to the O(N) reciprocal traversal: for each object whose outbound `wiki_relations`/`wiki_related` points to target T, count T as having one inbound link. This fallback is explicit and must be documented in code with a comment.

**Perf win:** D1 removes the second O(N) pass the master spec's primary path required. Combined with the per-run cache, a 500-object wiki stays within the ≤60s budget (see Performance section).

#### D2 — Re-target `stale_stub` check; rename to `stale_needs_review`

**Verdict (option B — no schema bump):** The `stub` tag does not exist. The check is re-targeted to a real signal without modifying `WIKI_SCHEMA_VERSION` or `MIGRATIONS.md`.

**Detection:** `wiki_status` select tag resolves to `"needs-review"` AND `wiki_ingested_at < now − WIKI_LINT_STALE_NEEDS_REVIEW_DAYS` (default 30d).

**Check enum:** `stale_needs_review` (replaces the master's `stale_stub` literal). The master LintReport schema `check` enum (lines 564) adds `stale_needs_review` and `unreviewed_needs_review`; `stale_stub` is no longer emitted.

**Applies to:** `wiki_entity` and `wiki_concept` only — these are the only types with `wiki_status` in `types_schema.WIKI_TYPES` (research §C).

**Severity:** Medium (same as master's `stale_stub`).

#### D3 — New live HIGH signal: `unreviewed_needs_review`

**Detection:** any `wiki_entity` or `wiki_concept` with `wiki_status` select tag resolving to `"needs-review"`, regardless of age.

**Check enum:** `unreviewed_needs_review`, severity High.

**Rationale:** `wiki_remember` (#289) sets `wiki_status=needs-review` when it detects an intra-entity conflict. Lint cannot distinguish conflict-flagged from other needs-review by reading the object alone (research §C confirms no separate conflict marker property). Therefore `unreviewed_needs_review` fires on ALL `needs-review` objects — it is the live High signal that pipeline-produced wikis will actually generate.

**Double-counting rule:** An aged needs-review object fires BOTH `unreviewed_needs_review` (High) and `stale_needs_review` (Medium). Both findings appear in `findings[]`; the `summary` counts each separately. Rationale: the two checks represent distinct actionable concerns (unreviewed conflict vs long-term staleness) and the operator benefits from seeing both.

**`wiki_status` tag resolution:** done once at the start of the lint run via the property-scoped two-step (`list_properties` → `list_tags`), storing the resolved `needs-review` tag id. This avoids per-object resolution overhead. Reuse `_resolve_select_tag` (remember.py:124–145) for the resolution pattern.

#### D4 — Reuse v0.4.0 infra verbatim

**Reuse map (exact names from research §D):**

| Helper | Location | Purpose |
|--------|----------|---------|
| `cache: dict[str, dict] = {}` | query.py:474 (pattern) | per-run object-fetch cache (initialize in `wiki_lint`) |
| `_fetch_cached(read_client, space_id, object_id, cache, enum_map=None)` | query.py:684 | cached `get_object` |
| `_looks_like_object(obj)` | query.py:709 | validate fetched object dict |
| `_parse_relation_elements(elements)` | query.py:72 | normalize relation arrays (both shapes) |
| `_qdrant()` | indexer.py:16 | Qdrant client factory |
| `semantic_search_core(query, space_id, types, limit)` | indexer.py:20 | potential-duplicates sweep |

`semantic_search_core` is called for the potential-duplicates sweep with `types=["wiki_entity","wiki_concept","wiki_comparison","wiki_query"]`. Results filtered to the `0.70–config.index_threshold()` band (the `score` field is 0.0–1.0 cosine similarity). `config.index_threshold()` (config.py:67) provides the upper bound, consistent with D5.

#### D5 — Schema v0.4.1; wire contracts pinned

**Display names vs keys:** property display names are now prefixed `Wiki …` (post-#303), but lint reads by KEY (`wiki_*`, unchanged). No logic change needed — state this explicitly at the head of `wiki/lint.py`.

**Wire contracts (every endpoint lint calls):**

| Call site | Verb | Path | Mock to mirror |
|-----------|------|------|----------------|
| `WikiClient.list_objects` (object enumeration) | GET | `/v1/spaces/{space_id}/objects?limit=100&offset=N` | `respx.get()` no-arg — mirror `test_ingest.py:314` |
| `WikiClient.list_properties` (tag resolution step 1) | GET | `/v1/spaces/{space_id}/properties` | `respx.get()` no-arg |
| `WikiClient.list_tags` (tag resolution step 2) | GET | `/v1/spaces/{space_id}/properties/{property_id}/tags` | `respx.get()` no-arg |
| `AnytypeReadClient.get_object` (full object + backlinks) | GET | `/v1/spaces/{space_id}/objects/{object_id}?format=md` | `respx.get(f"{ANYTYPE_BASE}/v1/spaces/{space_id}/objects/{object_id}")` specific |
| `WikiClient.search` (WikiLog cross-ref query) | POST | `/v1/spaces/{space_id}/search` | `respx.post()` no-arg |
| `WikiClient.create_object` (lint WikiLog receipt) | POST | `/v1/spaces/{space_id}/objects` | `respx.post()` no-arg — mirror `test_ingest.py:315` |
| `indexer.semantic_search_core` (duplicate sweep) | N/A — Qdrant internal | Collection query | monkeypatch at function boundary |

**Tag resolution note:** Space-level `/tags` endpoint 404s. The only working path is the property-scoped two-step: `list_properties` → find property by key → `list_tags(space_id, property_id)`. Do NOT call `/v1/spaces/{space_id}/tags`. This is identical to the pattern in `_resolve_wiki_action_tag` (ingest.py:212) and `_resolve_select_tag` (remember.py:124).

**WikiLog `lint` action tag:** already seeded in `_WIKI_ACTION_TAGS` (bootstrap.py:54, index 2). Resolve via `_resolve_wiki_action_tag(client, space_id, "lint")` (ingest.py:212). No bootstrap change needed.

**respx 0.23.x pattern:** no-arg `respx.get()` / `respx.post()` are catch-alls. Specific URL routes: `respx.get(url=...)`. `respx.patterns.M` is not used anywhere in the codebase and raises at registration — do not use it.

---

### Lint Checks

The authoritative check table, severity grades, and data-flow diagram are in master spec lines 519–607. The table below shows only the D2/D3 additions and the `pipeline_orphan` implementation note; all other checks are carried as specified in the master:

| Check enum | Severity | Delta vs master |
|------------|----------|-----------------|
| `asymmetric_relation` | Critical | No change to detection; **D1 makes `backlinks` the primary inbound-count source** |
| `pipeline_orphan` | High | No run-id linkage exists (research §F). Detection is a timestamp-proximity heuristic: enumerate WikiLog objects with `wiki_action=ingest` whose `wiki_notes` contains a failure marker (e.g. `"relation_rollback"`); objects with zero `wiki_relations` AND no inbound backlinks created near the partial-failure WikiLog's `wiki_timestamp` are flagged. Spec acknowledges this as heuristic — no false-negative guarantee |
| `orphan` | High | No change; 7-day grace via `wiki_ingested_at`; **D1 primary path** |
| `contradiction_unresolved` | High | PASSIVE until v0.6.0 (#287) — zero findings on pipeline wikis; fires only when `wiki_contradictions` manually populated |
| `stale` | Medium | No change; `last_modified < linked source wiki_ingested_at − 90d` |
| `unreviewed_needs_review` | High | NEW (D3): `wiki_status == "needs-review"`, any age — applies to `wiki_entity`/`wiki_concept` only |
| `stale_needs_review` | Medium | REPLACES `stale_stub` (D2): `wiki_status == "needs-review"` AND `wiki_ingested_at < now − 30d` — applies to `wiki_entity`/`wiki_concept` only |
| `oversized` | Low | No change; >~2000 chars (`WIKI_LINT_OVERSIZED_CHARS`, default 2000) |
| `empty_type` | Informational | No change |
| `potential_duplicate` | Informational | No change; Qdrant 0.70–`config.index_threshold()` band (D4) |

**LintReport schema:** master spec lines 548–586 (normative). `check` enum is extended with `unreviewed_needs_review` and `stale_needs_review`; `stale_stub` is dropped. No other schema field changes.

**Tool signature:** master spec lines 540–546 (normative, reproduced by reference only).

---

### Pre-Checks

Both pre-checks fire before any Anytype write or Qdrant call, in this order:

1. **QA#30 — `patch_decision_missing_or_invalid`** (pure filesystem read, no network): `util.read_patch_decision()` (util.py:229). Gate: result non-None AND contains both `patch_body_updates` AND `implementation_path` keys. Exact error string: `"[CONFIG ERROR] patch_decision_missing_or_invalid: a valid patch-decision.md with patch_body_updates and implementation_path is required"`. Mirrors query.py:395–398.

2. **QA#25 — `wiki_schema_outdated`**: enumerate objects first (one `list_objects` call), then call `bootstrap._schema_version_from_objects(all_objects)` (bootstrap.py:486) + `ingest._cmp_versions(live, code)` (ingest.py:447). Fires if live version < `WIKI_SCHEMA_VERSION = "0.4.1"`. Exact error string: `"[CONFIG ERROR] wiki_schema_outdated: space schema {live} < code {code}; run wiki_bootstrap to upgrade"`. Mirrors query.py:421 pattern. WikiLog write is skipped on either pre-check failure.

---

### Performance Budget

Budget: ≤60s for ≤500 objects. Above 500 objects, emit in `LintReport.warnings`:

```
lint_object_count_exceeded_budget: {N} objects found — lint may exceed 60s; consider archiving unused objects
```

Per `docs/known-limitations.md §9`, the O(N) enumeration concern is the same as `wiki_query`. D1 is the primary mitigation: it removes the second O(N) reciprocal traversal the master spec required. The count-cache referenced in §9 as a v0.5.0 candidate is NOT a v0.5.0 deliverable.

---

## Wire-Contract Pinning

(Summary table in D5 above. Implementation note: the mock pattern for WikiLog create is the no-arg `respx.post()` side-effect pattern from `test_ingest.py:314–315`. Tests that assert a specific body was POSTed inspect `request.content` JSON for `type_key="wiki_log"` — mirror `test_ingest.py:471–473`.)

---

## Configuration

New env knobs (all use `_positive_int` guard from config.py:45, rejecting 0/negative):

| Env var | Default | Purpose |
|---------|---------|---------|
| `WIKI_LINT_OVERSIZED_CHARS` | 2000 | Oversized-description threshold |
| `WIKI_LINT_ORPHAN_GRACE_DAYS` | 7 | Orphan entity/concept grace period |
| `WIKI_LINT_STALE_NEEDS_REVIEW_DAYS` | 30 | `stale_needs_review` age cutoff |

`WIKI_INDEX_THRESHOLD` (existing, default 200) is reused as the upper bound for the duplicate-sweep score band. No new threshold variable needed for duplicates.

Add to `.env.example`:

```
WIKI_LINT_OVERSIZED_CHARS=2000
WIKI_LINT_ORPHAN_GRACE_DAYS=7
WIKI_LINT_STALE_NEEDS_REVIEW_DAYS=30
```

---

## Security

`wiki_lint` is read-mostly. The only write it performs is its own WikiLog receipt (`wiki_action=lint`). It does not mutate any wiki objects. Pre-checks (QA#25/QA#30) fire before the WikiLog write.

**Prompt injection:** not applicable — `wiki_lint` produces a structural report from property reads and does not invoke an LLM. Object names and descriptions read during lint are not interpolated into any prompt.

**Credentials:** no new credential surfaces. `ANYTYPE_API_KEY` (bearer token) and optional `QDRANT_API_KEY` inherited from existing config. All error strings and WikiLog `notes` containing API endpoint fragments pass through `scrub_credentials()` (util.py:98) before being returned or written.

**SSRF:** lint fetches only Anytype objects by ID (configured host) and queries Qdrant (configured host). No user-supplied URLs are fetched.

---

## Resource Impact

- **Enumeration:** one `list_objects` paginated GET sequence, O(N). Seeds `all_objects` and `enum_map`.
- **Object fetch:** up to N `get_object` calls (one per object), mitigated by `_fetch_cached` — each object fetched at most once across all checks.
- **Duplicate sweep:** up to N `semantic_search_core` calls (or a configurable sample cap). Each call hits Qdrant locally. This is the most CPU-intensive pass; the Informational severity means it can be skipped via `severity_threshold` without losing High/Critical findings.
- **WikiLog cross-ref (pipeline_orphan):** one `WikiClient.search` POST to retrieve WikiLog objects with `wiki_action=ingest`.
- **Tag resolution:** two GETs at startup (properties + tags for `wiki_status`); cached for the run.
- **Total wall time target:** ≤60s for ≤500 objects. Above 500 objects the budget warning is emitted.

---

## Test Plan

All tests in `tests/wiki/test_lint.py`. CI-runnable tests use `@respx.mock`, `monkeypatch.setenv`, and no-arg `respx.get()`/`respx.post()` catch-alls (mirror `test_ingest.py:113–115`).

### CI-runnable mocked backstops

| Test | What it verifies |
|------|-----------------|
| `test_asymmetric_relation_check_fires` | Seed object A with `wiki_relations=[B]` and object B with no reciprocal; assert finding `check="asymmetric_relation"`, severity Critical. Backlinks-primary path: `obj["backlinks"]` present and empty → fallback fires. |
| `test_backlinks_primary_no_traversal` | Seed object A with `backlinks=["B"]` in the `get_object` response; assert no O(N) traversal occurs (the fallback branch is not entered). |
| `test_pipeline_orphan_check_fires` | WikiLog with `wiki_action=ingest` and `wiki_notes` containing `"relation_rollback"` near the timestamp of a zero-relation object; assert finding `check="pipeline_orphan"`, severity High. |
| `test_orphan_check_fires_after_grace` | Object with zero `wiki_relations` and `wiki_ingested_at` older than 7 days; assert finding `check="orphan"`, severity High. |
| `test_orphan_check_suppressed_within_grace` | Same object with `wiki_ingested_at` < 7 days ago; assert no orphan finding. |
| `test_unreviewed_needs_review_fires` | `wiki_entity` with `wiki_status=needs-review` (any age); assert finding `check="unreviewed_needs_review"`, severity High. |
| `test_stale_needs_review_fires` | `wiki_entity` with `wiki_status=needs-review` AND `wiki_ingested_at < now − 30d`; assert finding `check="stale_needs_review"`, severity Medium. |
| `test_both_needs_review_checks_fire_on_aged_object` | Same aged needs-review object fires BOTH `unreviewed_needs_review` (High) AND `stale_needs_review` (Medium); assert both appear in `findings[]` and `summary` counts each. |
| `test_stale_stub_check_never_emitted` | Full lint run on a fixture with only `needs-review` / `reviewed` / `archived` status values; assert no finding with `check="stale_stub"` in the report. |
| `test_contradiction_check_passive` | Object with non-empty `wiki_contradictions`; assert zero findings with `check="contradiction_unresolved"` when `wiki_contradictions` is set but `wiki_last_reviewed` is null — PASSIVE check, fires on manual population only. When `wiki_contradictions` is manually populated on a fixture, assert finding fires. |
| `test_stale_check_fires` | `last_modified < linked source wiki_ingested_at − 90d`; assert finding `check="stale"`, severity Medium. |
| `test_oversized_check_fires` | Description > 2000 chars; assert finding `check="oversized"`, severity Low. |
| `test_empty_type_check_fires` | Space with zero `wiki_concept` objects; assert finding `check="empty_type"`, severity Informational. |
| `test_duplicate_sweep_fires_in_band` | `semantic_search_core` monkeypatched to return a candidate with score 0.75 (in the 0.70–`index_threshold()` band); assert entry in `potential_duplicates[]` with correct `similarity_score`. |
| `test_duplicate_sweep_excludes_outside_band` | score < 0.70 and score > `index_threshold()` (as a float, e.g. `index_threshold()/1000`) both excluded from `potential_duplicates[]`. |
| `test_severity_threshold_high_filters_medium_low` | Full fixture with findings at all severities; `severity_threshold="high"` → `findings[]` contains only Critical + High; summary counts only those. |
| `test_pre_check_schema_outdated_fires_before_write` | Mocked schema version older than `"0.4.1"` → `[CONFIG ERROR] wiki_schema_outdated` returned; no POST to objects. |
| `test_pre_check_patch_decision_missing_fires_before_write` | Missing `patch-decision.md` (via `monkeypatch.setenv("ALDEIA_DIR", str(tmp_path))`) → `[CONFIG ERROR] patch_decision_missing_or_invalid` returned; no Anytype call. |
| `test_pre_checks_fire_before_wikilog_write` | Both pre-check failure paths assert zero POST calls. |
| `test_object_count_budget_warning_above_500` | Mocked enumeration returns 501 objects; assert `lint_object_count_exceeded_budget: 501` in `LintReport.warnings`. |
| `test_wikilog_receipt_written_on_clean_run` | Clean run; assert one POST with `type_key="wiki_log"` and `wiki_action=lint` in the body. |
| `test_wikilog_skipped_on_pre_check_failure` | Pre-check failure; assert zero POST calls. |
| `test_wiki_lint_registered_and_cli_routed` | `wiki_lint` in MCP tool registry (server.py); `"wiki-lint"` in `cli.SUBCOMMANDS`. No live services. |

### Live smoke test (additive, skip-gated)

```python
@pytest.mark.live
class TestLintLive:
    def test_end_to_end_lint(self):
        space_id = os.environ.get("ANYTYPE_SPACE_ID")
        if not space_id:
            pytest.skip("ANYTYPE_SPACE_ID not set — live lint test skipped")
        from anytype_llm_wiki.wiki.lint import wiki_lint
        result = wiki_lint(space_id=space_id)
        assert result["status"] in ("ok", "partial")
        assert result["wiki_log_id"] is not None
        assert isinstance(result["findings"], list)
        assert isinstance(result["summary"], dict)
```

Run with: `uv run pytest -m live tests/wiki/test_lint.py`
Exclude from CI: `uv run pytest -m 'not live'`

---

## Acceptance Criteria

1. **D1 — Backlinks primary:** `wiki_lint` reads inbound relations from `obj.get("backlinks", [])` on the `get_object` response as the primary path; the O(N) reciprocal traversal is code-level fallback, only entered when `backlinks` is absent/empty (CI-mocked `test_backlinks_primary_no_traversal`).

2. **D2 — `stale_needs_review` replaces `stale_stub`:** a needs-review entity/concept older than `WIKI_LINT_STALE_NEEDS_REVIEW_DAYS` (default 30d) yields a Medium finding with `check="stale_needs_review"`; no finding with `check="stale_stub"` is ever emitted (CI-mocked).

3. **D3 — `unreviewed_needs_review` fires as High:** any needs-review entity/concept (any age) yields a High finding with `check="unreviewed_needs_review"`; a seeded fixture with a recently-set `wiki_status=needs-review` produces at least one High finding (CI-mocked).

4. **Double-count rule:** a needs-review entity older than 30d fires BOTH `unreviewed_needs_review` (High) AND `stale_needs_review` (Medium) — both appear in `findings[]` and both are counted in `summary` (CI-mocked `test_both_needs_review_checks_fire_on_aged_object`).

5. **All 9 check types produce findings on seeded fixtures:** Critical (`asymmetric_relation`), High (`pipeline_orphan`, `orphan`, `unreviewed_needs_review`, `contradiction_unresolved`), Medium (`stale`, `stale_needs_review`), Low (`oversized`), Informational (`empty_type`, `potential_duplicate`) — each verified by a dedicated CI-mocked test.

6. **Contradiction check passive:** zero `contradiction_unresolved` findings on a pipeline wiki fixture (all `wiki_contradictions` empty); finding fires when `wiki_contradictions` is manually populated (CI-mocked `test_contradiction_check_passive`).

7. **`severity_threshold` filtering:** `severity_threshold="high"` returns only Critical and High findings in `findings[]` and summary; lower severities absent (CI-mocked `test_severity_threshold_high_filters_medium_low`).

8. **Duplicate sweep correct band:** potential-duplicate findings appear for scores in `[0.70, config.index_threshold()/1000)` band and are absent for scores outside that band (CI-mocked).

9. **QA#25 fires before write** (by reference — exact error strings, helpers, and ordering per master spec lines 743, 1590–1607 and research §G): outdated schema → `[CONFIG ERROR] wiki_schema_outdated`, no WikiLog POST (CI-mocked).

10. **QA#30 fires before write** (by reference — per master spec line 905 and research §G): missing patch-decision → `[CONFIG ERROR] patch_decision_missing_or_invalid`, no Anytype call (CI-mocked).

11. **WikiLog receipt:** every clean or partial run writes one `wiki_log` object with `wiki_action=lint`; WikiLog is skipped on pre-check failure (CI-mocked `test_wikilog_receipt_written_on_clean_run` + `test_wikilog_skipped_on_pre_check_failure`).

12. **500-object budget warning:** >500 objects enumerated → `lint_object_count_exceeded_budget: {N}` in `LintReport.warnings` (CI-mocked `test_object_count_budget_warning_above_500`).

13. **D5 wire contracts: tag resolution uses property-scoped two-step:** no call to `/v1/spaces/{space_id}/tags`; all tag resolution goes through `list_properties` → `list_tags(space_id, property_id)` (CI-mocked `test_asymmetric_relation_check_fires` + needs-review tests verify the two-step path).

14. **CLI + server registration:** `"wiki-lint"` in `cli.SUBCOMMANDS` routing to `_cmd_lint`; `wiki_lint` registered as MCP tool in `server.py` without shadowing existing tools (CI-mocked `test_wiki_lint_registered_and_cli_routed`).

15. **Live smoke (additive):** lint against a real space returns `status in ("ok", "partial")` and a non-null `wiki_log_id` (`@pytest.mark.live`, skip-gated on `ANYTYPE_SPACE_ID`).

---

## Implementation Plan

### Files Changed

| File | Action |
|------|--------|
| `src/anytype_llm_wiki/wiki/lint.py` | NEW — object enumeration, 9-check battery, duplicate sweep, LintReport assembly, WikiLog receipt |
| `src/anytype_llm_wiki/wiki/cli.py` | EDIT — add `"wiki-lint"` to `SUBCOMMANDS` (cli.py:21), add `_cmd_lint` |
| `src/anytype_llm_wiki/server.py` | EDIT — register `wiki_lint` MCP tool |
| `src/anytype_llm_wiki/wiki/config.py` | EDIT — add `lint_oversized_chars()`, `lint_orphan_grace_days()`, `lint_stale_needs_review_days()` using `_positive_int` guard |
| `.env.example` | EDIT — add three `WIKI_LINT_*` vars |
| `README.md` | EDIT — add lint section; "How it works" maintain loop; grep marketing claims for consistency (Mem0 #140 R2 lesson) |
| `CHANGELOG.md` | EDIT — v0.5.0 entry |
| `MIGRATIONS.md` | NOT touched — D2-option-B; no schema bump; `WIKI_SCHEMA_VERSION` stays at `"0.4.1"` |
| `tests/wiki/test_lint.py` | NEW — all CI-mocked tests + live smoke test per test plan |

### Reused Helpers (verbatim names from research)

| Helper | Location | Purpose |
|--------|----------|---------|
| `_schema_version_from_objects(objects)` | bootstrap.py:486 | QA#25 schema check (pure, no I/O) |
| `_cmp_versions(a, b)` | ingest.py:447 | version comparison |
| `_object_deeplink(space_id, object_id)` | bootstrap.py:83 | deeplink generation |
| `read_patch_decision()` | util.py:229 | QA#30 patch-decision gate |
| `scrub_credentials(url)` | util.py:98 | error/WikiLog string sanitization |
| `_resolve_wiki_action_tag(client, space_id, "lint")` | ingest.py:212 | WikiLog action tag resolution |
| `_write_wikilog(client, space_id, ...)` | ingest.py:241 | WikiLog write |
| `WikiClient.list_objects(space_id)` | wiki_client.py:136 | object enumeration (paginates internally) |
| `WikiClient.list_properties(space_id)` | wiki_client.py:124 | tag resolution step 1 |
| `WikiClient.list_tags(space_id, property_id)` | wiki_client.py:127 | tag resolution step 2 |
| `WikiClient.search(space_id, query, filter)` | wiki_client.py:91 | WikiLog cross-ref (pipeline_orphan) |
| `WikiClient.create_object(...)` | wiki_client.py:53 | WikiLog receipt write |
| `AnytypeReadClient.get_object(space_id, object_id)` | anytype_client.py:44 | full object + backlinks fetch |
| `_fetch_cached(read_client, space_id, object_id, cache, enum_map)` | query.py:684 | per-run cached `get_object` |
| `_parse_relation_elements(elements)` | query.py:72 | normalize relation arrays (both shapes) |
| `_looks_like_object(obj)` | query.py:709 | validate fetched object dict |
| `_qdrant()` | indexer.py:16 | Qdrant client factory |
| `semantic_search_core(query, space_id, types, limit)` | indexer.py:20 | potential-duplicates Qdrant sweep |

### Ordering

1. Add config vars to `wiki/config.py` (`lint_oversized_chars`, `lint_orphan_grace_days`, `lint_stale_needs_review_days`) and `.env.example`.
2. Implement `wiki/lint.py`: pre-checks → enumerate → tag resolution → check battery (in master spec data-flow order: asymmetric → orphan/pipeline-orphan → contradiction → stale → oversized → empty-type → duplicate sweep) → severity filter → LintReport assembly → WikiLog receipt.
3. Register `wiki_lint` in `server.py` and add `wiki-lint` to `cli.py`.
4. Write `tests/wiki/test_lint.py` — CI tests first (one per check), then filtering/pre-check/WikiLog tests, live smoke test last.
5. Update `README.md` and `CHANGELOG.md`.

---

## Open Questions

None. D1–D5 are all locked above. The master spec's OQ#7 is resolved by D1.

---

## Deferred Items

- **Automated `wiki_contradictions` population (v0.6.0 / #287):** re-activates the contradiction check for pipeline wikis. Keeps the check passive in v0.5.0.
- **Count-cache (`docs/known-limitations.md §9`):** deferred — not a v0.5.0 deliverable.
- **Duplicate-sweep sample cap:** if the full N-object sweep proves too slow in practice, a configurable `WIKI_LINT_DUPLICATE_SAMPLE` cap (random sample of wiki objects) is a natural follow-up. Not specified here to keep config surface minimal.
- **Multi-space federation:** deferred (master spec roadmap).
- **Auto-fix / auto-merge of findings:** explicitly out of scope — `wiki_lint` is report-only and mutates nothing but its own WikiLog receipt.
