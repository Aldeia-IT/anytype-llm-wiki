# Implementation Review R1 — wiki_remember (#289)

**Verdict: NEEDS CHANGES** (1 CRITICAL, 1 MAJOR, 2 MINOR)

**Date:** 2026-06-04
**Reviewers:** security (general-purpose), spec-compliance/correctness (general-purpose), lead inline checks
**Branch:** aldeia/289-anytype-llm-wiki-wiki-remember-llm-assisted-agent
**Test state at review:** full wiki suite 367 passed, 5 skipped, 2 xfailed. All 4 named regression guards green. The CRITICAL below is a "tests-pass-for-the-wrong-reason" defect — green suite does NOT clear it.

---

## CRITICAL

### C1 — Runtime tag resolvers call a non-existent Anytype endpoint; all select-tag writes silently fail on the live path
**Files:** `wiki/remember.py:120-165` (`_list_space_tags`, `_resolve_tag_by_name`, `_resolve_wiki_status_tag`, `_resolve_wiki_source_type_tag`, `_resolve_remember_action_tag`)

`_list_space_tags` GETs `/v1/spaces/{space_id}/tags` — a **space-level** tags endpoint that exists nowhere in `WikiClient`, in `bootstrap`/`ingest`, or in the real Anytype local API. The real API (and `WikiClient.list_tags` / `create_tag`) keys tags by **property id**: `/v1/spaces/{id}/properties/{property_id}/tags` (verified `wiki_client.py:36-51, 127-135`; cross-checked against `ingest.py::_resolve_wiki_action_tag` and the ingest test note `test_ingest.py:1372-1374`: "the tags URL is /v1/spaces/{id}/properties/{prop_id}/tags").

**Consequence (production):** against live Anytype every call to `_resolve_wiki_status_tag`, `_resolve_wiki_source_type_tag`, `_resolve_remember_action_tag` 404s → degrades. So `wiki_status=needs-review` is NEVER written (defeats AC-R5 conflict review-flagging), `wiki_source_type` is NEVER written (AC-R13/R18), and the WikiLog `wiki_action=remember` select is NEVER stamped (AC-R12). All three silently degrade with `*_tag_not_found` warnings — the headline conflict-trust guarantee of the feature is inert in production.

**Why tests miss it:** `test_remember.py` mocks the fabricated `router.get(".../tags")` exact path, so the suite is green against the wrong wire contract. This is the *same defect class* the council caught earlier on THIS ticket (search GET vs POST, commit 519a31b/52ad68b) and the Mem0 lesson `2d0dd099`: a test mocking an endpoint the real client never calls makes the suite satisfiable only by an incorrect impl. The fix is to correct BOTH impl and test mock — not to weaken assertions.

**Fix:**
1. In `remember.py`, replace the space-level resolver with the spec-mandated D6 two-step (mirror `ingest._resolve_wiki_action_tag`): `client.list_properties(space_id)` → match `key` == target property (`wiki_status` / `wiki_source_type`) → `client.list_tags(space_id, prop_id or <key>)` (keep the SF12 degraded `list_tags`-even-on-unresolved-pid read). Factor a single `_resolve_select_tag(client, space_id, property_key, tag_name) -> (id|None, degraded)` and have the two named wrappers delegate.
2. For the action tag, delete `_resolve_remember_action_tag` and call the already-imported `_resolve_wiki_action_tag(client, space_id, action_name="remember")` (resolves M1 too).
3. In `tests/wiki/test_remember.py`, change every `router.get(".../tags")` mock to the property-scoped path. Use a regex route so it matches regardless of pid, e.g. `router.get(url__regex=r".*/properties/[^/]+/tags(\?.*)?$")`. Keep the `.../properties` (list_properties) mock. **Do not change any assertion** — only the mocked endpoint path. Verify the degraded-path tests (`test_conflict_status_tag_absent_degrades`, `test_source_created_without_source_type_when_tag_absent`, `test_wikilog_action_tag_absent_degrades`) still drive the degrade branch.
4. Fix the misleading docstring on `ingest.py::_resolve_wiki_action_tag` ("remember.py resolves its own tags via a space-level endpoint" — no longer true).

---

## MAJOR

### M1 — D8 reuse violated; dead import
**File:** `wiki/remember.py:39` (import), `157-160` (`_resolve_remember_action_tag`)
`_resolve_wiki_action_tag` is imported but never called; the impl hand-rolls `_resolve_remember_action_tag` on the broken endpoint instead. Spec D8/Step 5.2 require reusing the generalized resolver. Fixed by C1 step 2 (delete the hand-rolled fn, call the imported one).

---

## MINOR

### m1 — `sources_overwrite_on_conflict` warning fires even when the PATCH is skipped
**File:** `wiki/remember.py:~483`
The warning is appended whenever `conflicts` is non-empty, before the D3 gate. On the conflict-but-PATCH-skipped path (AC-R28, re-asserted text normalizes equal) no `wiki_sources` overwrite actually occurs, yet the warning still fires. **Accepted as-is / documented:** addendum item 2 accepts either the warning or a WikiLog note as the surfacing mechanism, and over-warning on an audit signal is non-destructive and arguably correct (a re-asserted conflict on an object that carries sources still represents the provenance-overwrite risk). No change required; note the rationale in the debrief.

### m2 — `_object_deeplink` duplicated instead of imported
**File:** `wiki/remember.py:630`
Spec Step 5.3 says import `_object_deeplink` from `bootstrap`. The impl re-defines an identical copy. Replace the local def with `from .bootstrap import _object_deeplink` (or call `_bootstrap._object_deeplink`).

---

## Additional (test-guard hardening — fix this round)
The impl-worker `@pytest.mark.skip`-ped `test_bootstrap.py::TestSchemaVersionBumped::test_wiki_schema_version_is_030` (superseded by the mandated 0.3.1 bump). Rather than skip, convert it to a positive guard asserting `WIKI_SCHEMA_VERSION == "0.3.1"` (D11 makes 0.3.1 load-bearing for the AC-R11 schema-outdated abort; a positive pin is a stronger regression guard than the version-relative checks). The two version-relative edits (`_make_schema_ok_response`, upgrade-from-v0.2.0) are correct and stay.

---

## Confirmed correct (do not regress)
- **Security (all 9 items CLEAN):** anti-injection framing in `consolidate.md`; sanitize-on-write (`sanitize_property_value` on every wiki_facts/wiki_definition write, raw LLM text never reaches Anytype — AC-R27/B1); name policy via `sanitize_name`; consent fires before extract (AC-R-S1); URL credential scrubbing; all writes inside `space_ingest_lock` (AC-R-S2); empty/oversize gated before lock/extract/create; no hardcoded secrets; no broad-except masking of route mismatches.
- **Correctness:** idempotency double-gate ordering (conflict-flag → D3 skip) + `consolidated_despite_changed_flag` + conflicts_flagged-when-skipped (AC-R6/R28); conflict path (needs-review set, no wiki_last_reviewed, both facts retained) (AC-R5); supersede→WikiLog audit (addendum 1); ambiguity skip-one/write-others (AC-R29/B9); subject cap ≤8 (D12); lazy Source + source_type branch (SF10/B4); relations per-object counts + type-safe (G1/SF5); properties-only no body (AC-L1, lead-verified); consolidate() determinism+repair+degrade+model-not-pulled; `_call_ollama` delegate refactor byte-identical (regression guard green); bootstrap seeding (remember/status/source_type, union-only, key-fallback); `_write_wikilog`/`_resolve_wiki_action_tag` `action_name` default preserves ingest behavior.
- **DRY:** resolve_entity, `_write_bidirectional_relations`, `_write_wikilog`, `_domain_taxonomy`, `_maybe_reindex`, `_cmp_versions` correctly reused (no orchestration copy-paste).

## Exit gate for R2
All findings except m1 (accepted) addressed; full `pytest tests/wiki/ -q` green; the C1 fix must be proven against the **property-scoped** endpoint (tests re-mocked, not the fabricated path); 4 named regression guards still green; new positive 0.3.1 schema guard added.
