# Spec Scope: surface-concept-contradictions-in-wiki-lint (#426)

**Client:** anytype-llm-wiki · **Branch:** `aldeia/426-surface-concept-contradictions-in-wiki-lint`
**Parent epic:** #325 (Contradiction detection: extend to Concepts) — CLOSED/merged. #426 is its
declared closure-condition follow-up (the "Recommended Follow-Up" section of `#325/spec.md`).

## Baseline note (IMPORTANT)
This branch was bootstrapped from a pre-#325 `main`. The lead has **merged `origin/main`** into it,
so the working tree is now the true post-#325 baseline:
- Concept contradiction **detection is LIVE** (`ingest.py:944` — `if kind in ("entity", "concept")`).
- Concept contradiction **surfacing is NOT** — `lint.py:490` still gates `contradiction_unresolved`
  on `tk == "wiki_entity"` only (stale comment "wiki_entity only (SF9)").
- `wiki_concept` schema already carries `wiki_contradictions` but **NOT** `wiki_last_reviewed`
  (the property the lint check uses to mark a contradiction resolved). `wiki_entity` has it
  (`types_schema.py:97`).

## Domains touched
infrastructure, agent-operations (Anytype schema/bootstrap + wiki_lint surfacing). No product UI.

## Estimated complexity: moderate
Three coordinated change sites + a genuinely new bootstrap capability + schema bump + tests + docs.
Not trivial (new idempotent property-link-onto-existing-type capability, unverified API at #325 time),
not complex (each site is small and #325 already specified the blueprint).

## Gating question — RESOLVED by lead live-verification
"Does the Anytype property-link endpoint exist and behave idempotently?" → **YES.** See `research.md`
for the full probe transcript. `API-update-type` adds a property to an already-existing type, BUT it
**REPLACES the user-defined property set** (omitted properties are dropped; system props tag/backlinks
auto-preserved). Therefore the new bootstrap capability MUST be **read-modify-write**: GET the live
type, union its existing user properties with the declared-but-missing ones, send the FULL set.
Re-sending an existing property key **links** the existing space-level property (stable id) — idempotent.
The ticket is **NOT blocked**.

## The four deliverables (from #325 follow-up blueprint, verified against current main)
1. **Schema** (`types_schema.py`): add `wiki_last_reviewed` (date) to `wiki_concept`; bump
   `WIKI_SCHEMA_VERSION` (0.4.1 → next).
2. **New bootstrap capability** (`bootstrap.py` + `wiki_client.py`): idempotently link declared-but-
   missing properties onto already-existing wiki types via read-modify-write `update_type`
   (`wiki_client` has no `update_type` today — must add). Reconciles `wiki_last_reviewed` (+ any other
   missing declared property) onto existing `wiki_concept`/all wiki types.
3. **Lint gate** (`lint.py:490`): `tk == "wiki_entity"` → `tk in ("wiki_entity", "wiki_concept")`;
   fix the stale "SF9" comment. Body unchanged (reads `wiki_contradictions`, resolves via
   `wiki_last_reviewed`, severity `critical`).
4. **Docs**: README `:175` (drop the "concept ... not yet flagged by wiki_lint — a planned follow-up"
   surfacing-gap clause), CHANGELOG entry, MIGRATIONS.md re-bootstrap note.

## Key prior learnings to inject (Mem0 + #325)
- **`get_object` is the proven path** for objects-format relation arrays; do NOT assume Anytype
  *search* responses hydrate them (mem0 8f597af8). Lint already reads via list/get — preserve that.
- **objects-format properties return bare ID strings** (mem0 56845bac) — relevant to any
  contradiction-array reads.
- **`update_type` is replace-not-merge** (lead probe, this ticket) — the central correctness constraint.
- **#325 council pattern** (mem0 a2d84e10): this IS the filed closure follow-up; surfacing has
  user-visible payoff for fleet+Jan who consume via `wiki_lint`, not Anytype browsing.

## CLAUDE.md sections at risk of staleness
No CLAUDE.md in repo. Docs to keep honest: README §175 (surfacing gap), CHANGELOG, MIGRATIONS.md.

## Test surface
- `test_lint.py`: extend `_make_concept` (~157) with `wiki_contradictions`/`wiki_last_reviewed`
  params (mirror `_make_entity` ~117/124); add `test_concept_contradiction_unresolved` mirroring the
  entity test — must FAIL against current `lint.py`.
- `test_bootstrap.py`: cover the new property-reconcile-onto-existing-type path (idempotent; preserves
  existing properties; links only missing ones).
