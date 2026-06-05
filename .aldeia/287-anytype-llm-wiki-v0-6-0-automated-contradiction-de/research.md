# Technical Research: #287 v0.6.0 Automated Contradiction Detection

**Researcher:** technical
**Date:** 2026-06-05
**Ticket:** Aldeia-IT/aldeia-box#287
**Branch:** aldeia/287-anytype-llm-wiki-v0-6-0-automated-contradiction-de

---

## A. Ingest Hook Point

**Where to insert cross-object contradiction detection in `_run_ingest`:**

The hook point is in `ingest.py:_run_ingest`, after step 10 (resolve+create/update each
candidate) and before step 11 (bidirectional relations).

Specifically, after each candidate's `resolve_entity` returns `action="update"` and the PATCH
to `wiki_facts`/`wiki_definition` is sent (lines 534-545), the existing object's fact text is
already in hand via the resolved `target` dict's `properties[]`. That is the earliest point at
which we have:
- `obj_id`: the resolved existing object's id
- `existing_text`: the current `wiki_facts`/`wiki_definition` from `target`
- `new_facts` (`facts`): the candidate's incoming fact text (before or after write)
- `kind`: "entity" or "concept"

The alternative — inserting after step 11 (relation write) — adds no information and delays the
contradiction signal. Inserting before the PATCH write would also be valid and has a small
advantage: if contradiction detection fails we haven't written yet, but this complicates the
"degraded detection should not block the ingest" requirement.

**Recommended insertion point:**
After `result["objects_updated"].append(...)` (ingest.py:543-545) in the `resolution["action"]
== "update"` branch. This is inside the `for cand in candidates:` loop and immediately after
the existing-object PATCH. The data in hand at that point:

- `target` dict (from `resolve_entity` result) — contains current `properties[]` with existing
  `wiki_facts`/`wiki_description`
- `facts` variable — the sanitized new fact text (already computed at line 524)
- `obj_id` — resolved at line 544
- `kind` — "entity" or "concept"
- `space_id`, `client` — in scope

For new objects (`action="create"`), there are no existing facts to compare against, so
contradiction detection MUST be skipped for the create branch.

**Data available at the hook point (update branch only):**
```python
existing_text = _existing_text(target, prop_key)  # same helper as remember.py
# prop_key = "wiki_facts" for entity, "wiki_definition" for concept
new_facts = facts  # already sanitized at line 524
```

`_existing_text` is defined in `remember.py:629-642`. It should be extracted to a shared
location (e.g., `ingest.py` or `util.py`) or imported from `remember.py` for reuse. Currently
`remember.py` imports from `ingest.py`, not the reverse, so importing `_existing_text` into
`ingest.py` from `remember.py` would create a circular import. Moving it to a shared location
(or duplicating inline) is the cleanest approach.

---

## B. Contradiction Detection Mechanism

**Existing `consolidate` path:**
`extraction.py:consolidate` (lines 220-274) calls `_call_ollama_prompt` with
`consolidate.md` which already returns:
```json
{"consolidated_text": "...", "changed": bool, "fact_actions": [...], "conflicts": [...]}
```
The `conflicts[]` array (`extraction.py:294`) is: `[{"existing_fact": str, "new_fact": str,
"reason": str}]`.

This is INTRA-ENTITY detection (within the same object's facts). It cannot detect cross-object
contradictions without modification.

**Cross-object detection mechanism options:**

Option 1 — Extend `consolidate.md` with a "compare against other objects" field.
This would require passing all other objects' facts to the LLM — expensive and noisy.

Option 2 — New dedicated `contradiction.md` prompt that takes:
- `new_claim`: the new fact text for an object being updated
- `existing_claims`: list of `{object_id, name, facts}` for candidate objects
Returns: `[{"object_id": str, "reason": str}]` — contradicting pairs found.

Option 3 — Reuse `consolidate()` on the updated-object's fact text against each candidate peer
object's facts. This reuses the existing `consolidate()` call surface but requires N calls per
updated object (one per candidate peer).

**Recommendation: Option 2 with semantic pre-filter.** A new `contradiction.md` prompt that:
1. Takes the updated object's new fact text as the "claim"
2. Receives a batch of candidate peer object facts as context (pre-filtered by semantic
   similarity from Qdrant to limit N)
3. Returns contradicting object ids + reasons

This adds minimal new surface (one new prompt file, one new function `detect_contradictions`),
reuses `_call_ollama_prompt` from `extraction.py`, and degrades gracefully (no hits if Qdrant
is absent — skip detection, warn `contradiction_detection_degraded`).

For the MVP, a simpler approach without Qdrant pre-filtering is also viable:
limit to the objects that share the same `wiki_relations` (already-linked peers), which is
O(relations) not O(wiki) and keeps the scope tight.

**Prompt files location:**
`src/anytype_llm_wiki/wiki/prompts/` — currently has `extraction.md`,
`consolidate.md`, `synthesis.md` (extraction.py:27-28).

A new `contradiction.md` lives at the same path. The loader pattern is:
```python
_CONTRADICTION_PROMPT_PATH = Path(__file__).parent / "prompts" / "contradiction.md"
def _load_contradiction_prompt() -> str:
    try:
        return _CONTRADICTION_PROMPT_PATH.read_text(encoding="utf-8")
    except OSError:
        return "<fallback>"  # graceful degrade
```

---

## C. Bidirectional Write

**How `_write_bidirectional_relations` / `_patch_relation` works (ingest.py:287-351):**

`_patch_relation` (ingest.py:287-290) calls `client.update_object` with a `properties` payload
carrying an `objects`-format list:
```python
client.update_object(space_id, obj_id, {"properties": [{"key": rel_key, "objects": list(ids)}]})
```
This is a PATCH to `/v1/spaces/{space_id}/objects/{obj_id}`.

`_write_bidirectional_relations` (ingest.py:296-351) loops over `(from_id, to_id, label)` tuples,
PATCHes side A first, then side B, with rollback on B-failure.

**Can the same helper write `wiki_contradictions` bidirectionally?**

Yes, with a dedicated wrapper. The `wiki_contradictions` property key (format `objects`) is
schema-confirmed on both `wiki_entity` and `wiki_concept` (types_schema.py:95, 111). The same
`_patch_relation` call works:
```python
_patch_relation(client, space_id, obj_id, "wiki_contradictions", [peer_id])
_patch_relation(client, space_id, peer_id, "wiki_contradictions", [obj_id])
```

**Critical difference from `_write_bidirectional_relations`:** The existing helper accumulates a
`linked` dict per-run and APPENDS to it (ingest.py:321-335), but it does NOT first read the
current value. For `wiki_contradictions` we must first GET the existing objects value to avoid
overwriting it. The approach:

1. `GET /v1/spaces/{space_id}/objects/{obj_id}?format=md` → parse existing
   `wiki_contradictions` list from `properties[]`
2. Append the new peer_id (dedup)
3. PATCH with the full merged list

This requires using `AnytypeReadClient.get_object` to read the current value before patching —
the same pattern as `_existing_text` in `remember.py`.

**Wire contracts for this operation:**

Read (get full object):
- Method: `AnytypeReadClient.get_object(space_id, object_id)`
- HTTP: `GET /v1/spaces/{space_id}/objects/{object_id}?format=md`
- Response: `{"object": {..., "properties": [...]}}`
- Mock: `respx.get(f"{ANYTYPE_BASE}/v1/spaces/{space_id}/objects/{object_id}")` (path-specific GET)

Update (PATCH contradiction link):
- Method: `WikiClient.update_object(space_id, obj_id, {"properties": [{"key": "wiki_contradictions", "objects": [peer_id]}]})`
- HTTP: `PATCH /v1/spaces/{space_id}/objects/{obj_id}`
- Response: `{"object": {...}}`
- Mock: `respx.patch(f"{ANYTYPE_BASE}/v1/spaces/{space_id}/objects/{obj_id}")`

---

## D. Lint Activation

**Current state of `contradiction_unresolved` in `lint.py`:**

The check is ALREADY coded at lint.py:416-430 and reads `wiki_contradictions` correctly:
```python
if tk == "wiki_entity":
    contra_prop = _prop(o, "wiki_contradictions")
    contradictions = (
        _parse_relation_elements(contra_prop.get("objects"))
        if contra_prop else []
    )
    reviewed_prop = _prop(o, "wiki_last_reviewed")
    last_reviewed = reviewed_prop.get("date") if reviewed_prop else None
    if contradictions and not last_reviewed:
        findings.append(_finding(
            "high", "contradiction_unresolved", o, space_id,
            f"{len(contradictions)} unresolved contradiction(s) and no "
            "wiki_last_reviewed (PASSIVE check — see #287)",
        ))
```

The predicate `contradictions and not last_reviewed` is correct: non-empty
`wiki_contradictions` AND null `wiki_last_reviewed` fires the finding.

**Changes needed to activate:**

1. **`lint.py:20-22`** — Remove the `_PASSIVE_CONTRADICTION_NOTE` constant:
   ```python
   _PASSIVE_CONTRADICTION_NOTE = (
       "contradiction_unresolved is passive until v0.6.0 (#287): ..."
   )
   ```
   This is referenced in `_empty_report()` at lint.py:173 in `"notes":
   [_PASSIVE_CONTRADICTION_NOTE]`.

2. **`lint.py:173`** — Update `_empty_report()`: remove `_PASSIVE_CONTRADICTION_NOTE` from
   `notes`. After v0.6.0 the note should either be removed entirely or replaced with an
   active description.

3. **`lint.py:416-430`** — Remove `(PASSIVE check — see #287)` from the finding detail string.

4. **`lint.py:20-22, 78-83`** — Remove the CPO-6 docstring comment block referencing the
   passive state.

5. **`lint.py:213-214`** — Update the docstring: remove "The `contradiction_unresolved` check
   is PASSIVE until v0.6.0/#287".

**Severity is already High (lint.py:417).** No severity change needed.

**Does setting `wiki_last_reviewed` clear it?**
Yes. The predicate `if contradictions and not last_reviewed:` (lint.py:425) requires BOTH
conditions. Setting `wiki_last_reviewed` to any non-null date makes `last_reviewed` truthy,
which fails the predicate and removes the finding. This is the correct review-clear behavior.

**Does it already read `wiki_contradictions`?**
Yes. The check reads `wiki_contradictions` at lint.py:418-423. The only thing making it
"passive" is the `_PASSIVE_CONTRADICTION_NOTE` in the report notes and the docstring caveat —
the check logic itself is fully functional.

**Scope note (lint.py:417):** Check is scoped to `wiki_entity` only (`if tk == "wiki_entity"`).
Types_schema confirms `wiki_contradictions` exists on `wiki_concept` too (types_schema.py:111),
but the lint spec (SF9) scoped this check to entity only. The spec should decide whether to
extend to concepts in v0.6.0 or keep entity-only. If extending, remove the `tk == "wiki_entity"`
guard.

---

## E. Fold-in Dispositions

### E1. Ingest SLO (`< 2 min p95`, 10k words)

**Finding from master spec (spec.md:1624):**
> "No hard SLO in v0.3.0 (dominated by Ollama extraction latency, typically 10–40 s). A
> tuning-target of < 2 min p95 on a 10 k-word source is aspirational, not an AC. Revisit as
> a hard SLO in v0.6.0+ once extraction tuning lands."
> (spec.md:855 also: "Revisit as a hard SLO in v0.6.0+ once extraction tuning lands.")

**Recommendation:** Make it an **aspirational budget note, not a release gate**, for v0.6.0.
Rationale: contradiction detection adds at most 1-3 extra Ollama calls (the contradiction prompt
+ optional Qdrant pre-filter). Total additional latency is bounded but Ollama latency varies
wildly by model and hardware. A p95 gate requires CI infrastructure with consistent hardware and
a live Ollama instance — this cannot be measured in the CI unit-test suite. What IS measurable
in CI:
- A seam test that instruments the contradiction-detection call count (verify it is bounded)
- A skip-gated live smoke test that measures wall-clock on the pinned Wikipedia fixture and
  records the observed duration in test output for operator review

Record the p95 aspirational budget in a `docs/performance-notes.md` or the CHANGELOG entry, not
as a blocking AC.

### E2. Partial-state idempotency resume (#284 AC#18)

**Finding from commit `2c36f55`:**
The commit message is explicit: "fix(ingest): make re-ingest idempotent (deterministic
extraction + Source dedup)". The two root causes were:
1. Non-deterministic extraction (fixed: temperature=0, seed=0)
2. No Source dedup (fixed: `_create_source` now calls `resolve_entity` first and reuses the
   existing Source — ingest.py:627-644)

**What was shipped vs. master spec AC#18:**
The shipped behavior (`_create_source` reuse, `TestReingestIdempotency`) covers the
"reuse existing Source on re-ingest" part of AC#18. What is NOT shipped per the master spec text:
- `resumed_partial_ingest` WikiLog event: the current code does NOT log this. `_create_source`
  silently reuses the Source with no special WikiLog note.
- Entity/concept attachment to existing Source after partial failure: if extraction failed on
  run 1 but succeeded on run 2, the entities created on run 2 are attached to the existing
  Source via normal flow. There is no "resumed" marker.

**Exact gap:** The WikiLog `wiki_notes` for a re-ingest that reuses a Source still says `"ingest"`
(ingest.py:576). There is no `resumed_partial_ingest` log event.

**Recommendation:** Add a small extension:
- In `_create_source`, when the Source is reused (existing Source found), return a flag or add
  a `"resumed_partial_ingest"` string to the WikiLog `notes`. The cleanest approach: `_create_source`
  returns `(str | None, bool)` where bool is `was_resumed`. If True, append
  `"resumed_partial_ingest"` to `notes` before the WikiLog write (ingest.py:576-577).
- This is a small, contained change that closes the AC#18 gap. It should be shipped in v0.6.0
  alongside contradiction detection (same pipeline touch).

### E3. Backlinks O(1) (#286 OQ#7)

**Finding:**
- Master spec (spec.md:606, 945): OQ#7 deferred to v0.6.x.
- v0.5.0 lint spec (spec-addendum D1, spec.md:37-55): **REVERSED the deferral.** The native
  `backlinks` field IS already used by lint.py as the primary path (`_backlinks_inbound`,
  lint.py:126-136) with the O(N) fallback when absent.
- lint.py:360-361 confirms: `has_primary, inbound = _backlinks_inbound(o)` uses the
  `get_object` `backlinks` field first.

**Does #287 need it?**
Contradiction detection looks up peer objects to compare facts. If detection is limited to
already-linked peers (via `wiki_relations`/`wiki_related` on the target object), NO additional
backlinks lookup is needed — the peers are already in the candidate list.

If detection uses Qdrant for semantic pre-filtering, the Qdrant call returns object IDs without
needing backlinks.

**Conclusion:** #287 does NOT require extending backlinks usage. The D1 resolution already
shipped in v0.5.0. The spec should note "backlinks OQ#7 resolved by v0.5.0 D1 — no v0.6.0
action needed" and close the reference.

---

## F. Wire-Contract Table

Every Anytype endpoint #287 will call:

| WikiClient / Client Method | HTTP Verb | Path | Respx mock to mirror | Note |
|---|---|---|---|---|
| `WikiClient.list_objects(space_id)` | GET | `/v1/spaces/{space_id}/objects?offset=N&limit=100` | `respx.get().mock(...)` in test_lint.py `_standard_mocks` | Schema pre-check (inherited, no change) |
| `WikiClient.list_properties(space_id)` | GET | `/v1/spaces/{space_id}/properties?offset=N&limit=100` | `respx.get()` with path check `/properties` and no `/tags` in test_lint.py `_standard_mocks:310` | Tag resolution two-step step 1 |
| `WikiClient.list_tags(space_id, property_id)` | GET | `/v1/spaces/{space_id}/properties/{property_id}/tags?offset=N&limit=100` | `respx.get()` with path check `/properties/` and `/tags` in test_lint.py `_standard_mocks:315-322` | **Property-scoped two-step — landmine.** Always path `/properties/{id}/tags`, NEVER `/tags` alone |
| `WikiClient.search(space_id, query)` | **POST** | `/v1/spaces/{space_id}/search` | `respx.post(f"{ANYTYPE_BASE}/v1/spaces/{space_id}/search")` in test_ingest.py `capture_search` | **POST landmine** — not GET. Used in `resolve_entity` during ingest |
| `AnytypeReadClient.get_object(space_id, obj_id)` | GET | `/v1/spaces/{space_id}/objects/{obj_id}?format=md` | `respx.get()` with path `/objects/` AND `?` in url in test_lint.py `_standard_mocks:328-332` | **New for #287**: read existing `wiki_contradictions` before merge-and-patch |
| `WikiClient.update_object(space_id, obj_id, patch)` | PATCH | `/v1/spaces/{space_id}/objects/{obj_id}` | `respx.patch(f"{ANYTYPE_BASE}/v1/spaces/{space_id}/objects/{obj_id}")` in test_ingest.py `mock_patch` | Bidirectional `wiki_contradictions` write |
| `WikiClient.create_object(space_id, ...)` | POST | `/v1/spaces/{space_id}/objects` | `respx.post()` with path check `/objects` (not `/search`) in test_ingest.py | Source, entity, WikiLog creates (inherited) |
| `WikiClient.update_object` (wiki_status) | PATCH | `/v1/spaces/{space_id}/objects/{obj_id}` | same PATCH mock | Used by `_flag_conflict_status` in remember.py (NOT touched by #287) |

**Additional Ollama endpoints (#287's new LLM call):**
| Endpoint | HTTP | Path | Mock |
|---|---|---|---|
| Ollama generate | POST | `{WIKI_EXTRACT_ENDPOINT}/api/generate` | `respx.post(f"{OLLAMA_BASE}/api/generate")` — mirror test_extraction.py:66 |
| Ollama chat (fallback) | POST | `{WIKI_EXTRACT_ENDPOINT}/api/chat` | `respx.post(f"{OLLAMA_BASE}/api/chat")` — mirror test_extraction.py:72 |

**Flag: `list_tags` is a property-scoped two-step** — the path is always
`/v1/spaces/{sid}/properties/{property_id}/tags`. The test must mock GET to a path matching
BOTH `/properties/` AND `/tags` (test_lint.py:315-322). A space-level `/tags` path returns 404
(test_lint.py:347-348, "must not be called").

**Flag: `search` is POST** — mirror `respx.post(f"{ANYTYPE_BASE}/v1/spaces/{space_id}/search")`
from test_ingest.py. It returns `{"data": [...], "pagination": {"has_more": false}}`, NOT the
general `{"object": ...}` envelope.

---

## G. Test Surface

### CI-runnable seam tests (core contract)

The core promise per spec-scope.md:
> ingest a contradicting claim → bidirectional `wiki_contradictions` link + null
> `wiki_last_reviewed` → lint reports it High → setting `wiki_last_reviewed` clears it.

**Seam 1 — Contradiction detection fires on update path:**
- Fake Anytype (respx mocks): `search` returns existing entity with `wiki_facts="X is true"`,
  GET `get_object` returns same entity with empty `wiki_contradictions[]`.
- Monkeypatch `extract` and `consolidate` to degrade (bypass LLM), monkeypatch the new
  `detect_contradictions` function to return `[peer_obj_id]`.
- Assert: PATCH calls include one targeting the new object's `wiki_contradictions` with
  `[peer_obj_id]` and one targeting `peer_obj_id`'s `wiki_contradictions` with `[obj_id]`.
- Assert: `wiki_last_reviewed` is NOT set in any PATCH payload (null on contradiction flag).
- Assert: `result["contradictions_detected"]` > 0.

**Seam 2 — Lint fires High on pipeline-produced contradiction:**
- Existing test `TestContradictionCheck.test_contradiction_check_passive` in test_lint.py:897
  already seeds `wiki_contradictions=["obj-ref-contradiction"]` and `wiki_last_reviewed=None`
  and asserts the finding fires. This test needs only the `_PASSIVE_CONTRADICTION_NOTE` reference
  removed from its assertions; the check predicate is unchanged.
- A new test `test_contradiction_check_active` should verify: after v0.6.0 the `notes` field
  does NOT contain the passive caveat.

**Seam 3 — `wiki_last_reviewed` clears the finding:**
- Reuse `_make_entity` with `wiki_contradictions=["obj-ref"]` and
  `wiki_last_reviewed="2026-06-05T00:00:00+00:00"`.
- Assert: `contradiction_unresolved` finding does NOT fire.
- This is unit-testable entirely in-memory (no HTTP mocks needed — just call lint check
  predicate logic directly or via `wiki_lint` with full mock chain).

**Seam 4 — Contradiction detection degraded path:**
- Monkeypatch `detect_contradictions` to raise / return empty.
- Assert: ingest continues, `contradictions_detected: 0`, warning
  `contradiction_detection_degraded` in result.

### Must remain skip-gated live smoke tests

- End-to-end: live ingest of two conflicting sources → verify `wiki_contradictions` is
  bidirectionally set in the live space and `wiki_lint` reports the finding.
- Live SLO observation: timed run against the pinned Wikipedia fixture, print elapsed; not a
  blocking assert.

**Lesson from #284 applied:** Every CI-runnable seam test should use a fake WikiClient pattern
(monkeypatched `extract` + `consolidate` + `detect_contradictions`) plus respx mocks for the
PATCH/GET calls. The core promise (bidirectional link + lint finding + cleared by review) must
have CI coverage, not only live coverage.

---

## H. Hermes Contradiction Semantics

The verbatim policy text from the master spec (spec.md:204):

> "**Hermes' design decisions are the operational blueprint.** Page threshold policy (2+
> mentions or central to one source), cross-link minimum (≥2 outbound relations per object),
> severity-graded lint (critical/high/medium/low), **contradiction handling (document both
> positions, flag for review, never silently overwrite)**, append-only WikiLog. These are
> portable verbatim — only the storage mechanism changes."

And from spec-scope.md (line 11, referencing the feature description):
> "Hermes/Karpathy policy: document both positions, flag for operator review, never silently
> overwrite, no auto-merge"

The #289 spec (spec.md:328-331) provides the intra-entity version of the policy which is
parallel:
> "**#289 MUST NEVER silently overwrite a conflicting fact.** The `consolidated_text` includes
> BOTH facts (marked with `[CONFLICT: ...]`), and `wiki_status` is set to `"needs-review"`.
> The conflict is recorded in the WikiLog notes and the result dict even if the `wiki_status`
> select write degrades (tag absent — see D6)."

For cross-object contradictions (#287), the equivalent policy:
- BOTH objects retain their existing `wiki_facts`/`wiki_definition` — NEVER overwritten.
- `wiki_contradictions` is set on BOTH objects to record the contradiction link.
- `wiki_last_reviewed` is left NULL on both — signals "awaiting operator review".
- No auto-merge: the system records and surfaces; humans resolve.

The #289 spec explicitly documents the boundary (spec.md:1607-1609):
> "`wiki_remember` flags intra-entity conflicts only. Cross-object contradiction detection
> (linking two entity objects that carry contradictory facts) is the scope of ticket #287,
> planned for v0.6.0. #289 MUST NOT write `wiki_contradictions` object-links as a precursor
> or approximation."

---

## Summary of #289 → #287 Handoff

| Dimension | #289 `wiki_remember` | #287 `wiki_ingest` |
|---|---|---|
| Surface | Same-object (intra-entity) conflict | Cross-object contradiction |
| Trigger | `consolidate()` returns non-empty `conflicts[]` | New `detect_contradictions()` detects semantic conflict between different objects |
| Signal written | `wiki_status = "needs-review"` | `wiki_contradictions` (object link, bidirectional) |
| `wiki_last_reviewed` | NOT set (conflict unresolved) | NOT set (awaiting operator review) |
| Source in code | `remember.py:_flag_conflict_status` | New function in `ingest.py` |
| Auto-merge? | No | No |

---

## Additional Findings

### Schema confirmation (types_schema.py)

- `wiki_contradictions` (format `objects`) on `wiki_entity` (line 95) and `wiki_concept` (line 111) — confirmed.
- `wiki_last_reviewed` (format `date`) on `wiki_entity` (line 97) only — NOT on `wiki_concept`.
  This is a schema gap: if contradiction detection fires for a Concept, there is no
  `wiki_last_reviewed` field to clear the lint finding. Either:
  (a) Add `wiki_last_reviewed` to `wiki_concept` in the v0.6.0 schema (version bump to 0.5.0),
  or (b) Keep contradiction detection scoped to `wiki_entity` for v0.6.0.
  The lint check is already scoped to `wiki_entity` only (lint.py:417 `if tk == "wiki_entity"`).
  Recommendation: keep entity-only for v0.6.0, add `wiki_last_reviewed` to Concept as a v0.6.x
  follow-on.

### `_existing_text` circular import avoidance

`remember.py:629-642` defines `_existing_text`. `ingest.py` needs the same helper. To avoid a
circular import (remember.py imports from ingest.py), move `_existing_text` to `util.py` or
replicate it inline in the new contradiction-detection helper. Moving to `util.py` is cleaner.

### Rollback policy for contradiction write

When writing bidirectional `wiki_contradictions` links, use the same A-side/B-side rollback
pattern as `_write_bidirectional_relations` (ingest.py:296-351):
- If B-side PATCH fails, revert A-side by PATCHing its `wiki_contradictions` back to the prior
  list (GET the list first to know the prior value, or track it in the write function).
- WikiLog records `contradiction_rollback` event (parallel to `relation_rollback`).
- Ingest overall status downgrades to `"partial"` only if the contradiction write fails — entity
  create/update is not rolled back.

### WIKI_SCHEMA_VERSION bump

Adding the `resumed_partial_ingest` WikiLog marker and (if extending `wiki_last_reviewed` to
Concept) schema changes require a WIKI_SCHEMA_VERSION bump from `0.4.1` to `0.5.0`. The spec
should decide scope before implementation.

If no schema changes (entity-only contradiction detection, no new properties), the version can
stay at `0.4.1`. The contradiction detection uses existing properties only.
