# Implementation Review R1 — Concept Contradiction Detection (#325)

**Date:** 2026-06-24
**Reviewers:** security-reviewer, dry-checker, code-simplifier, performance-checker (agent team) + lead inline checks
**Diff under review:** `5e66d82..ed99e14` (5 impl commits)
**Verdict:** APPROVED WITH CONDITIONS

The production change (`ingest.py`) is clean, minimal, and matches the approved spec verbatim
(CS-1..CS-6, CS-9). Entity behaviour is byte-for-byte preserved. All findings are in **test
code** (maintainability polish) plus one trivial docstring/comment nit. No CRITICAL/BLOCKING.

---

## Lead inline checks (all PASS)

- **Entity preservation (AC-2):** `detect_contradictions` default `kind="entity"`; gate widened
  to `in ("entity", "concept")`; degraded warning stays the bare string on the entity path
  (CS-9 appends `:concept` only for non-entity). Entity assertions unchanged. ✓
- **CS-9 logic** matches the spec snippet exactly. ✓
- **`_facts_key_for_peer`** returns from a closed 2-key allowlist with safe `wiki_facts`
  default — no arbitrary-property read. ✓
- **Wire contract:** peer text still read via `read_client.get_object` (no target GET). ✓
- **Tests:** 10 concept tests (AC-C1, AC-C3..C10) + QA-ADV-1 clean-path negative present;
  full suite 709 passed / 37 skipped / 2 xfailed (lead re-ran). ✓

## Specialist findings

### Security — CLEAN (0 findings)
Concept `wiki_definition` text flows through the identical anti-injection preamble + JSON-escaped
candidate channel as entity text; `kind` only selects the read key, not prompt shape. No new
trust boundary, credential path, or unsanitized interpolation (`f":{kind}"` uses a code-constrained value).

### Performance — CLEAN (0 new findings)
New per-peer work is two O(1) dict lookups in `_facts_key_for_peer`, negligible vs. the network
`get_object` that dominates each iteration. Unbounded fan-out is the documented SG-1 deferral, not enlarged by #325.

### DRY
- **MAJOR-1 (FIX):** AC-C6 (`test_concept_dedup_no_op`, ~2442) and AC-C9
  (`test_concept_multiple_peers_contradict`, ~2677) hand-build the search response inline,
  bypassing `_make_objects_shaped_search_response`. Risk: silent divergence from the fixture if
  the wire contract changes, masking regressions. Fix: AC-C6 → pass
  `existing_contradictions=[peer_id]` to the fixture; AC-C9 → extend the fixture to accept
  multiple peer ids and call it.
- **MINOR-1 (FIX):** fixture `kind` ternaries (`test_ingest.py:1192-1195`, `1223-1224`) re-encode
  the `_REL_KEY_BY_KIND` / `_TEXT_KEY_BY_TYPE_KEY` mapping a third time. Collapse to reference the
  production constants or a small shared `_kind_attrs(kind)` test helper.
- **MINOR-2 (DEFER — see below):** JSON-parse boilerplate repeated 10× in new tests.
- Two-helper split (`_TEXT_KEY_BY_TYPE_KEY` vs `remember.py:_type_for_kind`) confirmed
  **deliberate** with adequate symmetric cross-reference comments — not a defect.

### Simplifier (all MINOR)
- **MINOR-1/MINOR-2 (FIX):** same fixture-ternary duplication as DRY MINOR-1 — shared `_kind_attrs` helper.
- **MINOR-4 (FIX):** `_TEXT_KEY_BY_TYPE_KEY` block comment (7 lines) over-long; trim to ~3 lines
  keeping the "MUST update BOTH" cross-reference.
- **MINOR-3 (DEFER):** CS-9 warning built via mutable reassignment vs a ternary — functionally
  identical; keep matching the approved spec snippet verbatim.
- **MINOR-5 (DEFER):** `Protocol` for fake-fn signatures — test convention, no value.

### Lead nit (FIX)
- `detect_contradictions` docstring rewrap orphaned the word "contradiction" onto its own line
  ("Returns [] when no\n contradiction\n is found"). Reflow to read cleanly.

---

## Conditions to resolve (impl-fixer)

1. DRY MAJOR-1 — refactor AC-C6 and AC-C9 to use `_make_objects_shaped_search_response`
   (extend it for multi-peer for AC-C9).
2. DRY MINOR-1 / Simplifier MINOR-1+2 — collapse fixture `kind` ternaries via a shared
   `_kind_attrs(kind)` test helper (single source for facts_key/type_key/rel_key).
3. Simplifier MINOR-4 — trim the `_TEXT_KEY_BY_TYPE_KEY` comment to ~3 lines.
4. Lead nit — reflow the `detect_contradictions` docstring line break.

All entity + concept tests must remain green after the fix.

## Deliberately deferred (rationale documented, not defects)

- **DRY MINOR-2 (JSON-parse boilerplate):** a pre-existing file-wide convention (13 prior copies);
  the new tests correctly follow it. Extracting a helper for only the new tests creates
  inconsistency; refactoring all 25 sites is broader than #325. Leave consistent with existing style.
- **Simplifier MINOR-3 / MINOR-5:** functionally neutral; MINOR-3 keeps the code matching the
  approved CS-9 spec snippet.
