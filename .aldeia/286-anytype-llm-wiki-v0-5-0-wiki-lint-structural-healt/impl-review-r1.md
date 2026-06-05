# Implementation Review R1 — wiki_lint v0.5.0 (#286)

**Date:** 2026-06-05
**Reviewers:** security+correctness reviewer (agent), quality+spec-compliance reviewer (agent), lead inline checks
**Scope:** `git diff main...HEAD` — `wiki/lint.py` (NEW), `wiki/config.py`, `wiki/cli.py`, `server.py`,
`.env.example`, `README.md`, `CHANGELOG.md`

## Verdict: **APPROVED** (0 BLOCKING, 0 SHOULD-FIX, 2 SUGGESTION)

Both independent reviewers returned `VERDICT: APPROVED` with no CRITICAL/MAJOR findings. Lead inline checks
concur. Full suite green.

## Test evidence (independently re-run by lead and both reviewers)
- `tests/wiki/test_lint.py -m 'not live'` → **44 passed, 2 deselected**
- `tests/wiki/ -m 'not live'` → **472 passed, 6 skipped, 6 deselected, 2 xfailed**
- Full repo suite (impl-worker) → 558 passed; doctor battery green.

## Checks confirmed (security/correctness)
- **SF11/SF12 data exposure:** object titles → `strip_control_chars(...)[:200]`; `oversized` detail is a char
  count (`description is {n} chars (> {threshold})`), never the raw body; both dynamic error strings
  (`anytype_unavailable` lint.py:230, `lint_sweep_failed` lint.py:501) pass through `scrub_credentials`; tokens
  live only in headers, never in output.
- **Robustness:** malformed `backlinks` (None/dict/scalar) → fallback, no raise (SF10); `_parse_date` guards bad
  dates; per-object `get_object` failure → `warnings[]` + `status="partial"` (SF6); enumeration failure → error;
  `try/finally` closes both clients.
- **Pre-check ordering:** QA#30 `read_patch_decision()` (lint.py:212) returns before either client is constructed
  (223–225) → zero network on failure; QA#25 missing/outdated branches `return` before the Step-10 WikiLog write.

## Checks confirmed (quality/spec-compliance)
- **Single enumeration (CTO-BLOCKING-1):** `list_objects` called exactly once (lint.py:228); `all_objects` feeds
  both `_schema_version_from_objects` and the battery. Lead grep-verified.
- **Reuse (D4):** all mandated v0.4.0 helpers imported and reused (`_parse_relation_elements`, `_fetch_cached`,
  `_resolve_select_tag`, `_cmp_versions`, `_resolve_wiki_action_tag`, `_write_wikilog`,
  `_schema_version_from_objects`, `_object_deeplink`, `indexer.semantic_search_core`); no re-implementation.
- **D1 backlinks** primary/fallback; **SF5** age via `wiki_sources` dereference; **SF9** contradiction entity-only;
  **AC8** duplicate band half-open `[0.70, lint_duplicate_max_score())` with self-exclusion + canonical dedup;
  **AC16** sweep gated on `include_duplicates=True` AND `N<=WIKI_LINT_MAX_OBJECTS`, `potential_duplicates[]`
  populated independently of `severity_threshold`.
- **Addendum item 5 (doc honesty):** README "Linting the wiki" section + server docstring + CHANGELOG + .env.example
  all carry: passive-contradiction caveat, opt-in sweep + truthful "≤60s/≤500 default sweep-off path only" claim,
  compact knob docs with explicit "you do not need to set any of these", honest `pipeline_orphan` ±300s heuristic.
- **Addendum item 6 (double-count legibility):** both `unreviewed_needs_review` and `stale_needs_review` details
  render `object {id} ({title})`.

## Suggestions (non-blocking; recorded, not fixed this round)
- **[SUGGESTION] orphan check is stricter than the master spec definition.** lint.py:377 requires
  `not has_inbound AND not _outbound(o)`; the master spec defines orphan as "no **inbound** relations". An
  entity with outbound-only links + no inbound + an aged source is therefore not flagged `orphan`. This is
  defensible — in a healthy bidirectional wiki such an object also triggers `asymmetric_relation` (Critical), a
  louder signal — and violates no AC or test. Candidate refinement for v0.6.0 if pure-inbound orphan detection is
  desired. Removing the `not _outbound` clause keeps all current tests green.
- **[SUGGESTION/MINOR] client construction outside try.** lint.py:223–225 constructs both clients before the
  `try`; `.close()` is in `finally`. Unreachable in practice (both constructors are lazy, no I/O until first
  request), so no leak occurs. Informational only.

## Disposition
No fix cycle required. Advance to PR preparation.
