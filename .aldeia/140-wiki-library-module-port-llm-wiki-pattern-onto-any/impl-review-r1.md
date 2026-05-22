# Implementation Review — v0.2.0 wiki module (Round 1)

**Ticket:** Aldeia-IT/aldeia-box#140
**Branch:** `aldeia/wiki-library-module-port-llm-wiki-pattern-onto-any`
**Reviewer:** impl lead (inline checks + independent security/correctness review agent)
**Date:** 2026-05-22

## Verdict: NEEDS CHANGES

Test suite is fully green for the v0.2.0 deliverables (208 passed, 6 skipped, 3 xfailed
in `tests/wiki/` + `tests/test_anytype_client.py`). The findings below are qualitative
(security hygiene + defensive correctness) that the tests do not exercise. One MAJOR
credential-hygiene finding plus three defensive fixes are required before exit; one finding
is a false positive (dismissed), one is deferred with rationale.

## Test verification (lead, independently run)
- `tests/wiki/ tests/test_anytype_client.py` → **208 passed, 6 skipped, 3 xfailed**. 0 failures.
- The 6 failures + 7 errors in the FULL `tests/` run are confined to v0.1.0 files
  (`test_server.py`, `test_indexer.py`), which are **byte-identical to the base commit**
  (`git diff 8898d56 HEAD -- tests/test_indexer.py tests/test_server.py src/anytype_llm_wiki/indexer.py`
  is empty). Root cause: empty `ANYTYPE_API_KEY` in the shell (→ `httpx.LocalProtocolError:
  Illegal header value b'Bearer '`) + no live Qdrant/Anytype. With a dummy key set, the
  non-network state tests pass. **Pre-existing environmental, NOT a regression** from the
  `anytype_client.py` refactor (`TestImportRegressionIndexer` passes; import surface preserved).
- Two test edits beyond the addendum were verified assertion-preserving:
  (a) `respx.<verb>(respx.patterns.M)` → `respx.<verb>()` ×54 — `respx.patterns.M` is a
  combinator factory, not a URL pattern, and raised `TypeError` at route-registration in
  respx 0.23.1; the no-arg form is the idiomatic match-any. (b) `lock_dir.mkdir(mode=0o700)`
  → `...exist_ok=True` ×2 — the autouse `set_env` fixture pre-creates the same dir, so the
  test body raised `FileExistsError` before `run_doctor()` ran. Both fix "fails-forever-
  regardless-of-implementation" defects; assertions/exit-code expectations unchanged.

## Findings

### MAJOR-1 — Doctor leaks raw URLs (incl. potential `?api_key=`/userinfo) in operator output
`src/anytype_llm_wiki/wiki/doctor.py` imports `util` but never calls `scrub_credentials`.
Every reachability/collection/Ollama message interpolates the raw `ANYTYPE_API_URL` /
`QDRANT_URL` / `OLLAMA_URL` (lines ~67, 71, 75, 113, 116, 120, 158, 160, 165, 322) into
strings printed to stdout and emitted in the `doctor --json` report. A hosted Qdrant Cloud
endpoint (`https://xyz.cloud.qdrant.io/...?api_key=SEKRET`) or a URL with userinfo would
reproduce the secret verbatim. This is the same class as AC #15 (credential scrubbing) and
the spec's Observability principle ("query-string and userinfo are stripped before logging").
**Fix:** wrap every URL interpolated into a check `message` with `util.scrub_credentials(url)`.
Tests miss it because they only use credential-free localhost URLs.

### SHOULD-FIX-1 (was MINOR-1) — `scrub_credentials` does not strip userinfo from scheme-less URLs
`src/anytype_llm_wiki/wiki/util.py:63`. `urlparse("user:pass@host/path")` puts the whole
string in `path` (empty `netloc`), so the `@`-strip on `netloc` is a no-op and the password
survives. AC #15 inputs are fully-schemed so tests pass, but this is THE credential-scrubbing
primitive — it must be robust. **Fix:** also handle the scheme-less / authority-in-path case
(e.g. detect `@` before the first `/` and strip it, or normalize a missing scheme before parse).

### SHOULD-FIX-2 (was MINOR-2) — `space_id` interpolated into lock path without sanitization
`src/anytype_llm_wiki/wiki/util.py:115` — `os.path.join(lock_dir, f"ingest-{space_id}.lock")`.
A `space_id` containing `/` or `..` could escape `WIKI_LOCK_DIR` or raise a raw `OSError`
outside the structured-error contract. Kernel semantics blunt a real traversal write, but
there is no defense-in-depth. **Fix:** sanitize `space_id` for the filename (e.g. restrict to
`[A-Za-z0-9._-]`, replacing/encoding others) before building the path.

### SHOULD-FIX-3 (was MINOR-5) — `_version_tuple` does not pad to equal length (docstring mismatch)
`src/anytype_llm_wiki/wiki/bootstrap.py:50`. The docstring claims "missing components pad to 0"
but the code returns the raw tuple, so `_version_tuple("0.2") < _version_tuple("0.2.0")`
(`(0,2) < (0,2,0)`) is True — a recorded `"0.2"` would trigger a spurious (harmless,
idempotent) schema upgrade. The load-bearing case `"0.10.0" > "0.2.0"` is correct. **Fix:**
pad both operands to equal length before comparison so behavior matches the docstring.

### DISMISSED (false positive) — verify-script "stray END"
The security agent flagged `scripts/verify-anytype-writes.sh:232` (`END` inside the `<<EOF`
heredoc) as a copy-paste defect. It is NOT a defect: the heredoc delimiter is `EOF`, and the
spec's `ANYTYPE_VERIFICATION_DECISION` block format (spec.md lines 1440–1448) mandates `END`
as the block's terminal marker. The `END` line is intentional, spec-conformant content. **No
change.**

### DEFERRED (documented) — verify-script passes bearer token via `curl -H` (visible in `ps`)
`scripts/verify-anytype-writes.sh` uses `-H "Authorization: Bearer $ANYTYPE_API_KEY"`, so the
token is briefly visible in `ps`/`/proc/<pid>/cmdline`. Deferral rationale: (a) the script is
**maintainer-local by design** (runs once on the maintainer's own single-user dev machine,
never in CI or shared hosts); (b) it matches the spec's authored script verbatim (spec lines
1397–1414), which the spec council approved; (c) hardening to a stdin/`--config` credential
path adds bash complexity and bug surface to a one-shot probe. Tracked as a v0.3.0+ hardening
suggestion. Recorded in the phase summary.

## Categories confirmed CLEAN (lead + agent)
- Bootstrap credential handling on error paths (no bearer token in 404/403/connection-error
  responses); HTTP exceptions caught and mapped to structured `[CONFIG ERROR]`/`[API ERROR]`.
- Lock permissions: dir 0o700 + file 0o600 with explicit `os.chmod` defeating umask.
- Verify script: `set -euo pipefail`, trap installed BEFORE probe creation, ownership-guarded
  cleanup (`[[ -n "${PROBE_*:-}" ]]`), all variables quoted, stderr diagnostics, no
  `ANYTYPE_OBJECT_ID`, `bash -n` + `shellcheck --severity=error` clean.
- Idempotency: union-only tag semantics; correct integer-tuple version compare for the
  load-bearing case; no duplicate root-collection on re-run.
- Resource cleanup: httpx clients closed; flock fd released in `finally`.
- Doctor robustness: no check raises (each returns OK/WARN/FAIL); exit-code 0/1/2 aggregation
  correct.
- stdout/stderr discipline: no `print()` in any library/tool path (MCP-stdio-safe); all prints
  confined to `cli.py`.
- Scope: no out-of-scope edits to v0.1.0 files; `anytype_client.py` refactor is intentional
  and preserves the free-function import surface; `pyproject.toml` psutil move is addendum-
  sanctioned.
- No shippability-blocking TODOs.

## Required for round 2
Fix MAJOR-1, SHOULD-FIX-1, SHOULD-FIX-2, SHOULD-FIX-3. Keep the full `tests/wiki/` +
`tests/test_anytype_client.py` suite green. Do not modify test assertions. Do not touch the
dismissed/deferred items.
