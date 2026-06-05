# Council Impl R1 — CTO Review (wiki_lint v0.5.0, ticket #286)

## Verdict

**SIGN OFF WITH ADVISORIES**

Both of my standing veto-lift conditions landed in code and are verified at
file:line. Single-enumeration is hard-enforced and the D1 backlinks primary
path has a correct malformed-fallback. Zero BLOCKING findings. The two
advisories below are residual-risk notes, not gates.

## Findings

### BLOCKING

None.

### ADVISORY

**ADV-1 — D1 live backlinks shape confirmed only against a real space, not in CI.**
- Verified: `_backlinks_inbound` (lint.py:117-127) takes `obj["backlinks"]` as the
  PRIMARY path; non-list / empty / None / dict / scalar all fall through to
  `(False, set())` — malformed never raises (SF10). The CI test battery exercises
  the fallback (test_lint.py:459-460, AC1). The live shape itself is asserted only
  by `test_backlinks_field_shape_live` (test_lint.py:1961-1979), which is
  double skip-gated on `ANYTYPE_SPACE_ID` + `ANYTYPE_BACKLINKED_OBJECT_ID` and
  therefore unexercised in CI.
- Impact: If Anytype's `get_object` returns backlinks under a different key/shape
  than the impl-task-ONE session finding assumed, the primary path silently
  degrades to the O(N) relation-scan fallback. That is a correctness-preserving
  degradation (no crash, no wrong findings — the fallback is the master-spec
  behavior), so the blast radius is performance, not correctness.
- Recommended action: ACCEPT for merge. The fallback fences the risk. Before the
  next release that *depends* on backlink precision, run the skip-gated smoke once
  against Jan's live space and record the result. This is exactly the mitigation I
  asked for post-spec; it is present, just not CI-wired. No gate.

**ADV-2 — Two known non-blocking suggestions carried from in-phase review.**
- orphan check stricter than master (lint.py:377) and client construction outside
  the try block (lint.py:223-225). I reviewed both; neither rises to blocking.
  The orphan strictness is a deliberate, documented heuristic choice; the client
  construction is `AnytypeReadClient()` (no I/O at construction) so the
  pre-check ordering (QA#30 `read_patch_decision` returns at lint.py:212 before
  either client is built) is unaffected. ACCEPT as-is.

## Verified veto-lift conditions (evidence)

1. **Single-enumeration (my post-test BLOCKING) — LANDED.**
   `grep -n list_objects src/.../lint.py` → exactly one call site (lint.py:228),
   inside its own try with `anytype_unavailable` error mapping. The same
   `all_objects` list feeds BOTH `_schema_version_from_objects(all_objects)`
   (lint.py:237, QA#25 gate) AND the battery filter
   `wiki_objects = [o for o in all_objects ...]` (lint.py:260-263). The enum is
   also reused as `enum_map` for the per-run fetch cache (lint.py:289-292). No
   second enumeration anywhere. Constraint satisfied exactly as the spec addendum
   pinned it.

2. **D4 reuse — LANDED, zero re-implementations.**
   `grep "def _parse_relation_elements|def _fetch_cached|def _resolve_select_tag|
   def _cmp_versions|def _write_wikilog|def _schema_version_from_objects|
   def _object_deeplink"` in lint.py → NO matches (none re-defined). All are
   imported and used: `_cmp_versions/_resolve_wiki_action_tag/_write_wikilog` from
   `.ingest` (lint.py:35), `_parse_relation_elements/_fetch_cached` from `.query`
   (lint.py:36), `_resolve_select_tag` from `.remember` (lint.py:37),
   `_schema_version_from_objects/_object_deeplink` via `_bootstrap` (lint.py:237,
   176, 564), `indexer.semantic_search_core` for the opt-in sweep (lint.py:496).
   `get_object` is reached only through `_fetch_cached` (query.py:695) — not
   imported into lint.py directly — which is the correct single-code-path reuse.

3. **D1 backlinks — primary + correct fallback LANDED; live shape unconfirmed.**
   See ADV-1. Primary at lint.py:124-126; fallback-empty re-derivation at
   lint.py:389-391. Residual risk assessed: ACCEPTABLE (degradation, not breakage).

4. **Top-level import path — CORRECT.**
   `from ..anytype_client import AnytypeReadClient` (lint.py:39); class lives at
   `src/anytype_llm_wiki/anytype_client.py:13`, `get_object` at :44. Not under
   `wiki/`. Constructed at lint.py:223. Matches my post-test carry.

5. **Documented spec/test divergence (budget count) — CORRECT CALL.**
   The fixture enumerates `[schema_marker] + 501 wiki_entities` =
   502 in `all_objects` but 501 content objects (test_lint.py:1811-1814 via
   `_make_entity`, which emits `type.key == "wiki_entity"`; the marker is a
   `collection`, excluded by `_CONTENT_TYPES`, per `_standard_mocks` docstring
   test_lint.py:292-295). The test asserts the `"501"` substring
   (test_lint.py:1831). The worker set `pre_filter_count = len(wiki_objects)`
   (lint.py:266) — counting only objects actually linted — which is what makes the
   "501" assertion pass AND is the semantically correct number (the schema marker
   is never linted). The worker correctly did NOT edit the test. Sound.

## Test evidence (my re-runs, this worktree)

```
uv run pytest tests/wiki/test_lint.py -m 'not live' -q
  → 44 passed, 2 deselected   (run 1: 0.92s, run 2: 0.93s, run 3: 0.92s — stable, no flake)

uv run pytest tests/wiki/ -m 'not live' -q
  → 472 passed, 6 skipped, 6 deselected, 2 xfailed   (no regressions in the wiki module)
```

The 2 deselected lint tests are the skip-gated live smoke (end-to-end + ADV-1
backlinks shape) — correctly gated, not silently dropped.

## Reviewer diligence

The in-phase impl review (`impl-review-r1.md`) is **source-grounded, not a rubber
stamp.** It cites concrete file:line evidence throughout (lint.py:228, :230, :212,
:377, :501, :223-225), explicitly states the lead **grep-verified** the
single-enumeration claim against CTO-BLOCKING-1 (review line 30-31), confirms the
SF10 malformed-backlinks fallback, and surfaces — rather than hides — the two known
suggestions with line numbers. The phase summary independently reproduces the
501/502 divergence reasoning and flags the live-smoke residual risk honestly
(phase-summary-impl.md:29-30, 49-51) rather than hedging it away. Diligence
standard met.

## Rationale

This is a clean increment on mature v0.4.0 infra. The one constraint I vetoed on
post-test — single enumeration — is enforced at exactly one `list_objects` call
with the list fanned out to schema gate, battery, and fetch cache. The one
advisory I carried — live backlinks shape — has the mitigation I asked for (primary
path + malformed-fallback + a dedicated skip-gated live assertion), and the only
residual is a performance degradation, not a correctness or safety risk. Tool is
report-only (no mutations), writes one WikiLog receipt, reuses the established
helpers without duplication, and the full wiki suite is green with no regressions.
Nothing here justifies blocking Jan's merge.

— CTO
