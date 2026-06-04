# Council Test Review R1 — CTO (Chief Technology Officer)

**Ticket:** #289 anytype-llm-wiki v0.3.1 `wiki_remember`
**Phase under review:** test (TDD failing-suite, commits `991af3e` + `2357b4a`)
**Verdict:** **VETO — 1 BLOCKING** (mock-shape defect that a correct impl cannot pass)
**Date:** 2026-06-04

This is a governance audit of the test phase, not a re-review. I spot-checked claims
against the actual codebase, ran probes, and audited reviewer diligence. The phase
reviewers did real codebase verification on what they checked, and most of the suite is
genuinely high quality. But there is one systematic technical defect both in-phase
reviewers missed because neither stood up the impl to see whether a *correct* implementation
would pass.

---

## What I verified (evidence)

**Spec line-citations are accurate (spot-check, 5/5 correct):**
- `_DETERMINISTIC_OPTS` at `extraction.py:41`; `_call_ollama` (generate-then-chat) at `:86`;
  `_is_model_not_pulled` at `:79`. ✓
- `_resolve_wiki_action_tag` at `ingest.py:212`; `_write_wikilog` name `f"ingest {subject}"`
  at `ingest.py:256`. ✓
- `resolve_entity` at `ingest.py:163`, calls `client.search(space_id, query=...)` at `:179`,
  swallows `(httpx.HTTPError, KeyError, ValueError, TypeError)` → `action="create"`. ✓
- `_check_ollama_models_pulled` registers doctor check name `"ollama_models_pulled"` at
  `doctor.py:206` — exactly the pre-existing check the R1 reviewer flagged as omitted from the
  whitelist. The R1 BLOCKING was a real, codebase-verified finding. ✓

**Dependency / stack alignment:** respx + monkeypatch, httpx, pytest — all the project's
established test stack (`pyproject.toml`). No alien tooling introduced. ✓

**The refactor regression guard (addendum item 8) is genuinely load-bearing.**
`test_extract_request_payload_unchanged_after_refactor` (`test_extraction.py:1056`) drives the
real `extract()` and pins **all four** dimensions item 8 demanded: `model == config.extract_model()`,
`options == _DETERMINISTIC_OPTS` on **both** generate and chat payloads, the generate-then-chat
fallback ordering (generate first; chat triggered by malformed JSON; `prompt` vs `messages` key
discrimination), and a sibling `test_extract_model_not_pulled_detection_unchanged` (`:1145`) pins
the 404 detection. Verified PASS pre-impl. This will catch a `_call_ollama_prompt` DRY refactor
that silently drifts the shipped `wiki_ingest` extraction wire behavior. **No concern here.**

**The two R1 fixes are real and correct, not cosmetic.**
- B-R1 fix (`test_bootstrap.py:1905`): the whitelist is gone, replaced by a before/after
  FAIL-set diff (`after_fail_names - before_fail_names == set()`). This is robust to
  env-dependent pre-existing failures and remains substantive (a new failing #289 doctor check
  would appear in `after` only). Verified PASS pre-impl. This is the *right* robustness call —
  it does not weaken the guard; it removes a stale hand-list that produced a false positive.
- S-R1 fix: `test_ambiguous_subject_skips_and_warns` search mock is now subject-aware with
  separate `ambig_update_calls` / `clear_update_calls` capture and a `len(clear_update_calls)==1`
  assertion proving the co-resident unambiguous subject still writes. Correct.

**AC-R27 byte-for-byte sanitize (addendum item 4) is honest** (`test_remember.py:1034`): feeds
U+200C, asserts the captured PATCH `wiki_facts` text `== sanitize_property_value(raw)`
byte-for-byte against the real `PATCH /v1/spaces/{space}/objects/entity-001` route. Strong.

**Chair's verified counts reproduced:** 5 designated regression/refactor guards
(`doctor_green_after_v031`, `write_wikilog_default_name_is_ingest`,
`resolve_action_tag_default_is_ingest`, `request_payload_unchanged_after_refactor`,
`model_not_pulled_detection_unchanged`) PASS pre-impl. ✓

---

## BLOCKING

### B-CTO-1 — `test_remember.py` mocks `search` as **GET**, but the shipped client POSTs. A correct impl cannot pass.

**What I checked.**
- `WikiClient.search` (`wiki_client.py:113`) issues `c.post(f"/v1/spaces/{space_id}/search", json=payload)` — a **POST**.
- Every entity-resolution route in `test_remember.py` is registered as a **GET**:
  `router.get("/v1/spaces/space-remember-test-001/search")` — **49 occurrences, 0 POST
  registrations, 0 catch-all `route()`** (`grep -c`).
- `resolve_entity` (imported from `ingest.py`, **not mocked** anywhere in `test_remember.py`)
  runs for real and calls `client.search`.

**Empirical proof (not reasoning).** I probed the real client against a GET-only `/search`
mock with `assert_all_called=False`:
```
search raised: respx.models.AllMockedAssertionError -> "...POST .../search ... not mocked!"
is httpx.HTTPError: False
is AssertionError:  True
```
respx 0.23.1 (`uv.lock`) defaults to `assert_all_mocked=True`, so an unmatched POST raises
`AllMockedAssertionError`, which **is** an `AssertionError` and is **NOT** an `httpx.HTTPError`.
`resolve_entity`'s `except (httpx.HTTPError, KeyError, ValueError, TypeError)` therefore does
**not** catch it.

Then I dropped a minimal **spec-faithful** `remember.py` stub (entry-validation-free: lock →
`extract` → `resolve_entity` → write) and ran `test_idempotency_gate_llm_changed_false_skips_patch`:
```
respx.models.AllMockedAssertionError: RESPX: <Request('POST',
'http://127.0.0.1:31012/v1/spaces/space-remember-test-001/search')> not mocked!
```
(Stub deleted immediately; `git status` clean — confirmed.)

**Impact.**
- The "74 failures = all impl-absence" state is true **only because the module is missing**.
  The search GET/POST mismatch is **masked** by the `ImportError`; it is latent, not absent.
- Once a *correct* impl lands, the large class of `test_remember.py` tests that depend on
  `resolve_entity` returning `action="update"` (idempotency double-gate, conflict-flagging,
  ambiguity/B9, source-link, sanitize-on-write, twice-converges, etc. — anything fed
  `_single_entity_response` expecting it to be *seen* via search) will fail with
  `AllMockedAssertionError`, **or**, under a defensively-wrapped impl, `resolve_entity` returns
  empty → `action="create"` and assertions like `assert "consolidated" in actions` fail. Either
  way the test cannot pass against a correct implementation.
- This inverts the phase summary's premise ("the impl must match these exactly or tests will
  fail — which is the intent"): here a **correct** impl fails for a mock-fidelity reason
  unrelated to behavior. The contract is not faithfully executable.
- Blast radius is confined to `test_remember.py` (bootstrap/extraction tests do not mock
  `search`). Write routes are correct: `create_object`→POST `/objects`, `update_object`→PATCH
  `/objects/{id}`, `list_properties`/`list_tags`→GET — all match the client. The defect is the
  single `search` method.

**Recommended action (test-phase fix, before advancing).** Change all 49 `router.get(.../search)`
registrations in `test_remember.py` to `router.post(.../search)` (matching `WikiClient.search`
and the existing `test_ingest.py` convention, which already uses `respx.post()` for search at
`test_ingest.py:848`). After the change, re-confirm: (a) every `test_remember.py` test still
FAILS pre-impl on `ImportError` (impl-absence), and (b) the same spec-faithful stub probe no
longer raises `AllMockedAssertionError` on `/search`. This is a mechanical, low-risk edit; it
does not touch assertions.

---

## ADVISORY

### A-CTO-1 — Reviewer diligence gap (process note, not a separate defect).
Both in-phase reviews show genuine codebase verification (reproduced doctor `AssertionError`
naming `ollama_models_pulled`; pinned file:line for fixes; pytest counts). That is good. But
**neither reviewer stood up even a stub impl**, so a method-level wire mismatch (GET vs POST on
the project's most-used read route) passed through R1 and R2 unflagged. For a TDD suite whose
entire value is "fails for the right reason now, passes for a correct impl later," verifying only
the *fails-now* half is insufficient. Recommend the impl phase (and future test reviews on
client-driven suites) include a quick spec-faithful smoke against the route mocks. No
documentation alternative — this should be fixed, not waived.

### A-CTO-2 — Contract is appropriately behavioral, not over-constrained (no action).
I checked for over-constraint (eval question 4). The suite asserts at the public boundary:
return-dict shape (`SF2` `_error_remember_result`), per-object action enum, `update_object`
payload contents, `conflicts_flagged` counting unit (`SF3`), spy-counts on `consolidate`/lock.
It mocks `extract`/`consolidate`/`space_ingest_lock` (legitimate seams) but exercises the real
`resolve_entity`, `_write_wikilog` defaults, sanitize, and the entry-gate ordering. It does not
pin arbitrary internal helper shapes. Aside from B-CTO-1, the impl has a clean behavioral target.
N-R1 (the 5→6 action-tag count update in two #284 tests) is correctly deferred to impl and is the
right call.

### A-CTO-3 — Flag to Infra Lead.
The search GET/POST mismatch has no production/operational implication (it's test-only). Nothing
for infra here. The operationally-relevant items (shared per-space lock back-pressure, reindex
cost, monotonic WikiLog growth) are correctly addendum item 9 / impl-docs scope, not test-phase.

---

## Sign-off

**VETO.** One BLOCKING defect (B-CTO-1): `test_remember.py` mocks the entity-resolution
`search` route as GET while the shipped `WikiClient.search` POSTs — proven empirically to raise
`AllMockedAssertionError` (an `AssertionError`, uncaught by `resolve_entity`) the moment a correct
impl runs. ~49 registrations affected; the suite cannot be satisfied by a correct implementation
as written. The fix is mechanical (GET→POST, mirroring the existing `test_ingest.py` convention)
and must be applied and re-verified in the test phase before advancing to impl. Everything else —
refactor regression guard (item 8), the B-R1 before/after doctor diff, the byte-for-byte sanitize
assertion, mock fidelity on all *other* routes, AC traceability, and behavioral (non-over-
constrained) contract shape — is technically sound and I would sign off on it. Re-dispatch the
one mock fix, then this is advanceable.
