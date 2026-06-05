# wiki_lint v0.5.0 — Structural Health Check

**Status:** SPEC (post-council rework — CA-B1 resolved)
**Date:** 2026-06-05
**Author:** spec-writer agent (council-rework edits applied directly per Jan's direction)
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

**Impl task ONE (CTO/QA ADV-1):** the `obj["backlinks"]` shape is asserted from a single live-API session finding (the only repo hit is a comment in `test_ingest.py`) — it is NOT verifiable from source. Before building the primary path, the implementer MUST confirm the real shape against a live `get_object` call (id string vs `{"id": ...}` element form, field presence on the current API version). The malformed-fallback test (`test_backlinks_malformed_falls_back`) and the `test_backlinks_field_shape_live` smoke (below) defensively fence this, but the live confirmation is task one — if the shape differs, the parse via `_parse_relation_elements` and the absent/empty fallback trigger must be reconciled before the asymmetric/orphan checks are trusted.

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

`semantic_search_core` is called for the potential-duplicates sweep with `types=["wiki_entity","wiki_concept","wiki_comparison","wiki_query"]`. The `score` field is a 0.0–1.0 cosine similarity (`indexer.py:79`). Results are filtered to the literal band **`[0.70, 0.85)`**: 0.70 is the master spec duplicate-surfacing floor (§424d/§600); 0.85 is the embedding auto-upsert threshold (master spec §424c) — at/above 0.85 the ingest pipeline would have auto-upserted rather than created a duplicate, so those pairs are not "potential duplicates." The upper bound is the new `config.lint_duplicate_max_score()` knob (`WIKI_LINT_DUPLICATE_MAX_SCORE`, default 0.85), NOT `index_threshold()` (which returns a Tier-1/Tier-2 object **count**, default 200 — `config.py:67` — and is not a similarity score at all). The band is half-open: score `s` qualifies iff `0.70 <= s < lint_duplicate_max_score()`.

Each `semantic_search_core` call embeds the query text via bge-m3 (`embed_query`, indexer.py:47) THEN runs one Qdrant query — so the sweep costs **N embeddings + N Qdrant queries** for N objects. This is the dominant cost of a lint run; see Performance Budget and Resource Impact for why it runs only when the caller **explicitly opts in via `include_duplicates=True`** (CA-B1 — the sweep is OFF on the default `wiki_lint(space)` call) and is further bounded by `WIKI_LINT_MAX_OBJECTS`.

**Sweep mechanics (SF8):** for each source object O, the sweep query uses O's title/description text and `limit=5`; candidates are filtered by (a) the band above, and (b) `candidate_id != O.object_id` (self-match exclusion). Each surviving pair is canonicalized to a sorted `(id_a, id_b)` tuple and inserted into a `set`, so a reciprocal pair (A→B and B→A) is emitted **once** in `potential_duplicates[]`.

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
| `pipeline_orphan` | High | No run-id linkage exists (research §F). Detection is a timestamp-proximity heuristic: enumerate WikiLog objects with `wiki_action=ingest` whose `wiki_notes` contains a failure marker (e.g. `"relation_rollback"`); a zero-relation, zero-backlink object is flagged when its source-derived ingest timestamp falls within **± `WIKI_LINT_PIPELINE_WINDOW_SECONDS` (default 300s)** of the failure WikiLog's `wiki_timestamp` (G3 — pinned tolerance makes `test_pipeline_orphan_check_fires` deterministic). Heuristic — no false-negative guarantee |
| `orphan` | High | No change; 7-day grace via the object's source-derived ingest age (see Age-derivation note); **D1 primary path** |
| `contradiction_unresolved` | High | PASSIVE until v0.6.0 (#287) — zero findings on pipeline wikis; fires only when `wiki_contradictions` manually populated. Applies to `wiki_entity` only (SF9 — `wiki_last_reviewed` is not on `wiki_concept`) |
| `stale` | Medium | No change; `last_modified < linked source wiki_ingested_at − 90d` (Age-derivation note) |
| `unreviewed_needs_review` | High | NEW (D3): `wiki_status == "needs-review"`, any age — applies to `wiki_entity`/`wiki_concept` only |
| `stale_needs_review` | Medium | REPLACES `stale_stub` (D2): `wiki_status == "needs-review"` AND source-derived ingest age `> 30d` — applies to `wiki_entity`/`wiki_concept` only |
| `oversized` | Low | No change; >~2000 chars (`WIKI_LINT_OVERSIZED_CHARS`, default 2000) |
| `empty_type` | Informational | No change |
| `potential_duplicate` | Informational | Qdrant `[0.70, 0.85)` band (D4); only computed when the caller passes `include_duplicates=True` — OFF by default (CA-B1) |

**Age-derivation note (SF5):** `wiki_ingested_at` is a property of `wiki_source` objects only (`types_schema.py:79`; written by `ingest.py:621` / `remember.py:189`). `wiki_entity`/`wiki_concept` carry NO top-level `wiki_ingested_at` — they reference sources via the `wiki_sources` relation (`types_schema.py:93`/`109`). Every age-based check (`orphan` grace, `stale`, `stale_needs_review`) therefore dereferences the object's `wiki_sources`, `_fetch_cached`-loads each linked source, and takes the **most-recent** linked `wiki_ingested_at` as the object's effective ingest timestamp. An object with no resolvable source timestamp is treated as ungated (its age cannot be established → age-conditioned checks do not fire; `stale_needs_review` collapses to the always-firing `unreviewed_needs_review`). These extra source fetches are budgeted in Resource Impact.

**LintReport schema:** master spec lines 548–586 (normative). `check` enum is extended with `unreviewed_needs_review` and `stale_needs_review`; `stale_stub` is dropped. Errors additionally carry `error_category` (`config_error`/`api_error`/`data_error`) per master §614/§617 — `lint.py` sets it on every error path exactly as `query.py:430/442` does (G5). No other schema field changes.

**Tool signature (CA-B1 delta — overrides master spec lines 540–546):** the master signature is `wiki_lint(space_id, severity_threshold="all") -> LintReport`. This increment adds a third parameter:

```python
wiki_lint(space_id: str,
          severity_threshold: str = "all",
          include_duplicates: bool = False) -> LintReport
```

`include_duplicates` is the **cost gate for the Qdrant duplicate sweep** and defaults to **`False`**, so the most-typed call — bare `wiki_lint(space)` and any scheduled run — runs only the fast structural battery and honors the advertised ≤60s/≤500 budget (CA-B1; see Performance Budget). The sweep (the dominant N-embedding + N-Qdrant-query cost) runs **only** when the caller explicitly passes `include_duplicates=True`, and even then is skipped above `WIKI_LINT_MAX_OBJECTS` (SF2). The MCP tool registration and the `wiki-lint` CLI (`--include-duplicates` flag) expose the parameter. The `check` enum now has **10** members (the master's 9 minus `stale_stub` plus the D2/D3 split into `stale_needs_review` + `unreviewed_needs_review`).

**Severity ordering + threshold gating (SF7):** the total order is `critical > high > medium > low > informational`. `severity_threshold` accepts `critical|high|medium|low|all`; a threshold `T` keeps findings with severity `>= T`. `low` therefore **excludes** informational (`empty_type`, `potential_duplicate`); only `all` includes informational. **`severity_threshold` and `include_duplicates` are independent and orthogonal:** `severity_threshold` is a pure post-filter on `findings[]`, while `include_duplicates` is the cost gate that decides whether the Qdrant sweep runs at all. The Qdrant sweep — and therefore the separate `potential_duplicates[]` array and any `potential_duplicate` finding — is computed **iff `include_duplicates=True`** (and `N <= WIKI_LINT_MAX_OBJECTS`); it is no longer keyed off `severity_threshold` (this is the CA-B1 fix that replaces the former B2 default-on gate). Note the two gates compose: to see `potential_duplicate` entries inside `findings[]` the caller must both opt in (`include_duplicates=True`) AND keep informational findings (`severity_threshold="all"`); the standalone `potential_duplicates[]` array is populated by the sweep regardless of `severity_threshold`.

**`status` lifecycle (SF6):** `ok` = every check ran on every enumerated object; `partial` = ≥1 `get_object`/`semantic_search_core` failure caused an object (or the sweep) to be skipped — the object id is recorded in `warnings[]` and lint continues; `error` = enumeration or a pre-check (QA#25/QA#30) aborted the run before findings could be produced (no WikiLog written). A `partial` run still writes its WikiLog receipt.

**Missing `wiki_status` (G4):** an entity/concept with no `wiki_status` value (pre-schema object) is treated as not-needs-review — neither `unreviewed_needs_review` nor `stale_needs_review` fires.

---

### Pre-Checks

Both pre-checks fire before any Anytype write or Qdrant call. The object enumeration read (`list_objects`) runs **between** QA#30 and QA#25 — intentional, because QA#25 needs the enumerated objects to derive the live schema version; a read is not a write, so the "before any write or Qdrant call" guarantee holds (G9). Order:

1. **QA#30 — `patch_decision_missing_or_invalid`** (pure filesystem read, no network): `util.read_patch_decision()` (util.py:229). Gate: result non-None AND contains both `patch_body_updates` AND `implementation_path` keys. Exact error string: `"[CONFIG ERROR] patch_decision_missing_or_invalid: a valid patch-decision.md with patch_body_updates and implementation_path is required"`. Mirrors query.py:395–398. Sets `error_category="config_error"`.

2. **Enumerate** objects (one paginated `list_objects` sequence) → `all_objects`.

3. **QA#25 — schema gate** (mirrors `query.py:421–448` exactly): `live = bootstrap._schema_version_from_objects(all_objects)` (bootstrap.py:486); `cmp = ingest._cmp_versions(live, code)` with `code = "0.4.1"` (ingest.py:447). Three branches (SF4 — verified against `query.py:424–448`):
   - `live is None` (never-bootstrapped / empty space): abort, `status="error"`, `error_category="config_error"`, error `"[CONFIG ERROR] wiki_schema_missing: run wiki_bootstrap on this space first"`. No WikiLog written.
   - `cmp < 0` (live < code): abort, `status="error"`, `error_category="config_error"`, error `"[CONFIG ERROR] wiki_schema_outdated: space schema {live} < code {code}; run wiki_bootstrap to upgrade"`. No WikiLog written.
   - `cmp > 0` (live > code, newer-than-code): **warn-and-continue** — append `"wiki_schema_newer: space schema {live} > code {code}; continuing"` to `warnings[]` and proceed with the lint (scope brief §65).

WikiLog write is skipped on either aborting pre-check failure (`error` status).

---

### Performance Budget

Budget: ≤60s for ≤500 objects. All phases are **sequential** (no concurrency is specified for v0.5.0). Per-phase worst-case arithmetic for N=500 (SF1), p50 ~100ms Anytype latency:

| Phase | Cost @ N=500 | Notes |
|-------|-------------|-------|
| Enumeration | ~5 GETs (batched 100/page) | ~0.5s |
| `get_object` fan-out | N × ~100ms ≈ **50s** | `_fetch_cached` ensures each object fetched at most once across all checks |
| Source fetches (age checks) | ≤(#sources) × ~100ms, cached | sources are few relative to entities; reuses the same cache |
| WikiLog cross-ref | 1 `search` POST | ~0.2s |
| Tag resolution | 2 GETs at startup | ~0.2s |
| **Default run — full structural battery, sweep OFF (`include_duplicates=False`)** | **≈ 51s** | within ≤60s for 500 objects; this is the default path |
| Duplicate sweep (only when `include_duplicates=True`) | N × (bge-m3 embed + Qdrant query) | the dominant, variable cost — opt-in only, see below |

The `get_object` fan-out alone nearly exhausts the budget, so the structural battery is the part that must fit ≤60s — and it does (~51s @ 500). **The default invocation honors the budget because the duplicate sweep is OFF by default** (CA-B1): the sweep runs only when the caller explicitly passes `include_duplicates=True`. There is therefore **no contradiction** between the advertised ≤60s/≤500 budget and the default path — the advertised budget describes the default (sweep-off) run, and the README/docstring states the budget on that basis. When a caller opts into the sweep (`include_duplicates=True`), they accept the additional variable cost (~110s of bge-m3 inference @ 500, bounded by `WIKI_LINT_MAX_OBJECTS`); this is a deliberate, caller-chosen heavyweight pass, not the default, and is documented as exceeding ≤60s. `severity_threshold` remains a pure post-filter and does not change wall-clock.

**Hard ceiling (SF2):** `WIKI_LINT_MAX_OBJECTS` (default 2000). When enumeration exceeds it, the **sweep is skipped automatically** (even when `include_duplicates=True`) and a warning is emitted; the rest of the lint still runs (degraded, not aborted) so High/Critical findings are never lost to a large wiki:

```
lint_sweep_skipped_object_cap: {N} objects exceed WIKI_LINT_MAX_OBJECTS={cap} — potential_duplicates sweep skipped to stay within budget
```

The softer count warning still fires above 500 objects (independent of the cap):

```
lint_object_count_exceeded_budget: {N} objects found — lint may exceed 60s; consider archiving unused objects
```

Per `docs/known-limitations.md §9`, the O(N) enumeration concern is the same as `wiki_query`. D1 is the primary mitigation: it removes the second O(N) reciprocal traversal the master spec required. The count-cache referenced in §9 as a v0.5.0 candidate is NOT a v0.5.0 deliverable.

---

## Wire-Contract Pinning

(Summary table in D5 above. Implementation note: the mock pattern for WikiLog create is the no-arg `respx.post()` side-effect pattern from `test_ingest.py:314–315`. Tests that assert a specific body was POSTed inspect `request.content` JSON for `type_key="wiki_log"` — mirror `test_ingest.py:471–473`.)

---

## Configuration

New env knobs. Integer knobs use the existing `_positive_int` guard (config.py:45, rejecting 0/negative). The duplicate band needs a fractional value, which `_positive_int` cannot express — so `wiki/config.py` gains a **new `_bounded_float(env, default, lo=0.0, hi=1.0)` guard** (parse via `float()`; on non-numeric/unset → `default`; clamp/reject out-of-range to `default`) used by `lint_duplicate_max_score()`.

| Env var | Default | Guard | Purpose |
|---------|---------|-------|---------|
| `WIKI_LINT_OVERSIZED_CHARS` | 2000 | `_positive_int` | Oversized-description threshold |
| `WIKI_LINT_ORPHAN_GRACE_DAYS` | 7 | `_positive_int` | Orphan grace period (source-derived age) |
| `WIKI_LINT_STALE_NEEDS_REVIEW_DAYS` | 30 | `_positive_int` | `stale_needs_review` age cutoff |
| `WIKI_LINT_DUPLICATE_MAX_SCORE` | 0.85 | `_bounded_float` `[0,1]` | Upper bound of the `[0.70, X)` duplicate band (B1) |
| `WIKI_LINT_MAX_OBJECTS` | 2000 | `_positive_int` | Object ceiling; above it the duplicate sweep is skipped (SF2) |
| `WIKI_LINT_PIPELINE_WINDOW_SECONDS` | 300 | `_positive_int` | ± window for the `pipeline_orphan` timestamp heuristic (G3) |

The earlier draft's claim "no new threshold variable needed for duplicates" is **reversed**: `index_threshold()` returns an object **count** (default 200), not a similarity score, and cannot serve as the band's upper bound.

Add to `.env.example`:

```
WIKI_LINT_OVERSIZED_CHARS=2000
WIKI_LINT_ORPHAN_GRACE_DAYS=7
WIKI_LINT_STALE_NEEDS_REVIEW_DAYS=30
WIKI_LINT_DUPLICATE_MAX_SCORE=0.85
WIKI_LINT_MAX_OBJECTS=2000
WIKI_LINT_PIPELINE_WINDOW_SECONDS=300
```

---

## Security

`wiki_lint` is read-mostly. The only write it performs is its own WikiLog receipt (`wiki_action=lint`). It does not mutate any wiki objects. Pre-checks (QA#25/QA#30) fire before the WikiLog write.

**Prompt injection:** not applicable — `wiki_lint` produces a structural report from property reads and does not invoke an LLM. Object names and descriptions read during lint are not interpolated into any prompt.

**Credentials:** no new credential surfaces. `ANYTYPE_API_KEY` (bearer token) and optional `QDRANT_API_KEY` inherited from existing config. `scrub_credentials()` (util.py:98) **strips userinfo (`user:pass@`) and the query string/fragment from URL-shaped fragments** — it does NOT redact bearer tokens or API keys (those live in request headers, never in lint output) (SF11). Lint never concatenates `ANYTYPE_API_KEY`/`QDRANT_API_KEY` into any `detail`, `notes`, or error string; any URL-shaped endpoint fragment in an error/notes string is passed through `scrub_credentials()` before being returned or written.

**Object-controlled text in output (SF12):** object titles/descriptions are not LLM-interpolated, but they ARE written into the report and into Anytype's WikiLog. To bound data exposure and log bloat: (a) the `oversized` finding's `detail` carries a **char-count summary** (e.g. `"description is 3140 chars (> 2000)"`), never the raw oversized body; (b) any object title/description placed into a finding `detail` or into WikiLog `wiki_subject`/`wiki_notes` is run through `strip_control_chars(...)[:N]` (precedent: `query.py:347` truncates the subject via `strip_control_chars(question)[:50]`).

**SSRF:** lint fetches only Anytype objects by ID (configured host) and queries Qdrant (configured host). No user-supplied URLs are fetched.

**Doctor (G8):** no `wiki/doctor.py` change — `run_doctor` is a fixed preflight battery and lint adds no new external dependency. Doctor remains green; this satisfies the ticket's "doctor green" AC without modification.

---

## Resource Impact

**Clients (G7):** lint uses the same dual-client setup as `query.py:405–406` — an `AnytypeReadClient` for `get_object`/backlinks, and a `WikiClient` for `list_objects`/`search`/`create_object`/WikiLog. The WikiLog write is routed through `WikiClient`, never the read client.

- **Enumeration:** one `list_objects` paginated GET sequence, O(N). Seeds `all_objects` and `enum_map`.
- **Object fetch:** up to N `get_object` calls (one per object), mitigated by `_fetch_cached` — each object fetched at most once across all checks. Lint is single-space-per-run, so the `_fetch_cached` `object_id`-only cache key (query.py:692) is sound (SF3).
- **Source fetches (SF5):** age-based checks dereference each object's `wiki_sources` and `_fetch_cached`-load the linked sources for `wiki_ingested_at`. Sources are few relative to entities/concepts and share the same per-run cache, so this adds at most (#distinct sources) extra GETs, not O(N).
- **Duplicate sweep:** N `semantic_search_core` calls (bge-m3 embed + Qdrant query each) — the dominant cost. It runs **only** when the caller passes `include_duplicates=True` AND `N <= WIKI_LINT_MAX_OBJECTS`; otherwise it is skipped (sweep-skip warning) without losing any High/Critical finding (CA-B1/SF2). On the default `include_duplicates=False` path it never runs, so the default lint imposes zero bge-m3 load on the shared local Ollama.
- **WikiLog cross-ref (pipeline_orphan):** one `WikiClient.search` POST to retrieve WikiLog objects with `wiki_action=ingest`.
- **Tag resolution:** two GETs at startup (properties + tags for `wiki_status`); cached for the run.
- **Total wall time target:** ≤60s for ≤500 objects (non-sweep battery; see Performance Budget arithmetic). Above 500 objects the budget warning is emitted.

---

## Test Plan

All tests in `tests/wiki/test_lint.py`. CI-runnable tests use `@respx.mock`, `monkeypatch.setenv`, and no-arg `respx.get()`/`respx.post()` catch-alls (mirror `test_ingest.py:113–115`).

### CI-runnable mocked backstops

| Test | What it verifies |
|------|-----------------|
| `test_asymmetric_relation_check_fires` | Seed object A with `wiki_relations=[B]` and object B with no reciprocal; assert finding `check="asymmetric_relation"`, severity Critical. Backlinks-primary path: `obj["backlinks"]` present and empty → fallback fires. |
| `test_backlinks_primary_no_traversal` | Seed object A with `backlinks=["B"]` in the `get_object` response; assert no O(N) traversal occurs (the fallback branch is not entered). |
| `test_backlinks_malformed_falls_back` | `backlinks` present but non-list (`null`, a dict, a non-list scalar); assert it is treated identically to absent — fallback traversal runs and the primary path does not raise (SF10). |
| `test_pipeline_orphan_check_fires` | WikiLog with `wiki_action=ingest` and `wiki_notes` containing `"relation_rollback"` near the timestamp of a zero-relation object; assert finding `check="pipeline_orphan"`, severity High. |
| `test_orphan_check_fires_after_grace` | Object with zero `wiki_relations`/`backlinks` whose effective ingest age is older than 7 days. **The age MUST be seeded on a linked `wiki_source` (reached via `wiki_sources`), NOT as a top-level `wiki_ingested_at` on the object** — the entity/concept carries no `wiki_ingested_at` (SF5). The fixture seeds the `wiki_sources` relation + a `wiki_source` whose `wiki_ingested_at` is >7d old; assert the source dereference happens and finding `check="orphan"`, severity High. (Seeding the property on the object would false-green against an impl that never dereferences the source — ADV-3.) |
| `test_orphan_check_suppressed_within_grace` | Same fixture, but the linked `wiki_source.wiki_ingested_at` is < 7 days ago; assert no orphan finding. |
| `test_unreviewed_needs_review_fires` | `wiki_entity` with `wiki_status=needs-review` (any age); assert finding `check="unreviewed_needs_review"`, severity High. |
| `test_stale_needs_review_fires` | `wiki_entity` with `wiki_status=needs-review` AND an effective ingest age > 30d **seeded on a linked `wiki_source` (`wiki_ingested_at < now − 30d`), via `wiki_sources` — NOT on the object** (SF5); assert the source dereference happens and finding `check="stale_needs_review"`, severity Medium. (Object-level seeding would false-green — ADV-3.) |
| `test_both_needs_review_checks_fire_on_aged_object` | Same aged needs-review object fires BOTH `unreviewed_needs_review` (High) AND `stale_needs_review` (Medium); assert both appear in `findings[]` and `summary` counts each. |
| `test_stale_stub_check_never_emitted` | Full lint run on a fixture with only `needs-review` / `reviewed` / `archived` status values; assert no finding with `check="stale_stub"` in the report. |
| `test_contradiction_check_passive` | `wiki_entity` with non-empty `wiki_contradictions` AND null `wiki_last_reviewed` → finding fires (manual population); pipeline fixture with empty `wiki_contradictions` → zero findings. Check scoped to `wiki_entity` only — `wiki_concept` has no `wiki_last_reviewed` (SF9). |
| `test_stale_check_fires` | Entity whose linked `wiki_source` has `wiki_ingested_at` such that `last_modified < that − 90d`; assert the source dereference happens and finding `check="stale"`, severity Medium (SF5). |
| `test_oversized_check_fires` | Description > 2000 chars; assert finding `check="oversized"`, severity Low, and `detail` is a char-count summary (not the raw body) (SF12). |
| `test_empty_type_check_fires` | Space with zero `wiki_concept` objects; assert finding `check="empty_type"`, severity Informational (only under default `all`). |
| `test_duplicate_sweep_fires_when_opted_in` | `semantic_search_core` monkeypatched to return a candidate with score **0.75** (in `[0.70, 0.85)`); call with `include_duplicates=True`; assert one entry in `potential_duplicates[]` with `similarity_score=0.75`. |
| `test_duplicate_sweep_excludes_outside_band` | `include_duplicates=True`; candidates with score **0.60** (below floor) and **0.95** (≥ 0.85 upper bound) both excluded from `potential_duplicates[]`. |
| `test_duplicate_sweep_self_match_and_pair_dedup` | `include_duplicates=True`; sweep returns the source object itself (excluded via `object_id` match) AND a reciprocal pair A→B / B→A; assert the pair appears **exactly once** in `potential_duplicates[]` (canonicalized) (SF8). |
| `test_duplicate_sweep_off_by_default` | Default call `wiki_lint(space)` (and `wiki_lint(space, severity_threshold="all")`) with `include_duplicates` unset; assert `semantic_search_core` is **never called**, `_qdrant()` is never constructed, and `potential_duplicates[]` is empty — the default path runs no sweep (CA-B1). |
| `test_duplicate_sweep_runs_regardless_of_threshold` | `include_duplicates=True, severity_threshold="high"`; assert `semantic_search_core` **is** called and `potential_duplicates[]` is populated (gates are orthogonal — the standalone array ignores the post-filter), while any `potential_duplicate` entry is absent from `findings[]` (Informational, filtered by the `high` threshold). |
| `test_duplicate_sweep_skipped_over_object_cap` | Enumeration returns > `WIKI_LINT_MAX_OBJECTS` (monkeypatched low) with `include_duplicates=True`; assert sweep skipped, `lint_sweep_skipped_object_cap` warning present, High/Critical findings still produced (SF2). |
| `test_severity_threshold_high_filters_medium_low` | Full fixture, all severities; `severity_threshold="high"` → `findings[]` only Critical + High; informational excluded; summary matches. |
| `test_severity_threshold_low_excludes_informational` | `severity_threshold="low"` (default `include_duplicates=False`) → Critical/High/Medium/Low retained, `empty_type`/`potential_duplicate` (informational) absent from `findings[]`; `potential_duplicates[]` empty (no sweep on the default path) (SF7). |
| `test_pre_check_schema_outdated_fires_before_write` | Mocked schema version older than `"0.4.1"` → `[CONFIG ERROR] wiki_schema_outdated`, `status="error"`, `error_category="config_error"`; no POST to objects. |
| `test_pre_check_schema_missing_aborts` | `_schema_version_from_objects` returns `None` (empty space) → `[CONFIG ERROR] wiki_schema_missing`, `status="error"`, no WikiLog POST (SF4). |
| `test_pre_check_schema_newer_warns_and_continues` | Live schema > code → lint continues, `wiki_schema_newer` warning in `warnings[]`, WikiLog still written (SF4). |
| `test_partial_status_on_get_object_failure` | One `get_object` returns 5xx → that object skipped + recorded in `warnings[]`, lint continues, `status="partial"`, WikiLog still written (SF6). |
| `test_pre_check_patch_decision_missing_fires_before_write` | Missing `patch-decision.md` (via `monkeypatch.setenv("ALDEIA_DIR", str(tmp_path))`) → `[CONFIG ERROR] patch_decision_missing_or_invalid` returned; no Anytype call. |
| `test_pre_checks_fire_before_wikilog_write` | Both pre-check failure paths assert zero POST calls. |
| `test_object_count_budget_warning_above_500` | Mocked enumeration returns 501 objects; assert `lint_object_count_exceeded_budget: 501` in `LintReport.warnings`. |
| `test_wikilog_receipt_written_on_clean_run` | Clean run; assert one POST with `type_key="wiki_log"` and `wiki_action=lint` in the body, and `elapsed_ms >= 0` in the report (G1). |
| `test_wikilog_skipped_on_pre_check_failure` | Pre-check failure; assert zero POST calls. |
| `test_tag_resolution_never_calls_space_level_tags` | **Negative assertion (QA ADV-2):** register a distinct `respx` route for the space-level `GET /v1/spaces/{space_id}/tags` endpoint; run a full lint that resolves the `needs-review`/`lint` tags; assert that route's `.called` is **False** and that resolution went through the property-scoped two-step (`list_properties` → `list_tags(space_id, property_id)`). Guards the exact #285/#289 wire defect from slipping past the no-arg catch-all mocks. |
| `test_wiki_lint_registered_and_cli_routed` | `wiki_lint` in MCP tool registry (server.py) with the `include_duplicates` parameter exposed; `"wiki-lint"` in `cli.SUBCOMMANDS` with a `--include-duplicates` flag routing to `_cmd_lint`. No live services. |

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

    def test_backlinks_field_shape_live(self):
        """ADV-1: confirm the live `get_object` backlinks shape the D1 primary
        path depends on (asserted from a session finding, not CI-covered).
        Impl task ONE is to confirm this against a real object before building
        the primary path; this smoke keeps that confirmation alive."""
        space_id = os.environ.get("ANYTYPE_SPACE_ID")
        if not space_id:
            pytest.skip("ANYTYPE_SPACE_ID not set — live backlinks smoke skipped")
        from anytype_llm_wiki.wiki.anytype_client import AnytypeReadClient
        # Pick any enumerable object with a known inbound relation in the test space.
        obj_id = os.environ.get("ANYTYPE_BACKLINKED_OBJECT_ID")
        if not obj_id:
            pytest.skip("ANYTYPE_BACKLINKED_OBJECT_ID not set — backlinks smoke skipped")
        obj = AnytypeReadClient().get_object(space_id, obj_id)
        # The D1 contract: `backlinks` is present and is a list (possibly empty),
        # each element parseable by _parse_relation_elements (id string or {"id": ...}).
        assert "backlinks" in obj, "get_object response lacks `backlinks` — D1 primary path assumption violated"
        assert isinstance(obj["backlinks"], list), f"backlinks is {type(obj['backlinks'])}, expected list"
```

Run with: `uv run pytest -m live tests/wiki/test_lint.py`
Exclude from CI: `uv run pytest -m 'not live'`

---

## Acceptance Criteria

1. **D1 — Backlinks primary:** `wiki_lint` reads inbound relations from `obj.get("backlinks", [])` on the `get_object` response as the primary path; the O(N) reciprocal traversal is code-level fallback, only entered when `backlinks` is absent/empty (CI-mocked `test_backlinks_primary_no_traversal`).

2. **D2 — `stale_needs_review` replaces `stale_stub`:** a needs-review entity/concept older than `WIKI_LINT_STALE_NEEDS_REVIEW_DAYS` (default 30d) yields a Medium finding with `check="stale_needs_review"`; no finding with `check="stale_stub"` is ever emitted (CI-mocked).

3. **D3 — `unreviewed_needs_review` fires as High:** any needs-review entity/concept (any age) yields a High finding with `check="unreviewed_needs_review"`; a seeded fixture with a recently-set `wiki_status=needs-review` produces at least one High finding (CI-mocked).

4. **Double-count rule:** a needs-review entity older than 30d fires BOTH `unreviewed_needs_review` (High) AND `stale_needs_review` (Medium) — both appear in `findings[]` and both are counted in `summary` (CI-mocked `test_both_needs_review_checks_fire_on_aged_object`).

5. **All 10 check types produce findings on seeded fixtures:** Critical (`asymmetric_relation`), High (`pipeline_orphan`, `orphan`, `unreviewed_needs_review`, `contradiction_unresolved`), Medium (`stale`, `stale_needs_review`), Low (`oversized`), Informational (`empty_type`, `potential_duplicate`) — each verified by a dedicated CI-mocked test (G2).

6. **Contradiction check passive:** zero `contradiction_unresolved` findings on a pipeline wiki fixture (all `wiki_contradictions` empty); finding fires when `wiki_contradictions` is manually populated (CI-mocked `test_contradiction_check_passive`).

7. **`severity_threshold` filtering + informational gating (SF7):** order `critical > high > medium > low > informational`. `="high"` returns only Critical+High; `="low"` retains down to Low but excludes informational; only `="all"` includes informational findings. `severity_threshold` is a pure post-filter on `findings[]` and does NOT control whether the Qdrant sweep runs (that is `include_duplicates`, AC16) (CI-mocked `test_severity_threshold_high_filters_medium_low` + `test_severity_threshold_low_excludes_informational`).

8. **Duplicate sweep correct band + dedup (B1/SF8):** when invoked with `include_duplicates=True`, potential-duplicate pairs appear for `0.70 <= score < WIKI_LINT_DUPLICATE_MAX_SCORE` (default 0.85) and are absent below 0.70 / at-or-above 0.85; self-matches are excluded and each reciprocal pair is emitted exactly once (CI-mocked `test_duplicate_sweep_fires_when_opted_in`, `test_duplicate_sweep_excludes_outside_band`, `test_duplicate_sweep_self_match_and_pair_dedup`).

9. **QA#25 schema gate — three branches (SF4):** `live < code` → `[CONFIG ERROR] wiki_schema_outdated`; `live is None` → `[CONFIG ERROR] wiki_schema_missing`; both abort with `status="error"`, `error_category="config_error"`, no WikiLog POST. `live > code` → `wiki_schema_newer` warning and lint continues (CI-mocked, three tests).

10. **QA#30 fires before write** (by reference — per master spec line 905 and research §G): missing patch-decision → `[CONFIG ERROR] patch_decision_missing_or_invalid`, no Anytype call (CI-mocked).

11. **WikiLog receipt + status lifecycle (SF6/G1):** every `ok` or `partial` run writes one `wiki_log` object with `wiki_action=lint` and reports `elapsed_ms >= 0`; a `get_object`/sweep failure yields `status="partial"` (skipped object in `warnings[]`) without aborting; WikiLog is skipped only on aborting pre-check failure (`status="error"`) (CI-mocked `test_wikilog_receipt_written_on_clean_run`, `test_partial_status_on_get_object_failure`, `test_wikilog_skipped_on_pre_check_failure`).

12. **Object budget warning + sweep cap (SF2):** >500 objects enumerated → `lint_object_count_exceeded_budget: {N}` in `warnings`; > `WIKI_LINT_MAX_OBJECTS` → duplicate sweep auto-skipped with `lint_sweep_skipped_object_cap` warning while High/Critical findings still produced (CI-mocked `test_object_count_budget_warning_above_500` + `test_duplicate_sweep_skipped_over_object_cap`).

13. **D5 wire contracts: tag resolution uses property-scoped two-step:** no call to `/v1/spaces/{space_id}/tags`; all tag resolution goes through `list_properties` → `list_tags(space_id, property_id)` (CI-mocked `test_asymmetric_relation_check_fires` + needs-review tests verify the two-step path).

14. **CLI + server registration:** `"wiki-lint"` in `cli.SUBCOMMANDS` routing to `_cmd_lint` with a `--include-duplicates` flag; `wiki_lint` registered as MCP tool in `server.py` with the `include_duplicates` parameter exposed and without shadowing existing tools (CI-mocked `test_wiki_lint_registered_and_cli_routed`).

15. **Live smoke (additive):** lint against a real space returns `status in ("ok", "partial")` and a non-null `wiki_log_id`; a second skip-gated smoke confirms the live `get_object` `backlinks` field is present and a list (ADV-1, the D1 primary-path assumption) (`@pytest.mark.live`, skip-gated on `ANYTYPE_SPACE_ID` / `ANYTYPE_BACKLINKED_OBJECT_ID`).

16. **Duplicate sweep is opt-in — default honors the perf budget (CA-B1):** `include_duplicates` defaults to `False`; the default `wiki_lint(space)` call (and any `severity_threshold` value) runs **no** Qdrant sweep — `semantic_search_core` is never called, `_qdrant()` is never constructed, `potential_duplicates[]` is empty — so the default path imposes zero bge-m3 load and honors the advertised ≤60s/≤500 budget. The sweep runs only when `include_duplicates=True` (and is still skipped above `WIKI_LINT_MAX_OBJECTS`). The advertised perf claim describes the default sweep-off path (CI-mocked `test_duplicate_sweep_off_by_default` + `test_duplicate_sweep_runs_regardless_of_threshold`).

---

## Implementation Plan

### Files Changed

| File | Action |
|------|--------|
| `src/anytype_llm_wiki/wiki/lint.py` | NEW — `wiki_lint(space_id, severity_threshold="all", include_duplicates=False)`; dual-client setup, object enumeration, 10-check battery, duplicate sweep (band `[0.70, 0.85)`, **gated on `include_duplicates=True`** + object cap), LintReport assembly, WikiLog receipt |
| `src/anytype_llm_wiki/wiki/cli.py` | EDIT — add `"wiki-lint"` to `SUBCOMMANDS` (cli.py:21), add `_cmd_lint` with a `--include-duplicates` flag (store_true, default False) threaded into `wiki_lint(..., include_duplicates=...)` |
| `src/anytype_llm_wiki/server.py` | EDIT — register `wiki_lint` MCP tool exposing the `include_duplicates: bool = False` parameter (docstring notes the sweep is opt-in and exceeds the ≤60s budget) |
| `src/anytype_llm_wiki/wiki/config.py` | EDIT — add a `_bounded_float([0,1])` guard; add `lint_oversized_chars()`, `lint_orphan_grace_days()`, `lint_stale_needs_review_days()`, `lint_max_objects()`, `lint_pipeline_window_seconds()` (`_positive_int`) + `lint_duplicate_max_score()` (`_bounded_float`) |
| `.env.example` | EDIT — add six `WIKI_LINT_*` vars |
| `README.md` | EDIT — add lint section; "How it works" maintain loop; **document that the duplicate sweep is opt-in (`include_duplicates=True`) and that the advertised ≤60s/≤500 budget describes the default sweep-off path** (CA-B1 — no false perf claim); grep marketing claims for consistency (Mem0 #140 R2 lesson) |
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
| `scrub_credentials(url)` | util.py:98 | strip userinfo + query/fragment from URL-shaped error/WikiLog fragments (SF11) |
| `strip_control_chars(text)` | util.py:82 | sanitize+truncate object text in `detail`/WikiLog subject/notes (SF12) |
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

1. Add the `_bounded_float` guard and config accessors to `wiki/config.py` (`lint_oversized_chars`, `lint_orphan_grace_days`, `lint_stale_needs_review_days`, `lint_max_objects`, `lint_pipeline_window_seconds`, `lint_duplicate_max_score`) and the six vars to `.env.example`.
2. Implement `wiki/lint.py` with signature `wiki_lint(space_id, severity_threshold="all", include_duplicates=False)`: QA#30 → enumerate → QA#25 (3 branches) → tag resolution → check battery (asymmetric → orphan/pipeline-orphan → contradiction → stale → oversized → empty-type → duplicate sweep [only if `include_duplicates=True` and `N <= lint_max_objects()`]) → severity filter → LintReport assembly → WikiLog receipt. The empty-type check is placed late here (the master data-flow lists it first); this reorder is deliberate and harmless — checks are independent and share the per-run cache (G6).
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
- **Duplicate-sweep random sampling:** v0.5.0 makes the sweep opt-in (`include_duplicates=True`, CA-B1) and bounds its cost via the `WIKI_LINT_MAX_OBJECTS` hard skip (SF2) — so the default path is always cheap and an opted-in sweep above the cap is skipped wholesale. A finer-grained `WIKI_LINT_DUPLICATE_SAMPLE` (embed a random subset rather than all-or-nothing) remains a natural follow-up: it would let an opted-in caller get partial-coverage duplicate detection on a very large wiki instead of a skipped sweep.
- **Multi-space federation:** deferred (master spec roadmap).
- **Auto-fix / auto-merge of findings:** explicitly out of scope — `wiki_lint` is report-only and mutates nothing but its own WikiLog receipt.

---

## Review Resolution (R1)

Each finding from `review-r1.md` → disposition. Source-cited findings (SF4/SF5/SF11) re-verified against the cited lines.

- **B1** (duplicate band was an object-count) — FIXED: D4, Lint-Checks, Config, AC8, and both duplicate tests now use literal `[0.70, 0.85)` via new `WIKI_LINT_DUPLICATE_MAX_SCORE` knob (default 0.85) guarded by new `_bounded_float`; `index_threshold()` reuse and `/1000` hack removed; Config claim reversed.
- **B2** (uncapped N-embedding sweep) — FIXED: sweep runs only on `severity_threshold="all"`, auto-skips above `WIKI_LINT_MAX_OBJECTS`; Performance Budget gives per-phase arithmetic showing the no-sweep battery ≈51s ≤60s @ 500.
- **SF1** (fan-out arithmetic) — FIXED: Performance Budget table, sequential, per-phase derivation.
- **SF2** (hard cap) — FIXED: `WIKI_LINT_MAX_OBJECTS` (default 2000) auto-skips sweep with warning; lint continues degraded.
- **SF3** (single-space cache key) — FIXED: stated in Resource Impact.
- **SF4** (schema branches) — FIXED: Pre-Checks now has `None→wiki_schema_missing` (abort), `<→outdated` (abort), `>→newer` (warn-continue); verified against `query.py:424–448`. Three tests + AC9.
- **SF5** (`wiki_ingested_at` cross-source hop) — FIXED: Age-derivation note covers orphan/stale/stale_needs_review; verified `wiki_ingested_at` is on `wiki_source` only (`types_schema.py:79`, `ingest.py:621`); source fetches budgeted in Resource Impact.
- **SF6** (status lifecycle) — FIXED: ok/partial/error defined; `test_partial_status_on_get_object_failure` + AC11.
- **SF7** (severity ordering + informational) — FIXED: total order stated, `low` excludes informational, `potential_duplicates[]` gated to `all`; `severity_threshold="low"` test + AC7.
- **SF8** (self-match + pair canonicalization) — FIXED: D4 sweep mechanics; dedup test.
- **SF9** (contradiction on concept) — FIXED: check scoped to `wiki_entity` only (verified `wiki_last_reviewed` absent from `wiki_concept`, `types_schema.py:106–113`).
- **SF10** (malformed backlinks) — FIXED: non-list treated as absent → fallback; `test_backlinks_malformed_falls_back`.
- **SF11** (scrub_credentials wording) — FIXED: corrected to "strips userinfo + query/fragment from URL-shaped fragments"; verified `util.py:98–141`.
- **SF12** (detail/WikiLog truncation) — FIXED: char-count summary for oversized; `strip_control_chars(...)[:N]` on object text into detail/subject/notes.
- **G1** (`elapsed_ms`) — FIXED: `elapsed_ms >= 0` asserted in clean-run test + AC11.
- **G2** (9→10 checks) — FIXED: relabelled in Tool-signature note + AC5.
- **G3** (pipeline_orphan window) — FIXED: `WIKI_LINT_PIPELINE_WINDOW_SECONDS` (default 300s) tolerance.
- **G4** (missing `wiki_status`) — FIXED: treated as not-needs-review (severity/status block).
- **G5** (`error_category`) — FIXED: set on all error paths matching `query.py:430/442`.
- **G6** (check reorder) — FIXED: deliberate-reorder call-out in Ordering.
- **G7** (dual-client) — FIXED: Resource Impact states AnytypeReadClient + WikiClient split.
- **G8** (doctor) — FIXED: "no doctor change; doctor remains green" in Security.
- **G9** (enumeration between gates) — FIXED: Pre-Checks states the read is intentionally between QA#30 and QA#25.

> **Note on B2 (superseded by CA-B1):** the R1 resolution above gated the sweep on `severity_threshold="all"`. The post-spec council found that gate insufficient because `"all"` is the *default* — so the default call was still the heavy path. CA-B1 (below) supersedes it: the sweep is now gated on `include_duplicates=True` (default `False`), decoupled from `severity_threshold` entirely.

---

## Council Resolution (post-spec R1)

The post-spec review council reached **REWORK → spec** on one BLOCKING finding (CA-B1), with all five other dimensions clean ("do not reopen"). Per Jan's direction these edits were applied directly to the spec rather than re-running the spec phase. Disposition:

- **CA-B1 (BLOCKING — Client Advocate, corroborated by Infra) — default invocation violates the ≤60s/≤500 budget because the sweep is gated on the *default* `severity_threshold="all"`.** RESOLVED via the council's preferred direction (Jan's call: **opt-in**). Added `include_duplicates: bool = False` as the sweep's sole cost gate, decoupled from `severity_threshold`. The default `wiki_lint(space)` call now runs only the ~51s structural battery and honors the advertised budget with zero bge-m3 load on the shared Ollama. Edits: Tool-signature delta; SF7 (gates orthogonal); D4 + `potential_duplicate` check row; Performance Budget (default-path budget statement + internal-contradiction resolved); Resource Impact; SF2 ceiling wording; Implementation Plan (lint/cli/server/README rows + Ordering); new **AC16**; reworked sweep tests (`test_duplicate_sweep_off_by_default`, `test_duplicate_sweep_runs_regardless_of_threshold`, opted-in band tests); Deferred-items sampling note. The spec-internal contradiction the chair flagged (≤60s budget vs default-on sweep) is now resolved — the advertised budget describes the default sweep-off path.
- **ADVISORY-1 (CTO + QA ADV-3) — `backlinks` shape unverifiable from source.** FOLDED: D1 "Impl task ONE" note (confirm live shape before building the primary path) + new skip-gated `test_backlinks_field_shape_live` smoke asserting `backlinks` is present and a list + AC15 updated.
- **ADVISORY-2 (QA) — AC13 needs an explicit negative assertion against the space-level `/tags` endpoint.** FOLDED: new `test_tag_resolution_never_calls_space_level_tags` (registers the space-level route and asserts `.called is False`).
- **ADVISORY-3 (QA) — age-check fixtures must seed `wiki_ingested_at` on a linked `wiki_source`, not the object.** FOLDED: `test_orphan_check_fires_after_grace`, `test_orphan_check_suppressed_within_grace`, and `test_stale_needs_review_fires` reworded to seed the timestamp on a linked `wiki_source` reached via `wiki_sources` (false-green guard).
- **ADVISORY 4–10 (CSO/CPO/CA, impl/test/docs guidance):** carried forward to the test/impl phases — single shared sanitize+truncate helper (CSO-4); confirm tokens never interpolated into output (CSO-5); passive-contradiction behavior must reach README/docstring (CPO-6); double-count detail legibility (CPO-7); `WIKI_LINT_DUPLICATE_SAMPLE` on the roadmap (CPO/CA-8, see Deferred Items); compact knob docs + don't oversell `pipeline_orphan` (CA-9); cosmetic `indexer.py` path note (CTO-10). These are not spec defects and require no spec edit.
