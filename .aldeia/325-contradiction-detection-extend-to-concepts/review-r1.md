# Spec Review R1 — Contradiction Detection: Extend to Concepts (#325)

**Date:** 2026-06-18
**Reviewers:** chief-technology-officer (technical/codebase), qa-director (AC coverage/test/regression), infrastructure-lead (ops/resource); lead consolidation + spot-checks.
**Spec under review:** `.aldeia/325-contradiction-detection-extend-to-concepts/spec.md`

## Verdict: NEEDS REVISION

Governing verdict is the most severe across the panel (CTO: NEEDS REVISION; QA: APPROVED WITH CONDITIONS; Infra: APPROVED WITH CONDITIONS). The detection-mechanism extension (CS-1..CS-6) is technically sound and verified accurate against the code, but the spec misses a load-bearing change site (lint surfacing) and states a regression claim that is demonstrably wrong (monkeypatch stub signatures). Both must be fixed before the spec advances.

Lead spot-checks confirmed the two highest-impact findings directly against source: `lint.py:490` gate (BL-1) and the `fake_detect_contradictions` stub signatures at `test_ingest.py:1319,1388` (SF-1/SF-2 below).

---

## BLOCKING

### BL-1 — Concept contradictions are written but never surfaced by `wiki_lint` (missed change site). [CTO; lead-verified]
`src/anytype_llm_wiki/wiki/lint.py:490` gates the `contradiction_unresolved` (Critical) finding to `if tk == "wiki_entity":` (comment: "active; wiki_entity only (SF9)"). The adjacent orphan (line 459) and stale (line 506) checks already use `tk in ("wiki_entity", "wiki_concept")`, so concept objects flow through the loop — only the contradiction surfacing excludes them. A `wiki_contradictions` link written onto a `wiki_concept` (which this spec enables) will never produce a lint finding.

This defeats the ticket's purpose. `README.md:175` defines the feature as "both are cross-linked via `wiki_contradictions` and left for review (`wiki_lint` flags them `High`)." Shipping concept-contradiction *writes* without lint *surfacing* delivers a half-built feature and would make the planned README update overclaim coverage.

**Required fix:** Add a change site. Update `lint.py:490` to `if tk in ("wiki_entity", "wiki_concept"):` and fix the "wiki_entity only (SF9)" comment. Add a spec AC + a test mirroring the entity `contradiction_unresolved` lint test for a `wiki_concept` object.

**Lead discovery — resolution affordance gap (must be addressed in the fix):** `wiki_concept` does NOT currently carry the `wiki_last_reviewed` property. `types_schema.py:89-97` gives `wiki_entity` `wiki_contradictions` (95) AND `wiki_last_reviewed` (97); the `wiki_concept` block (`types_schema.py:101-113`) has `wiki_contradictions` (111) but **no `wiki_last_reviewed`**. The entity lint check resolves a contradiction via `if contradictions and not last_reviewed` (`lint.py:497-503`). Without `wiki_last_reviewed` on concepts, every concept with a contradiction would be flagged with **no way to mark it resolved** — a broken UX.

Therefore the coherent fix requires **adding `wiki_last_reviewed` to the `wiki_concept` type** in `types_schema.py`. This is additive and idempotent (bootstrap "idempotently creates types, properties" per the `types_schema.py` module docstring) — existing concept objects simply have no value (= unreviewed = flagged, the desired default), so it is NOT a data migration, but it IS a schema/bootstrap addition that revises the spec's "no new types/properties, no schema migration" claim. The spec must:
- add `wiki_last_reviewed` to the concept type schema (CS),
- note the bootstrap re-run in `MIGRATIONS.md` (additive property),
- keep the lint write-side `wiki_last_reviewed`-never-touched guarantee intact (detection still never writes it).

**Scope note for Decide:** this pulls the contradiction *surfacing* affordance into a ticket whose literal ACs name only detection + cross-linking. The lead judges this in-scope because the feature (per `README.md:175`) is defined as "cross-linked … and left for review (`wiki_lint` flags them)"; concept writes that can never surface or resolve are an incoherent half-feature. Surfaced here so Jan can veto/split at Decide.

---

## SHOULD-FIX

### SF-1 — Monkeypatch stubs will raise `TypeError` once CS-6 passes `kind=kind`. [QA; lead-verified]
The integration tests monkeypatch `detect_contradictions` with stubs whose signature is `(new_facts, obj_id, target, space_id, client, read_client)` — no `kind` (`test_ingest.py:1319` and `:1388`). After CS-6 makes the real call site pass `kind=kind`, these stubs raise `TypeError`, which is swallowed by the `except Exception` at `ingest.py:925` → tests see `contradiction_detection_degraded` and `contradictions_detected == 0`, silently failing their assertions.
**Required fix:** The spec must instruct that every `fake_detect_contradictions` stub accept the new keyword — add `**kwargs` (or `*, kind="entity"`) to each stub signature. Call this out as the single most likely impl-time breakage.

### SF-2 — AC-2 "9 entity tests pass without modification" is incorrect. [QA; lead-verified]
The claim holds only for the two unit-level tests that call the real function (`test_hallucinated_id_filtered`, `test_self_reference_skipped`). The monkeypatched integration tests will break per SF-1 unless their stubs are touched.
**Required fix:** Correct AC-2 to state that monkeypatch stubs need a one-line signature touch-up (adding the keyword), and that "unchanged" applies only to the real-call unit tests. Keep AC-2 as the regression guard, with the corrected mechanism.

### SF-3 — No real-function coverage of the `wiki_concept → wiki_definition` dispatch branch. [QA]
AC-1 reuses the monkeypatch pattern, so the real `detect_contradictions` never runs for a concept peer; `_facts_key_for_peer`'s `wiki_concept → wiki_definition` branch is asserted only indirectly via the fixture. AC-7 (mixed-kind) only exercises the `wiki_facts` fallback branch.
**Required fix:** Add real-function coverage of the concept-peer→`wiki_definition` dispatch — either make one concept test call the real `detect_contradictions` (not monkeypatched) with a concept peer and assert the prompt's candidate `facts` is drawn from `wiki_definition`, or add a sibling to AC-7 that asserts the concept-peer branch. Assert the value is present AND the wrong-key text is absent.

### SF-4 — Concept mirror omits the multiple-peers case. [QA]
The entity suite has `test_multiple_peers_contradict` (AC-13); the spec's concept mirror has no analogue. The multiple-concept-peers case is the one that would catch a regression where candidates are read from the wrong relation key (`wiki_related` vs `wiki_relations`) while writes still land.
**Required fix:** Add `test_concept_multiple_peers_contradict` (mirror of AC-13). Explicitly document that `test_anti_injection_preamble_present` (AC-10) needs no concept variant because the prompt is shared.

### SF-5 — `_facts_key_for_peer` duplicates `remember.py:_type_for_kind` mapping. [CTO]
`remember.py:226-230` already encodes concept→`wiki_definition`/else→`wiki_facts` (keyed by kind). The new helper re-encodes the same mapping (keyed by type-key). That makes three sites for this rule (`_type_for_kind`, `ingest.py:888-895`, new helper).
**Required fix:** The spec must acknowledge `_type_for_kind` and either (a) reuse a single source of truth (e.g., a `_TEXT_KEY_BY_TYPE_KEY` constant both derive from), or (b) justify why a separate type-key-keyed helper is warranted. A new helper is defensible; silently adding a parallel mapping is not.

### SF-6 — Degraded warning is not kind-discriminated. [Infra Finding 4]
`contradiction_detection_degraded` is identical for entity and concept failures; with concepts in scope the degrade surface roughly doubles and an operator cannot tell which path degraded. Per-peer `get_object` skips (`ingest.py:564-566`) and the `_facts_key_for_peer` fallback are also silent.
**Required fix:** Specify a `kind` discriminator in the warning (e.g., `contradiction_detection_degraded:concept`). Add a brief operational note that per-peer skips / type-key fallback are silent today; capture deeper observability (debug-log on per-peer skip) as a follow-up if not trivially in scope.

---

## SUGGESTIONS (resolve by tightening; defer only with concrete rationale)

- **SG-1 [Infra Finding 1] Unbounded peer fan-out** — a hub object with many linked peers triggers N sequential `get_object` calls + a large LLM prompt. **Pre-existing for entities; #325 inherits, does not enlarge, the risk** (concept `wiki_definition` may skew prompt size larger). **Deferral rationale:** out of #325's confined scope and equal in kind to the existing entity profile. Spec should note it and file/point to a follow-up ticket (cap top-N peers / truncate per-peer text).
- **SG-2 [Infra Finding 2] Silent mis-key fallback** — a concept peer whose `get_object` omits `type.key` falls back to `wiki_facts` and reads empty text (silent false-negative). Tie resolution to SF-6 (visibility).
- **SG-3 [QA SG-1] Empty/absent `wiki_definition` peer** — add one assertion that a concept peer with empty definition does not crash and is not spuriously flagged.
- **SG-4 [QA SG-2] B-side rollback on a concept** — `_write_contradiction_links` is kind-agnostic and locked; the entity suite has no rollback test either (pre-existing debt). Note as known coverage gap, not a #325 requirement.
- **SG-5 [QA SG-3] AC-numbering collision** — new concept tests should carry a distinct tag in docstrings (e.g., `#325 AC-C1`) to avoid conflation with the in-file AC-10..AC-14 docstrings.
- **SG-6 [CTO SG-1 / Infra] Line-ref drift** — several spec line refs are ~10-20 lines off (cosmetic; symbol names are accurate). Add a note to locate by symbol, not line number.
- **SG-7 [CTO SG-2] AC-7 envelope foot-gun** — `_make_peer_get_object_response` returns a `{"object": {...}}` envelope; a unit test that mocks `get_object` directly must return the *unwrapped* object dict (mirror `test_hallucinated_id_filtered`). Add an implementer note.

---

## Confirmed correct (no change needed)
- CS-1..CS-6 change sites verified accurate against `ingest.py` (gate 920, signature 533-540, candidate 555, peer-facts 570, call site 922-924). `facts` genuinely carries concept `wiki_definition` text at the call site (887/891).
- `peer_obj.get("type", {}).get("key")` is the correct, verified way to read peer type from a `get_object` result (`anytype_client.py:44-52`; test fixtures).
- `_rel_key`/`_REL_KEY_BY_KIND` already map `"concept"` → `"wiki_related"`; reused unchanged.
- `_write_contradiction_links`, `_existing_text`, `_relation_ids`, the contradiction prompt, and the non-blocking exception handler are correctly identified as locked/reused.
- Wire contract (peers read via `get_object`, never search-response relation arrays) matches existing behaviour and is operationally sound.
- No deployment, migration, config, or new dependency. Trivial git-revert rollback. Resource profile inherited from the entity path, not enlarged (modulo SG-1).
- No new trust boundary; concept text enters the same anti-injection-wrapped prompt as entity facts.
