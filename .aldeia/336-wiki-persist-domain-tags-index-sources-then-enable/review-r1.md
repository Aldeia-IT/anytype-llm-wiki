# Spec Review R1 — wiki-persist-domain-tags-index-sources-then-enable (#336)

**Date:** 2026-06-13
**Reviewers:** 3 independent spec reviewers (architecture/completeness; product/operational; QA/testability/security) + lead inline checks.
**Spec under review:** `spec.md` (status SPEC, commit 3b293f6 + status edit).

## Consolidated Verdict: **NEEDS REVISION**

All three reviewers returned APPROVED WITH CONDITIONS. The conditions include **one BLOCKING** test-coverage gap (B1, lead-verified) plus a cluster of SHOULD-FIX items, several of which are load-bearing (the resolver home-module direction, the empty-excerpt inert-filter gap, the OD-B third option, the AC-P3 test seam). Because BLOCKING findings exist and several SHOULD-FIX items change the design (not just prose), this goes to a fix cycle. The spec is fundamentally sound and well-grounded — every #323 seam was independently verified as accurate — so one focused fix round should resolve it.

---

## BLOCKING

### B1 — §10/§12 omit four existing `test_chunker.py` tests that #336 inverts (lead-verified)
Adding `wiki_excerpt` to `WIKI_TEXT_PROPERTY_KEYS` breaks four tests that encode the OLD "wiki_excerpt excluded / sources produce zero chunks" contract. Confirmed present on this branch:
- `tests/test_chunker.py:159` `test_wiki_text_property_keys_has_eight_entries` — asserts `len(...) == 8` → becomes 9.
- `tests/test_chunker.py:164` `test_wiki_text_property_keys_exact_set` — asserts the exact 8-key frozenset.
- `tests/test_chunker.py:179` `test_wiki_excerpt_not_in_allowlist` — asserts `"wiki_excerpt" not in WIKI_TEXT_PROPERTY_KEYS` (directly inverted by #336).
- `tests/test_chunker.py:315` `test_wiki_excerpt_excluded` — asserts a `wiki_source` with `wiki_excerpt` produces `chunks == []` (directly inverted by AC-S1).

The spec correctly identifies the `test_reindex_creates_payload_indexes` inversion (§10.2) but misses these four. **Fix:** Add a §10.2 subsection enumerating all four as required updates: bump count to 9, update the exact-set expectation to include `wiki_excerpt`, invert/delete `test_wiki_excerpt_not_in_allowlist`, and invert `test_wiki_excerpt_excluded` (rename to assert chunks ARE produced — becomes AC-S1's sibling). Add a line to §12. (`test_wiki_property_heading_maps_all_eight_keys` at line ~189 and `test_wiki_property_heading_values` survive — note them as safe.)

---

## SHOULD-FIX

### SF1 — Resolver home module is backwards relative to the codebase's own precedent (consensus: arch + product reviewers)
The spec defines `_resolve_multi_select_tags` in `remember.py` and inline-duplicates it in `ingest.py` (D1, D4, Alternatives), accepting duplication to avoid a circular import. But the existing precedent is the opposite: `_resolve_wiki_action_tag` lives in **`ingest.py`** and `remember.py` already imports from `ingest.py` (`remember.py:39 from .ingest import (...)`; docstring: "remember.py reuses this resolver"). The non-circular direction is **ingest → (remember imports from ingest)**. **Fix:** Define `_resolve_multi_select_tags` in `ingest.py` (alongside `_resolve_wiki_action_tag`) and import it into `remember.py`, mirroring the established pattern. This eliminates the duplication the spec accepts and matches the dependency arrow. Update D1/D4/§Alternatives accordingly. (`_create_source`'s source_type resolve then also reuses the same in-module helper — no duplication.)

### SF2 — Empty-excerpt remember sources are an inert-filter gap (consensus: arch + QA)
`_create_remember_source` writes `excerpt = ""` for agent-type sources with no `source_note` (remember.py:178-181), and `_chunk_properties` skips empty text. So agent sources get `wiki_source_type="agent"` written but produce ZERO chunks → never reach Qdrant → `source_type=["agent"]` returns empty. This is exactly the "no inert filter" footgun the ticket forbids. **Fix:** Either (a) document the limitation explicitly (agent sources without a note are not filterable by source_type), or preferably (b) have `_create_remember_source` write a minimal non-empty excerpt (e.g. the source name / a stub) so a chunk is produced. Add a test for the chosen behavior.

### SF3 — D2 per-candidate `props` append placement is ambiguous (arch)
In `ingest.py`, `props` is rebuilt fresh INSIDE the `for cand in candidates` loop (lines ~811/815), with `create_object` at ~855 and `update_object` at ~823. D2 says resolve once at the start of `_run_ingest` (correct) then "append to `props`" — but an implementer could append to a list that's reassigned each iteration. **Fix:** State explicitly that `domain_tag_prop` is appended to the per-candidate `props` list inside the loop, for BOTH the create and update branches.

### SF4 — `_create_source` reuse/update path under-specified (arch)
`_create_source` has two write paths: the dedup-reuse `update_object` at ~954 and `create_object` at ~962, both using the shared `props` built at ~935. Appending `wiki_source_type` to that shared `props` covers both — favorable — but the spec's "before the create_object call" wording understates it and AC coverage only names create. **Fix:** State that source_type is appended to the shared `props` (covering both reuse-update and create), and add a test for the reuse path.

### SF5 — OD-B should present the "index but default-exclude" third option (product; load-bearing)
The spec frames OD-B as binary (default-on vs defer entirely) and pre-decides default-on. A middle option exists and is never put to Jan: chunk+index `wiki_excerpt` (so `source_type` filter and `types=["wiki_source"]` work — the full ticket value) BUT have `semantic_search`'s DEFAULT `types` exclude `wiki_source` unless explicitly requested — preserving today's default result semantics, symmetric with how `wiki_query` already excludes sources. **Fix:** Add this third option to OD-B with its one-line tradeoff and let Jan choose. Also note explicitly that result dicts/payloads carry `type_key`, so the assistant CAN distinguish source excerpts from synthesized knowledge (materially softens the noise concern). Indexing-vs-surfacing are separable — #323's OD-2 deferred precisely the surfacing decision.

### SF6 — OD-A: name the manual-backfill follow-on and surface the corpus-coverage caveat to Jan (product)
The "no auto-derivation → forward-only" conclusion is sound (lead + research cross-checked: domain_hint is discarded at ingest.py:660, absent from WikiLog/source/entity). But forward-only means the ENTIRE pre-#336 corpus stays un-filterable by domain_tags — a material caveat on a single-user wiki, currently only a release-note footnote. The write path being built (`_resolve_multi_select_tags` + `update_object`) makes a manual bulk-tag/re-ingest path cheap. **Fix:** In OD-A, name manual backfill as an explicit (out-of-scope but available) follow-on, and surface the corpus-coverage caveat in the Jan-facing Open Questions, not just the release note.

### SF7 — AC-P3 test seam targets the wrong call (QA)
`wiki_remember` does not call `_apply_batch` directly — it calls `worklog.begin(space_id, new_subjects, meta=meta)` (remember.py:345) and the drain path reconstructs `_meta` from the persisted JSON (worklog.py:230). Asserting against `_apply_batch` requires mocking the queue and can mask whether `domain_tags` survives JSON serialization. **Fix:** Specify AC-P3 to assert the `meta` argument to `worklog.begin` (or the drained `_meta` round-trip) carries `domain_tags`, exercising the real serializer.

### SF8 — Missing tests: `_chunk_to_payload` propagation + resolver unit behavior (QA)
- D6's `_chunk_to_payload` extension (the code that copies `source_type`/`domain_tags` into the Qdrant payload, and omits them when absent) has NO dedicated test. AC-S2/S3 test `chunk_object` output; AC-F-* test the filter build; nothing covers the payload-builder copy. **Fix:** add a payload-level assertion (reindex-seam or direct `_chunk_to_payload` unit test).
- `_resolve_multi_select_tags` has no direct test, yet AC-P1/P4 MOCK it out. The wiring tests (AC-P1/P4) are legitimate (they fail pre-impl, testing real append-to-props wiring — not tautological), but a resolver that silently returns `[]` for valid names would pass every AC-P/S test. **Fix:** add a resolver unit test covering success, unknown-name silent-skip, and `degraded=True` on `httpx.HTTPError`.

### SF9 — Add a test pinning the documented unknown-value→zero-match/no-raise behavior (QA)
§D11/§14 document that unknown `source_type`/`domain_tags` values produce zero matches with no error. This is the typo-footgun the ticket warns of; the mitigation is docs only. **Fix (min):** add a test asserting unknown-value → zero results, no raise, on both tools. **Consider (SUGGESTION):** `wiki_query` already calls `_domain_taxonomy(client, space_id)` on the write path and has a live client — an optional taxonomy *warning* (not error) on out-of-taxonomy filter values, via the existing `schema_warnings` mechanism, would turn silent-empty into actionable feedback. Weigh against scope.

### SF10 — Pin the moot `source_type`-in-`wiki_query` no-op with a test (QA)
D10 documents that `source_type` on `wiki_query` is a no-op (no `wiki_source` in Tier-1 enumeration or Tier-2 types). It's documented but not test-pinned, so a future reader could "fix" it. **Fix:** add a `wiki_query`-level test passing `source_type=["document"]` and asserting entities/concepts are still returned (behavior unaffected).

### SF11 — Release note + rollback clarity (product)
- Release note must state forward-only explicitly ("existing objects are not retroactively tagged; only objects created/updated after upgrade carry `domain_tags`") and make source-excerpt scoping prescriptive (give the exact `types=[...]` to preserve prior behavior).
- §15 rollback: label the downgrade re-embed as expected-cost, not a surprise ("rollback re-stamps v2 and forces one more full re-embed — seconds, expected, not an error"). Reconcile with the "needs no data migration" phrasing.

---

## SUGGESTION

- **SG1 (arch/OD-C):** Re-ingesting an entity with a different `domain_hint` REPLACES tags (SET semantics) — lossy for multi-domain entities. Note in the release note alongside forward-only. Merge is the documented follow-on.
- **SG2 (arch):** AC-S1 test assertion is weak (substring check passes trivially). Assert `heading == "Excerpt"` directly to pin `WIKI_PROPERTY_HEADING["wiki_excerpt"]`.
- **SG3 (product):** Consider NOT exposing `source_type` on `wiki_query`'s public signature at all (a permanent documented no-op invites confusion), or make the no-op impossible to miss. Defensible either way — flag as a deliberate choice.
- **SG4 (QA):** Name the current-branch fakes (`tests/test_indexer.py` `FakeQdrantClient` ~172, `FakeQdrantClientV2` ~283) as "verified safe under the getattr guard, no update needed" so the implementer confirms post-rebase rather than hitting an `AttributeError`.
- **SG5:** Minor line-number drift (e.g. `config.py` version at line 37 not 43) — already hedged by the spec's note that line numbers may drift. No action.

---

## Verified CORRECT (no action — recorded so the fixer doesn't churn them)
- All #323 extension seams independently verified against `git show aldeia/323-...`: `_chunk_to_payload` (indexer.py:20-37), `_ensure_payload_indexes` + getattr guard (40-57), `semantic_search_core` must-build + `Filter(must=must) if must else None` (88/116), D3 migration (`force_full`, marker gated to `space_id is None`), Tier-1 predicates (query.py:275-300), `_WIKI_TYPE_KEYS` (query.py:50). `MatchAny` importable on pinned qdrant-client.
- `MatchAny` semantics: correct on BOTH scalar `source_type` (equals-any) and array `domain_tags` (ANY-overlap).
- No-filter regression preserved (empty lists falsy → `must` empty → `None`).
- Chunker read shape matches prereq-verification.md; `wiki_excerpt` written as `{"key":...,"text":...}` matches `_chunk_properties`' `prop.get("text")`; body-vs-properties dedup fires correctly for body-less sources.
- D3 meta bug real (lead-verified: remember.py:336 `meta` omits domain_tags; validated at 301-308).
- Source object correctly NOT given domain_tags (design rationale sound, consistently applied).
- No existing `test_ingest.py`/`test_remember.py` assertion asserts domain_tags is NOT written (silent absence, not asserted) → no breakage there.
- Egress claim holds; validation split (semantic_search raises / wiki_query error-dict) consistent with #323.

---

## Conditions to clear for APPROVAL
1. Resolve **B1** (enumerate the four chunker-test inversions in §10.2 + §12).
2. Address **SF1–SF11** (design + test-plan fixes). SF1, SF2, SF5, SF6, SF7, SF8 are the load-bearing ones.
3. **OD-A (forward-only)** and **OD-B (source-surfacing — now with the third option)** and **OD-C (SET semantics)** remain Jan's calls at the Decide gate — the spec must present them as decisions, not pre-decide them.
