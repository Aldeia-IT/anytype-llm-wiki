# Security + Correctness Review — v0.2.0 wiki module (R1)

Scope: `git diff 8898d56 HEAD -- src/ scripts/ README.md` (plus `pyproject.toml`,
which the diff also touches to declare `psutil`).
Reviewer mandate: defects the green test suite (208 passed in-scope) cannot catch.
This is a review only — nothing was changed.

Method: read all focus files, reproduced `scrub_credentials` / version-tuple /
lock-path / HEREDOC behavior in throwaway interpreters, ran `shellcheck` (clean),
and re-ran the in-scope tests (`tests/wiki/` + `tests/test_anytype_client.py` =
208 passed, 6 skipped, 3 xfailed). The 6 failures / 7 errors in the full suite are
pre-existing v0.1.0 environment skew (`tests/test_server.py`,
`tests/test_indexer.py` — qdrant_client/httpx local version mismatch), unrelated
to this diff.

---

## CRITICAL

None.

---

## MAJOR

### MAJOR-1 — Doctor leaks credentials embedded in `QDRANT_URL` / `OLLAMA_URL` / `ANYTYPE_API_URL`
**File:** `src/anytype_llm_wiki/wiki/doctor.py` — messages at lines 67, 71, 75 (anytype),
105–121 (qdrant reachable), 124–149 (qdrant collection), 154–165 (ollama).
`doctor.py` imports `util` but **never calls `scrub_credentials`** (confirmed: zero
matches in the file). Every reachability/collection check embeds the raw configured
URL directly into the check `message`/`detail`, which is then printed to stdout and
serialized into the `--json` report (`cli.py:96`, `_cmd_doctor`).

If an operator sets a URL with embedded userinfo or a secret query string — both are
real-world patterns for hosted Qdrant/Ollama gateways, e.g.
`QDRANT_URL=https://default:SUPERSECRET@xyz.qdrant.cloud:6333` or
`QDRANT_URL=https://host:6333?api_key=SEKRET` — the secret is reproduced verbatim in
the doctor report. The review checklist explicitly flags "URL query string" and "URL
userinfo" in doctor output as a leak vector, and `scrub_credentials` exists precisely
to prevent this but is not applied here.

**Why tests miss it:** `tests/wiki/test_doctor.py` drives doctor with default
localhost URLs that carry no credentials, so the leak never materializes in CI.

**Suggested fix:** wrap every `url` interpolated into a doctor message with
`util.scrub_credentials(url)` (e.g. `f"Qdrant reachable at {util.scrub_credentials(url)}."`).
Note this also depends on the MINOR-1 schemeless-URL gap below for full coverage of
userinfo-without-scheme inputs.

---

## MINOR

### MINOR-1 — `scrub_credentials` does not strip userinfo from a scheme-less URL
**File:** `src/anytype_llm_wiki/wiki/util.py:63-90`.
`urlparse` only populates `netloc` (and thus triggers the `@`-stripping at lines 78–79)
when the input has a `scheme://` authority. Reproduced:

```
'user:pass@host/path?token=xyz'  -> 'user:pass@host/path'   # password NOT stripped
'redis://default:secret@h:6379'  -> 'redis://h:6379'        # ok (has scheme)
'http://host/x?token=secret'     -> 'http://host/x'         # ok
```

For `user:pass@host/path?token=xyz`, urlparse reads `user` as the scheme, leaving
`pass@host/path` in `path`; the userinfo password survives. The query string IS
dropped in this case, but the userinfo is not. This is the one input class
`tests/wiki/test_util.py` (lines 312–404) never exercises — every scrub test uses a
fully schemed URL. In v0.2.0 the only userinfo-bearing input is the lock payload's
`source_ref`, which is operator-supplied; combined with MAJOR-1 it widens the
doctor-leak surface for scheme-less URLs.

**Suggested fix:** when `parsed.netloc` is empty but the input looks like an
authority (contains `@` before the first `/`), reparse with a synthetic `//` prefix,
or strip a leading `userinfo@` token from `parsed.path` before rebuilding.

### MINOR-2 — `space_id` interpolated into the lock path with no sanitization
**File:** `src/anytype_llm_wiki/wiki/util.py:115` —
`lock_path = os.path.join(lock_dir, f"ingest-{space_id}.lock")`.
A `space_id` of `../../etc/x` produces `…/locks/ingest-../../etc/x.lock`, which
`os.path.normpath` resolves to `…/locks/etc/x.lock` — outside the intended leaf.
In practice a true escape is blunted because `os.open(O_CREAT)` does not create
parent directories and the kernel must resolve the literal `ingest-..` component
(which does not exist), so a crafted `space_id` yields an opaque `FileNotFoundError`
rather than a clean error or a confirmed traversal write. Still, there is **zero
defense-in-depth**: the value flows straight from MCP/CLI input into a filesystem
path. A `space_id` containing `/` also raises a raw `OSError` instead of the module's
structured error contract.

**Suggested fix:** validate/sanitize `space_id` before path construction — reject or
percent/`os.path.basename`-encode anything containing `/`, `..`, or path separators
(Anytype space IDs are opaque base32-ish tokens, so a `^[A-Za-z0-9_.-]+$` allowlist is
safe), and raise the standard `[DATA ERROR]`/`[CONFIG ERROR]` shape on rejection.

### MINOR-3 — Stray `END` literal in the verify script's decision block (copy-paste defect)
**File:** `scripts/verify-anytype-writes.sh:224-234`.
The HEREDOC opens with `<<EOF` and closes with `EOF` on line 233, but line 232
contains a stray literal `END` that becomes a data line. Reproduced — the emitted
`ANYTYPE_VERIFICATION_DECISION` block (and the text appended to `patch-decision.md`)
ends with a spurious `END` line. It is benign downstream (`read_patch_decision`
skips lines without `:`), but it is a clear leftover from a delimiter rename.

**Suggested fix:** delete line 232 (`END`).

### MINOR-4 — API key visible in `ps` / `/proc/<pid>/cmdline` for the verify script
**File:** `scripts/verify-anytype-writes.sh:65,107-202`.
`auth_header="Authorization: Bearer $ANYTYPE_API_KEY"` is passed to every `curl` as
`-H "$auth_header"`, so the bearer token appears as a process argument — readable by
any local process via `ps`/`/proc` for the lifetime of each curl. The script is
maintainer-local and the key never reaches `eval`, the appended file, or stdout (only
`$ANYTYPE_API_VERSION` is echoed), so impact is limited to a local-multi-user box.

**Suggested fix:** pass the key off the command line, e.g.
`curl -H @<(printf 'Authorization: Bearer %s\n' "$ANYTYPE_API_KEY") …` or
`--config` from a `printf` here-string / process substitution that curl reads as a
config file. (Quoting/`set -euo pipefail`/trap-before-create are all correct — see
clean notes below.)

### MINOR-5 — `_version_tuple` does not pad to equal length as its docstring claims
**File:** `src/anytype_llm_wiki/wiki/bootstrap.py:50-61`.
Docstring says "missing components pad to 0," but the code returns the raw tuple, and
tuple comparison treats `(0, 2) < (0, 2, 0)` as True. So a recorded
`wiki_schema_version` of `"0.2"` would be classified as an upgrade-needed against the
running `"0.2.0"`, triggering a spurious (idempotent, harmless) upgrade pass. The
core requirement — `"0.10.0" > "0.2.0"` — is handled correctly (verified). Only an
abbreviated recorded version is affected, which the writer never produces (it always
writes the full `WIKI_SCHEMA_VERSION`).

**Suggested fix:** pad both tuples to equal length with `0`s before comparing, or use
`packaging.version.Version`, to match the documented contract.

---

## Checklist coverage (categories confirmed clean)

1. **Credential leakage (bootstrap/lock):** CLEAN. `_api_error`/`_config_error_*`
   (bootstrap.py:98-140) never include the bearer token or any URL; messages are
   static + the `space_id`. HTTP exceptions are caught in `wiki_bootstrap`
   (bootstrap.py:162-180) so no stack trace with `Authorization` headers escapes.
   The lock payload (util.py:141-148) stores only pid, UTC timestamp, and a
   scrubbed `source_ref`; JSON-safe. (Doctor leak tracked separately as MAJOR-1;
   scheme-less scrub gap as MINOR-1.)
2. **Lock permissions:** CLEAN. Dir created `0o700` then explicitly `os.chmod 0o700`
   (util.py:111-113, defeating umask); file opened `0o600` then `chmod 0o600`
   (util.py:116-117). Doctor verifies the `0o700` mode at runtime (doctor.py:238-245).
   Path-safety is MINOR-2.
3. **Verify script:** Mostly CLEAN. `set -euo pipefail` present (line 25); the trap is
   installed (line 101) BEFORE any artifact is created (lines 106+); cleanup deletions
   are guarded by `[[ -n "${PROBE_OBJECT_ID:-}" ]]` and a `PROBE_TYPE_CREATED_BY_US=1`
   ownership flag so an empty/unowned id can never delete the wrong object
   (lines 73-98); no `eval`; all expansions quoted (shellcheck clean, exit 0); the
   probe object id is parsed defensively with a fallback and an empty-id guard
   (lines 133-137). Residual: MINOR-3 (stray `END`), MINOR-4 (key in `ps`).
4. **Bootstrap error handling:** CLEAN. 404 → `[CONFIG ERROR] wiki_space_missing`,
   403 → `[CONFIG ERROR] insufficient_token_scope`, connect/transport →
   `[API ERROR]`, other HTTP → generic `[API ERROR]` — all without the token
   (bootstrap.py:162-180). `finally: client.close()` guarantees socket cleanup.
5. **Idempotency:** CLEAN. Re-bootstrap tag logic is union-only — all existing tags
   are recorded as skipped and only argument tags not already present are created
   (bootstrap.py:284-307); on first bootstrap custom `domain_tags` replace defaults
   (308-321). Version comparison is tuple-of-int and correct for `0.10.0` vs `0.2.0`
   (verified); only MINOR-5 abbreviated-version edge. Root-collection detection
   reuses the existing "Wiki"/version-marked object (bootstrap.py:324-357,
   `_find_root_collection` 429-442) — no duplicate on re-run (covered by
   `test_bootstrap.py` re-run tests).
6. **Resource cleanup:** CLEAN. httpx clients closed via `finally`
   (bootstrap.py:181-182; anytype_client.py wrappers 60-81; doctor uses one-shot
   `httpx.get`). Lock fd always released in the context manager's `finally`
   (util.py:152-157), with double-close tolerated on the contention path.
7. **Doctor robustness:** CLEAN. Every `_check_*` catches its own errors and returns
   a status dict; the RAM and fs-type probes have defensive `except Exception`
   (doctor.py:201, 309). Exit-code aggregation is correct: FAIL→1, else WARN→2,
   else 0 (doctor.py:374-380).
8. **stdout/stderr discipline:** CLEAN. No `print()` in any library/tool path
   (bootstrap, doctor, util, clients, schema, config) — verified by grep. All prints
   live in `cli.py`, and the verify script writes diagnostics to `>&2`, emitting only
   the decision block to stdout. MCP stdio protocol is safe.
9. **Scope / dead code:** CLEAN. v0.1.0 chunker/embedder/indexer untouched;
   `anytype_client.py` refactor adds `AnytypeReadClient` + preserves the free-function
   wrappers as documented (intentional). `pyproject.toml` adds `psutil>=5.9` (declared,
   used by doctor) — slightly outside the stated `src/ scripts/ README.md` scope but
   correct and necessary.
10. **TODO/placeholder shippability:** CLEAN. Only intentional, documented v0.3.0
    forward-scaffolds (`WIKI_EXTRACT_MODEL` placeholder in config.py:17-34;
    `read_patch_decision` scaffold — which is in fact wired into two doctor checks, so
    not dead). No `NotImplementedError`/`FIXME`/`XXX`. README privacy/copyright
    additions are accurate.

---

## Findings by severity
- CRITICAL: 0
- MAJOR: 1 (doctor URL credential leak)
- MINOR: 5

## Verdict
HAS-MAJOR
