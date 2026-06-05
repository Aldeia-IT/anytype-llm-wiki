# Spec Review R2 — anytype-llm-wiki v0.6.0 contradiction detection (#287)

**Date:** 2026-06-05
**Reviewer:** lead re-review (round 2), verified against real code in `src/anytype_llm_wiki/wiki/` + `src/anytype_llm_wiki/anytype_client.py` and `tests/wiki/`
**Spec:** `.aldeia/287-anytype-llm-wiki-v0-6-0-automated-contradiction-de/spec.md` (619 lines, 14 ACs)
**Prior review:** `review-r1.md` (7 BLOCKING, 6 SHOULD-FIX, 3 SUGGESTION)
**Verdict:** **NEEDS REVISION** — 1 BLOCKING, 2 SHOULD-FIX, 2 SUGGESTION.

The fix round resolved 6 of 7 R1 blockers cleanly and all SHOULD-FIX/SUGGESTION items.
However, the BL-3 fix ("read target relations/contradictions from the in-memory
`target` dict") reached for the **wrong helper** — `_existing_text`, which only reads
text-format properties — and pairs it with `_parse_relation_elements` in a way that
cannot compile/run. This is a new, genuine implementability blocker introduced by the
fix itself. It is a tight, one-section correction.

---

## R1 BLOCKING re-verification

| R1 | Status | Evidence |
|---|---|---|
| **BL-1** read_client never constructed | **RESOLVED** | §3.1/§3.2/§3.3/§3.4/§8-step7 all consistently construct `AnytypeReadClient()` in `_run_ingest` under `try/finally: close()` and thread it into both functions. Verified `AnytypeReadClient` lives in `src/anytype_llm_wiki/anytype_client.py:13`, has `get_object` (line 44) and inherits `close()` (`wiki/_base_client.py:76`). Import path `from ..anytype_client import AnytypeReadClient` matches `lint.py:39` / `query.py:40`. |
| **BL-2** must be `str.replace()` not `.format()` | **RESOLVED** | §3.3 mandates `str.replace()` with sentinel tokens `{{NEW_CLAIM}}`/`{{CANDIDATES}}` (lines 166-168, 190-197) and the OSError fallback uses the same tokens (lines 213-214). Matches real code: `extraction.py` uses `.replace()` exclusively (lines 161, 242-245); no `.format()`. Consistent. |
| **BL-3** target facts/relations source incoherent | **PARTIALLY FIXED → new BLOCKING (see BL-3-RESIDUAL)** | The "no target GET; read from in-memory `target`; `get_object` peer-only" decision is now stated consistently across §3.2/§3.3/§3.4/§3.8/§4. BUT the *mechanism* prescribed for reading objects-format props from `target` is wrong (uses `_existing_text`). |
| **BL-4** wrong passive-note test named | **RESOLVED** | §7 adds the grep instruction and names both real sites. Verified: `test_lint.py:897 test_contradiction_check_passive` does NOT assert the note (asserts the finding fires) — spec correctly says rename + add "no PASSIVE" assertion. The real note assertion is `test_wikilog_receipt_written_on_clean_run`, `assert any("passive until v0.6.0" in str(n) ...)` at `test_lint.py:1786-1788` (def at 1740) — spec's "~1782-1788" is accurate. lint.py line refs (79-83, 172, 429, 20-22, 211-214) all verified correct. |
| **BL-5** `test_live.py` nonexistent | **RESOLVED** | `tests/wiki/test_live.py` confirmed absent. AC-8/AC-9 now target `tests/wiki/test_ingest.py` with `@pytest.mark.live`; the live block exists at `test_ingest.py:1094+` (markers at 1097, 1167). No residual `test_live.py` reference anywhere in the spec. |
| **BL-6** both `_create_source` call sites unpack tuple | **RESOLVED** | `grep -n "_create_source(" src/` returns exactly two callers: `ingest.py:477` and `ingest.py:510` (def at 613) — exactly the two sites §3.6/§8-step2 update. Spec line refs match the real file. |
| **BL-7** `ollama_base` undefined | **RESOLVED** | §3.3 derives `ollama_base = (os.environ.get("WIKI_EXTRACT_ENDPOINT") or _ollama_url()).rstrip("/")` inside the function (line 152). Matches `extraction.py:172,236`. |

**6/7 R1 blockers fully resolved. BL-3 is only partially fixed — the directional
decision is correct and coherent, but the concrete helper it prescribes is unusable.**

## R1 SHOULD-FIX re-verification (all resolved)

- **SF-1** RESOLVED — §3.5a shows the hook `try/except` that appends
  `contradiction_detection_degraded`; AC-5 asserts the warning is PRESENT and the
  contrast (no-contradiction) path asserts it ABSENT. `detect_contradictions` raises on
  hard failure (§3.3 step 7) so the three outcomes are distinguishable. Coherent.
- **SF-2** RESOLVED — increment by deduped `links_written` is stated identically in
  §3.4 (return), §3.5, §3.5a, the flowchart, and §6. No residual `len(peer_ids)`.
- **SF-4** RESOLVED — `list_tags` row dropped from the wire table with an explanatory
  note (§3.8 lines 371) telling the test phase not to over-mock it. No dangling
  `list_tags` row remains.
- **SF-5** RESOLVED — preamble required in BOTH `contradiction.md` and the
  `_load_contradiction_prompt()` OSError fallback (§3.3 lines 199-216); AC-10 tests
  both; §5 wording corrected to "peer facts are attacker-influenced LLM-summarized
  source text" (no longer "system-controlled").
- **SF-6** RESOLVED — §5 documents the widened disclosure scope (peer `wiki_facts`
  shipped off-machine) and the consent decision (existing gate sufficient, README note).

## R1 SUGGESTION re-verification (all resolved)

- **SG-1** scrub `{exc}` — DONE (§3.4 uses `type(exc).__name__ + scrub_credentials(...)[:120]`).
- **SG-2** hallucinated-ID invariant — DONE (§3.3 step 6 + AC-11 negative test).
- **SG-3** edge-case ACs — DONE (AC-12 self-ref, AC-13 multi-peer, AC-14 dedup no-op).

---

## BLOCKING

### BL-3-RESIDUAL — `_existing_text` cannot read `wiki_relations` / `wiki_contradictions` (objects-format); §3.3 and §3.4 are unimplementable as written

The BL-3 fix correctly decided to read the target's relations and contradictions from
the in-memory `target` dict (no GET). But it prescribes the **wrong reader**:

- §3.3 step 1 (spec.md:156-160): "Read the target's `wiki_relations` from the in-memory
  `target` dict via `_existing_text(target, "wiki_relations")` … Parse linked peer ids
  via `_parse_relation_elements` (query.py:72)."
- §3.4 step 1 (spec.md:237): "A-side list = `_existing_text(target, "wiki_contradictions")`
  parsed to ids".

Two compounding problems, both verified against the real code:

1. **`_existing_text` only reads text-format properties.** Its body
   (`remember.py:629-642`) returns `p.get("text")` for the matching property, else `""`.
   `wiki_relations` and `wiki_contradictions` are `objects`-format properties whose value
   lives under the `objects` key, not `text`. So `_existing_text(target, "wiki_relations")`
   returns `""` for every real object — the candidate set is always empty and **no
   contradiction would ever be detected**. (Its own docstring: "Read the current
   wiki_facts / wiki_definition text" — it is the facts reader, not a relations reader.)

2. **Type mismatch with `_parse_relation_elements`.** `_existing_text` returns a `str`;
   `_parse_relation_elements` (`query.py:72`) expects the `objects` **array** (a list of
   id-strings/dicts). Passing one to the other is incoherent — these two helpers are
   mutually incompatible for this data, so the spec states the read "two ways" (#140
   risk) that cannot both be true.

**The correct, code-proven pattern is already in the codebase** (`query.py:719-720` and
`query.py:923-924`):
```python
for prop in target.get("properties", []):
    if isinstance(prop, dict) and prop.get("key") == "wiki_relations":
        peer_ids = _parse_relation_elements(prop.get("objects"))
```
i.e. find the property dict by `key` in `target["properties"]`, then feed
`prop.get("objects")` to `_parse_relation_elements`. `_existing_text` should be used
**only** for the text props (target `wiki_facts` / new_facts), which is exactly what LD5
moves it for.

**Fix (concrete):**
- spec.md:156-160 (§3.3 step 1): replace the `_existing_text(target, "wiki_relations")`
  instruction with the by-key lookup + `_parse_relation_elements(prop.get("objects"))`
  pattern above. Keep `_existing_text` for the target's `wiki_facts` only.
- spec.md:237 (§3.4 step 1): same — read A-side existing `wiki_contradictions` via the
  property-by-key lookup + `_parse_relation_elements(prop.get("objects"))`, not
  `_existing_text`.
- spec.md:159 (the parenthetical "remember.py's `_existing_text` already reads facts
  from it") is fine *for facts*, but must not be cited as the relations/contradictions
  reader — correct that sentence so it does not imply `_existing_text` reads relations.
- LD5/§3.1/§8-step1 remain correct as-is (they only move `_existing_text` for the
  facts/definition text path); no change needed there.

Severity rationale: as written, the MVP detection path silently no-ops (empty candidate
set) AND the prescribed helper combination does not type-check — a downstream
implementer following the spec literally ships a feature that never fires. This is the
same class of "internal incoherence / unimplementable as written" that BL-3 was raised
for in R1; the fix moved the incoherence rather than removing it.

---

## SHOULD-FIX

### SF-A — §3.2 flowchart drops the `target` argument from the `detect_contradictions` call
spec.md:114 shows `detect_contradictions(new_facts, obj_id, space_id, client, read_client)`
— missing `target`. The canonical signature (§3.3, spec.md:131-138) and the hook call
(§3.5a, spec.md:282-284) both correctly pass `target` as the 3rd positional arg. The
diagram label is stale. **Fix:** add `target` to the flowchart node at spec.md:114 so the
three depictions agree. (Low risk — canonical signature and hook code are mutually
consistent; only the diagram is out of date.)

### SF-B — confirm Anytype `search` results actually carry populated `properties.objects`
AC-1 (spec.md:484) and §3.8 assume the POST `/search` response returns the target with
`properties` including `wiki_relations`/`wiki_contradictions` `objects` arrays. The
in-memory-only design (no target GET) depends entirely on this. `resolve_entity`
(ingest.py:163-204) returns the raw search-result object, and text props are read off it
elsewhere, but I did not find a code path that reads objects-format `objects` arrays off
a *search* result (the verified `prop.get("objects")` readers in query.py operate on
`get_object` results). **Fix:** add one sentence to §3.3/§3.8 stating the assumption
explicitly ("the search response includes objects-format property arrays") and have the
implementer assert it in the AC-1 fixture; if search omits `objects`, a single target
GET (still peer-pattern, one extra call) becomes necessary and §4's "NO target GET"
claim must be revisited. Flagging as SHOULD-FIX rather than BLOCKING because it is a
verify-at-impl assumption, not a proven defect.

---

## SUGGESTION

- **SG-A** — Incorrect helper citation carried over from R1: §5 (spec.md:443) and the
  R1 SF-5 text reference `sanitize_property_value (util.py:82)`. No such function exists;
  the real function is `strip_control_chars` (util.py:84), and util.py:82 is inside the
  `_CONTROL_CHAR_RE` regex literal. The security reasoning is still correct (it strips
  only control/bidi chars, not NL instructions). Fix the name to `strip_control_chars`
  for accuracy.
- **SG-B** — Minor redundancy: the "no target GET / peer-only" decision is restated in
  §3.2, §3.3, §3.4, §3.8, §4, and the R1 disposition table. This is defensible emphasis
  given it was an R1 blocker, but once BL-3-RESIDUAL is fixed, consider consolidating the
  rationale to §3.3 + the wire table and cross-referencing, to avoid future drift between
  six copies.

---

## Other mandated checks

- **Frontmatter `status: SPEC`** — confirmed (spec.md:3).
- **Declared fields written AND read** — `contradictions_detected`: written in
  `_empty_result` (§3.5) and incremented (§3.5a); read by AC-2/AC-5/AC-13/AC-14 and §6
  Monitoring. `was_resumed`: produced by `_create_source` (§3.6), consumed in WikiLog
  notes (§3.6 step 12 / §8-step3). `links_written` / `rollback_notes`: returned by
  `_write_contradiction_links` and both consumed in §3.5a. All wired.
- **No dangling references to removed elements** — dropped target GET: no residual
  "GET obj_id for wiki_relations" anywhere (grep clean). Dropped `list_tags` row:
  removed from the wire table with a note; not referenced as a contradiction-path mock.
- **New ACs AC-10..AC-14** — each is testable, mapped to a Test Plan row with a named
  test + CI-seam strategy, non-duplicative (preamble / hallucinated-id / self-ref /
  multi-peer / dedup are distinct invariants), and consistent with §3 design. AC-11
  exercises the real `detect_contradictions` (monkeypatch `_call_ollama_prompt`) rather
  than monkeypatching the function under test — correct. No #140 "same fact two ways"
  contradiction introduced by the AC additions themselves (the only #140-class issue is
  BL-3-RESIDUAL in §3.3/§3.4).
- **AC numbering** — AC-1..AC-14 contiguous, no duplicates/gaps.
- **No spec bloat beyond SG-B** — the additions are proportionate to the R1 findings.

---

## Verdict

**NEEDS REVISION** — 1 BLOCKING (BL-3-RESIDUAL), 2 SHOULD-FIX (SF-A, SF-B),
2 SUGGESTION (SG-A, SG-B).

Six of seven R1 blockers and every SHOULD-FIX/SUGGESTION are genuinely and correctly
resolved (verified against code, not merely present). The one remaining blocker is a
narrow, mechanical mis-fix of BL-3: the spec must read objects-format
`wiki_relations`/`wiki_contradictions` from `target["properties"]` via the existing
`_parse_relation_elements(prop.get("objects"))` pattern, not via `_existing_text` (which
reads only text props and returns `""` here). One focused edit to §3.3 step 1 and §3.4
step 1 (plus the SF/SG touch-ups) closes this out.
