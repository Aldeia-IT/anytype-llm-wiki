# Implementation Review R1 — #426 Surface concept contradictions in wiki_lint

**Date:** 2026-06-25
**Reviewers:** security-reviewer, dry-checker, code-simplifier, performance-checker (agent team) + lead inline checks
**Diff under review:** `git diff 4efca25..HEAD -- src/ docs/`
**Verdict:** APPROVED WITH CONDITIONS — no correctness/security/perf defects; readability fixes for safety-critical code requested.

## Verification status (lead inline checks)
- Full wiki suite green independently re-run by lead: **611 passed, 14 skipped, 2 xfailed**.
- Source diffs spot-checked against spec §1–§5: faithful transcription.
- All four BL-6 guards present; `update_type` ValueError refusal present (addendum item 6).
- httpx errors propagate (narrow `except (KeyError, TypeError)`) → ordering-invariant test holds.
- Docs honor both addenda (README "not yet flagged" removed; MIGRATIONS un-clearable-critical warning; deploy-runbook + durable audit log).

## Findings

### Security (LOW risk — 0 CRITICAL, 0 MAJOR)
- **S-MINOR-1** (`bootstrap.py` union build): union iterates raw `live_props` list, not the
  deduped key-set; a duplicated live key inflates both sides of the monotonic guard
  symmetrically. **Not a data-loss path** (every live key still present). Optional dedup.
- **S-MINOR-2** (per-type resilience): a PATCH HTTP error aborts the whole bootstrap run.
  Verified to be the **correct fail-safe trade-off** (idempotent re-run recovers); no change.
- **S verifications:** httpx propagation correct; SG-e audit log before every PATCH; lint gate
  has no injection/trust issue. No action.

### DRY (0 CRITICAL, 0 MAJOR)
- **D-MINOR-1**: tolerant dual-key accessor `p.get("key") or p.get("property_key")` repeated
  across 8 call sites (4 new + 4 pre-existing); no shared helper exists. → consolidate into a
  `_prop_key` helper (also addresses Simplifier MINOR-1).

### Simplicity / readability (0 CRITICAL, 2 MAJOR, 3 MINOR)
- **C-MAJOR-1** (`bootstrap.py:532-534`): overlapping `isinstance(live_type, dict)` checks across
  the `try/except` and the pagination guard, plus a confusing double `pag =` assignment. Fold the
  non-dict/missing-`properties` shape check into the malformed-envelope handling; leave the
  pagination guard to handle only `has_more`. **Preserve all abort behavior** (warn + skip + no PATCH).
- **C-MAJOR-2** (`bootstrap.py` `_reconcile_existing_type` signature): redundant `type_key`
  parameter (always `type_def["type_key"]`) creates a latent mismatch risk. Derive it inside the
  function; drop the parameter.
- **C-MINOR-1**: walrus-in-comprehension readability → use the new `_prop_key` helper.
- **C-MINOR-2** (`bootstrap.py:586`): monotonic-union guard conflates empty-payload and shrinkage
  invariants; the warning text only mentions shrinkage, so an empty-union abort logs a misleading
  message. Split into two guards with accurate messages.
- **C-MINOR-3** (`wiki_client.py:38`): unreachable `isinstance(type_def, dict)` branch in
  `update_type`; simplify to a plain `.get("properties")` with a clarifying comment.

### Performance (PASS — 0 blocking)
- 6 GET + ≤6 PATCH per bootstrap, bounded by `len(WIKI_TYPES)`; fresh-GET-per-type is the correct
  read-modify-write tradeoff. Lint gate extension is O(1) per object, no new I/O. No action.

## Disposition
All findings are readability/auditability or optional robustness — **none block correctness,
security, or performance**. Because this is destructive-PATCH safety-critical code where
readability == auditability, the lead dispatches an impl-fixer to apply C-MAJOR-1, C-MAJOR-2,
C-MINOR-1/2/3 and the `_prop_key` consolidation (D-MINOR-1), and to add the optional S-MINOR-1
dedup. S-MINOR-2 and the perf note are accepted as-is (correct trade-offs). All existing tests
MUST remain green and no guard may be weakened.
