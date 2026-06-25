# Spec Review — Round 1 — Surface concept contradictions in wiki_lint (#426)

**Date:** 2026-06-25
**Reviewers:** completeness-reviewer, spec-architecture-reviewer, infra-reviewer, security-reviewer (agent team) + lead consolidation/spot-check
**Spec:** `.aldeia/426-surface-concept-contradictions-in-wiki-lint/spec.md`

## Verdict: NEEDS REVISION

The design is fundamentally sound and well-researched (the replace-not-merge footgun is correctly identified and the gating question is genuinely resolved). The problems are all concentrated in the **§3 bootstrap reconcile** reference implementation, which is under-specified and self-contradictory in ways that would cause silent graph corruption or a non-functional reconcile. This is a precision/altitude problem in one section, **not** a ticket-scope problem — the fix is to tighten §3 + the test plan + the docs sequencing, not to decompose the ticket.

All findings below were cross-checked against the actual code by the lead. Where reviewers' claims were wrong, that is noted.

---

## BLOCKING

### BL-1 — `SYSTEM_PROP_KEYS` is referenced in the union builder but defined nowhere
*Sources: completeness M1, architecture S4, infra I1, security B1 (4-way convergence).*
`spec.md:132` filters live props with `if p.get("key") not in SYSTEM_PROP_KEYS`, but the constant exists nowhere in `src/` (verified) — only as prose (`tag, backlinks, created_date, creator, links`). An implementer must invent it; a wrong spelling either leaks a system prop into the replace-set union (untested round-trip) or filters out a real user prop (silent destruction).
**Fix:** Define `SYSTEM_PROP_KEYS = {"tag", "backlinks", "created_date", "creator", "links"}` as a named module constant in `types_schema.py` (imported by `bootstrap.py`), referenced by both code and spec, with a unit assertion pinning membership. Per research §1/§4 the probe showed system props are auto-preserved when omitted, so the safer framing is: the union is built from live **user** props (those not in `SYSTEM_PROP_KEYS`) + missing declared props; system props are never sent and are auto-re-added by Anytype.

### BL-2 — Reconcile gating is self-contradictory (`is_upgrade` vs unconditional)
*Sources: infra D1, completeness M2, architecture S3 (3-way convergence).*
The §3 pseudocode runs the reconcile unconditionally inside the existing-types loop, but the prose (`spec.md:78-79, 164-166, 236-238`) says it "runs on the `is_upgrade` path." Verified: the type loop (`bootstrap.py:279`) runs on **every** bootstrap; `is_upgrade` (`:265-268`) only gates the `schema_upgrade` *reporting* block (`:433`). If an implementer wraps reconcile in `if is_upgrade:`, then (a) marker-less legacy spaces (`found_version is None` → `is_upgrade=False`) are skipped — exactly the spaces that need it; (b) a fresh property added without a version bump is never reconciled.
**Fix:** State plainly that reconcile runs in the existing-types branch on **every** bootstrap, gated **only** on the per-type missing-set being non-empty (which makes it a no-op when complete). Decouple from `is_upgrade` entirely; remove the "runs on the is_upgrade path" language at `:78-79, 164-166, 236-238`.

### BL-3 — Live-vs-declared key normalization: bare-subscript on two different key fields
*Sources: architecture B1, security B2, infra I1/D3 (3-way convergence).*
`live_prop_keys` reads `p["key"]` (`:125`) while `declared_prop_keys` reads `p["property_key"]` (`:126`), and the union builder bare-subscripts `p["key"]`/`p["name"]`/`p["format"]` on live entries (`:130`). The existing code already defends against this exact field ambiguity with the tolerant accessor `p.get("key") or p.get("property_key")` (`bootstrap.py:273-277`). If `get_type` echoes a key under a different field (or `None`), the set difference miscomputes → a present property reads as "missing" (duplicate in the replace-set PATCH) or a live property is omitted (destroyed).
**Fix:** Normalize both sides through the established tolerant accessor (`p.get("key") or p.get("property_key")`); guard against a `None` key (skip/raise on a malformed entry — never include it in `live_prop_keys`). Reuse the idiom already at `bootstrap.py:273-277`, do not invent a new bare-subscript convention.

### BL-4 — §3 mis-describes the existing-types branch; `type_id` map + `types_skipped` placement
*Sources: architecture B2, security S1, completeness A2.*
Two concrete code-shape errors:
1. The spec says "replace the bare `continue`" (`:117`), but the branch is **not** bare — it appends to `types_skipped` first (`bootstrap.py:281-285`). If literally replaced, a reconciled type lands in **both** `types_skipped` and `types_reconciled`, contradicting the spec's own decision flow + AC#2. The `types_skipped.append(...)` must move into the *no-missing* branch.
2. `type_id` resolution: `spec.md:110-111,122` says resolve from the `list_types` result. Verified: `existing_types` (the full list of `{id,key,name}` dicts) **is** in scope at `bootstrap.py:271` — but only the derived `existing_type_keys` **set** is currently kept (`:272`), which discards ids. The spec must direct building a `{t["key"]: t for t in existing_types if t.get("key")}` (or key→id) map and resolving `type_id = ...get("id")`, with a `None` guard. (Reviewers said the id is "discarded" — slightly overstated; the source list is in scope, only the derived set drops it. Either way the spec must pin the map construction.)

### BL-5 — `types_reconciled` must be registered in `_empty_result`
*Sources: architecture S2, completeness C2.*
Verified: `_empty_result` (`bootstrap.py:146-162`) enumerates every result key (`types_created`, `types_skipped`, `warnings`, …) and `test_result_has_required_keys` asserts the exact key set. A `types_reconciled` created only inside the loop KeyErrors for any consumer / non-reconciling run.
**Fix:** Add `"types_reconciled": []` to `_empty_result` alongside `types_created`/`types_skipped`. Update AC#2 to assert the `types_reconciled` entry for `wiki_concept` (`properties_added=["wiki_last_reviewed"]`).

### BL-6 — `get_type` REST read-side completeness is unverified; replace-PATCH on a partial read silently drops properties
*Sources: infra F1, completeness M4, infra D3, security S2/S3.*
The gating probe (research §1) exercised `API-update-type` via the Anytype MCP and verified the **write** contract (replace-not-merge, idempotent re-link). It did **not** transcribe the **read** side: that the raw `GET /v1/spaces/{id}/types/{type_id}` returns a *complete, non-paginated* `properties[]` with `name` + `format` on each entry. `get_type` as specified (`:88-93`) is a single `c.get` with no pagination loop (unlike every other list helper, which routes through `_paginated_get`). If the live `properties` array is ever truncated/paginated, a real user property is omitted from the union and **destroyed** on the replace-PATCH — the exact corruption the design exists to prevent. The union also bare-reads `p["name"]`/`p["format"]` from the live echo, which the REST docs do not guarantee are present.
**Fix (design-level, removes the dependency on the unverified detail):**
1. **Monotonic-union guard (hard invariant):** never issue `update_type` if the computed union's user-prop count is **less than** the live user-prop count (`len(union_user_props) < len(live_user_props)` → abort that type's reconcile and append a `warnings[]` entry). A union that would *shrink* the live set is always a bug.
2. **Source `name`/`format` from the declared schema (or `list_properties`, which carries `format` — see `test_bootstrap.py:51`) where a key overlaps**, rather than trusting the live echo to carry them; fall back `name = p.get("name") or key`.
3. **Pagination/shape guard:** if `get_type` returns a `pagination.has_more is True` (or no `properties` key on a known-non-trivial type), treat as a malformed/partial read and abort that type's reconcile with a warning — do not PATCH.
4. **Residual verification (carry into impl/test phase):** the impl/test phase MUST verify `get_type` against a live bootstrapped wiki type (the `wiki-validation-throwaway` space) and record the exact per-property field set + pagination behavior in research.md before the reconcile ships. The design above is safe regardless, but this closes the empirical gap. *(The lead has Anytype MCP access; this is a live-probe the impl lead can run — it is not a blocker on an upstream capability.)*

---

## SHOULD-FIX

### SF-1 — `get_type` test route collides with the existing list-`/types` router
*Sources: infra D2, completeness A5.*
`_install_success_routes` GET router matches `path.endswith("/types")` and returns `{"data":[...], "pagination":...}`. A `GET /types/{type_id}` falls through and returns the wrong shape → `get_type` KeyErrors on `["type"]`. The new `/types/{type_id}` route must be matched by `"/types/" in path` (trailing segment) **ordered before** the `endswith("/types")` list route, returning `{"type": {...}}`. Likewise add the `patch_response` route carefully so it does not clobber existing tests that set their own `respx.patch()` capture (prefer an optional `patch_handler` param, or scope it to the new reconcile tests).

### SF-2 — `type_id is None` guard: specify the action
*Sources: completeness A3, infra F3.*
The spec mandates a guard (`:243-244`) but not the behavior. Specify: if `type_id` is `None` for a type with missing declared props, append a `warnings[]` entry (the result dict already carries `warnings` — `bootstrap.py:161`) and skip that type; do **not** raise. A reconcile that *should* have run but couldn't must be visible in the result.

### SF-3 — Partial-reconcile recoverability depends on an unpinned ordering invariant
*Source: infra F2.*
The spec claims partial reconcile is recoverable on re-run (`:245-248`) but doesn't pin why. The schema-version marker is stamped *after* the type loop (`bootstrap.py:422`), so a mid-loop failure leaves `is_upgrade` true and re-run retries. **Fix:** state this invariant explicitly ("the version marker MUST be stamped only after the reconcile loop completes for all types; each per-type reconcile is independently idempotent"). Add a test: `update_type` raises on the 2nd type → error propagates, version marker NOT stamped, clean re-run completes the remaining type.

### SF-4 — Migration sequencing: re-bootstrap is REQUIRED, not optional, and the lint gate ships independently of the schema
*Source: infra M1.*
The lint-gate change surfaces concept contradictions as `critical` regardless of whether `wiki_last_reviewed` exists on `wiki_concept`. An existing space that runs the new `wiki_lint` **without** re-bootstrapping would fire `critical` with no field to resolve it — the broken UX the spec set out to avoid (problem statement #1). **Fix:** MIGRATIONS.md must state re-running `wiki_bootstrap` is **required** (not optional) and is a prerequisite for the new lint behavior to be resolvable; sequence the rollout so the lint gate and bootstrap reconcile ship together; make the migration note prominent. (Optional: have lint emit a guidance warning when `wiki_concept` lacks the `wiki_last_reviewed` field — note as a consideration, not mandatory.)

### SF-5 — Reconcile loop scope (all WIKI_TYPES vs only wiki_concept) is ambiguous
*Source: completeness A1.*
The pseudocode iterates all `WIKI_TYPES`; the motivation sentence names only `wiki_concept`. Clarify the loop is intentionally general (all 6 types) so future schema additions benefit; for the 0.4.1→0.4.2 upgrade only `wiki_concept` has a missing property.

### SF-6 — AC#3 (docs) has no verifiable check; AC#1 under-specifies the asserted fields
*Source: completeness C3, C1.*
AC#3 is prose-only. Add a substring-absence test (`"not yet flagged" not in README.read_text()`) OR explicitly mark it a manual-review gate with the three concrete checks enumerated. AC#1: tighten to assert `check == "contradiction_unresolved"` and `severity == "critical"` in `result["findings"]`.

### SF-7 — `update_type` defensive guard against an empty `properties` payload
*Source: security SG3, partial.*
A `{"properties": []}` PATCH would, under replace-not-merge, wipe all user props. `update_type` (or the caller) should refuse an empty/None `properties` list defensively even though the caller never intends to send one. (Folds together with BL-6's monotonic guard.)

---

## SUGGESTION

- **SG-a (completeness E5):** Document that of the three `test_reconcile_*` tests, only `test_reconcile_adds_missing_property` and `test_reconcile_never_drops_existing_properties` fail-first; `test_reconcile_no_op_when_complete` passes against the current (unimplemented) code and is a forward regression guard. Keep it, but label it.
- **SG-b (completeness A4):** The existing `_make_concept` (`test_lint.py:167`) uses `wiki_description`; `wiki_concept` schema uses `wiki_definition`. Pre-existing harmless inconsistency — note it so the test-writer doesn't propagate or "fix" it blindly.
- **SG-c (completeness E2):** Declare format-mismatch correction on existing properties explicitly out of scope (reconcile only adds missing keys).
- **SG-d (completeness E3 / security):** Add a one-line note that a property shared across types (e.g. `wiki_last_reviewed` already linked to `wiki_entity`) is correctly handled — the union re-sends the key and Anytype links the existing space-level property (research §1 step 3), no duplicate.
- **SG-e (security SG1):** Consider an INFO-level log of the computed union before each `update_type` PATCH, for post-hoc audit given the blast radius.

---

## Corrections to reviewer claims (lead spot-check)
- **Completeness M3** (claimed `assert WIKI_SCHEMA_VERSION == "0.4.1"` at `test_bootstrap.py:868`): **NOT FOUND.** No hardcoded `0.4.1` assertion exists; version tests compare dynamically to the `WIKI_SCHEMA_VERSION` symbol (`test_bootstrap.py:711`). M3 is dropped — but the fixer/test-writer should still grep to confirm no test hardcodes the old version before the bump.
- **BL-4 nuance:** `existing_types` is in scope at `bootstrap.py:271` (the id is available); only the derived `existing_type_keys` set discards it. The fix is to keep a key→id map, not to re-fetch.

---

## Disposition
All BLOCKING and SHOULD-FIX items must be addressed (per phase-spec Phase 5: every finding is fixed unless deferral is justified). Dispatch a fresh spec-fixer to revise §3 (the bulk of the work), the Test Plan, the Docs/migration section, and the ACs. Re-review after the fixer. BL-6 item 4 (live `get_type` probe) is carried forward as an explicit impl/test-phase precondition recorded in the spec, since the design is made safe-by-construction here.
