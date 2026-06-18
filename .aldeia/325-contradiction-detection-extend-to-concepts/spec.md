# Contradiction Detection: Extend to Concepts (#325)

**Status:** SPEC
**Date:** 2026-06-18
**Author:** spec-writer worker (claude-sonnet-4-6)
**Review rounds:** 0
**Ticket:** aldeia-box#325
**Branch:** `aldeia/325-contradiction-detection-extend-to-concepts`

---

## Problem Statement

Cross-object contradiction detection (introduced in #287, shipped v0.6.0) only fires when an **Entity** (`wiki_entity`) is updated with facts that conflict with a linked peer. Concepts (`wiki_concept`) are excluded by a hard gate at `ingest.py:920` (`if kind == "entity":`). Conflicting definitions or claims between already-linked Concepts go entirely undetected.

From `README.md:175`:
> "Today detection is **entity-only** and bounded to **linked entities** (`wiki_concept` scope deferred) — an entity that contradicts something it isn't linked to won't surface a finding yet."

This is a correctness gap: the typed knowledge graph includes first-class Concept Objects, and a wiki that silently ignores contradictions between linked Concepts is unreliable. The fix is a confined extension of the existing mechanism — no new approach, no new relation types, no schema migration.

---

## Research Summary

Research confirmed (`.aldeia/325-contradiction-detection-extend-to-concepts/research.md`, 2026-06-18):

- All four change sites identified in `spec-scope.md` are confirmed at the stated line numbers.
- `_write_contradiction_links` is confirmed fully kind-agnostic (operates only on `wiki_contradictions`).
- `_rel_key` already maps `"concept"` → `"wiki_related"` (`ingest.py:437–441`).
- The mixed-kind peer design question is resolved: **Option A** — each peer's comparable text is read using the key derived from *that peer's own type* (`peer_obj.get("type", {}).get("key")`), not from the calling object's kind.
- No blockers found. All change sites are minimal and non-invasive.

### Alternatives Considered

**Option B — same-kind peers only.** Restrict detection to peers of matching kind (concept↔concept, entity↔entity). Rejected: would silently skip cross-kind peers rather than compare them, leaving real contradictions undetected. The `peer_obj.get("type", {}).get("key")` field is always present on `get_object` responses, so reading the facts key from the peer's own type has no implementation risk.

---

## Proposed Solution

Five surgical changes to `src/anytype_llm_wiki/wiki/ingest.py`. No other files change (except tests, README, and CHANGELOG at the implementation step).

### CS-1 — Detection gate (`ingest.py:920`)

```python
# Before
if kind == "entity":

# After
if kind in ("entity", "concept"):
```

This is the only call-site change. The gate is in the `resolution["action"] == "update"` branch; the create branch has no contradiction call and stays untouched (LD3).

### CS-2 — New `_facts_key_for_peer` helper (new, ~`ingest.py:532`)

Add a module-level helper immediately before `detect_contradictions`:

```python
def _facts_key_for_peer(peer_obj: dict) -> str:
    """Return wiki_definition for concept peers, wiki_facts for all others."""
    type_key = peer_obj.get("type", {}).get("key", "")
    return "wiki_definition" if type_key == "wiki_concept" else "wiki_facts"
```

Default of `"wiki_facts"` ensures safe fallback for unknown or missing type keys.

### CS-3 — `detect_contradictions` signature (`ingest.py:533–540`)

Add `kind` as a keyword-only parameter with default `"entity"` for backward compatibility:

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

### CS-4 — Candidate relation key (`ingest.py:555`)

```python
# Before
candidates = [pid for pid in _relation_ids(target, "wiki_relations") if pid != obj_id]

# After
candidates = [pid for pid in _relation_ids(target, _rel_key(kind)) if pid != obj_id]
```

`_rel_key` already exists at `ingest.py:440–441` and already maps `"concept"` → `"wiki_related"`. No change to `_rel_key`.

### CS-5 — Peer facts key (`ingest.py:570`)

```python
# Before
"facts": _existing_text(peer_obj, "wiki_facts"),

# After
"facts": _existing_text(peer_obj, _facts_key_for_peer(peer_obj)),
```

For entity peers this resolves to `"wiki_facts"` (unchanged). For concept peers it resolves to `"wiki_definition"`.

### CS-6 — Pass `kind` at the call site (`ingest.py:922–923`)

```python
# Before
peers = detect_contradictions(
    facts, obj_id, target, space_id, client, read_client
)

# After
peers = detect_contradictions(
    facts, obj_id, target, space_id, client, read_client, kind=kind
)
```

`facts` already carries concept definition text at this point: the concept branch at `ingest.py:887` sets `facts = sanitize_property_value(cand.get("facts", "") or "")` and stores it as `wiki_definition` at `ingest.py:891`. No change to the new-claim argument.

---

### Mixed-Kind Peer Rule (Option A)

When a Concept is updated and its `wiki_related` list contains an Entity peer (or vice versa), the peer's comparable text is read using the key implied by **the peer's own type**, determined from `peer_obj.get("type", {}).get("key")` on the `get_object` result:

- `wiki_concept` peer → `"wiki_definition"`
- any other type → `"wiki_facts"` (including `wiki_entity` and unknown types)

This is implemented solely in `_facts_key_for_peer`. The `kind` parameter to `detect_contradictions` is used only to select the candidate relation key (CS-4); peer facts dispatch is type-driven, not kind-driven.

### Wire Contract: Peer reads always via `get_object`

**Hard requirement (from #287, memory `8f597af8`):** Anytype search responses are NOT guaranteed to hydrate objects-format relation arrays. Peer comparable text must be read via `read_client.get_object(space_id, peer_id)` — never off the search-response relation array. The existing code at `ingest.py:563` already uses `get_object`; the concept extension continues this pattern unchanged.

Endpoint: `GET /v1/spaces/{space_id}/objects/{peer_id}?format=md`
Test mock to mirror: `test_ingest.py` → `_make_peer_get_object_response` (~line 1204) — respx GET mock on `/objects/{peer_id}` with `?` in URL.

---

### What Must NOT Change

The following are locked and must be left untouched:

| Symbol | Location | Why locked |
|--------|----------|------------|
| `_write_contradiction_links` | `ingest.py:598–665` | Kind-agnostic; operates only on `wiki_contradictions`; carries A/B rollback pattern, dedup-as-no-op, `wiki_last_reviewed`-never-touched guarantees |
| Contradiction prompt (`prompts/contradiction.md`) | prompt file + `_load_contradiction_prompt` fallback | Same LLM task regardless of kind; anti-injection preamble already covers untrusted concept text as DATA |
| `_existing_text` | `util.py:98–116` | Generic by design; calling it with `"wiki_definition"` already works |
| `_relation_ids` | `util.py:141–153` | Generic by design; already used with `"wiki_contradictions"` |
| `_rel_key` / `_REL_KEY_BY_KIND` | `ingest.py:437–441` | Already correct; `"concept"` → `"wiki_related"` already present |
| Non-blocking exception handler | `ingest.py:925–927` | Detection must never block ingest; the `try/except Exception` + `contradiction_detection_degraded` warning is a hard constraint from #287 |

---

## Resource Impact

Each Concept update that passes the gate adds O(linked-peers) `get_object` calls — identical shape to the existing entity path. One LLM call per qualifying update (same prompt). No new Anytype types, properties, or relations. No schema migration. Negligible additional load on the 32 GB Mac Mini.

---

## Security Considerations

The contradiction prompt already carries an anti-injection preamble (verified in `test_anti_injection_preamble_present`, AC-10). Concept `wiki_definition` text enters the prompt under `{{NEW_CLAIM}}` and `{{CANDIDATES}}`; it is treated as untrusted DATA, same as entity `wiki_facts`. No new trust boundary is opened. No new credential handling.

---

## Operational Considerations

Failure mode is identical to the entity path: any exception in detection → `contradiction_detection_degraded` appended to `result["warnings"]`; ingest continues and returns non-error status. No new monitoring required. No deployment steps beyond shipping the code change.

---

## Test Plan

### Wire contract (unchanged from #287)

- `search` = `POST /v1/spaces/{sid}/search`
- `get_object` = `GET /v1/spaces/{sid}/objects/{oid}?format=md` (peer reads only — never target)
- `update_object` = `PATCH /v1/spaces/{sid}/objects/{oid}` (bidirectional write)

All respx mocks in new tests mirror the shape of existing `TestContradictionDetection` mocks (`test_ingest.py:1224+`).

### Fixture helper changes

**`_make_objects_shaped_search_response` (test ~line 1168):** Add a `kind: str = "entity"` parameter:

```python
def _make_objects_shaped_search_response(
    obj_id: str,
    name: str,
    peer_id: str,
    existing_contradictions: list | None = None,
    kind: str = "entity",     # NEW
) -> dict:
    rel_key   = "wiki_related"    if kind == "concept" else "wiki_relations"
    facts_key = "wiki_definition" if kind == "concept" else "wiki_facts"
    type_key  = "wiki_concept"    if kind == "concept" else "wiki_entity"
    ...
```

Existing call sites pass no `kind` → default `"entity"` → no change to entity tests.

**`_make_peer_get_object_response` (test ~line 1204):** Add a `kind: str = "entity"` parameter that sets `"type": {"key": "wiki_concept"}` and uses `"wiki_definition"` property key when `kind == "concept"`. Existing call sites unaffected.

### Regression guard tests (entity path — must stay green unchanged)

All tests in `TestContradictionDetection` (from `test_ingest.py:1224`) are entity-path tests. Because `detect_contradictions` gains `kind` as keyword-only with default `"entity"`, none require modification. The monkeypatches in integration-level tests bypass the real function; the unit-level tests (`test_hallucinated_id_filtered`, `test_self_reference_skipped`) call the real function without `kind` → default `"entity"` preserved.

| Test | Guards |
|------|--------|
| `test_contradiction_bidirectional_write` | Bidirectional `wiki_contradictions` PATCH; no target GET (BL-3) |
| `test_no_detection_on_create` | Create branch → no detection call |
| `test_detection_degraded` | LLM failure → ingest continues; `contradiction_detection_degraded` in warnings |
| `test_detection_degraded_warning_absent_on_clean_path` | No-contradiction path → warning absent |
| `test_anti_injection_preamble_present` | Prompt carries anti-injection preamble |
| `test_hallucinated_id_filtered` | Ghost id from LLM filtered |
| `test_self_reference_skipped` | Self-referencing `wiki_relations` entry skipped |
| `test_multiple_peers_contradict` | Two peers → `contradictions_detected == 2`; 4 PATCHes |
| `test_dedup_no_op` | Already-linked peer → no PATCH |

### Acceptance criteria

**AC-1 — Concept bidirectional detection (maps to ticket checkbox 1)**

`test_concept_contradiction_bidirectional_write`: Concept update (`kind="concept"`) with a contradicting `wiki_related` peer → `detect_contradictions` called with `kind="concept"` → candidates read from `wiki_related` → `wiki_contradictions` PATCHed bidirectionally → `result["contradictions_detected"] >= 1`, `result["status"] != "error"`, no target GET (BL-3). Uses `_make_objects_shaped_search_response(kind="concept")` and `_make_peer_get_object_response(kind="concept")`.

**AC-2 — Entity regression unchanged (maps to ticket checkbox 2)**

All nine existing `TestContradictionDetection` tests pass without modification. This is the primary regression guard.

**AC-3 — Concept create branch no-op (maps to ticket checkbox 3)**

`test_concept_no_detection_on_create`: Concept ingest where `resolve_entity` returns `action == "create"` → `detect_contradictions` never called → `result["contradictions_detected"] == 0`.

**AC-4 — Concept degraded-on-error (maps to ticket checkbox 3)**

`test_concept_detection_degraded`: Concept update, `detect_contradictions` raises → `"contradiction_detection_degraded"` in `result["warnings"]`; ingest returns non-error status; no PATCH fired.

**AC-5 — Concept self-reference skipped (maps to ticket checkbox 3)**

`test_concept_self_reference_skipped`: Concept's `wiki_related` includes its own `obj_id` → that id excluded from candidates → no `get_object` call for self, no result entry.

**AC-6 — Concept dedup no-op (maps to ticket checkbox 3)**

`test_concept_dedup_no_op`: Concept update where peer is already in `wiki_contradictions` → no PATCH issued; `result["contradictions_detected"] == 0`.

**AC-7 — Mixed-kind peer uses peer's facts key (Option A, maps to ticket checkbox 1 and 3)**

`test_concept_mixed_kind_peer_uses_peer_facts_key`: Call `detect_contradictions(..., kind="concept")` directly with a `target` carrying `wiki_related = [entity_peer_id]`. Mock `get_object` to return `_make_peer_get_object_response(kind="entity")` (type key `"wiki_entity"`, `wiki_facts` populated). Assert `_call_ollama_prompt` is called with a candidates JSON whose entry has `"facts"` drawn from the entity peer's `wiki_facts` (not `wiki_definition`). This test must call the real `detect_contradictions` (not monkeypatched) to validate Option A dispatch.

### Tests must be able to fail before implementation

New concept-path tests (AC-1, AC-3 through AC-7) must fail when run against the current codebase (gate is `kind == "entity"`, no `kind` parameter on `detect_contradictions`). This validates the test is actually exercising the new code path.

---

## Implementation Plan

1. **Code changes** — apply CS-1 through CS-6 in `src/anytype_llm_wiki/wiki/ingest.py`:
   - Add `_facts_key_for_peer` helper (~line 532, before `detect_contradictions`)
   - Add `kind: str = "entity"` keyword-only parameter to `detect_contradictions` signature
   - Update candidate line (`ingest.py:555`) to use `_rel_key(kind)`
   - Update peer facts line (`ingest.py:570`) to use `_facts_key_for_peer(peer_obj)`
   - Update gate (`ingest.py:920`) from `== "entity"` to `in ("entity", "concept")`
   - Update call site (`ingest.py:922–923`) to pass `kind=kind`

2. **Tests** — in `tests/wiki/test_ingest.py`:
   - Add `kind` parameter to `_make_objects_shaped_search_response` and `_make_peer_get_object_response`
   - Add new tests: `test_concept_contradiction_bidirectional_write`, `test_concept_no_detection_on_create`, `test_concept_detection_degraded`, `test_concept_self_reference_skipped`, `test_concept_dedup_no_op`, `test_concept_mixed_kind_peer_uses_peer_facts_key`
   - Run full `TestContradictionDetection` suite to confirm all regression guards are green

3. **Docs** — after tests pass:
   - `README.md:175` — remove "entity-only … (`wiki_concept` scope deferred)"; replace with "detection fires for both entity and concept updates, bounded to already-linked peers"
   - `README.md:237` — remove "and across Concepts" from roadmap bullet (shipped)
   - `CHANGELOG.md` — new version entry: "Contradiction detection extended to `wiki_concept` objects (#325)"

---

## Acceptance Criteria Checklist

Mapping directly to the three ticket checkboxes (aldeia-box#325):

- [ ] **Ticket AC-1:** A newly-ingested Concept claim conflicting with an already-linked Concept is detected and cross-linked via `wiki_contradictions`. Covered by spec AC-1 (`test_concept_contradiction_bidirectional_write`).
- [ ] **Ticket AC-2:** Existing Entity contradiction behaviour unchanged (regression-guarded). Covered by spec AC-2 (all nine `TestContradictionDetection` entity-path tests pass unchanged).
- [ ] **Ticket AC-3:** Tests cover the Concept conflict path mirroring the Entity tests. Covered by spec AC-3 through AC-7 (`test_concept_*` suite, including the mixed-kind peer test).

---

## Open Questions

None. Design decision (Option A) is resolved. All change sites identified and confirmed by research. No human input required before implementation.

---

## Deferred Items

Contradiction detection between **unlinked** Objects via semantic pre-filter → aldeia-box#328. Explicitly out of scope for this ticket.
