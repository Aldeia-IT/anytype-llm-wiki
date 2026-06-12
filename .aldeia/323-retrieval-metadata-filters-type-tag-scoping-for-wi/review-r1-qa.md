# QA Review R1 — Spec-Phase: Retrieval Metadata Filters (#323)

**Reviewer:** QA Director
**Date:** 2026-06-12
**Artifact:** `.aldeia/323-retrieval-metadata-filters-type-tag-scoping-for-wi/spec.md`
**Phase:** Spec review (acceptance criteria will become test assertions; mock realism is the #289 failure class)

---

## Traceability Table (ticket AC → spec test → covered?)

| Ticket AC (original intent) | Spec test(s) | Covered? | Notes |
|---|---|---|---|
| type filter | AC-F2 (`test_type_filter_applied`, indexer); AC-F10 (Tier-1) | **Partial** | Indexer level OK; AC-F10 not concrete (see BLOCKING-2). No `semantic_search` tool-surface test, no Tier-2 `wiki_query` test. |
| domain_tags filter | — (DEFERRED, D4/§12) | **No (deferred)** | Scope gap requiring explicit Jan acceptance — see BLOCKING-1. |
| date/source filter | AC-F3 (source_type), AC-F4 (date), AC-F8/F9 (chunker writes) | **Yes (Tier-2 indexer)** | Tier-1 date/source_type predicates have NO test (see BLOCKING-2 / SHOULD-FIX-1). |
| combined AND | AC-F5 (`test_combined_filter_and`) | **Yes** | Asserts ≥3 must-conditions + keys present. Adequate. |
| no-filter regression | AC-F1 (`test_no_filter_regression`) | **Partial** | Asserts `query_filter is None` only — not byte-identical (see SHOULD-FIX-2). |
| invalid-value rejection | AC-F6 (`test_invalid_date_raises_value_error`) | **Partial** | Only `semantic_search` date path tested. `wiki_query` error-dict path and empty-type-intersection path untested (see SHOULD-FIX-3). |
| payload-index-confirmed | AC-F7 (`test_ensure_collection_creates_payload_indexes`) | **Yes** | Verifies the three new index fields are created. Adequate. |

---

## Findings

### BLOCKING-1 — domain_tags deferral is a real scope gap; needs explicit Jan acceptance, not just a spec note
**Spec ref:** §2 (Out of Scope), D4, §4 OD-2, §12 (DEFERRED line)
The ticket title is literally "Type/Tag Scoping" and the ticket body enumerates a domain_tags filter as a required AC. The spec defers it. The *technical* justification is sound and well-evidenced (research Q3 §237-249: `wiki_domain_tags` is never written onto objects by ingest/remember, so a filter param would be inert and silently return zero). That is a legitimate reason to defer — shipping an inert param is a genuine footgun.

However, from a quality-gate standpoint this is a **scope reduction against the ticket's stated acceptance criteria**, and the spec correctly routes it to Jan via OD-2 but its status is still "SPEC, Review rounds: 0" with OD-2 unratified (§16 Q2). **This cannot be signed off as meeting the ticket's ACs until Jan ratifies the deferral at the Decide gate.** The "tag scoping" half of the title delivers 0% in v1.

**Impact:** If advanced without ratification, the deliverable will not satisfy the ticket as written and the gap will surface at acceptance.
**Recommended action:** Block advancement until OD-2 is explicitly ratified by Jan (CPO loop). The follow-up ticket scope in D4 is well-bounded and should be created as a linked dependency *before* this ticket closes, so the tag-scoping intent is not silently dropped. Flag to CPO: confirm the user's intent is satisfied by type+source+date in v1 with tags as a fast-follow.

---

### BLOCKING-2 — AC-F10 is not implementable as written ("full test setup omitted")
**Spec ref:** §10.2 AC-F10, §12 AC-F10
AC-F10 is the *only* test covering the Tier-1 in-memory filter path of `wiki_query` (§8.1–§8.4), and the entire cross-tier consistency claim ("consistent across Tier 1 and Tier 2", AC-F2/AC-F10 in §12) rests on it. The spec body says verbatim: *"Full test setup omitted here; test must monkeypatch synthesize to return a sentinel, and verify sources_consulted contains only objects of the requested type."*

This is exactly the failure class the prompt warns about: a test that cannot be written from the spec without the implementer guessing. The Tier-1 path (`query.py:478-485`) requires a constructed `wiki_query` call with: schema pre-checks passed (`_schema_version_from_objects` must return a valid version — §387), `AnytypeReadClient`/`WikiClient` mocked, `config.index_threshold` forced high to select Tier 1, synthesis stubbed, and `last_modified_date` present on enumerated objects. None of this is specified. The §8 predicates (`_has_source_type`, `_in_date_range`, type intersection) are presented as inline lambdas inside `wiki_query`, so they are **not independently unit-testable** as written — there is no seam.

**Impact:** Tier-1 filtering (a co-equal retrieval path) could ship with no real test coverage. The "consistent across Tier 1 and Tier 2" guarantee would be unverified. This directly touches existing `wiki_query` behavior — high regression surface.
**Recommended action:** Either (a) extract the three Tier-1 predicates into module-level pure functions (`_filter_by_type`, `_filter_by_source_type`, `_filter_by_date_range`) that take `(objects, param)` and return filtered lists, so each is unit-testable without standing up the full pipeline; or (b) fully specify the AC-F10 integration harness (the exact monkeypatch set, the enumerated-object fixtures with mixed types and dates, and the `sources_consulted` assertion). Option (a) is strongly preferred — it removes the "omitted" hole and gives Tier-1 the same assertion rigor as Tier-2. Add explicit Tier-1 tests for source_type and date (not just type).

---

### SHOULD-FIX-1 — AC-F2 assertion shape: verify against §6.2's nested-Filter construction (the #289 trap)
**Spec ref:** §6.2 (construction), §10.2 AC-F2 (assertion), research Q1 §100-110
I executed AC-F2 against §6.2 by hand. **The spec is internally consistent here — and notably avoids the #289 trap** — but there is a latent contradiction with the research that an implementer could trip over:

- §6.2 builds the type filter as a **nested `Filter(should=[FieldCondition(..., match=MatchValue(value=t))])`** (preserving the existing `indexer.py:53-61` pattern). The `must` list contains a `Filter` object, not a `FieldCondition`.
- AC-F2 (§10.2) correctly looks for `next(c for c in must if hasattr(c, "should") and c.should)` and reads `c.match.value` off the `should` children. **This matches §6.2's construction.** Good — the assertion does not contradict the build.

The trap: research Q1 §100-110 and §6.1's import of `MatchAny` recommend the *simpler* `FieldCondition(key="type_key", match=MatchAny(any=[...]))` form, and AC-F2's own import line (`from qdrant_client.models import FieldCondition, MatchAny, MatchValue`) imports `MatchAny`. If the implementer follows the research's "cleaner" recommendation instead of §6.2, the AC-F2 assertion (`hasattr(c, "should")`) will **fail** — because `MatchAny` produces a flat `FieldCondition` with no `.should`. The spec ships *two* contradictory type-filter shapes (nested-should in §6.2; MatchAny in §6.1 imports + research) and a test pinned to only one.

**Impact:** Implementer ambiguity → either the test or the impl is wrong on day one. This is precisely the mock-vs-reality mismatch that sank #289.
**Recommended action:** Pick ONE shape and state it as binding. Recommend keeping the existing nested-`Filter(should=...)` (§6.2) since it preserves current behavior and the regression test depends on it — and then **remove `MatchAny` from the §6.1 imports and add a one-line note** that the MatchAny alternative from research is explicitly NOT adopted in v1. AC-F2 is already correct for the nested form; do not change it.

---

### SHOULD-FIX-2 — No-filter regression test (AC-F1) is not strong enough to guarantee byte-identical behavior
**Spec ref:** §6.2 (no-filter guarantee), §10.2 AC-F1, research Q7
AC-F1 asserts only `fake.query_filter is None`. That proves the *filter* is unchanged but does **not** prove byte-identical behavior of the whole call. The new code path adds metadata extraction in the chunker and new payload writes; a regression could appear in: (a) the `query_points` kwargs other than filter (`limit`, `with_payload`, `collection_name`), (b) the result-dict shape returned to callers, or (c) `wiki_query` Tier-2 still passing `types=list(_WIKI_TYPE_KEYS)` when no `types` arg is given (the §8.1 change replaces that hardcoded value — a real regression risk for the default `wiki_query` path).

**Impact:** A change to the default `wiki_query` retrieval (e.g. `effective_types` computing to `None` vs `list(_WIKI_TYPE_KEYS)`) would not be caught. The §8.1 snippet sets `effective_types = None` when `types` is falsy, but Tier-2 must then still pass the full `_WIKI_TYPE_KEYS` — the spec says "replaces the current hardcoded `types=list(_WIKI_TYPE_KEYS)`" without stating what is passed when `effective_types is None`. **Underspecified and regression-prone.**
**Recommended action:** (1) Strengthen AC-F1 to also assert the full `query_calls[-1]` kwargs equal the pre-change kwargs (limit, collection, with_payload). (2) Add an explicit regression test for `wiki_query` with no `types` arg asserting Tier-2 still receives `types == list(_WIKI_TYPE_KEYS)` (not `None`). (3) Resolve the §8.1 ambiguity: state that when `effective_types is None`, Tier-2 passes `list(_WIKI_TYPE_KEYS)`.

---

### SHOULD-FIX-3 — Invalid-value rejection (AC-F6) covers only one of three error paths
**Spec ref:** §9.1, §9.2, §8.1, §10.2 AC-F6
The ticket AC is "invalid-value rejection." AC-F6 tests only the `semantic_search` invalid-date → `ValueError` path. Two specified error paths have **no test**:
1. `wiki_query` invalid date → must return the error **dict** `{"status":"error", ..., "error_category":"config_error"}` and NOT raise (§9.2, the never-raise contract). Untested.
2. `wiki_query` empty type-intersection → error dict with `error_category="config_error"` (§8.1). Untested.

Both are negative-path behaviors with a contract (never-raise / specific `error_category` string) that is easy to get wrong. Note also §8.1's inline error string hardcodes `"[CONFIG ERROR] type_filter_empty: ..."` rather than using the existing `_CONFIG_ERROR_PREFIX` constant (`query.py:64`) — a consistency nit that should reference the constant.

**Impact:** The `wiki_query` never-raise contract could regress (a raised `ValueError` would crash the tool instead of returning a structured error), undetected.
**Recommended action:** Add two tests: `test_wiki_query_invalid_date_returns_error_dict` (asserts no exception + `error_category == "config_error"`) and `test_wiki_query_empty_type_intersection_returns_error_dict`. Specify the exact `error_category` string value as a binding constant and have §8.1 use `_CONFIG_ERROR_PREFIX`.

---

### SHOULD-FIX-4 — Missing edge-case tests called out in the review mandate
**Spec ref:** §10.2 (test list), §6.2
None of these edge cases have tests, and each is a documented behavioral question:
- **Empty-list filter param** (`types=[]`, `source_type=""`): §6.2 guards with `if types:` / `if source_type:`, so `[]`/`""` are falsy and produce NO condition. This is *defined* behavior but **untested**, and it differs from `None` only in caller intent. Add `test_empty_type_list_produces_no_filter` asserting `query_filter is None` for `types=[]`.
- **Both date bounds present**: AC-F5 sets both but only asserts the key exists, not that `gte` AND `lte` are both populated on the `DatetimeRange`. Add an assertion that `date_cond.range.gte is not None and date_cond.range.lte is not None`.
- **Filter matching zero results**: no test that a valid filter returning an empty Qdrant result set yields `[]` (semantic_search) / the no-sources answer (wiki_query) without error. Add one.
- **Non-functional param on a tool**: `source_type` on entity/concept chunks matches nothing (D2). This is the silent-zero-result footgun the spec used to *justify* deferring domain_tags — yet source_type has the same property for non-source objects. Add `test_source_type_on_entity_matches_nothing` to document/lock the behavior.
- **Mixed valid+invalid type list** in `wiki_query` (§3 D1 / §16 Q3 "silent narrowing"): `types=["wiki_entity","wiki_source"]` silently drops `wiki_source`. This is an *open question* (Q3) with no test. Add a test pinning the silent-narrowing behavior once Jan decides Q3.

**Impact:** These are exactly the boundaries where behavior is "guessed" rather than verified; several are the spec's own justification arguments.
**Recommended action:** Add the five tests above. They are cheap (all use `FakeQdrantClientWithSearch`).

---

### SUGGESTION-1 — `FakeQdrantClientWithSearch` mock fidelity vs real `query_points` result objects
**Spec ref:** §10.1
The fake's `query_points` returns `_Result.points = self._mock_results`. The real `semantic_search_core` (`indexer.py:72-82`) reads `r.payload.get(...)` and `r.score` off each point. The spec's fake defaults `mock_results=[]`, so the result-mapping code is never exercised by the filter tests. That is acceptable for *filter-shape* tests (which is their purpose), but means no test confirms the new payload fields (`source_type`, `last_modified_date`) round-trip into results if ever surfaced. Low priority — those fields are filter-only, not returned. Note only.

### SUGGESTION-2 — Confirm tests FAIL before implementation (test-first verification)
**Spec ref:** §10, §11 Step 6
The spec orders tests as Step 6 (after impl). For a spec whose ACs become test assertions, recommend the test phase explicitly verify each of AC-F1..F9 **fails** against current `main` (e.g. AC-F3 source_type, AC-F7 new indexes) before impl, per project test-first convention. AC-F1 (regression) will *pass* on current code by design — call that out so it is not mistaken for a non-failing (therefore suspect) test.

### SUGGESTION-3 — Test convention alignment
**Spec ref:** §10, tests/test_indexer.py
The new tests use the established `monkeypatch.setattr(_indexer, "_qdrant", ...)` seam (matches `test_indexer.py:203`) — good. Confirm new tests are NOT placed inside the `_requires_live = True` `TestEnsureCollection` class (they would be auto-skipped, `test_indexer.py:53-55`). AC-F7 tests `_ensure_collection` with a pure fake and must live OUTSIDE that class. State this in §10.3.

---

## Assessment of the domain_tags deferral (mandate item 1)

The deferral is **technically well-justified and evidence-backed** (research Q3 §237-249 is conclusive: no write path exists; a Qdrant-only change cannot make the filter functional). The remaining ACs (type + source_type + date + combined + regression + invalid + index) **do satisfy the core retrieval-scoping intent** for the fields that are actually populated today. However, because the ticket *names* tag scoping in its title and ACs, this is a scope reduction that **Jan must explicitly accept** (OD-2), and a linked follow-up ticket must be created before close. It is not a defect in the spec; it is an unratified scope decision blocking sign-off.

---

## Verdict

**VETO (conditional) — do not advance until BLOCKING-1 (Jan ratifies domain_tags deferral + linked follow-up) and BLOCKING-2 (AC-F10 made implementable / Tier-1 predicates given a testable seam) are resolved; SHOULD-FIX-1..4 should be addressed before the test phase begins to prevent the #289 mock-vs-reality and untested-negative-path failure modes.**
