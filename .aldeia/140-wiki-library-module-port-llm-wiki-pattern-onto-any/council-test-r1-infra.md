# Council Meeting — Post-test (Round 1) — Infrastructure Lead

**Date:** 2026-04-23
**Ticket:** #140 — Wiki Library Module: Port LLM Wiki Pattern onto Anytype
**Phase reviewed:** test (post-test council, R1)
**Reviewer:** Infrastructure Lead
**Commit under review:** `8f94d09` (test branch head; includes R1→R2 fixer rework `ab25890` and R2 APPROVED `8f94d09`)
**Review mode:** Post-test governance — verify impl-phase operational readiness after the test scaffolding was reviewed and approved by the test-reviewer.

---

## Verdict

**SIGN OFF. No BLOCKING. 2 ADVISORY.**

The v0.2.0 failing-test scaffolding is operationally sound from an infrastructure-readiness standpoint. The doctor 12-check enumeration is complete and matches the spec (including the R1 SHOULD-FIX-4 fix for `ollama_extraction_model_ram_fit` at entry 8). The `space_ingest_lock` concurrency test uses real `multiprocessing.Process` with kernel-held `fcntl.flock` per spec Test Plan line 1913 — no mocked flock, no threads, no asyncio-gather shortcut. The verification script test battery exercises the AC #7 structural contract (trap-before-probe, conditional guards, stderr routing, `ANYTYPE_OBJECT_ID` absence) against a yet-to-be-authored script. The cross-host bootstrap probe correctly stays a pre-release checklist item (spec line 765), not a pre-authored failing test. No launchd, Colima, or Docker surface is touched by this phase — the test scaffolding is filesystem-only, pytest-only, and introduces zero new co-resident services on the Mac Mini.

The two ADVISORY items concern **CI flake risk on the `time.sleep(0.3)` concurrency sync** (manageable with a deterministic handoff tweak at impl phase) and **`uv.lock` drift** from the four new dev deps (resolved by a single `uv sync --extra dev` at impl-phase opening, but should be noted in the impl phase kickoff to prevent an implementer from tripping over a stale lockfile). Neither blocks advancing to `decide`.

---

## Summary

The test phase delivered what the R3 spec council (including my prior sign-off) asked for. Eight new test files under `tests/wiki/` cover the 15 v0.2.0 ACs with structural assertions against a not-yet-extant `anytype_llm_wiki.wiki` module; 193 failures pre-implementation with the correct `ModuleNotFoundError` / `ImportError` failure mode; 6 passes for v0.1.0 surfaces that should remain green; 6 skips for live-API-gated tests; 3 xfail for v0.3.0+ activation. All doctor checks are named and enumerated. Credential scrubbing is tested at the unit level against `scrub_credentials` directly (not via a tautological bootstrap path — R1 BLOCKING-B1 resolution). MCP registration is tested in a module without the `autouse=True` service check that was silently skipping AC #11 in R1 (R1 BLOCKING-B2 resolution).

Operationally, this phase adds:
- 4 new **dev-only** deps (`respx>=0.21`, `pytest-timeout>=2.2`, `freezegun>=1.5`, `psutil>=5.9`). None touch the runtime install footprint.
- Zero new **runtime** deps. No new Ollama models, no new Qdrant collections, no new environment variables mandated by the tests beyond those the spec already mandates at the implementation layer.
- Zero new **services**. No launchd plist, no Docker container, no ntfy topic, no watchdog endpoint. Mac Mini memory envelope is unchanged from v0.1.0 steady state (v0.2.0 is bootstrap-only + preflight — no LLM invocation at runtime).
- One new **filesystem concern** — a lock directory at `WIKI_LOCK_DIR` (default `~/.cache/anytype-llm-wiki/locks`) that the test suite exercises under `tmp_path` in CI and that the doctor's step 7/9 probe at runtime. No backup implications (lock files are transient; losing them on Mac Mini restart is a feature, not a bug — flocks die with the process).

The test scaffolding is ready to hand off to implementation. I see no path that requires an infra gate (launchd unit, Colima VM size bump, ntfy routing, Caddy upstream) before or during impl.

---

## Doctor 12-check spot verification

R1 SHOULD-FIX-4 flagged that `EXPECTED_CHECK_NAMES` was missing the check-6b entry. R2 claims it is now present as entry 8 of 12. I verified this directly.

**File:** `/Users/Shared/development/anytype-llm-wiki-worktrees/test/wiki-library-module-port-llm-wiki-pattern-onto-any/tests/wiki/test_doctor.py` lines 105–118.

**List in the test:**

```
 1. anytype_api_key                  (spec check 1)
 2. anytype_reachable                (spec check 2)
 3. anytype_version_drift            (spec check 3 — WARN on drift)
 4. qdrant_reachable                 (spec check 4)
 5. qdrant_collection                (spec check 4b — WARN, not FAIL)
 6. ollama_reachable                 (spec check 5)
 7. ollama_models_pulled             (spec check 6)
 8. ollama_extraction_model_ram_fit  (spec check 6b — R1 SHOULD-FIX-4)
 9. wiki_lock_dir                    (spec check 7 — mode 0o700)
10. patch_decision_md                (spec check 8)
11. wiki_lock_dir_fs_type            (spec check 9 — NFS WARN)
12. wiki_fetch_extra_ports           (spec check 10 — WARN if non-empty)
```

Cross-reference to spec.md lines 1158–1169:
- Spec check 1 → test entry 1. MATCH.
- Spec check 2 → test entry 2. MATCH.
- Spec check 3 → test entry 3. MATCH.
- Spec check 4 → test entry 4. MATCH.
- Spec check 4b (Qdrant collection, line 1162) → test entry 5. MATCH.
- Spec check 5 → test entry 6. MATCH.
- Spec check 6 → test entry 7. MATCH.
- Spec check 6b (RAM WARN, line 1165) → test entry 8. MATCH — **this is the R1 SHOULD-FIX-4 fix**.
- Spec check 7 (lock dir mode 0o700, line 1166) → test entry 9. MATCH.
- Spec check 8 (patch-decision.md, line 1167) → test entry 10. MATCH.
- Spec check 9 (filesystem-type probe, line 1168) → test entry 11. MATCH.
- Spec check 10 (extra ports, line 1169) → test entry 12. MATCH.

**All 12 checks present. Enumeration integrity verified.** The parametrize at line 124 will generate 12 parametrized test instances — each of which will fail pre-implementation with `ModuleNotFoundError` (correct failure mode). The spec-to-test name mapping has no drift; the implementer has a clean name contract to hit.

---

## Concurrency-test realism check

Spec Test Plan line 1913 explicitly rejects threads, asyncio.gather, and mocked flock for `space_ingest_lock` concurrent-acquisition testing. The correct mechanism is `multiprocessing.Process` with each process opening the same file separately and calling `fcntl.flock(fd, LOCK_EX | LOCK_NB)`.

**File:** `/Users/Shared/development/anytype-llm-wiki-worktrees/test/wiki-library-module-port-llm-wiki-pattern-onto-any/tests/wiki/test_util.py` lines 230–281.

**What I verified:**
- Line 230: helper function `_try_acquire_lock(lock_dir, space_id, result_queue)` runs in the child process.
- Line 234: `from anytype_llm_wiki.wiki.util import space_ingest_lock` is imported **inside** the subprocess, which gets a fresh module state (correct — avoids any monkeypatched state from the parent test leaking into the child).
- Line 258: `multiprocessing.Queue` is used for cross-process signalling. Correct primitive for the happy-path sync.
- Line 261–265: `multiprocessing.Process(target=_try_acquire_lock, args=(...))` — real OS-level process isolation. **This is the canonical mechanism the spec requires.**
- Line 268: `time.sleep(0.3)` is the handoff window for the child to acquire the lock before the parent attempts acquisition.
- Line 272–278: parent attempts `space_ingest_lock(same_space_id)` and asserts `ingest_in_progress` in the raised exception's message.
- Line 280–281: `holder.terminate()` + `holder.join(timeout=5)` — correct child-process cleanup.

**Mechanism assessment: PASS.** This is `multiprocessing.Process`, not threading or asyncio, and the flock is held by a real file descriptor in a real second process. The spec's mechanism requirement is met.

**Phase summary discrepancy noted:** The phase summary (line 52) says "`multiprocessing.Event` for synchronization." The actual test uses `multiprocessing.Queue` + `time.sleep(0.3)` — not `Event`. The summary is inaccurate on this detail. Not a correctness issue (Queue works), but ADVISORY-1 below addresses the downstream flake risk the sleep-based sync introduces.

**Determinism analysis:**
- The 0.3s sleep is the child's window to: (a) boot Python in the subprocess (~50–200ms cold on Mac/Linux), (b) import `anytype_llm_wiki.wiki.util`, (c) enter the `space_ingest_lock` context manager, (d) call `fcntl.flock(fd, LOCK_EX | LOCK_NB)` and acquire, (e) put "acquired" on the queue.
- On a healthy Mac Mini M4 or clean GitHub Actions runner, this completes in 100–200ms — well under 300ms. Tests should pass reliably.
- **Flake vector:** On a heavily loaded CI runner (especially cold-start Ubuntu runners, or a Mac runner with parallel jobs), Python cold-start + module import can exceed 300ms. If the parent reaches its `space_ingest_lock` call before the child has acquired the flock, the parent acquires successfully and the test fails with `pytest.fail("Second process should NOT have acquired the lock")`.
- **Impact:** Intermittent red CI on a test that's actually correct. Not a soundness bug; a reliability bug.

**Preferred pattern (ADVISORY-1 recommendation):** Replace `time.sleep(0.3)` with a blocking `result_queue.get(timeout=5)` against an "acquired" sentinel the child puts on the queue before its `time.sleep(2)` hold. This makes the handoff deterministic — the parent only proceeds once the child has signalled lock acquisition, regardless of CI runner speed. The existing queue infrastructure supports this with a two-line edit.

---

## Dep / CI readiness assessment

**`pyproject.toml` changes** (`/Users/Shared/development/anytype-llm-wiki-worktrees/test/wiki-library-module-port-llm-wiki-pattern-onto-any/pyproject.toml`):

```
[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",        # pre-existing
    "respx>=0.21",          # NEW — httpx mocking
    "pytest-timeout>=2.2",  # NEW — @pytest.mark.timeout for AC #6
    "freezegun>=1.5",       # NEW — time freezing (if used by stale-lint tests in v0.5.0)
    "psutil>=5.9",          # NEW — for doctor step 6b RAM check
]
```

**`uv.lock` state:** The file exists in the repo (committed from v0.1.0), but has NOT been regenerated for the four new dev deps. The phase summary notes this explicitly (line 71). I confirm: `uv.lock` presence alone does not mean the lock is current.

**Is this a blocker for impl-phase CI?**

No. `uv sync --extra dev` at impl-phase opening (or equivalently, the implementer's first `uv run pytest` invocation) will refresh the lockfile with the new deps. The operations are:
1. Implementer opens the impl worktree.
2. Runs `uv sync --extra dev` (or any `uv run` command, which triggers a lock refresh).
3. `uv.lock` is regenerated to include `respx`, `pytest-timeout`, `freezegun`, `psutil` and their transitive deps.
4. The implementer commits the refreshed `uv.lock` as part of their first commit on the impl branch.

**However**, the pre-release checklist at spec line 787 has `uv lock --locked` as a required gate. `--locked` fails CI if the committed lock doesn't match `pyproject.toml`. If the implementer doesn't commit a refreshed `uv.lock`, the v0.2.0 pre-release will fail at this gate. That's a SHOULD-FIX-severity item for impl, not a BLOCKING for test.

**Impl-phase readiness items (not blocking for test advancing to decide, but should be flagged to implementer):**
- Run `uv sync --extra dev` **before** the first `pytest` invocation.
- Commit the refreshed `uv.lock` as part of the first impl commit.
- **Dependency supply-chain note:** `psutil>=5.9` is a C-extension package. On macOS (the primary dev environment) it builds from wheels for Python 3.11+. No build toolchain surprises expected on Mac Mini M4 (arm64 wheels are published on PyPI). On Linux CI runners, manylinux wheels cover Python 3.11/3.12. No sdist build fallback expected.
- **No new CI infra required.** Shellcheck is skip-gated in `test_verify_script.py` (lines 74–77 — `pytest.mark.skipif`), so the test suite does NOT require shellcheck to be installed on CI runners. That's a correct graceful-degradation pattern.

ADVISORY-2 below captures the `uv.lock` flag as a formal reminder to the impl kickoff checklist.

---

## Verification script tests (AC #7)

**File:** `/Users/Shared/development/anytype-llm-wiki-worktrees/test/wiki-library-module-port-llm-wiki-pattern-onto-any/tests/wiki/test_verify_script.py`.

AC #7 (spec line 737) requires `scripts/verify-anytype-writes.sh` to exist and to satisfy a structural contract. The spec specifically calls out (line 1384 and line 1429):
- Trap-before-probe ordering: the `trap cleanup EXIT` must be installed BEFORE the first `curl POST /types` that creates the probe.
- Conditional guards: cleanup must guard `DELETE` calls with `[[ -n "${PROBE_OBJECT_ID:-}" ]]` and `[[ -n "${PROBE_TYPE_KEY:-}" ]]`.
- No `ANYTYPE_OBJECT_ID` reference (removed as data-loss foot-gun).
- Non-2xx DELETE diagnostics to stderr (`>&2`).

**Spot-check results:**
- `TestScriptExists` (lines 26–35) — file existence + is-file.
- `TestScriptExecutableBit` (38–45) — `stat()` mode check for `0o111` any-x bit.
- `TestScriptShebang` (48–55) — first line must be `#!/usr/bin/env bash` or `#!/bin/bash`.
- `TestScriptSyntax` (58–87) — `bash -n` (with `shutil.which('bash')` skip-gate) and shellcheck (skip-gated on absence).
- `TestScriptTrapBeforeProbe` (90–115) — **the critical one**. Iterates lines; finds first `\btrap\b.*\bcleanup\b` line number and first `curl.*types` line number with `POST`; asserts `trap_line_no < probe_create_line_no`. Correctly enforces spec line 1384 ordering.
- `TestScriptConditionalGuards` (118–144) — regex search for `[[ -n .*PROBE_OBJECT_ID` or `${PROBE_OBJECT_ID:-}` and same for `PROBE_TYPE_KEY`. Correct.
- `TestScriptStderrDiagnostics` (147–155) — asserts `>&2` appears in the script content. Simple but effective.
- `TestScriptNoANYTYPE_OBJECT_ID` (158–174) — strips comment lines first, then asserts `ANYTYPE_OBJECT_ID` does not appear in non-comment content. **Good — permits the spec's explanation of why the variable was removed to appear in a comment without triggering the test.**
- `TestScriptEnvironmentVariables` (177+) — required env var presence (`ANYTYPE_API_KEY`, `ANYTYPE_SPACE_ID`, `ANYTYPE_API_URL`-or-default).

**Path resolution:** `SCRIPT_PATH = REPO_ROOT / "scripts" / "verify-anytype-writes.sh"` with `REPO_ROOT = pathlib.Path(__file__).parent.parent.parent`. This resolves relative to the test file's location. In the worktree `/Users/Shared/development/anytype-llm-wiki-worktrees/test/.../tests/wiki/test_verify_script.py`, `REPO_ROOT` correctly resolves to the test worktree root. **Worktree-agnostic, no hardcoded `/Users/` paths.** Confirmed via Grep against `tests/wiki/` — zero hardcoded absolute paths.

**Current state:** `scripts/` directory does NOT exist in the test worktree (confirmed via `ls`). This is the correct pre-implementation state: the test will fail pre-implementation (script absent), and the implementer must author `scripts/verify-anytype-writes.sh` during impl. The test will go green once the script exists and meets the structural contract.

**AC #7 coverage: PASS.** The structural contract is exercised; live execution is correctly gated out ("CI does not run the script — maintainer-local per AC #7").

---

## Cross-host bootstrap probe (R2 Infra/CSO A1)

The R2 CSO/Infra joint concern about cross-machine TOCTOU during `wiki_bootstrap` (two operators running bootstrap from two hosts against the same Anytype vault) landed in the spec at **line 765 as a pre-release checklist item**, not as a v0.2.0 authored failing test.

**Verification that the test phase did NOT pre-empt this:**

Searched `tests/wiki/` for any cross-host / two-host / simultaneously-from-two-hosts test. Zero matches. The concurrent `fcntl.flock` test covers **same-host** two-process concurrency (correct scope — flocks are per-host). The cross-machine probe is correctly left as an **empirical pre-release checklist item** to be performed by Jan at release-time on real hardware against a real Anytype vault.

**Assessment: correct.** A cross-host concurrency test cannot be realistically authored in pytest — it requires two actual hosts, a shared Anytype vault, and orchestration tooling the test suite doesn't have. The pre-release checklist is the right venue for this probe; the spec correctly scopes it there.

**Reminder for impl-phase-end / pre-release:** When Jan does the v0.2.0 tag, he (or whoever performs the release) must run the cross-host probe and record the result in the v0.2.0 pre-release notes. This is operationally important because Anytype's dedup-by-`type_key` is the only serialization for cross-machine bootstrap; if it fails, duplicate Types would be created on the vault and the spec requires a defect + documented limitation in §Concurrent Ingest Policy.

---

## Deployment risk assessment

Per my mandate — is there any operational readiness concern for the impl phase to handle?

**Test suite path assumptions:**
- All tests use `tmp_path` for filesystem artifacts — no hardcoded `/Users/` or `/tmp/` (grep verified zero occurrences).
- `REPO_ROOT` in `test_verify_script.py` uses `pathlib.Path(__file__).parent.parent.parent` — worktree-agnostic.
- Lock directory tests use `monkeypatch.setenv("WIKI_LOCK_DIR", str(tmp_path / "locks"))` — correct isolation.
- No test relies on a specific cwd; `pytest` invocation from any location within the worktree works.

**Live-service dependencies in CI:**
- `TestBootstrapLiveAPI` (`test_bootstrap.py:837`) is skip-gated on `ANYTYPE_API_KEY` env var. Absent in CI → skip. Correct.
- `tests/test_server.py::TestSemanticSearch` and `TestReindexTool` continue to use the module-level `autouse=True` `check_services` fixture. Services absent in CI → skip. Unchanged from v0.1.0; correct.
- `TestScriptSyntax::test_bash_n_parses_clean` skip-gates on `shutil.which('bash')`. Linux CI has bash; macOS CI has bash. No practical skip; safe.
- `TestScriptSyntax::test_shellcheck_clean` skip-gates on `shutil.which('shellcheck')`. Neither GitHub Actions ubuntu-latest nor macos-latest ships shellcheck by default — the test will skip on vanilla runners. That's acceptable; shellcheck is a maintainer-local nicety, not a CI gate.

**Mac Mini resource envelope delta:**
- v0.2.0 test phase: zero. The tests run in `uv run pytest`; total memory < 500 MB for a full pytest session (pytest + respx + the test worktree in memory). Nothing persistent, nothing launchd-registered, nothing docker-ized.
- v0.2.0 impl phase (bootstrap + preflight): still zero steady-state delta. Bootstrap runs on-demand and exits; doctor runs on-demand and exits. No new daemon, no new process footprint on the Mac Mini after the tool's invocation completes.
- Cumulative with other Aldeia-IT services (PostgreSQL 18, Ollama, Colima 2GB, ntfy, Caddy, IronClaw, Claude Code workers): unchanged from v0.1.0. Mac Mini 32GB envelope is not approaching any constraint for v0.2.0.

**Launchd / Docker / Caddy:** No changes needed in v0.2.0. Correct.

**Backup impact:** Lock files at `~/.cache/anytype-llm-wiki/locks/` are transient and do NOT need backup (they die with the process that holds them; stale files are cleaned up on next lock acquisition by the implementation per spec). `patch-decision.md` is in `.aldeia/` and is git-tracked. `positioning-verification.md` is in `.aldeia/` and is git-tracked. No new non-git-tracked data stores.

**Monitoring / watchdog:** No new services to watchdog. Doctor is invoked on-demand; it is not a daemon.

**ntfy alerts:** None needed. This is a library/CLI tool; failures surface to the operator's shell or MCP host, not to ntfy.

**No deployment risk identified for the impl phase.**

---

## Findings

### BLOCKING

_None._

### ADVISORY

#### ADVISORY-1 — `time.sleep(0.3)` handoff in `TestSpaceIngestLockConcurrency::test_second_process_fails_with_ingest_in_progress` is a CI flake vector

**File:** `/Users/Shared/development/anytype-llm-wiki-worktrees/test/wiki-library-module-port-llm-wiki-pattern-onto-any/tests/wiki/test_util.py` line 268.

**Description:** The test relies on a fixed 300ms sleep for the child process to: boot Python, import the module, enter the context manager, and acquire the flock. On healthy Mac Mini M4 or clean GitHub Actions runners this is reliable (100–200ms typical). On loaded runners (parallel CI matrix, cold-start Ubuntu, noisy neighbor VM), Python cold-start + import can exceed 300ms, in which case the parent acquires the lock first and the test fails with `pytest.fail("Second process should NOT have acquired the lock")`.

**Operational impact:** Intermittent red CI on a test that is functionally correct. The test does exercise real `fcntl.flock` with real multiprocessing — the **mechanism is correct per spec line 1913**, this is a timing-sync robustness concern only. Flaky tests erode confidence and train developers to re-run CI rather than read failures, which is an infrastructure-level hazard in its own right.

**Recommended action (for impl phase or R1 fixer if extended):** Replace `time.sleep(0.3)` (line 268) with a blocking `result_queue.get(timeout=5)` against an "acquired" sentinel. The child (`_try_acquire_lock` at line 230) already puts `"acquired"` on the queue at line 237 before sleeping — the parent can simply read it instead of sleeping. Two-line edit:

```python
# replace: time.sleep(0.3)
# with:
acquired = result_queue.get(timeout=5)
assert acquired == "acquired", f"Child failed to acquire lock: {acquired!r}"
```

This eliminates the timing assumption entirely. The child signals readiness explicitly; the parent proceeds only after the signal. Deterministic across all CI hardware.

**Severity:** ADVISORY. The test is not broken; it will pass on the Mac Mini M4 where v0.2.0 is dogfooded. It will flake on slow CI. Since this project's target CI is GitHub Actions (per `pre-release checklist` phrasing that assumes CI exists), this is worth fixing before the v0.2.0 tag. Not a test-phase blocker — it can be landed as part of impl-phase if the implementer touches these tests at all, or as a trivial follow-up.

---

#### ADVISORY-2 — `uv.lock` not regenerated for new dev deps; impl kickoff must run `uv sync --extra dev` first

**File:** `/Users/Shared/development/anytype-llm-wiki-worktrees/test/wiki-library-module-port-llm-wiki-pattern-onto-any/pyproject.toml` (4 new dev deps); `uv.lock` (unchanged from v0.1.0).

**Description:** The test phase added `respx>=0.21`, `pytest-timeout>=2.2`, `freezegun>=1.5`, `psutil>=5.9` to `[project.optional-dependencies] dev` in `pyproject.toml`, but `uv.lock` was not regenerated. The spec's v0.2.0 pre-release checklist (spec line 787) requires `uv lock --locked` green before tagging, which fails when the committed lock is out of sync with `pyproject.toml`.

**Operational impact:** If the implementer's first action at impl-phase opening is `uv run pytest` without a prior `uv sync --extra dev`, `uv` will warn about lock drift (or implicitly resolve — behavior depends on `uv` version). An implementer who doesn't know about the four new deps might be puzzled by an "outdated lock" message or miss committing the updated lockfile. Pre-release checklist's `uv lock --locked` gate will catch this at tag time, but the friction at impl-phase opening is avoidable with an explicit note.

**Recommended action (for impl-phase kickoff checklist):** The impl phase lead should include in their first commit or first README/runbook update: *"Before first `pytest` run: `uv sync --extra dev` to refresh `uv.lock` with the four new dev deps added in the test phase (respx, pytest-timeout, freezegun, psutil). Commit the refreshed `uv.lock` as part of your first impl commit."*

Alternatively, this could be a one-line fix in the test branch itself — run `uv lock` and commit the refreshed lockfile as a trivial post-R2 housekeeping commit before advancing to decide. But since the test-reviewer already APPROVED and the phase is closing, it's equally defensible to leave this for impl. Jan's feedback *"fix the advisory findings as well"* in spirit suggests we should offer to fix it; pragmatically it's a 30-second operation for the impl lead on day 1.

**Severity:** ADVISORY. No test is broken; no CI gate fails in the test phase itself (the test phase does not execute `uv lock --locked`). Impact is contained to implementer onboarding friction and the downstream pre-release check. Not a test-phase blocker.

---

## Cross-thread items

- **To CSO (if writing their own council-test-r1-cso.md):** The cross-host bootstrap probe (joint CSO/Infra R2 A1) is correctly left in the pre-release checklist and is NOT pre-empted by the test phase. No new CSO concern from the test scaffolding's infrastructure surface.
- **To QA Director:** My ADVISORY-1 (sleep-based concurrency sync) overlaps with test quality / flakiness. Flagging in case QA wants to call it BLOCKING from a determinism standpoint — I'm categorizing ADVISORY because the mechanism is correct and the flake is probabilistic, not guaranteed. QA has purview to escalate.
- **To CTO:** `psutil>=5.9` is a new C-extension runtime dep (moved from dev to runtime via the doctor step 6b). Actually — verifying: `psutil` is in `[project.optional-dependencies] dev` per the current pyproject.toml. If doctor step 6b runs in production (and it must, per spec line 1165), `psutil` needs to be a **runtime** dep, not just dev. Flagging to CTO: **this is actually an impl-phase implementation question**. The test scaffolding's `EXPECTED_CHECK_NAMES` includes `ollama_extraction_model_ram_fit` which requires `psutil.virtual_memory()` at runtime. When the implementer writes `wiki/doctor.py`, they'll need to move `psutil` from `dev` to the main `dependencies` list. Not a test-phase finding (the test scaffolding doesn't dictate where `psutil` lives in `pyproject.toml`), but the CTO should confirm this at impl-phase review if they hadn't already.
- **To CPO:** No product-facing concerns from the infra surface. The two-defaults extraction model config (16GB WARN via doctor step 6b) is tested and named correctly; the README table is a docs deliverable untouched by the test phase.

---

## Recommendation

**Advance to `decide`.** No BLOCKING findings. The test phase is operationally sound for impl hand-off. Two ADVISORY items (concurrency-sync flake risk, `uv.lock` drift) are manageable at impl-phase opening with a documented kickoff step and a 2-line test edit, neither of which blocks the current phase gate.

**Sign-off:** SIGN OFF (unconditional for test-phase infra-scope). Concurrence with test-reviewer R2 APPROVED and phase-summary recommendation to advance.

---

## Relevant file paths

- `/Users/Shared/development/anytype-llm-wiki-worktrees/test/wiki-library-module-port-llm-wiki-pattern-onto-any/.aldeia/140-wiki-library-module-port-llm-wiki-pattern-onto-any/spec.md` — spec under review (AC list at line 730, doctor at line 1154, Test Plan at line 1894, pre-release checklist at line 760).
- `/Users/Shared/development/anytype-llm-wiki-worktrees/test/wiki-library-module-port-llm-wiki-pattern-onto-any/tests/wiki/test_doctor.py` — doctor 12-check enumeration (EXPECTED_CHECK_NAMES at lines 105–118).
- `/Users/Shared/development/anytype-llm-wiki-worktrees/test/wiki-library-module-port-llm-wiki-pattern-onto-any/tests/wiki/test_util.py` — space_ingest_lock concurrency (TestSpaceIngestLockConcurrency at lines 243–303) + scrub_credentials unit tests (TestCredentialScrubbing at line 310+).
- `/Users/Shared/development/anytype-llm-wiki-worktrees/test/wiki-library-module-port-llm-wiki-pattern-onto-any/tests/wiki/test_verify_script.py` — verification script structural tests (trap-before-probe at TestScriptTrapBeforeProbe lines 90–115).
- `/Users/Shared/development/anytype-llm-wiki-worktrees/test/wiki-library-module-port-llm-wiki-pattern-onto-any/pyproject.toml` — dev deps at lines 18–25 (4 new deps, lock drift).
- `/Users/Shared/development/anytype-llm-wiki-worktrees/test/wiki-library-module-port-llm-wiki-pattern-onto-any/.aldeia/140-wiki-library-module-port-llm-wiki-pattern-onto-any/test-review-r1.md` — R1 test review (NEEDS CHANGES, 2 BLOCKING + 4 SHOULD-FIX).
- `/Users/Shared/development/anytype-llm-wiki-worktrees/test/wiki-library-module-port-llm-wiki-pattern-onto-any/.aldeia/140-wiki-library-module-port-llm-wiki-pattern-onto-any/test-review-r2.md` — R2 test review (APPROVED, all findings FIXED).
- `/Users/Shared/development/anytype-llm-wiki-worktrees/test/wiki-library-module-port-llm-wiki-pattern-onto-any/.aldeia/140-wiki-library-module-port-llm-wiki-pattern-onto-any/council-spec-r3-infra.md` — my prior R3-spec sign-off (baseline for this review).
- `/Users/Shared/development/tasks/logs/140-wiki-library-module-port-llm-wiki-pattern-onto-any/phase-summary-test.md` — test-phase lead's phase summary.
