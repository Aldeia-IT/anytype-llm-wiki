# Spec Review — Round 2 (post-fix re-review) — #426

**Date:** 2026-06-25
**Reviewers:** spec-architecture-reviewer, infra-reviewer (focused re-review) + lead consolidation
**Spec:** `.aldeia/426-surface-concept-contradictions-in-wiki-lint/spec.md`

## Verdict: APPROVED

Both reviewers independently verified, against the actual code, that **every** R1 finding
(BL-1..BL-6, SF-1..SF-7, SG-a..SG-e) is genuinely resolved in the revised spec — not merely
acknowledged — and that the rewritten §3 introduces no new bug or contradiction.

## Per-finding resolution (all RESOLVED)
- **BL-1** `SYSTEM_PROP_KEYS` defined as a named constant in `types_schema.py`, imported by bootstrap, with a membership assertion + test.
- **BL-2** Reconcile decoupled from `is_upgrade` (runs every bootstrap, gated only on missing-set); all "is_upgrade path" language removed. Verified `is_upgrade` gates only the report block (`bootstrap.py:433`).
- **BL-3** Both live and declared key extraction use the tolerant accessor with `None`-skip (matches `bootstrap.py:273-277`).
- **BL-4** `types_skipped.append` moved into the no-missing/guard branches (type never in both lists); `existing_type_map` key→entry map built; `type_id` resolved with `None` guard.
- **BL-5** `types_reconciled` registered in `_empty_result`; AC#2 asserts it + `test_result_has_required_keys` coverage.
- **BL-6** Monotonic-union guard, name/format-from-declared-schema, and pagination/shape guard all present; the `get_type` read-side live-probe carried into Open Questions as a non-blocking impl/test precondition (design is safe-by-construction).
- **SF-1** Test route ordering (`/types/{id}` GET before `endswith("/types")`; optional `patch_handler`).
- **SF-2** `type_id is None` → `warnings[]` + skip, not raise.
- **SF-3** Version-marker ordering invariant pinned + recovery test. **Verified against code:** both markers (root collection `bootstrap.py:422-424`, WikiLog `:458`) are stamped AFTER the type loop — spec line references accurate.
- **SF-4** MIGRATIONS states re-bootstrap REQUIRED (prerequisite); lint gate + reconcile ship together; broken-UX risk addressed.
- **SF-5..SF-7, SG-a..SG-e** all folded in.

## New-pseudocode correctness (architecture reviewer)
- Monotonic-union arithmetic is correct (`len(union_props) == live_user_count + len(missing)` by construction; the `<` guard is a sound defensive invariant; no double-count possible since `missing = declared − live`).
- `declared_by_key[k]` cannot KeyError (`k ∈ missing ⊆ declared_prop_keys`, same tolerant accessor on both).
- Create path preserved by the branch inversion.
- Mermaid flow maps 1:1 to the pseudocode exits. Mermaid validated to render via `mmdc`.

## Residual (cosmetic SUGGESTIONs — non-blocking)
- **Create-path reporting note** (arch SUGGESTION 1): the abbreviated `... create_type (unchanged) ...` branch must retain the existing `types_created.append(...)` reporting. **Applied inline by the lead** (one-line comment added to the pseudocode).
- **"the marker" singular** (infra cosmetic): there are two post-loop markers (collection + WikiLog); the invariant holds for both. Left as-is — purely editorial, no correctness impact.
- **Serial unbatched GETs** if `WIKI_TYPES` grows to dozens (infra SUGGESTION): non-issue at 6 types. Noted for the future, not gating.

## Disposition
Zero BLOCKING, zero SHOULD-FIX. Spec is implementation-ready. Proceed to finalize (Phase 8) and route to Decide. The one impl/test-phase precondition (live `get_type` read-side probe, BL-6.4) is recorded in the spec's Open Questions and carried forward to the test/impl phase — it is a verification step, not a design blocker.
