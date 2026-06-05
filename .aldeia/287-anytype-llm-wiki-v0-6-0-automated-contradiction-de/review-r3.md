# Spec Review R3 — anytype-llm-wiki v0.6.0 contradiction detection (#287)

**Date:** 2026-06-05
**Reviewer:** focused round-3 verification (BL-3 + minors only), verified against real code in `src/anytype_llm_wiki/wiki/`
**Spec:** `.aldeia/287-anytype-llm-wiki-v0-6-0-automated-contradiction-de/spec.md`
**Closes:** `review-r2.md` (1 BLOCKING BL-3-RESIDUAL, 2 SHOULD-FIX SF-A/SF-B, 2 SUGGESTION SG-A/SG-B)
**Verdict:** **APPROVED**

This was a scoped re-review of the BL-3 fix and the minor items only — not a full re-review.

---

## BL-3 (blocker) — FULLY RESOLVED

**1. Objects-format relations now read via `_relation_ids`, not `_existing_text`.** Verified every site:
- §3.3 step 1 (spec.md:163-172): `_relation_ids(target, "wiki_relations")`, with an explicit warning that `_existing_text` would return `""`. Correct.
- §3.3 step 2 (spec.md:173-177): peer `wiki_facts` via `_existing_text(peer_obj, "wiki_facts")` — text-format, correct use.
- §3.4 step 1 (spec.md:249): `_relation_ids(target, "wiki_contradictions")`. Correct.
- §3.4 step 3 (spec.md:255): `_relation_ids(peer_obj, "wiki_contradictions")`. Correct.
- §3.2 flowchart node H (spec.md:120): `_relation_ids(target,...)`. Correct.
- AC-1 (spec.md:498): asserts `_relation_ids(target, "wiki_relations")` yields `["peer-id"]` from an objects-shaped fixture. Correct.
- Whole-spec grep: `_existing_text` appears only against `wiki_facts`/`wiki_definition` or in cautionary text warning against its misuse. No objects-format prop is read with `_existing_text` anywhere. No residual contradiction.

**2. Helper placement is circular-import-safe — independently confirmed against code:**
- `util.py` imports only `from . import config` (util.py:24); no sibling imports. Valid base module.
- `ingest.py` does NOT import from `query` (grep clean) — so `ingest` importing the readers from `util` is sound.
- `query.py` imports from `ingest` (query.py:38) — confirms the circular hazard, so the spec's re-export direction (`query` re-imports from `util`) is the correct resolution.
- `_parse_relation_elements` is currently defined at query.py:72 (verified). The only test importer is `test_query.py:2260`, wrapped in `try/except ImportError` with a `pytest.skip` fallback — the re-export `from .util import _parse_relation_elements` keeps the symbol importable from `query`, so the test runs (does not skip). No breakage.
- The proven runtime pattern (`query.py:716-720` `_neighbor_ids_of`: find prop by `key`, feed `prop.get("objects")` to `_parse_relation_elements`) is exactly what `_relation_ids` codifies. Coherent.

**3. Original bug confirmed real.** `_existing_text` (remember.py:629-642) reads only `p.get("text")` for a matching prop and returns `""` otherwise. For objects-format props (value under `objects`, not `text`) it always returns `""` — the candidate set would always be empty and detection would never fire. The R2 finding was correct; the `_relation_ids` fix is necessary.

**4. LD5 / §3.1 table / §8 step 1 mutually consistent:**
- LD5 (spec.md:68-76): moves both `_existing_text` and `_parse_relation_elements` to `util.py`, adds `_relation_ids`, re-exports from `query`, has `remember`+`ingest` import from `util`. The load-bearing reader distinction is stated explicitly (line 76).
- §3.1 table (spec.md:96-101): util.py / query.py / ingest.py / remember.py rows all match LD5.
- §8 step 1 (spec.md:551): identical move + re-export + import plan; names `test_remember/query/ingest` verification.
- Line refs verified: `_existing_text` def at remember.py:629; its internal use at remember.py:450 (kept working by the new `from .util import _existing_text`); `_parse_relation_elements` def at query.py:72.

## Minor items — ALL CLOSED

- **SF-A (flowchart `target` arg):** §3.2 node I (spec.md:121) now reads `detect_contradictions(new_facts, obj_id, target, space_id, client, read_client)` — `target` present, matching the canonical signature (§3.3) and hook call (§3.5a).
- **SF-B (AC-1 objects-shaped response):** AC-1 (spec.md:498) now states the search response must carry objects-shaped `properties` with the `wiki_relations` prop's `objects` array populated, and the fixture MUST populate it. Closed.
- **SG (sanitizer citation):** §5 (spec.md:457) reads `sanitize_property_value (extraction.py:323, which delegates to strip_control_chars at util.py:82)`. Both verified: `sanitize_property_value` def at extraction.py:323 delegating to `strip_control_chars` (extraction.py:327); `strip_control_chars` def at util.py:82. Citations accurate.

## Additional checks

- **No NEW contradiction introduced:** full-spec grep of `_existing_text` / `_relation_ids` / `_parse_relation_elements` shows consistent, correct binding throughout. No dangling reference to a removed element.
- **Frontmatter:** `status: SPEC` (spec.md:3). Confirmed.

---

## Verdict

**APPROVED.** BL-3-RESIDUAL is fully and correctly resolved (verified against code, not merely present): objects-format `wiki_relations`/`wiki_contradictions` are read via the new `_relation_ids` helper everywhere, `_existing_text` is confined to text-format props, and the move/re-export plan is circular-import-safe and test-safe. SF-A, SF-B, and the SG sanitizer citation are closed. No new contradictions; frontmatter intact. The spec is implementable as written.
