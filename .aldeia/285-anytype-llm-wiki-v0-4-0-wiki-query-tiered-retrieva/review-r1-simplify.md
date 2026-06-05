# R1 Simplification / Readability Review — wiki_query (v0.4.0)

**Verdict: APPROVED WITH CONDITIONS**

Scope: `git diff 6975fff HEAD`, primary `src/anytype_llm_wiki/wiki/query.py` (~950 lines)
plus `indexer.py`, `server.py`, `cli.py`, `config.py`, `prompts/synthesis.md`.

This is a readability/simplification pass only. No correctness or security findings
were sought. The code is well-structured: the main `wiki_query` pipeline reads
top-to-bottom with clearly-labelled phases, helpers have tight single
responsibilities, and the security-critical fencing/sanitization is intentionally
explicit. Most apparent "duplication" (e.g. `_fetch_cached` vs
`_refetch_for_writeback`) is a deliberate semantic distinction (cached read-time
fetch vs. uncached write-time fetch) and should NOT be merged.

**Counts:** CRITICAL 0 / MAJOR 0 / MINOR 3

---

## Minor Issues (Consider Fixing)

### MINOR-1 — Dead/unreachable `count < threshold` branch inside the Tier-2 except
- **File:** `src/anytype_llm_wiki/wiki/query.py:528-531`
- **Category:** Simplification (dead branch)
- **Description:** The `except` block at line 527 is only reached from inside the
  `if tier2:` block (line 506). `tier2` is `count >= threshold` (line 499) and is
  not mutated before the except fires. Therefore `count < threshold` at line 528 is
  always `False` — the branch that sets `retrieval_mode = "index_navigation"` /
  `tier2 = False` can never execute. The author already labelled it
  `# (Unreachable: tier2 implies count>=threshold, but keep guard.)`.

  The Qdrant-down boundary test (`test_qdrant_down_boundary_matrix`,
  `tests/wiki/test_query.py:1022`) confirms this: the `count=199` (below-threshold)
  case reaches Tier-1 via the normal `if not tier2:` path (line 544) — it never
  enters the `tier2` block at all, because `semantic_search_core` is only invoked
  when `count >= threshold`. The raising mock for the 199 case never fires. Only
  the `count=200` case exercises the except, and it takes the `else` (error) arm.

- **Recommended simplification:** Collapse the except to its only reachable arm. The
  `if/else` and the dead `tier2 = False` re-assignment can go:

  ```python
  except Exception as exc:  # noqa: BLE001 — Qdrant down
      result["status"] = "error"
      result["error"] = f"{_API_ERROR_PREFIX} qdrant_unavailable"
      result["error_category"] = "api_error"
      result["wiki_log_id"] = _wikilog(
          write_client, space_id, safe_question, 0,
          "vector_augmented", False,
          notes_override="query: error qdrant_unavailable, vector_augmented",
      )
      _attach_log_deeplink(result, space_id)
      return _log_error(result)
  ```

  This removes a branch that can mislead a reader into thinking Tier-2→Tier-1
  silent fallback happens here (it does not; the silent fallback is structurally a
  Tier-1-from-the-start path). No behavior change, no test impact. The unused
  `exc` binding can also be dropped if the message doesn't interpolate it (it
  currently doesn't).
  - **Note:** This is purely cosmetic. The branch is harmless and the author kept
    it as a defensive guard. Leaving it is acceptable; the comment already
    documents the dead-ness. Flagged at MINOR because removing it genuinely
    reduces reader confusion about where the silent fallback lives.

### MINOR-2 — `status` tracked in both a local and `result["status"]`, reconciled at the end
- **File:** `src/anytype_llm_wiki/wiki/query.py:502, 604, 666-672`
- **Category:** Readability
- **Description:** A local `status` variable ("ok"/"partial") is maintained
  alongside `result["status"]`, then reconciled in a final `if status == "partial"`
  block (lines 669-672). The local is only ever set to `"partial"` (line 604 on
  fetch failure, line 667 on file-back partial); it is otherwise the initial "ok".
  The trailing reconciliation is a small extra indirection a reader must hold in
  mind across ~170 lines.
- **Recommended simplification:** This is borderline and could be left as-is. If
  touched, the two `status = "partial"` assignments could write
  `result["status"] = "partial"` directly (the earlier zero-candidate/error returns
  set `result["status"]` explicitly and return before reaching here, so there is no
  clobber risk), eliminating the local and the final reconciliation block. Verify
  no early-return path leaves `result["status"]` as the default "ok" when it should
  be "partial" — none currently do, because partial only matters on the success
  tail. Low value; flag only if the file is already being edited.

### MINOR-3 — Local imports inside functions
- **File:** `src/anytype_llm_wiki/wiki/query.py:99` (`_ollama_base`), `:208`
  (`_build_synthesis_prompt` imports `pathlib.Path`), `:237`
  (`types_schema_text_keys` imports `WIKI_TEXT_PROPERTY_KEYS`)
- **Category:** Readability (minor)
- **Description:** Several imports are function-local. `from pathlib import Path`
  inside `_build_synthesis_prompt` (line 208) has no plausible cycle reason and
  would read more cleanly at module top. The `root_config` and
  `WIKI_TEXT_PROPERTY_KEYS` locals may be deliberate cycle-avoidance / lazy-load —
  if so they should stay.
- **Recommended simplification:** Hoist only `from pathlib import Path` to the
  module header. Leave the others if they break an import cycle (verify before
  moving). Trivial; non-blocking.

---

## Explicitly NOT Flagged (assessed and rejected as findings)

- **`_fetch_cached` vs `_refetch_for_writeback`** — look similar but are
  intentionally distinct: one is cached read-time, the other an uncached
  fresh write-time read (SF4 staleness guard). Merging would weaken a correctness
  guard. Not a finding.
- **Repeated `except (httpx.HTTPError, KeyError, ValueError, TypeError)` tuples in
  `_maybe_file_back`** — each guards a distinct best-effort write with a distinct
  warning string; consolidating would obscure which write failed. Not a finding.
- **Two zero-candidate blocks (lines 553-563 and 606-616)** — distinct
  preconditions (no candidates enumerated vs. all candidate fetches failed) with
  different status semantics ("ok" vs. "partial"). Not duplicate logic.
- **`_build_synthesis_prompt` rebuilds context while `_build_context` /
  `_truncate_object_content` already shaped objects** — the prompt builder reads
  the already-truncated objects; no redundant re-fetch. Not a finding.
- **`_wikilog` repeated call sites with `notes_override`** — each carries a
  path-specific receipt note; the helper already centralizes the write. Fine.
- **Constants without "why this number" comments** (thresholds, caps) — suppressed
  per review-impl-reference (tuning constants).
- **`indexer.semantic_search_core` extraction** — clean DRY win (server.py now
  delegates); the nested AND-of-OR filter is documented and necessary. Good.

## Summary

| Category    | Count | Priority |
|-------------|-------|----------|
| Complexity  | 1 (MINOR-1) | Low |
| Readability | 2 (MINOR-2, MINOR-3) | Low |
| Redundancy  | 0 | — |
| Patterns    | 0 | — |

No simplification hides a bug. All three findings are non-blocking and safe to
defer. The strongest candidate is MINOR-1 (delete the documented-unreachable
branch) purely to reduce reader confusion about where Tier-2→Tier-1 fallback
occurs.
