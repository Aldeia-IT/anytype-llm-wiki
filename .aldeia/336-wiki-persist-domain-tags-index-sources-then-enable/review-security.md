# Security + Correctness Review — aldeia-box#336

**Reviewer:** security-reviewer (Product + Agent-Operations domains)
**Scope:** `git diff main...HEAD -- src/ docs/`
**Files:** chunker.py, config.py, indexer.py, server.py, wiki/ingest.py, wiki/query.py, wiki/remember.py
**Overall risk:** LOW — no CRITICAL or MAJOR findings. The change is clean against the checklist.

---

## Verdict: CLEAN (no blocking findings)

All five focus areas from the brief were verified and pass.

---

## Checklist results

### 1. Input validation at the MCP boundary — PASS

- **`semantic_search`** (`server.py:80-86`): validates both `source_type` and `domain_tags`
  with `not isinstance(val, list) or not all(isinstance(s, str) and s for s in val)`. A
  non-list raises `ValueError`; an empty string in the list is falsy under `and s`, so
  `all(...)` is False and it raises. Matches the "MUST raise ValueError" contract.
- **`wiki_query`** (`query.py:505-520`): identical structural check, but returns a
  `config_error` dict (`status=error`, `error_category=config_error`) — never raises. The
  block sits at the top of `wiki_query` BEFORE any client construction / try-block, so no
  raise path exists. Matches the "MUST return config_error dict, never raise" contract.
- **Injection surface via `MatchAny`:** `indexer.semantic_search_core` (`indexer.py:133-140`)
  passes filter values as `MatchAny(any=source_type)` / `MatchAny(any=domain_tags)` through
  the Qdrant client's structured filter API — values are carried as data, not interpolated
  into any query string. No injection surface. Unknown/whitespace values match nothing
  (fail-safe), they do not error.

### 2. Credential / control-char handling — PASS

- **Stub-excerpt path** (`remember.py:166-172`): the new `excerpt = name` branch executes
  ONLY when `source_note` is empty/falsy. In that branch `name` is the hardcoded constant
  `f"agent {YYYY-MM-DD}"` (`remember.py:161-165`) — no user-controlled data, no control
  chars. The non-empty branch still routes through `sanitize_property_value(scrub_credentials(...))`.
  Safe.
- **Source name field** (`remember.py:162`) is `scrub_credentials(source_note)[:200]` and is
  not control-char-stripped, but this is pre-existing main behavior unchanged by #336 (not in
  the diff) and the `name` is not on the indexed text path. Out of scope; noted only.
- **Tag-name reads from Anytype GET responses** (`chunker.py:50-70`): `source_type` from
  `prop["select"]["name"]` and `domain_tags` from `[t["name"] for t in multi_select ...]`,
  both guarded by `isinstance(...)` checks and `t.get("name")` truthiness. Values flow into
  the Qdrant payload only as KEYWORD match data — no shell, no SQL, no query-string
  interpolation. The same shape-guarded reads appear in `query.py:_passes_source_type_filter`
  / `_passes_domain_tags_filter`. No injection or crash vector.

### 3. Degrade-not-abort on tag-resolution failure — PASS

- `_resolve_select_tag` (`ingest.py:333-360`) returns `(None, True)` on `httpx.HTTPError`
  AND on any other `Exception` (broad fallback). `_resolve_multi_select_tags`
  (`ingest.py:363-393`) returns `([], True)` on both. Neither aborts.
- Callers record warnings on degrade: `ingest._run_ingest` appends
  `"domain_tags_resolution_degraded"` (`ingest.py:873-874`); `_create_source` appends
  `"source_type_resolution_degraded"` (`ingest.py:1033-1035`); `remember._apply_batch`
  appends `"domain_tags_resolution_degraded"` (`remember.py:519-521`). When a tag is
  unresolved the prop is simply not appended — the object is still written without the tag.
- Re-export integrity verified: `remember.py` now imports `_resolve_select_tag` /
  `_resolve_multi_select_tags` from `ingest`, and `lint.py`'s
  `from .remember import _resolve_select_tag` still resolves (confirmed via live import).

### 4. CRITICAL data-integrity invariant (#323) — PASS / NOT REGRESSED

- `indexer._run_reindex` (`indexer.py:336-337`): the global marker advance
  `state["_payload_schema_version"] = config.PAYLOAD_SCHEMA_VERSION` remains gated on
  `if space_id is None:`. A scoped reindex (the auto-fire after every ingest/remember) does
  NOT advance the marker, so other spaces are not stranded on the old payload. The gate's
  rationale is documented inline (`indexer.py:330-335`). `PAYLOAD_SCHEMA_VERSION` bumped
  2→3 (`config.py`). Invariant intact.

### 5. New error paths — no leak / no crash — PASS

- `_save_state` (`indexer.py:181-198`): rewritten to atomic temp-write + `os.fsync` +
  `os.replace`. Temp file via `tempfile.mkstemp` (mode 0o600, same dir). On any
  `BaseException` it unlinks the temp and re-raises — no partial/corrupt state.json, no
  secret leak (state holds object ids + timestamps only).
- `_reindex_lock` (`indexer.py:210-232`): advisory `flock` lock, lock file mode 0o600,
  non-blocking; on contention yields False and the caller returns zeroed `skipped=True`
  stats. Worst case is deferred indexing of just-written data (eventual consistency), not a
  data-loss or security issue.
- Taxonomy-warning block (`query.py:585-617`): `_domain_taxonomy` call wrapped in
  `except Exception: known_domain = set()` (best-effort, degrade). Warnings are
  informational strings; no data leak. Runs only on opt-in filtered queries.
- `_create_remember_source` create failure (`remember.py:184-186`) is caught and recorded
  as a warning string with the exception message — exception text here is local Anytype
  client errors, not credentials; consistent with existing patterns.

---

## Security Assessment Table

| Category | Status | Notes |
|----------|--------|-------|
| SQL Injection | N/A | No SQL. |
| Command Injection | N/A | No shell with user/LLM input on the diff paths. |
| Injection via Qdrant filter | Pass | `MatchAny` carries values as structured data, not query strings. |
| Input Validation | Pass | `semantic_search` raises ValueError; `wiki_query` returns config_error. Non-list and empty-string-in-list both rejected. |
| Authorization | N/A | Local-first MCP; unchanged trust model. |
| Secrets Management | Pass | Stub excerpt is a constant; non-empty notes still scrubbed+sanitized; no secrets in new logs/warnings. |
| Control-char handling | Pass | Tag-name reads shape-guarded; sanitize path preserved for note text. |
| Degrade-not-abort | Pass | Resolvers return safe sentinels + warning on HTTPError and any Exception. |
| Data-integrity invariant | Pass | Schema-version marker advance still gated on `space_id is None`. |
| Crash safety / file I/O | Pass | Atomic state write + advisory lock; no corrupt-state or race regression. |

---

## Minor observations (non-blocking, informational)

1. **Whitespace-only filter values** (`server.py:80`, `query.py:508`): a value like `" "`
   passes the non-empty check (`and s` is truthy) and reaches `MatchAny`, where it simply
   matches nothing. Fail-safe, not exploitable. No action required.
2. **Source `name` not control-char-stripped** (`remember.py:162`): pre-existing main
   behavior, not introduced by this diff; the name is not on the embedded-text path. Out of
   scope for #336.

No changes required for merge from a security/correctness standpoint.
