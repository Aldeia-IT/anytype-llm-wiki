# Council — Post-Impl Review (R1) — QA Director

**Ticket:** Aldeia-IT/aldeia-box#140 — Wiki Library Module (v0.2.0 tranche)
**Branch:** `aldeia/wiki-library-module-port-llm-wiki-pattern-onto-any`
**Phase reviewed:** impl (final delivery gate — merge to `main`)
**Reviewer:** QA Director
**Date:** 2026-05-22
**HEAD:** `02b6470`

---

## Verdict: SIGN OFF WITH ADVISORIES

**Recommended target: `done`** (open PR → "Rebase and merge").

Merging to `main` is sound. Every v0.2.0 acceptance criterion that is *verifiable in CI* is gated by a substantive, spec-anchored test, and the suite is green (independently re-run: **210 passed, 6 skipped, 3 xfailed** in `tests/wiki/ tests/test_anytype_client.py`). All advisories below are **tag-gating, not merge-gating** — none blocks the merge that unblocks content collection (Deliverable 1). The `git tag v0.2.0` step remains correctly gated on the maintainer-local pre-release checklist.

---

## Summary

This is a clean delivery against a test-first contract that survived a R1→R2 test-review cycle, a post-test council, and a post-impl technical review (1 MAJOR + 3 SHOULD-FIX, all resolved). I independently:

- Re-ran the in-scope suite (green, matching the chair's confirmation).
- Re-ran the FULL `tests/` suite (6 failed + 7 errored, all confined to v0.1.0 files) and confirmed those files are **byte-identical to base** — the failures are environmental (empty `ANYTYPE_API_KEY` → `httpx.LocalProtocolError`; Qdrant 401, no live service), not a refactor regression.
- Traced the headline ACs (#5, #6, #9, #10, #12, #13, #15) to their tests at file:line.
- Inspected the two test-edits-beyond-the-addendum (respx.patterns.M ×54; mkdir ×2) at the commit level and confirmed they are assertion-preserving.

The central QA tension — "pytest green ≠ shippable" (addendum item #9) — is correctly honored by the impl lead's phase summary, which enumerates the per-item done/deferred/N-A state of the pre-release checklist rather than resting on the green bar.

---

## Spot-checks performed (AC → test, file:line)

| AC | What it requires | Test traced | Verdict |
|----|------------------|-------------|---------|
| #5 | union-only re-bootstrap: `["a","b"]` then `["c"]` → `["a","b","c"]` via a *second bootstrap call* | `test_bootstrap.py:464` `test_rebootstrap_with_new_tags_is_union_only` — asserts `a`,`b` in `tags_skipped`, `c` in `tags_created` via a real second `wiki_bootstrap` call (not state injection) | Substantive, spec-faithful |
| #6 | p95 < 30s (maintainer-measured); CI sanity bound = 5× target | `test_bootstrap.py:515` `test_bootstrap_completes_within_timing_budget` — `@pytest.mark.timeout(150)` + `assert elapsed < 150` (mocked). 150s = 5×30s, matches spec line 736 | CI-sanity only, by design |
| #9 | 403 → `[CONFIG ERROR]` AND `insufficient_token_scope` AND "Settings → API" | `test_bootstrap.py:592` conjunction (`and`) + `:613` exact `"Settings → API"` breadcrumb — addendum items #2/#3 landed | Strengthened per addendum |
| #10 | doctor exit 0 clean / 1 on FAIL | `test_doctor.py:179` (exit 1, key missing) + `:191` (exit 1, unreachable) STRICT; `:149` (exit 0) is **weak** (`in (0,2)`) | exit-1 strict; exit-0 weak — see ADVISORY-1 |
| #12 | refactor preserves class/wrapper/indexer import surface | `test_anytype_client.py:125` class path, `:198` wrapper path, `:253` `TestImportRegressionIndexer` reproducing `indexer.py:11` verbatim | Adequate — merge-safe |
| #13 | bootstrap on outdated schema proceeds with upgrade (not `[CONFIG ERROR]`) | `test_bootstrap.py:618` `test_bootstrap_on_outdated_schema_returns_ok` — asserts `status=="ok"` + `schema_upgrade` section | Substantive |
| #15 | scrub `?api_key=SEKRET` and `user:pass@` from error strings | `test_util.py:315` `TestCredentialScrubbing` — 8 direct `scrub_credentials` assertions, no bootstrap tautology | Substantive (unit-level; e2e correctly → v0.3.0) |
| #8 | verbatim privacy notice | `test_bootstrap.py:560` fixture-gated `assert FIXTURE in readme_text`; fixture present at `tests/wiki/fixtures/readme_privacy_notice_verbatim.md` (2868 bytes) | Strengthened per addendum #5 |

**Test-edit legitimacy (verified at commit level):**
- `respx.patterns.M` → no-arg ×54: commit `df07bac`, landed BEFORE src work (`bf9ce2e`). Diff is purely route-registration calls; **zero** `.mock()`, `side_effect`, return-value, or `assert` lines touched. `respx.patterns.M` raised `TypeError` at route-registration in respx 0.23.1; the no-arg form is the idiomatic match-any. Assertion-preserving runnability fix.
- `mkdir(exist_ok=True)` ×2: autouse `set_env` fixture pre-creates the dir → `FileExistsError` in test setup before `run_doctor()` ran. Setup-runnability fix; assertions/exit-code expectations unchanged.

**Regression-risk (verified):** `git diff 8898d56 HEAD -- tests/test_indexer.py tests/test_server.py src/anytype_llm_wiki/indexer.py` is **empty**. The refactor (`anytype_client.py` +90/-28, `server.py` +29) preserves the three module-level wrappers (`list_spaces`/`list_objects`/`get_object`) with intact signatures; `indexer.py:11`'s import resolves; AC #12c green. The full-suite failures are byte-identical-base files failing on missing live services — **not** a regression.

---

## Findings

### BLOCKING

_None._

### ADVISORY

**ADVISORY-1 — AC #10 exit-0 test is tautologically weak (tag-gating).**
`test_doctor.py:174` asserts `result.get("exit_code") == 0 or result.get("exit_code") in (0, 2)`, which collapses to `exit_code in (0,2)`. The docstring says "must return exit_code=0," but the assertion accepts 2 (WARN). This does **not** structurally enforce AC #10's "exits 0 on a fresh install." This is exactly prior council CPO observation #15, which was explicitly recorded as observation-only and **deliberately NOT carried into the addendum** — i.e. it was knowingly accepted. The strict-0 contract is verified at tag time via the live `doctor` green (pre-release checklist, spec line 764). **Impact:** a future regression that flips a clean-env check to WARN would not be caught in CI. **Recommended action:** tighten to strict `== 0` when the v0.3.0 test phase touches `test_doctor.py` (cheap; aligns with the addendum's "no escape-valve disjunctions" convention). **Merge-gating: NO. Tag-gating: the live doctor green covers the real contract.**

**ADVISORY-2 — `EXPECTED_CHECK_NAMES` count vs docstring (cosmetic).**
`test_doctor.py:105` lists **12** check names (1–10 + 4b + 6b, matching spec 1158–1169, Infra-verified); the class docstring at `:122` says "All 11 checks." Cosmetic doc/data mismatch only — the parametrized test correctly iterates all 12. **Recommended action:** correct the docstring to "12" opportunistically. **Merge-gating: NO.**

**ADVISORY-3 — `test_missing_space_returns_config_error` silent-skip on raise (inherited).**
Wraps its assertion in `if isinstance(result, dict):` — if impl *raises* instead of *returns*, the `[CONFIG ERROR]` check silently skips. Recorded in the addendum's Observations (item not carried as AC). The impl returns a dict per spec, so the test exercises its assertion in practice. Inherited pattern, R2-flagged not-a-regression. **Merge-gating: NO.**

---

## Unverified ACs — merge-gating vs tag-gating (per brief mandate)

The central governance question: several ACs **cannot** be verified in the pipeline (no live Anytype/Qdrant/Ollama, no two-host setup). My per-item determination:

| Unverified item | Why unverifiable in CI | Gating |
|-----------------|------------------------|--------|
| AC #6 p95 < 30s on Jan's Mac Mini M4 | needs the maintainer's hardware; CI runs only the 150s sanity bound (present, green) | **TAG-gating.** Spec line 736 explicitly designates it maintainer-measured-at-release. CI sanity bound is in place. |
| AC #7 live `verify-anytype-writes.sh` end-to-end | needs running Anytype desktop | **TAG-gating.** Spec line 737 explicitly says "CI does not execute it." Script is *shipped* (executable, `bash -n` + shellcheck clean) and its structure is unit-tested (`test_verify_script.py`). |
| Cross-host bootstrap dedup probe | needs two hosts + shared vault | **TAG-gating.** Pre-release checklist item (spec line 765), correctly not pre-authored. |
| Live `doctor` green | needs live Anytype/Qdrant/Ollama + pulled models | **TAG-gating.** Unit-tested for exit-code aggregation + 12 check names; the real-env green is a tag-time maintainer step (spec line 764). This is also where ADVISORY-1's strict-0 contract is actually exercised. |
| `wiki-bootstrap --space-id <real>` demo | needs live Anytype | **TAG-gating** (spec line 790). |
| Anytype REST endpoint guesses (`/properties`, `/properties/{pk}/options`) | mock-validated only | **TAG-gating** — the live verify run + first live bootstrap confirm them. Flagged by impl lead as a possible small `wiki_client.py` fix before tag. |

**Verdict on the central question:** It is **acceptable to merge** with these unverified, because (a) the spec *itself* designates them maintainer-local / not-CI-enforced (ACs #6, #7 explicitly; the rest by physical necessity), and (b) merge ≠ tag. None is merge-blocking. Every one is tag-blocking and is correctly enumerated in the impl lead's "Pre-release checklist state" section per addendum item #9 — which I verified the lead did honor (done / deferred-to-tag-with-rationale / N/A all present).

---

## Quality-gate scorecard

- **Acceptance criteria:** 15 spec ACs + 8 addendum criteria — all CI-verifiable ones gated by substantive tests; addendum items #1–8 confirmed landed (psutil runtime-dep `ba08e1c`; conjunction + breadcrumb strengthenings; verbatim fixture present; sentinel handoff `9ec2160`; uv.lock refresh `bc8c6f7`; test-as-contract captured). Item #9 (checklist enumeration) honored. Items #10–12 forwarded to v0.3.0. ✅
- **Test coverage:** critical paths (idempotency, union dedup, token-scope, schema-outdated, import regression, credential scrubbing) all covered with negative cases (403, unreachable, missing space, outdated schema). ✅ One weak positive assertion (ADVISORY-1).
- **Regression risk:** LOW. Refactor import surface preserved + regression-gated (AC #12c); v0.1.0 files byte-identical to base. ✅
- **Quality gates:** impl review completed in-phase; 1 MAJOR + 3 SHOULD-FIX all resolved (commits `3ebfd16`, `f95a11f`, `02b6470`); zero deferred BLOCKING. ✅

---

## Cross-communication

- **CTO** (refactor correctness + test-edit legitimacy): notified — QA concurs the test edits are assertion-preserving and the refactor is merge-safe; asked for concurrence.
- **CSO** (credential-scrubbing test adequacy): notified — QA reads unit-level `scrub_credentials` coverage as the correct v0.2.0 scope with e2e correctly carried to v0.3.0; asked for security-lens confirmation no v0.2.0 leak path is ungated.
- **Infra** (concurrency-test determinism + CI gates): notified — asked to confirm sentinel handoff wiring and concurrence that the 0-or-2 exit gate + 5× sanity timing is an acceptable CI posture for merge (ADVISORY-1 tag-gating).
- **CPO:** no acceptance-criteria-vs-user-need mismatch found; no escalation needed.

---

## Sign-off

**SIGN OFF WITH ADVISORIES — advance to `done` (merge to `main`).** The v0.2.0 deliverable is fit for purpose: green where it can be, honestly deferred where it cannot, with zero merge-blocking quality-gate failures. The three advisories are tag-gating or cosmetic and do not warrant another impl round. The `git tag v0.2.0` step must walk the maintainer-local pre-release checklist (live verify, live doctor green, p95 timing, cross-host probe, positioning + OSS-hygiene deliverables) — that list is correctly enumerated and is out of scope for the merge gate.
