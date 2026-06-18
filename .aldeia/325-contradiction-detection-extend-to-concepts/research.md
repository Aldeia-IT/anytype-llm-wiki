# Research: Extend Contradiction Detection to Concepts (#325)

**Date:** 2026-06-18
**Researcher:** technical-research worker (claude-sonnet-4-6)
**Questions investigated:** Verify spec-scope claims; resolve mixed-kind peer design question; map test mirroring.

---

## Summary

All four verified change sites in `spec-scope.md` are confirmed correct at the stated line numbers. The three hardcoded keys in `detect_contradictions` (`"wiki_relations"` at line 555, `"wiki_facts"` at line 570) and the gate at line 920 are the exact points requiring change. `_write_contradiction_links` is confirmed kind-agnostic and reusable unchanged.

**Design decision on mixed-kind peers: Option A is recommended** — read each peer's text using the key implied by that peer's own type (`wiki_entity` → `wiki_facts`; `wiki_concept` → `wiki_definition`), determined from `peer_obj.get("type", {}).get("key")` on the `get_object` result. No blocker found. `detect_contradictions` needs one new parameter (`kind: str`) and a small helper.

---

## Current Mechanism (Verified)

### 1. Detection Gate — `ingest.py:920`

```python
if kind == "entity":   # line 920 — gates entire detect+write-links block
    try:
        peers = detect_contradictions(...)
```

Confirmed: the gate is `kind == "entity"` at line 920 in the update branch (after `resolution["action"] == "update"` check at line 905). The create branch (line 938–948) has no contradiction call at all — correct by design (LD3).

The wrapping `try/except Exception` is at line 925, with `result["warnings"].append("contradiction_detection_degraded")` on error — confirmed non-blocking.

### 2. `_REL_KEY_BY_KIND` and `_rel_key` — `ingest.py:437–441`

```python
_REL_KEY_BY_KIND = {"entity": "wiki_relations", "concept": "wiki_related"}  # line 437

def _rel_key(kind: str) -> str:
    return _REL_KEY_BY_KIND.get(kind, "wiki_relations")  # line 440–441
```

Confirmed. This dict and helper already exist. `_rel_key` already resolves `"concept"` → `"wiki_related"`. It is already used in `_write_bidirectional_relations` (lines 475–476) for per-object key dispatch. Detection must reuse it.

### 3. `detect_contradictions` — `ingest.py:533–595`

**Signature (line 533–540):**
```python
def detect_contradictions(
    new_facts: str,
    obj_id: str,
    target: dict,
    space_id: str,
    client: WikiClient,
    read_client: AnytypeReadClient,
) -> list[dict]:
```

**Candidate set (line 555) — hardcoded entity key:**
```python
candidates = [pid for pid in _relation_ids(target, "wiki_relations") if pid != obj_id]
```
Must become `_relation_ids(target, _rel_key(kind))` where `kind` is the new parameter.

**Peer facts read (line 563–571) — hardcoded entity facts key:**
```python
peer_obj = read_client.get_object(space_id, peer_id)  # line 563 — get_object confirmed
...
"facts": _existing_text(peer_obj, "wiki_facts"),  # line 570 — hardcoded
```
Must become `_existing_text(peer_obj, _facts_key_for_peer(peer_obj))` where the key is derived from `peer_obj.get("type", {}).get("key")`.

**Hallucinated-ID filter (lines 558, 591–593):**
```python
candidate_set = set(candidates)  # line 558
...
if peer_id not in candidate_set:  # line 592
    continue
```
Confirmed: operates purely on ids, kind-agnostic. No change needed.

### 4. `_write_contradiction_links` — `ingest.py:598–665`

Confirmed kind-agnostic. The function:
- Reads A-side contradictions via `_relation_ids(target, "wiki_contradictions")` (line 617)
- Reads B-side contradictions via `read_client.get_object` then `_relation_ids(peer_obj, "wiki_contradictions")` (lines 641–642)
- Writes via `_patch_relation(..., "wiki_contradictions", ...)` (lines 630, 644)

All operations are on `"wiki_contradictions"`, which is the same relation key for both entity and concept. No type discrimination anywhere. **Reuse unchanged.**

### 5. `_existing_text` and `_relation_ids` — `util.py:98–153`

Defined in `src/anytype_llm_wiki/wiki/util.py`, imported in `ingest.py` at lines 39–40.

`_existing_text(target, prop_key)` (line 98): reads `p.get("text")` from the `properties` list for matching `prop_key`. Fully generic — works for any text property key. Calling it with `"wiki_definition"` is correct for concept peers.

`_relation_ids(obj, prop_key)` (line 141): reads `p.get("objects")` from the `properties` list. Also fully generic. Already used with `"wiki_contradictions"` in `_write_contradiction_links`. Calling it with `"wiki_related"` for concept candidates will work.

### 6. Peer Kind Determination from `get_object` Result

`AnytypeReadClient.get_object` (line 44 of `anytype_client.py`) returns `resp.json()["object"]`. Every response shape confirmed in the test fixtures includes `"type": {"key": "wiki_entity"}` or `"type": {"key": "wiki_concept"}`.

Confirmed from `_make_peer_get_object_response` (test line 1204–1216): the object dict has `"type": {"key": "wiki_entity"}`. This matches the search-result shape used in `resolve_entity` (line 258): `o.get("type", {}).get("key") == type_key`.

Peer kind determination: `peer_obj.get("type", {}).get("key")` returns `"wiki_entity"` or `"wiki_concept"`.

Facts key mapping (same pattern used in `remember.py:226–230`):
```python
"wiki_definition" if type_key == "wiki_concept" else "wiki_facts"
```

### 7. `facts` Variable at the Call Site — `ingest.py:887, 891`

For `kind == "concept"`, `facts` is already set to `sanitize_property_value(cand.get("facts", "") or "")` (line 887) and stored as `wiki_definition` (line 891). The call at line 922 passes `facts` as `new_facts`. This is correct — no change needed at the call site for the new-claim side.

---

## Exact Change Sites

| # | File | Lines | What to Change |
|---|------|-------|----------------|
| CS-1 | `ingest.py` | 920 | `if kind == "entity":` → `if kind in ("entity", "concept"):` |
| CS-2 | `ingest.py` | 533–540 | Add `kind: str` parameter to `detect_contradictions` signature |
| CS-3 | `ingest.py` | 555 | `_relation_ids(target, "wiki_relations")` → `_relation_ids(target, _rel_key(kind))` |
| CS-4 | `ingest.py` | 570 | `_existing_text(peer_obj, "wiki_facts")` → `_existing_text(peer_obj, _facts_key_for_peer(peer_obj))` |
| CS-5 | `ingest.py` | 922–923 | Pass `kind=kind` to `detect_contradictions` call |

New helper (ingest-internal, ~line 532):
```python
def _facts_key_for_peer(peer_obj: dict) -> str:
    """Return wiki_definition for concept peers, wiki_facts for all others."""
    type_key = peer_obj.get("type", {}).get("key", "")
    return "wiki_definition" if type_key == "wiki_concept" else "wiki_facts"
```

---

## Design Decision: Mixed-Kind Peers

**Recommendation: Option A — read each peer's facts key by that peer's own type.**

### Justification

1. **No blocker found.** The `peer_obj` from `read_client.get_object` always carries `type.key` in both the real API shape (line 52 of `anytype_client.py`: `resp.json()["object"]`) and every test fixture (e.g., test line 1210: `"type": {"key": "wiki_entity"}`). Peer kind is always available.

2. **Semantic correctness.** If a concept (`wiki_concept`) links an entity peer via `wiki_related`, the entity's comparable text is `wiki_facts`, not `wiki_definition`. Restricting to same-kind only (Option B) would silently skip cross-kind peers rather than compare them accurately — leaving real contradictions undetected.

3. **Consistency with existing patterns.** `_write_bidirectional_relations` (lines 475–476) already dispatches per-object relation key: `from_key = _rel_key(kind_by_id.get(from_id, "entity"))`. The facts-key dispatch for detection is the same pattern applied to `peer_obj.get("type", {}).get("key")`.

4. **`_existing_text` is already generic.** Passing `"wiki_definition"` or `"wiki_facts"` to the existing helper requires no helper changes.

5. **Candidate set:** when the target is a concept, `_rel_key("concept")` = `"wiki_related"`. Peers found there may be of any kind; we read each peer's facts key from its own type. If `wiki_related` happens to point at a `wiki_entity` peer, that entity's `wiki_facts` is used — this is correct.

### Precise signature change to `detect_contradictions`

Add `kind: str` as the third positional parameter (after `obj_id`, before `target`), or more conservatively as a keyword argument after `target`. Recommended: insert after `obj_id` to keep `target` as positional in same position or add as keyword-only at the end. The simplest backward-compatible change:

```python
def detect_contradictions(
    new_facts: str,
    obj_id: str,
    target: dict,
    space_id: str,
    client: WikiClient,
    read_client: AnytypeReadClient,
    *,
    kind: str = "entity",       # NEW — keyword-only; default preserves entity behaviour
) -> list[dict]:
```

The `kind` parameter is used only to select the candidate relation key (`_rel_key(kind)`). Peer facts key uses `_facts_key_for_peer(peer_obj)` regardless of `kind`. Default `"entity"` makes the change backward-compatible with existing tests that do not pass `kind`.

---

## Reuse Unchanged

- `_write_contradiction_links` (`ingest.py:598–665`): confirmed kind-agnostic, operates only on `wiki_contradictions`. No change.
- `_existing_text` (`util.py:98–116`): generic, no change.
- `_relation_ids` (`util.py:141–153`): generic, no change.
- `_rel_key` (`ingest.py:440–441`): already handles `"concept"`. No change.
- A/B rollback pattern, dedup-as-no-op, `wiki_last_reviewed`-never-touched: all in `_write_contradiction_links`, unchanged.
- Contradiction prompt (`prompts/contradiction.md`): no change — same LLM task regardless of kind.

---

## Test Plan / Mirroring

### Existing tests (regression guard — must stay green unchanged)

All tests in `TestContradictionDetection` (`test_ingest.py:1224`) are entity-path tests:

| Test | AC | What it guards |
|------|----|----------------|
| `test_contradiction_bidirectional_write` | AC-1 | Entity update → bidirectional `wiki_contradictions` PATCH; no target GET (BL-3) |
| `test_no_detection_on_create` | AC-2 | Create branch → no detection call; `contradictions_detected == 0` |
| `test_detection_degraded` | AC-5 | LLM failure → ingest continues; `contradiction_detection_degraded` in warnings |
| `test_detection_degraded_warning_absent_on_clean_path` | AC-5 contrast | No-contradiction path → warning absent |
| `test_anti_injection_preamble_present` | AC-10 | Prompt file + fallback carry anti-injection preamble |
| `test_hallucinated_id_filtered` | AC-11 | Ghost id from LLM filtered; candidate set enforced |
| `test_self_reference_skipped` | AC-12 | Self-referencing `wiki_relations` entry skipped |
| `test_multiple_peers_contradict` | AC-13 | Two peers → `contradictions_detected == 2`; 4 PATCHes |
| `test_dedup_no_op` | AC-14 | Already-linked peer → no PATCH; `contradictions_detected == 0` |

Since `detect_contradictions` gains `kind` as keyword-only with default `"entity"`, none of these tests need modification — the monkeypatches bypass the real function anyway for most cases, and `test_hallucinated_id_filtered` / `test_self_reference_skipped` call the real function but don't pass `kind` → default `"entity"` preserved.

### Fixture helpers to extend

**`_make_objects_shaped_search_response` (test line 1168):** currently entity-only (hardcodes `"type": {"key": "wiki_entity"}`, `"wiki_facts"`, `"wiki_relations"`). For concept tests, add a parallel builder or a `kind` parameter:

```python
def _make_objects_shaped_search_response(
    obj_id: str,
    name: str,
    peer_id: str,
    existing_contradictions: list | None = None,
    kind: str = "entity",   # NEW
) -> dict:
    rel_key = "wiki_related" if kind == "concept" else "wiki_relations"
    facts_key = "wiki_definition" if kind == "concept" else "wiki_facts"
    type_key = "wiki_concept" if kind == "concept" else "wiki_entity"
    props = [
        {"key": facts_key, "text": "Some facts here."},
        {"key": rel_key, "objects": [peer_id]},
    ]
    if existing_contradictions is not None:
        props.append({"key": "wiki_contradictions", "objects": existing_contradictions})
    return {
        "data": [{"id": obj_id, "name": name, "type": {"key": type_key}, "properties": props}],
        "pagination": {"has_more": False},
    }
```

**`_make_peer_get_object_response` (test line 1204):** currently entity-only. Add a `kind` parameter (same pattern as above) so concept peer responses carry `"type": {"key": "wiki_concept"}` and `"wiki_definition"` text. Used in detection tests to verify correct facts-key dispatch.

### New tests to add (concept path mirrors)

| New Test | AC mirror | What to cover |
|----------|-----------|---------------|
| `test_concept_contradiction_bidirectional_write` | AC-1 concept | Concept update → candidates from `wiki_related`; bidirectional `wiki_contradictions`; no target GET |
| `test_concept_no_detection_on_create` | AC-2 concept | Concept create → no detection; `contradictions_detected == 0` |
| `test_concept_detection_degraded` | AC-5 concept | Concept update, LLM raises → `contradiction_detection_degraded`; ingest continues |
| `test_concept_self_reference_skipped` | AC-12 concept | `wiki_related` self-ref → no GET, no result entry |
| `test_concept_dedup_no_op` | AC-14 concept | Concept peer already in `wiki_contradictions` → no PATCH |
| `test_concept_mixed_kind_peer_uses_peer_facts_key` | Option A design | Concept target links entity peer → peer text read via `wiki_facts` (not `wiki_definition`) |

The mixed-kind peer test is the key new test for Option A. It should directly call `detect_contradictions(kind="concept")` with a `target` carrying `wiki_related = [entity_peer_id]`, mock `get_object` to return an entity peer (type key `"wiki_entity"`, `wiki_facts` populated), and assert `get_object` was called and the result was obtained (via `_call_ollama_prompt` capture of the prompt JSON containing the entity's facts).

`test_no_detection_on_create` for concept: the existing test already covers any kind because detection is gated by `if kind in ("entity", "concept"): ...` only in the update branch. The existing AC-2 test may already cover this implicitly if the search returns no existing object. A dedicated concept create test improves clarity.

---

## Docs to Update (when implemented)

- `README.md:175` — Remove "entity-only … (`wiki_concept` scope deferred)". New text: "detection fires for both entity and concept updates."
- `README.md:237` — Remove "and across Concepts" from the roadmap bullet (it will have shipped).
- `CHANGELOG.md` — New version entry: contradiction detection extended to `wiki_concept` objects.

---

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| `peer_obj.get("type", {}).get("key")` returns `None` or unexpected value | Low | `_facts_key_for_peer` defaults to `"wiki_facts"` — correct fallback for any non-concept type |
| `wiki_related` array on a concept contains an entity peer id | Low | Option A handles it correctly — entity peer's `wiki_facts` is read |
| Test monkeypatches bypass real `detect_contradictions` | Low | Existing monkeypatch tests remain valid as integration-level tests; the mixed-kind peer test must call the real function to validate Option A dispatch |
| Signature change breaks callers | None | keyword-only `kind="entity"` default; only one call site (line 922); test monkeypatches don't call the real function |

---

## Open Questions

None blocking implementation. The design decision is resolved (Option A). All change sites are identified and confirmed.

---

## Sources

- `src/anytype_llm_wiki/wiki/ingest.py` — lines 437–441, 533–595, 598–665, 886–895, 918–937
- `src/anytype_llm_wiki/wiki/util.py` — lines 98–116, 141–153
- `src/anytype_llm_wiki/anytype_client.py` — lines 44–52
- `src/anytype_llm_wiki/wiki/remember.py` — lines 226–230
- `tests/wiki/test_ingest.py` — lines 1168–1216, 1224–1997
- `.aldeia/325-contradiction-detection-extend-to-concepts/spec-scope.md`
