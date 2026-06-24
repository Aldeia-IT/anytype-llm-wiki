# Spec Review R2 — Contradiction Detection: Extend to Concepts (#325)

**Date:** 2026-06-18
**Reviewer:** chief-technology-officer (scoped re-review of R1 resolutions + new change sites); lead consolidation + verification + scope decision.
**Spec under review:** `.aldeia/325-contradiction-detection-extend-to-concepts/spec.md` (post-R1-fix, incl. lead CS-9 refinement)

## Verdict: NEEDS REVISION → resolved by lead scope decision (re-scope, not re-fix)

R2 confirmed every R1 resolution is correctly anchored and internally consistent, with the SF-1/SF-2 stub list complete (6 stubs: 1319/1388/1452/1524/1765/1899), CS-9 asymmetry endorsed, and CS-1..CS-6 verified clean. It surfaced **one new BLOCKING** (BL-R2-1) that invalidates the *mechanism* of the BL-1 surfacing fix — and, on the lead's analysis, reveals that the surfacing piece is out of proportion to this ticket's confined scope.

## BLOCKING (R2)

### BL-R2-1 — CS-7's "re-run bootstrap to provision the property" mechanism does not work on existing spaces. [CTO; lead-verified]
Verified directly against `src/anytype_llm_wiki/wiki/bootstrap.py`:
- Lines 281-285: for any `type_key` already present, the loop `continue`s and **skips `create_type` entirely**. `create_type` (286-302) is the **only** path that links inline properties to a type.
- Lines 330-353: the property loop only *reports* created/skipped detached properties and builds `prop_map`; it **never links a property onto an already-existing type**.
- `wiki_last_reviewed` already exists globally (declared on `wiki_entity`), so on a re-bootstrap it lands in `pre_existing_prop_keys` → reported `properties_skipped: already_exists` (337-344). Nothing attaches it to `wiki_concept`.
- The cited "v0.3.0 precedent" does not apply: v0.3.0 added **tag options to an existing select property** via dedicated `_ensure_*` tag paths — not a new property onto an already-provisioned type. **No code path in this repo adds a property to an existing type.**

**Impact:** On every already-bootstrapped space (i.e. the real aldeia-box wiki), CS-8 lint would flag concept contradictions as `critical` while CS-7 fails to give them a `wiki_last_reviewed` field to mark them resolved — the exact broken UX R1's BL-1 fix intended to prevent. Delivering surfacing correctly requires a **new bootstrap capability**: an idempotent "ensure declared properties are linked onto existing types" step (diff declared-vs-live per type, add missing via the Anytype type/property API — `API-update-type` needs verification). That is genuinely new logic touching the bootstrap path for all types, with its own review surface.

## SHOULD-FIX (R2)
- **SF-R2-1** — `README.md:175` says lint flags contradictions `High`; actual severity is `critical` (`lint.py:500`, `test_lint.py:1197`). The doc rewrite step must say Critical, not propagate High.
- **SF-R2-2** — the `_make_objects_shaped_search_response(kind=)` snippet elides the concept text-key (`wiki_definition`) body line; add it so the implementer doesn't guess.

## SUGGESTION (R2)
- **SG-R2-1** — CS-9 asymmetry (append `:concept` only on the concept path, entity stays bare) is the right call; endorsed.

---

## Lead Decision (scope re-frame, recorded for Decide)

The literal ticket ACs are: (1) concept claim detected + cross-linked via `wiki_contradictions`; (2) entity behaviour unchanged; (3) tests mirror the entity path. **All three are fully satisfied by the core change set CS-1..CS-6 + CS-9 alone** — no schema change, no lint change, no bootstrap change. Concept contradictions are recorded in the graph and browsable in Anytype; they are simply not yet surfaced by `wiki_lint`.

Lint surfacing (CS-7 schema + CS-8 lint gate + the new bootstrap-ensure-properties capability + AC-C11) was an addition beyond the literal ACs, raised in R1 (BL-1) on coherence grounds under the then-believed assumption it was a ~3-line additive change. R2 proves it requires a new bootstrap capability of materially larger scope and risk than this confined detection extension.

**Resolution:** re-scope #325 to the confined detection + cross-linking extension (CS-1..CS-6, CS-9), which meets its own acceptance criteria in full. Move lint surfacing (concept `wiki_last_reviewed` + `lint.py` gate + bootstrap ensure-properties-on-existing-type + AC-C11) into a clearly-scoped **recommended follow-up ticket**, documenting the BL-R2-1 bootstrap gap so the follow-up is well-specified. This is a re-scope, not another fix round.

**Flagged for Jan at Decide:** he may (a) accept the confined #325 + a surfacing follow-up (lead recommendation), or (b) pull surfacing back into #325 with the larger bootstrap scope understood. The spec is revised to present the core as shippable and the surfacing follow-up as a documented, optional add — so either decision is one step away.
