# CSO Assessment — Post-test Council R1 (Strategic Security Sign-off)

**Reviewer:** chief-security-officer (council-level, post-test-phase governance)
**Date:** 2026-04-23
**Ticket:** Aldeia-IT/aldeia-box#140 — anytype-llm-wiki (public OSS, MIT)
**Phase under review:** `test` (v0.2.0 failing-test scaffolding)
**Branch:** `test/wiki-library-module-port-llm-wiki-pattern-onto-any`
**Final commit:** `8f94d09`
**Review cycle:** R1 NEEDS CHANGES → r1-fixer (`ab25890`) → R2 APPROVED (`8f94d09`)
**Scope:** strategic security evaluation of the test artifact as a spec gate. Not a line-by-line code review; that work was completed by the per-phase test reviewer.

---

## Verdict

**SIGN OFF WITH ADVISORIES.**

The two BLOCKING defects from test R1 (my domain on B1) are genuinely fixed. R3-CSO-1 (escape-form encoding of the dash-fold codepoints) was pre-emptively applied by the test writer and verified by me at the byte level. R3-CSO-2 (pyproject.toml description) has been resolved. R3-CSO-3 (source_ref redaction) is partially covered by the existing test scaffolding even before being promoted to a formal AC.

Three new advisory-level findings surface in the test suite itself — weak-assertion patterns (OR-disjunctions, and/and instead of exact-phrase match) on ACs #8 and #9. They resemble the R1 SF-1 defect (AC #3 OR escape valve) that was correctly caught and fixed. Given Jan's directive — *"Since we're addressing the blocking issue in a spec re-run, fix the advisory findings as well!"* — these should be addressed before implementation begins. None is a BLOCKING gate for advancing past Decide, but each should land as a small test-strengthening commit under the same spirit.

---

## Summary

The test-writer and r1-fixer, working under the per-phase test reviewer, produced a scaffold that now genuinely gates credential scrubbing through a direct unit test of `scrub_credentials` rather than the tautological `wiki_bootstrap` path that R1 correctly identified. The R2 review's byte-level claim that the 10-codepoint dash-fold parametrize table is ASCII-clean is credible and I independently verified it: every non-ASCII byte in `tests/wiki/test_util.py` lives either in docstrings, prose comments, or in `\uXXXX` Python escape sequences — none of them inside a test's DATA string. The ten codepoints (U+00AD, U+2010-U+2015, U+2212, U+FE63, U+FF0D) decode correctly when Python parses the file. This is exactly the "editor round-trip stable, byte-stable, diff-visible" posture R3-CSO-1 asked for.

AC #15 (credential scrubbing) is the single most security-consequential item in v0.2.0. The R2 fix is a substantive strengthening: the TestCredentialScrubbing class at `tests/wiki/test_util.py:310` directly imports `scrub_credentials` from `anytype_llm_wiki.wiki.util` and asserts three distinct invariants (value scrubbed, query-string form scrubbed, host preserved) for both the QDRANT_URL api_key shape and the WIKI_EXTRACT_ENDPOINT userinfo shape. No path through `wiki_bootstrap` — the call path where the original tautology lived — is involved. The test will fail pre-implementation with `ModuleNotFoundError` (correct) and will fail post-implementation if scrubbing is incomplete (correct). The tautology is eliminated, not relocated.

Two test-level weaknesses carried forward from pre-fix state remain and should be addressed: AC #9's `test_403_on_create_type_returns_config_error` uses an OR assertion (`"insufficient_token_scope" OR "[CONFIG ERROR]"`), and AC #9's `test_insufficient_scope_error_mentions_settings_api` splits "Settings" and "API" into separate `in` checks rather than matching the exact "Settings → API" phrase the spec demands. Both patterns mirror the R1 SF-1 defect and can be resolved by the same fix template.

---

## AC #15 Scrubbing Integrity Verification (spot-checked)

**File:** `/Users/Shared/development/anytype-llm-wiki-worktrees/test/wiki-library-module-port-llm-wiki-pattern-onto-any/tests/wiki/test_util.py`
**Class:** `TestCredentialScrubbing` (lines 310–400)

Verified by direct file read:

| Invariant | Test method | Line | Direct call path | Assertion |
|-----------|-------------|------|------------------|-----------|
| (a) QDRANT_URL api_key value absent | `test_qdrant_url_api_key_value_scrubbed` | 330 | `scrub_credentials(url)` | `"SEKRET123" not in result` |
| (a') QDRANT_URL `?api_key=` substring absent | `test_qdrant_url_api_key_query_param_scrubbed` | 339 | `scrub_credentials(url)` | `"?api_key=" not in result` |
| (b) Userinfo password absent | `test_userinfo_password_scrubbed` | 357 | `scrub_credentials(url)` | `"api-secret" not in result` |
| (b') Userinfo `user:pass@` form absent | `test_userinfo_colon_password_at_combo_scrubbed` | 366 | `scrub_credentials(url)` | `"api-user:api-secret@" not in result` |
| (c) QDRANT host preserved | `test_qdrant_url_host_preserved` | 348 | `scrub_credentials(url)` | `"xyz.cloud.qdrant.io" in result` |
| (c') Userinfo host preserved | `test_userinfo_host_preserved` | 375 | `scrub_credentials(url)` | `"hosted.example.com" in result` |
| (d) No wiki_bootstrap call path | (class-level design) | — | No test method imports or invokes `wiki_bootstrap` | Tautology re-introduction path closed |
| Returns string type | `test_returns_string` | 394 | `scrub_credentials(url)` | `isinstance(result, str)` |

All invariants are asserted. Crucially for (d): I grep'd the entire `tests/wiki/test_util.py` for `wiki_bootstrap` — zero matches. There is no path by which an implementation that fails to scrub could accidentally pass these tests because `wiki_bootstrap` doesn't touch the test. The scrubbing contract is pinned to `scrub_credentials` as a unit, which is the right level of granularity for a library primitive.

**Host-preservation note (important):** The host-preservation tests (invariants c and c') are what prevent a naive implementation from just blanking the entire URL. Without these, an implementation that returns `"[scrubbed]"` for any credentialed URL would satisfy the "secret absent" tests but would also destroy the operator's ability to diagnose which host failed. The R2 fix correctly includes both halves of the contract.

**Non-tautological proof:** `scrub_credentials` is a pure function of its input URL. There is no environment state, no bootstrap path, no conditional branch on QDRANT_URL-being-set-but-not-read — all the pathological shapes that made the R1 test tautological. An implementation that simply returns its input unchanged will fail 6 of the 10 test methods. An implementation that returns `""` or `"[scrubbed]"` will fail the 2 host-preservation tests. The assertion surface genuinely spans the implementation space.

**Verdict on AC #15:** PASS. The test is now a genuine spec gate. The R1 BLOCKING-B1 (my domain) is resolved in substance, not just in form.

**Caveat for v0.3.0:** The spec AC #15 text reads "A forced `[API ERROR]` triggered by a Qdrant failure…returns an error string containing neither…" — an end-to-end assertion semantic. The v0.2.0 scaffold covers the unit-level primitive because `wiki_bootstrap` in v0.2.0 doesn't call Qdrant. The end-to-end assertion belongs in the v0.3.0 test phase when `wiki_ingest` actually exercises the Qdrant call-path that can produce `[API ERROR]`. I advise the next test-phase lead to add (at v0.3.0 test time) an integration-style test that forces a Qdrant 500, invokes `wiki_ingest`, and asserts the resulting error string passed through the same scrubbing primitive. Note this as a carry-forward for the v0.3.0 test lead.

---

## R3-CSO-1 Escape-Form Verification (spot-checked)

**File:** `/Users/Shared/development/anytype-llm-wiki-worktrees/test/wiki-library-module-port-llm-wiki-pattern-onto-any/tests/wiki/test_util.py`
**Parametrize table:** lines 38–67 (14 rows total; rows 2–11 carry the non-ASCII codepoints)

Method: byte-level scan of each line via `open(..., 'rb')`; also a second scan via `open(..., 'r')` to separate data portions from comment portions.

**Finding:** All 10 non-ASCII dash codepoints are in `\uXXXX` escape form. The only non-ASCII bytes in the parametrize table (6 lines — 39, 41, 53, 61, 63, 65) are em-dashes (U+2014, `0xe2 0x80 0x94`) appearing in **prose comments** (e.g. "— U+00AD — invisible conditional hyphen"), never in a test's DATA string literal.

Per-row byte inspection of rows 2–11 (DATA strings):

| Row | Line | Data string | Byte breakdown | Codepoint after Python parsing |
|-----|------|-------------|----------------|-------------------------------|
| 2   | 42   | `BGE­M3` | `B G E \ u 0 0 a d M 3` | U+00AD (SOFT HYPHEN) ✓ |
| 3   | 44   | `BGE‐M3` | `B G E \ u 2 0 1 0 M 3` | U+2010 (HYPHEN) ✓ |
| 4   | 46   | `BGE‑M3` | `B G E \ u 2 0 1 1 M 3` | U+2011 (NON-BREAKING HYPHEN) ✓ |
| 5   | 48   | `BGE‒M3` | `B G E \ u 2 0 1 2 M 3` | U+2012 (FIGURE DASH) ✓ |
| 6   | 50   | `BGE–M3` | `B G E \ u 2 0 1 3 M 3` | U+2013 (EN DASH) ✓ |
| 7   | 52   | `BGE—M3` | `B G E \ u 2 0 1 4 M 3` | U+2014 (EM DASH) ✓ |
| 8   | 54   | `BGE―M3` | `B G E \ u 2 0 1 5 M 3` | U+2015 (HORIZONTAL BAR) ✓ |
| 9   | 56   | `BGE−M3` | `B G E \ u 2 2 1 2 M 3` | U+2212 (MINUS SIGN) ✓ |
| 10  | 58   | `BGE﹣M3` | `B G E \ u f e 6 3 M 3` | U+FE63 (SMALL HYPHEN-MINUS) ✓ |
| 11  | 60   | `BGE－M3` | `B G E \ u f f 0 d M 3` | U+FF0D (FULLWIDTH HYPHEN-MINUS) ✓ |

Every byte in the DATA strings is ≤ 0x7F. Python's source decoder expands the `\uXXXX` escape to the correct codepoint at parse time; the runtime test sees the intended invisible/bidi-prone character, but the source file itself is round-trip-stable across editors, diff tools, and chat windows.

**Verdict on R3-CSO-1:** PASS. The test writer pre-emptively applied my v0.3.0 advisory during v0.2.0 test scaffolding. This is exactly the right posture for OSS-facing code — a future contributor who opens this file in any editor will see ASCII-only diffs for any future edit, and a normalizing editor cannot silently shrink coverage.

The comment em-dashes (U+2014) in lines 39, 41, 53, 61, 63, 65 are acceptable: they're in prose-only positions that do not affect the regex or the test parametrize behavior; they're visible as em-dashes in any text editor (not invisible/bidi); and they cannot be silently normalized in a way that changes test semantics. If the project wants absolute ASCII-only files, these can be mechanically replaced by `--` in a follow-up — but it's not a security concern.

---

## Other Security-Relevant Test Checks

### AC #9 `insufficient_token_scope` — the "Settings → API" phrase

**File:** `tests/wiki/test_bootstrap.py:588–632`

Two tests gate AC #9. Both have weak assertions:

1. `test_403_on_create_type_returns_config_error` (line 609): `assert "insufficient_token_scope" in result_str or "[CONFIG ERROR]" in result_str`. An implementation that returns `[CONFIG ERROR] some_other_reason` (without the `insufficient_token_scope` token) passes this test. The spec (line 739) is explicit: the error string is `[CONFIG ERROR] insufficient_token_scope: the configured ANYTYPE_API_KEY cannot create Types in this space. Regenerate with write scope via Anytype Settings → API.` — both tokens must appear. This OR-disjunction is the same defect class as R1 SF-1 (AC #3 OR escape valve).

2. `test_insufficient_scope_error_mentions_settings_api` (line 630): `assert "Settings" in result_str and "API" in result_str`. An implementation that says "See Settings in the app, or regenerate your API key separately" would pass without ever producing the load-bearing "Settings → API" phrase. The arrow glyph `→` (U+2192) is the navigation breadcrumb operators search for in troubleshooting; making the test match it (or match the explicit three-token string "Settings → API") closes the gap. The R2 review did not flag this. I am flagging it now.

**Risk if unfixed:** Low-medium at the code level, but this is a documentation/UX defense-in-depth item. An operator locked out by a write-scope misconfiguration searches their error output for a breadcrumb to action. A test that doesn't enforce the exact breadcrumb lets an implementer accidentally ship ambiguous prose (e.g. "see Settings > API" or "in the Anytype API menu") that a locked-out operator wouldn't match against the spec's documentation. This is the class of defect that surfaces as a support-bug after release.

### AC #8 README GDPR controller statement

**File:** `tests/wiki/test_bootstrap.py:577–585`

`test_readme_contains_gdpr_controller_statement` uses OR: `"GDPR" in content or "controller" in content`. A README containing only the word "controller" (e.g. a JS MVC reference) would pass. The spec AC #8 requires the verbatim privacy notice, which includes an explicit GDPR Art. 4(7) controller statement. SHOULD-FIX: change to `"GDPR" in content and "controller" in content` (both must appear), or test for a more specific phrase ("controller within the meaning of GDPR" or similar from the spec). This is a minor advisory-level issue in isolation but the pattern (weak OR instead of exact verbatim match) is what makes the privacy-notice gate soft.

### psutil dev-dep placement

`pyproject.toml` lines 18–25: `psutil>=5.9` is listed under `[project.optional-dependencies].dev`. The spec (lines 1165, 1633) uses `psutil.virtual_memory()` in the **runtime** doctor command (check 6b RAM WARN and the 8 GB unsupported WARN). Therefore psutil must be a runtime dependency, not a dev-only dependency. If the v0.2.0 implementation adds psutil only to dev deps, the doctor command will fail with `ModuleNotFoundError` when a consumer installs via `pip install anytype-llm-wiki` (no `[dev]` extras).

**Security classification:** not a security defect (it's a packaging defect). But it has a second-order security implication: doctor check 6b is a **safety feature** that prevents operators from running 16 GB systems into swap (which could induce OOM-kill mid-ingest and leave partial-state writes in Anytype). If doctor fails to start at all because psutil isn't installed, operators lose that safety signal silently. Cross-thread: CTO/Infra — psutil needs to move to `[project].dependencies`, not `[project.optional-dependencies].dev`. The test writer should keep it in dev-deps too (for the mock test at `test_doctor.py:298`), but it must primarily be a runtime dep.

**Supply-chain surface for psutil:** psutil is a mature, widely-used library (Python 2015+, ~180M downloads/month on PyPI, maintained by Giampaolo Rodolà, no open critical CVEs per my knowledge cutoff). As a runtime dep it's acceptable; as a dev dep it's fine. No supply-chain concern from the version pin `>=5.9`; the two-layer supply-chain posture (README lines 674-680) documents that uv.lock pins the exact tree.

### AC #11 isolation fix — genuinely resolves the skip-vs-fail question

**File:** `tests/wiki/test_server_registration.py`

Verified: zero `autouse` fixture decorators in the file. The class inspects the MCP tool registry at import time via multiple compatibility paths for FastMCP versions. The test imports from `anytype_llm_wiki.server` and will fail with `ModuleNotFoundError: No module named 'anytype_llm_wiki.wiki'` pre-implementation (since `server.py` has to import `wiki_bootstrap` from the wiki module to register it). CI will see FAIL, not SKIP. R1 BLOCKING-B2 is resolved at the structural level.

**Observation (not a finding):** The version-compatibility sniffing inside `test_wiki_bootstrap_is_registered_mcp_tool` (lines 31–53) is graceful but could silently return `tool_names = set()` if FastMCP is upgraded to a version that exposes a new registry shape. If that happens and `wiki_bootstrap` is then asserted against an empty set, the test would correctly fail (good), so the compatibility sniffing doesn't weaken the gate. Noted but not actionable.

### R3-CSO-3 source_ref redaction — partial pre-emptive coverage

The R3-CSO-3 advisory asked for an AC explicitly asserting the source_ref redaction property. The AC was not added to v0.2.0 (correct scope — it's a v0.3.0 lock-payload AC). However, the test writer pre-emptively added `TestSpaceIngestLockSourceRefRedaction` at `tests/wiki/test_util.py:196–227` with two tests: `test_source_ref_strips_query_string` and `test_source_ref_strips_userinfo`. This covers the URL-redaction half of R3-CSO-3. The file-path-redaction half (R3-CSO-3 concern #1 — basename-only for file paths) is not covered. Acceptable: file-based ingest is a v0.3.0 feature, so the test for that side belongs in v0.3.0's test phase. Carry-forward noted.

### Tests that actually fail pre-implementation (pre-implementation failure discipline)

The phase summary claims 193 failed, 6 passed, 6 skipped, 3 xfail. I did not independently re-run the suite (the lead reported sandbox couldn't invoke uv run pytest). Structural inspection: every test I reviewed imports from `anytype_llm_wiki.wiki.*` or `anytype_llm_wiki.server`, which will not exist pre-implementation → ModuleNotFoundError as expected. No test class has a try/except around the import that would mask pre-implementation failures. The xfail-gated tests (AC #13/#14 v0.3.0 activation) use `strict=False` correctly.

---

## Findings

### BLOCKING

**None.** The two R1 BLOCKING defects (B1 scrubbing tautology — my domain; B2 AC #11 skip-vs-fail) are genuinely resolved in `ab25890`. The R3-CSO-1 escape-form advisory was pre-emptively applied and verified at the byte level. No new BLOCKING defects surface from my review.

### ADVISORY

**R1-CSO-A1 — AC #9 `insufficient_token_scope` test uses OR-disjunction (same pattern as R1 SF-1).**

File: `tests/wiki/test_bootstrap.py:609`
Current: `assert "insufficient_token_scope" in result_str or "[CONFIG ERROR]" in result_str`
Spec (line 739): error must contain both `[CONFIG ERROR]` and `insufficient_token_scope`.

Risk: An implementation returning `[CONFIG ERROR] wrong_reason` or returning `insufficient_token_scope` without the `[CONFIG ERROR]` severity prefix would pass. The severity prefix is load-bearing because the spec's error-shape grammar (seven `[SEVERITY]` labels) drives operator troubleshooting behavior.

Recommended action: change to `and` (both substrings required). One-line test edit. Given Jan's "fix the advisory findings as well" directive, this should be addressed before implementation begins.

**R1-CSO-A2 — AC #9 "Settings → API" test splits the breadcrumb into separate `in` checks.**

File: `tests/wiki/test_bootstrap.py:630`
Current: `assert "Settings" in result_str and "API" in result_str`
Spec (line 739): the error's final sentence is "Regenerate with write scope via Anytype Settings → API." — the three-token phrase "Settings → API" is the spec's documented operator breadcrumb.

Risk: An implementation emitting "See Settings in the app, regenerate API key" (no arrow glyph, no three-token sequence) passes the current test but fails the spec's breadcrumb contract. Operators searching error output for "Settings → API" would not match.

Recommended action: change to `assert "Settings → API" in result_str` (or `"Settings → API"` in escape form for byte-stability, consistent with the R3-CSO-1 pattern already applied to `test_util.py`). Given Jan's directive, this should be addressed before implementation begins.

**R1-CSO-A3 — AC #8 GDPR controller test uses OR-disjunction.**

File: `tests/wiki/test_bootstrap.py:583`
Current: `assert "GDPR" in content or "controller" in content`
Spec AC #8: README must contain the *verbatim privacy notice from this spec*, which includes the GDPR controller statement (not "either GDPR or controller").

Risk: A README that uses only the word "controller" (e.g. in unrelated context) passes. The R1 review did not flag this; I am flagging it now because the pattern matches R1 SF-1.

Recommended action: change to `and` (both must appear), or assert a more specific phrase from the spec's privacy-notice block. One-line test edit.

**R1-CSO-A4 — psutil packaging placement. (Cross-thread: CTO / Infrastructure.)**

File: `pyproject.toml:9-25`
Current: `psutil>=5.9` only in `[project.optional-dependencies].dev`.
Spec: `psutil.virtual_memory()` is called at runtime by the doctor command (spec lines 1165, 1633).

Risk: If v0.2.0 ships with psutil only in dev deps, consumers who install via `pip install anytype-llm-wiki` (no `[dev]`) will see `ModuleNotFoundError` when running `anytype-llm-wiki doctor`. Security-adjacent because doctor check 6b is a safety signal preventing 16 GB + 7B-model swap-thrash → OOM-kill → partial-state write to Anytype.

Recommended action: add `psutil>=5.9` to `[project].dependencies` as a runtime dependency. Keep it in dev deps too for consistency. Cross-thread to CTO (packaging correctness) and Infrastructure (doctor safety-signal continuity). Two-line pyproject.toml edit.

**R1-CSO-A5 — Carry-forward: AC #15 end-to-end assertion at v0.3.0 test phase.**

The v0.2.0 test suite correctly gates the unit-level `scrub_credentials` contract. The spec's AC #15 text ("A forced `[API ERROR]` triggered by a Qdrant failure…") implies an end-to-end integration assertion that cannot be satisfied at v0.2.0 because `wiki_bootstrap` doesn't call Qdrant. When v0.3.0 test writing begins (`wiki_ingest` exists, Qdrant/extraction call-paths exist), an integration-tier test must be added that:
1. Sets `QDRANT_URL=https://host/path?api_key=SEKRET`.
2. Forces a Qdrant 500 via respx or mock.
3. Invokes `wiki_ingest(...)`.
4. Asserts the resulting `[API ERROR]` string passes through `scrub_credentials` before surfacing (SEKRET absent, host preserved).
5. Same for `WIKI_EXTRACT_ENDPOINT` userinfo failure from the extraction call-path.

This is a carry-forward note for the v0.3.0 test-phase lead, not an action item for the v0.2.0 lead. Record in test-phase handover notes.

**R1-CSO-A6 — Carry-forward: file-path source_ref redaction (R3-CSO-3 completion at v0.3.0).**

The v0.2.0 test scaffold covers URL-redaction of `source_ref`. The R3-CSO-3 concern about file-path sources (e.g. `/Users/jane/Documents/internal-report.md`) leaking an operator's home-directory layout into the lock payload is not covered. v0.3.0 accepts file-path ingest as a first-class source; at that point the lock-payload AC should require `source_ref` to contain only the basename (or a hash) when the source is a file path, not the full absolute path. Carry-forward note for the v0.3.0 spec and test leads.

---

## Cross-Thread Messages

- **CTO / Infrastructure:** R1-CSO-A4 (psutil runtime-vs-dev placement). Two-line pyproject.toml fix. Packaging correctness + doctor safety-signal continuity. Please confirm placement in the impl-phase opening checklist.
- **QA:** R1-CSO-A1/A2/A3 (weak-assertion patterns on AC #8 and AC #9). These are the same defect class as the R1 SF-1 catch on AC #3. Adding "no OR-disjunction in assertions against spec-verbatim strings" as a standing test-writer convention would prevent the pattern from recurring in v0.3.0+ test phases.
- **CPO / Legal:** No new positioning or legal concerns from the test phase. R3-CSO-2 (pyproject.toml description) is resolved — I verified `pyproject.toml:4` now reads the reconciled narrower claim.
- **Council Chair:** Six advisories total, three actionable before implementation (A1/A2/A3/A4) and two carry-forward to v0.3.0 (A5/A6). None blocking.

---

## Recommendation

**SIGN OFF ADVANCEMENT TO `decide` with the ADVISORY findings attached.**

The test phase produced a genuinely gating scaffold for v0.2.0. The R1 BLOCKING-B1 defect (my domain — the tautological QDRANT_URL scrubbing test) is resolved in substance; `TestCredentialScrubbing` is a proper unit-level gate with six independent assertions spanning value, form, and host-preservation invariants across both supported credential shapes. The R3-CSO-1 escape-form advisory I filed at spec time was pre-emptively applied to `tests/wiki/test_util.py` before I had occasion to re-raise it; byte-level verification confirms all 10 dash codepoints are `\uXXXX`-escaped and the file is round-trip stable.

The four pre-implementation advisories (R1-CSO-A1 through A4) are small, fast fixes that align with Jan's "fix the advisory findings as well" directive. I recommend the Decide gate bundle them into a one-commit test-strengthening PR before the impl phase opens, rather than deferring to the impl phase itself. This keeps the "test phase delivers a correct gate" invariant intact.

The two carry-forward items (A5, A6) are scope-correctly deferred to v0.3.0.

**I concur with the council's expected APPROVED verdict and sign off from the security-governance perspective.**

---

## Files Referenced

- `/Users/Shared/development/anytype-llm-wiki-worktrees/test/wiki-library-module-port-llm-wiki-pattern-onto-any/tests/wiki/test_util.py` (AC #15 TestCredentialScrubbing at lines 310–400; dash-fold parametrize at lines 38–67; source_ref redaction at lines 196–227)
- `/Users/Shared/development/anytype-llm-wiki-worktrees/test/wiki-library-module-port-llm-wiki-pattern-onto-any/tests/wiki/test_bootstrap.py` (AC #9 at 588–632; AC #8 GDPR at 577–585)
- `/Users/Shared/development/anytype-llm-wiki-worktrees/test/wiki-library-module-port-llm-wiki-pattern-onto-any/tests/wiki/test_server_registration.py` (AC #11 isolation fix)
- `/Users/Shared/development/anytype-llm-wiki-worktrees/test/wiki-library-module-port-llm-wiki-pattern-onto-any/pyproject.toml` (R1-CSO-A4 psutil dep placement; R3-CSO-2 resolved description at line 4)
- `/Users/Shared/development/anytype-llm-wiki-worktrees/test/wiki-library-module-port-llm-wiki-pattern-onto-any/.aldeia/140-wiki-library-module-port-llm-wiki-pattern-onto-any/test-review-r1.md` (R1 review — BLOCKING-B1, SHOULD-FIX findings)
- `/Users/Shared/development/anytype-llm-wiki-worktrees/test/wiki-library-module-port-llm-wiki-pattern-onto-any/.aldeia/140-wiki-library-module-port-llm-wiki-pattern-onto-any/test-review-r2.md` (R2 APPROVED; claimed byte-level scan verified)
- `/Users/Shared/development/anytype-llm-wiki-worktrees/test/wiki-library-module-port-llm-wiki-pattern-onto-any/.aldeia/140-wiki-library-module-port-llm-wiki-pattern-onto-any/council-spec-r3-cso.md` (my R3 advisories; R3-CSO-1 pre-emptively applied, R3-CSO-2 resolved, R3-CSO-3 partial pre-emptive coverage)
- `/Users/Shared/development/anytype-llm-wiki-worktrees/test/wiki-library-module-port-llm-wiki-pattern-onto-any/.aldeia/140-wiki-library-module-port-llm-wiki-pattern-onto-any/spec.md` (AC #15 at 745; AC #9 at 739; privacy-notice AC #8 at 738; source_ref at 1579; psutil runtime usage at 1165, 1633)
- `/Users/Shared/development/tasks/logs/140-wiki-library-module-port-llm-wiki-pattern-onto-any/phase-summary-test.md` (phase summary and quality assessment)
