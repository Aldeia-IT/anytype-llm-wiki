# Contradiction Detection: Extend to Concepts (#325)

**Status:** SPEC
**Date:** 2026-06-18
**Author:** spec-writer worker (claude-sonnet-4-6); fix worker (claude-opus-4-8), R1 + R2 re-scope
**Review rounds:** 2 (review-r1.md + review-r2.md addressed)
**Ticket:** aldeia-box#325
**Branch:** `aldeia/325-contradiction-detection-extend-to-concepts`

> **Locate by symbol, not line number (SG-6).** All line numbers in this spec are
> approximate anchors current as of 2026-06-18 and drift with edits. The implementer
> must locate every change site by the named symbol (function, constant, comment text),
> then confirm the surrounding code matches the quoted "before" snippet before editing.

---

## Problem Statement

Cross-object contradiction detection (introduced in #287, shipped v0.6.0) only fires when an **Entity** (`wiki_entity`) is updated with facts that conflict with a linked peer. Concepts (`wiki_concept`) are excluded by a hard gate in the update branch of `wiki_ingest` (`if kind == "entity":`, ~`ingest.py:920`). Conflicting definitions or claims between already-linked Concepts go entirely undetected.

From `README.md:175`:
> "Today detection is **entity-only** and bounded to **linked entities** (`wiki_concept` scope deferred) — an entity that contradicts something it isn't linked to won't surface a finding yet."

This is a correctness gap: the typed knowledge graph includes first-class Concept Objects, and a wiki that silently ignores contradictions between linked Concepts is unreliable.

### Scope: confined detection extension (#325 core) + a documented surfacing follow-up

The three literal ticket acceptance criteria are: (1) a newly-ingested Concept claim conflicting with an already-linked Concept is detected and cross-linked via `wiki_contradictions`; (2) existing Entity behaviour is unchanged; (3) tests cover the Concept path mirroring the Entity tests. **All three are fully satisfied by the confined detection change set CS-1..CS-6 + CS-9 alone** — seven change sites in `ingest.py`, with no schema change, no lint change, and no bootstrap change. Concept contradictions are recorded in `wiki_contradictions` and browsable in Anytype.

R1 raised an additional *surfacing* affordance (concept contradictions flagged by `wiki_lint` and markable-resolved) on coherence grounds, under the assumption it was a small additive bootstrap change. **R2 (BL-R2-1) disproved that assumption:** re-running `wiki-bootstrap` does NOT attach a new property to the already-existing `wiki_concept` type — `bootstrap.py:281-285` `continue`s past existing types and never calls `create_type` (the only inline-property-link path), and the property loop at `bootstrap.py:330-353` only reports created/skipped properties, never links one onto a live type. Delivering surfacing correctly requires a **new, idempotent bootstrap capability** ("ensure declared properties are linked onto existing wiki types") of materially larger scope and review surface than this confined ticket. It is therefore moved into a clearly-labelled **recommended follow-up** (see "Recommended Follow-Up" below), not the #325 core.

**For Decide:** the lead recommendation is to ship the confined #325 core (which meets its own ACs in full) and open a dedicated surfacing follow-up ticket. Jan may instead pull surfacing back into #325 at Decide, with the larger bootstrap scope (the new ensure-properties-on-existing-types capability) understood. Both options are one step away: the core is shippable as-is, and the follow-up section is fully specified so it can be folded back in or split out without further analysis.

---

## Research Summary

Research (`.aldeia/325-contradiction-detection-extend-to-concepts/research.md`, 2026-06-18) plus R1 review verification (`review-r1.md`) confirmed:

- The detection change sites (CS-1..CS-6) are accurate against `ingest.py` (gate ~920, signature ~533–540, candidate ~555, peer-facts ~570, call site ~922–924). `facts` genuinely carries concept `wiki_definition` text at the call site (~887/891).
- `_write_contradiction_links` is fully kind-agnostic (operates only on `wiki_contradictions`); the A/B rollback pattern, dedup-as-no-op, and `wiki_last_reviewed`-never-touched (write-side) guarantees are reused unchanged.
- `_rel_key` / `_REL_KEY_BY_KIND` already map `"concept"` → `"wiki_related"` (~`ingest.py:437`); reused unchanged.
- `peer_obj.get("type", {}).get("key")` is the verified way to read peer type from a `get_object` result (`anytype_client.py:44–52`).
- **R1 lead discovery:** the monkeypatch `fake_detect_contradictions` stubs in `test_ingest.py` have signature `(new_facts, obj_id, target, space_id, client, read_client)` with no `kind` — they will raise `TypeError` once CS-6 passes `kind=kind` (SF-1/SF-2).
- **R2 lead discovery (BL-R2-1):** `bootstrap.py:281-285` skips `create_type` for already-existing types and the property loop at `bootstrap.py:330-353` never links a property onto a live type, so re-bootstrap cannot provision `wiki_concept.wiki_last_reviewed` on an existing space. This is why lint surfacing is a follow-up, not core (see "Recommended Follow-Up").
- `remember.py:_type_for_kind` (~226) already encodes the concept→`wiki_definition` mapping, keyed by `kind` (SF-5).

### Alternatives Considered

**Mixed-kind peers — Option B (same-kind peers only).** Restrict detection to peers of matching kind. Rejected: would silently skip cross-kind peers rather than compare them, leaving real contradictions undetected. `peer_obj.get("type", {}).get("key")` is always present on `get_object` responses, so reading the facts key from the peer's own type (Option A) has no implementation risk.

---

## Proposed Solution

**Seven change sites, all in `ingest.py`:** the detection extension (CS-1..CS-6) plus the kind-discriminated degraded warning (CS-9). No other source file changes in the core scope — no schema change, no lint change, no bootstrap change. Tests, README, and CHANGELOG are touched at the implementation step. (The lint surfacing additions originally numbered CS-7/CS-8 are relocated to "Recommended Follow-Up" below.)

### CS-1 — Detection gate (`ingest.py`, comment "entity-only (LD1)", ~920)

```python
# Before
if kind == "entity":

# After
if kind in ("entity", "concept"):
```

Only call-site change. The gate is in the `resolution["action"] == "update"` branch; the create branch has no contradiction call and stays untouched (LD3). Update the adjacent comment ("entity-only (LD1)") to reflect entity+concept.

### CS-2 — New `_facts_key_for_peer` helper (new, immediately before `detect_contradictions`, ~532)

```python
def _facts_key_for_peer(peer_obj: dict) -> str:
    """Return the comparable-text property key for a peer, by the peer's own type.

    wiki_concept peers store comparable text in wiki_definition; all others
    (wiki_entity and unknown/missing type) use wiki_facts. Mirrors the
    kind→text-key rule in remember.py:_type_for_kind, keyed by type-key here
    because detection reads the peer's type off get_object, not a caller kind.
    """
    type_key = peer_obj.get("type", {}).get("key", "")
    return _TEXT_KEY_BY_TYPE_KEY.get(type_key, "wiki_facts")
```

**Single source of truth (SF-5).** `remember.py:_type_for_kind` (~226) already maps `concept → wiki_definition` / else → `wiki_facts`, but keyed by *subject kind* and returning a 3-tuple `(type_key, label, property_key)`. Detection needs the inverse lookup — *type-key → text-key* — because it reads each peer's type off `get_object`, not a caller-supplied kind. Reusing `_type_for_kind` would require inverting type-key back to kind first, which is more indirection than the rule deserves.

Decision: introduce one explicit constant and have `_facts_key_for_peer` derive from it, so the rule is named once and not silently duplicated:

```python
# module-level in ingest.py, near _REL_KEY_BY_KIND
_TEXT_KEY_BY_TYPE_KEY = {"wiki_concept": "wiki_definition", "wiki_entity": "wiki_facts"}
```

A short comment on both `_TEXT_KEY_BY_TYPE_KEY` and `_type_for_kind` must cross-reference each other so a future editor changing the rule finds both. This is the SF-5 "(b) justify a separate helper" path: the two helpers key on different inputs (kind vs type-key) and serve different call shapes; collapsing them is not worth the indirection, but the duplication is now documented and the literal string pair lives in one constant.

### CS-3 — `detect_contradictions` signature (`ingest.py`, ~533–540)

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

### CS-4 — Candidate relation key (`ingest.py`, `_relation_ids(target, "wiki_relations")`, ~555)

```python
# Before
candidates = [pid for pid in _relation_ids(target, "wiki_relations") if pid != obj_id]

# After
candidates = [pid for pid in _relation_ids(target, _rel_key(kind)) if pid != obj_id]
```

`_rel_key` already maps `"concept"` → `"wiki_related"`. No change to `_rel_key`.

### CS-5 — Peer facts key (`ingest.py`, `_existing_text(peer_obj, "wiki_facts")`, ~570)

```python
# Before
"facts": _existing_text(peer_obj, "wiki_facts"),

# After
"facts": _existing_text(peer_obj, _facts_key_for_peer(peer_obj)),
```

Entity peers → `"wiki_facts"` (unchanged); concept peers → `"wiki_definition"`.

### CS-6 — Pass `kind` at the call site (`ingest.py`, the `detect_contradictions(...)` call, ~922–923)

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

`facts` already carries concept definition text here (set at ~887, stored as `wiki_definition` at ~891). No change to the new-claim argument.

> **Impl-time breakage warning (SF-1 — single most likely breakage):** passing `kind=kind`
> here makes every monkeypatch stub named `fake_detect_*` in `test_ingest.py` raise
> `TypeError` (their signatures omit `kind`), which is swallowed by the `except Exception`
> at ~`ingest.py:925`. See Test Plan → "Monkeypatch stub signature touch-up".

### CS-9 — Kind-discriminated degraded warning (`ingest.py`, `result["warnings"].append("contradiction_detection_degraded")`, ~926) — SF-6

```python
# Before
result["warnings"].append("contradiction_detection_degraded")

# After — discriminator appended ONLY for the new (non-entity) path; entity stays byte-for-byte
warning = "contradiction_detection_degraded"
if kind != "entity":
    warning += f":{kind}"
result["warnings"].append(warning)
```

So an operator can tell when the **concept** path degraded (`contradiction_detection_degraded:concept`) now that the degrade surface roughly doubles with concepts in scope. **Entity behaviour is preserved exactly:** the entity path still emits the bare `contradiction_detection_degraded` string, so the existing entity regression test (`test_detection_degraded`) needs **no assertion change** and AC-2 stays clean (bare string ⇒ entity, `:concept` ⇒ concept is still fully diagnosable). Detection fires only for entity/concept today, so the asymmetry has no other-kind case to cover. Any README/known-limitations wording referencing the warning, if present, stays valid for entities and gains the concept variant.

---

### Mixed-Kind Peer Rule (Option A)

When a Concept is updated and its `wiki_related` list contains an Entity peer (or vice versa), the peer's comparable text is read using the key implied by **the peer's own type** (`_facts_key_for_peer`):

- `wiki_concept` peer → `"wiki_definition"`
- any other type → `"wiki_facts"` (including `wiki_entity` and unknown/missing types)

The `kind` parameter to `detect_contradictions` selects only the *candidate relation key* (CS-4); peer facts dispatch is type-driven, not kind-driven.

### Wire Contract: Peer reads always via `get_object`

**Hard requirement (#287, memory `8f597af8`):** Anytype search responses are NOT guaranteed to hydrate objects-format relation arrays. Peer comparable text is read via `read_client.get_object(space_id, peer_id)` — never off the search-response relation array. Existing code (~`ingest.py:563`) already uses `get_object`; the concept extension continues this unchanged.

Endpoint: `GET /v1/spaces/{space_id}/objects/{peer_id}?format=md`
Test mock to mirror: `_make_peer_get_object_response` in `test_ingest.py` (~1204) — respx GET mock on `/objects/{peer_id}` with `?` in URL.

### What Must NOT Change

| Symbol | Why locked |
|--------|------------|
| `_write_contradiction_links` | Kind-agnostic; operates only on `wiki_contradictions`; A/B rollback, dedup-as-no-op, **`wiki_last_reviewed`-never-touched (write-side)** guarantees preserved |
| Contradiction prompt (`prompts/contradiction.md`) + `_load_contradiction_prompt` fallback | Same LLM task regardless of kind; anti-injection preamble already covers untrusted concept text as DATA |
| `_existing_text` (`util.py`) | Generic; calling with `"wiki_definition"` already works |
| `_relation_ids` (`util.py`) | Generic; already used with `"wiki_contradictions"` |
| `_rel_key` / `_REL_KEY_BY_KIND` (`ingest.py`) | Already maps `"concept"` → `"wiki_related"` |
| Non-blocking exception handler (`ingest.py`, ~925) | Detection must never block ingest (#287 hard constraint); control flow unchanged. CS-9 only *appends* a `:concept` suffix on the concept path; the entity warning string is untouched |
| `lint.py` (entire file) | **Core scope touches no lint code.** Concept lint surfacing is a follow-up (see "Recommended Follow-Up") |
| `types_schema.py` (entire file) | **Core scope adds no type or property.** The concept `wiki_last_reviewed` property is a follow-up |

---

## Resource Impact

Each Concept update that passes the gate adds O(linked-peers) `get_object` calls + one LLM call — identical shape to the existing entity path, inherited not enlarged (modulo SG-1 below).

**No schema change, no new types or properties, no schema-version bump, no deployment steps.** The core change set is entirely in `ingest.py`. No new Anytype types or relations, no new dependency, no data migration. Negligible additional load on the 32 GB Mac Mini. **Rollback is a trivial `git revert`** — there is no provisioned state to unwind. (Schema/bootstrap/migration impact applies only to the surfacing follow-up — see "Recommended Follow-Up".)

### SG-1 — Unbounded peer fan-out (deferred, pre-existing)

A hub object with many linked peers triggers N sequential `get_object` calls plus a large LLM prompt. **Deferral rationale (concrete):** this risk is pre-existing for entities and #325 does not enlarge it in kind — the same per-peer-GET + single-prompt profile applies; concept `wiki_definition` text may make a given prompt marginally larger, but the fan-out *count* is unchanged and is governed by the same `wiki_related`/`wiki_relations` cardinality an entity already has. Capping top-N peers or truncating per-peer text is a cross-cutting change to the shared detection loop that would also alter entity behaviour — out of #325's confined scope. **Follow-up:** file/point a ticket to cap top-N peers / truncate per-peer text in `detect_contradictions` for both kinds.

---

## Security Considerations

The contradiction prompt already carries an anti-injection preamble (verified in `test_anti_injection_preamble_present`). Concept `wiki_definition` text enters under `{{NEW_CLAIM}}`/`{{CANDIDATES}}` as untrusted DATA, same as entity `wiki_facts`. No new trust boundary; no new credential handling.

---

## Operational Considerations

Failure mode is identical to the entity path: any exception in detection → degraded warning appended to `result["warnings"]`; ingest continues, returns non-error status.

**SF-6 / SG-2 — observability of degraded/silent paths.** The top-level degraded warning is now kind-discriminated (CS-9: `contradiction_detection_degraded:concept`). Two finer-grained failure surfaces remain **silent today** and are *not* changed by #325:

- **Per-peer `get_object` skip** (~`ingest.py:564–566`): a peer that fails to fetch is skipped with no warning.
- **`_facts_key_for_peer` fallback** (SG-2): a peer whose `get_object` omits `type.key` falls back to `wiki_facts` and may read empty text — a silent false-negative for a concept peer.

**Deferral rationale (concrete):** both are pre-existing for entities and equally silent there; adding per-peer debug logging touches the shared loop and is a broader observability change than #325's confined extension warrants. Captured as a follow-up: emit a debug-level log on per-peer skip and on type-key fallback in `detect_contradictions`. The kind discriminator (CS-9) is the one cheap, in-scope visibility win and is included.

**Deployment:** none. The core change is code-only in `ingest.py` — no bootstrap re-run, no schema-version stamp, no migration note. Rollback is a trivial `git revert`.

---

## Test Plan

### Wire contract (unchanged from #287)

- `search` = `POST /v1/spaces/{sid}/search`
- `get_object` = `GET /v1/spaces/{sid}/objects/{oid}?format=md` (peer reads only — never target)
- `update_object` = `PATCH /v1/spaces/{sid}/objects/{oid}` (bidirectional write)

All respx mocks in new tests mirror existing `TestContradictionDetection` mocks (`test_ingest.py:1224+`).

> **Locate-by-symbol (SG-6).** Find existing tests/helpers by name (`grep` for the symbol),
> not by the approximate line numbers in this spec.

> **Envelope foot-gun (SG-7).** `_make_peer_get_object_response` returns a `{"object": {...}}`
> envelope. A unit test that mocks `get_object` *directly* (e.g. AC-7) must return the
> **unwrapped** object dict (mirror `test_hallucinated_id_filtered`), because
> `read_client.get_object` already unwraps `resp.json()["object"]`. Mocking the HTTP layer
> via respx uses the full envelope; mocking the client method uses the unwrapped dict.

### Monkeypatch stub signature touch-up (SF-1 / SF-2 — required, the most likely breakage)

Every `fake_detect_*` stub in `test_ingest.py` that monkeypatches `detect_contradictions` currently has signature `(new_facts, obj_id, target, space_id, client, read_client)` — no `kind`. After CS-6, the real call site passes `kind=kind`, so each stub raises `TypeError`, which is swallowed by the `except Exception` at ~`ingest.py:925` → tests silently see `contradiction_detection_degraded:*` and `contradictions_detected == 0`, failing their assertions in a confusing way.

**Required fix:** add `**kwargs` (or `*, kind="entity"`) to every monkeypatch stub. Stubs to touch (locate by name; current approximate lines): `fake_detect_contradictions` (~1319, ~1388), `fake_detect_raises` (~1452), `fake_detect_no_contradictions` (~1524), `fake_detect_two_peers` (~1765), `fake_detect_one_peer` (~1899). This is a one-line signature change per stub — no behaviour change.

### Fixture helper changes

**`_make_objects_shaped_search_response` (~1168):** add `kind: str = "entity"`. The new branch must set the relation key, the comparable-text property key, and the type key together, and write the comparable text into the kind-appropriate body property (a concept's text lives under `wiki_definition`, an entity's under `wiki_facts`) so the real `_facts_key_for_peer` dispatch is exercised end-to-end:

```python
def _make_objects_shaped_search_response(
    obj_id, name, peer_id, existing_contradictions=None, kind="entity",
):
    rel_key   = "wiki_related"    if kind == "concept" else "wiki_relations"
    facts_key = "wiki_definition" if kind == "concept" else "wiki_facts"
    type_key  = "wiki_concept"    if kind == "concept" else "wiki_entity"
    # ... build the object with "type": {"key": type_key},
    #     relations under rel_key, and the comparable text under facts_key:
    #     properties/body[facts_key] = <the object's definition-or-facts text>
    ...
```

Existing call sites pass no `kind` → default `"entity"` → unchanged.

**`_make_peer_get_object_response` (~1204):** add `kind: str = "entity"` that sets `"type": {"key": "wiki_concept"}` and writes the peer's comparable text under the `"wiki_definition"` property key when `kind == "concept"` (else `"type": {"key": "wiki_entity"}` and `"wiki_facts"`). Existing call sites unaffected.

### Regression guard tests (entity path)

All `TestContradictionDetection` tests (`test_ingest.py:1224+`) are entity-path tests. Because `detect_contradictions` gains `kind` keyword-only with default `"entity"`, the *real-call* unit tests are truly unchanged; the *monkeypatched* integration tests need only the one-line stub touch-up above. CS-9 leaves the entity warning string bare, so `test_detection_degraded`'s assertion is unchanged.

| Test | Guards | R1 touch-up |
|------|--------|-------------|
| `test_contradiction_bidirectional_write` | Bidirectional PATCH; no target GET | stub `**kwargs` |
| `test_no_detection_on_create` | Create branch → no detection call | none (no detection call) |
| `test_detection_degraded` | LLM failure → ingest continues; warning present | stub `**kwargs` (warning string unchanged — entity stays bare) |
| `test_detection_degraded_warning_absent_on_clean_path` | No-contradiction → warning absent | stub `**kwargs` |
| `test_anti_injection_preamble_present` | Prompt carries anti-injection preamble | none if real-call; else stub `**kwargs` |
| `test_hallucinated_id_filtered` | Ghost id filtered (real call) | **none — truly unchanged** |
| `test_self_reference_skipped` | Self-ref skipped (real call) | **none — truly unchanged** |
| `test_multiple_peers_contradict` | Two peers → 2 detected; 4 PATCHes | stub `**kwargs` |
| `test_dedup_no_op` | Already-linked peer → no PATCH | stub `**kwargs` |

### Acceptance criteria

Concept tests carry a distinct docstring tag `#325 AC-Cn` (SG-5) to avoid collision with the in-file entity AC-10..AC-14 docstrings.

**AC-C1 — Concept bidirectional detection (ticket checkbox 1)**
`test_concept_contradiction_bidirectional_write`: Concept update (`kind="concept"`) with a contradicting `wiki_related` peer → `detect_contradictions` called with `kind="concept"` → candidates from `wiki_related` → `wiki_contradictions` PATCHed bidirectionally → `contradictions_detected >= 1`, `status != "error"`, no target GET. Uses both fixtures with `kind="concept"`.

**AC-C2 — Entity regression (ticket checkbox 2)**
All `TestContradictionDetection` entity tests pass after the **stub signature touch-up** (SF-1/SF-2): the real-call unit tests (`test_hallucinated_id_filtered`, `test_self_reference_skipped`) are unchanged; the monkeypatched integration tests get a one-line `**kwargs` stub edit. The entity degraded-warning string is unchanged (CS-9 appends `:concept` only on the concept path), so no entity assertion changes. This remains the primary regression guard — corrected mechanism, not "unchanged across the board".

**AC-C3 — Concept create branch no-op (ticket checkbox 3)**
`test_concept_no_detection_on_create`: Concept ingest where `resolve_entity` returns `action == "create"` → `detect_contradictions` never called → `contradictions_detected == 0`.

**AC-C4 — Concept degraded-on-error (ticket checkbox 3)**
`test_concept_detection_degraded`: Concept update, detection raises → `contradiction_detection_degraded:concept` in `warnings` (CS-9); ingest returns non-error; no PATCH fired.

**AC-C5 — Concept self-reference skipped (ticket checkbox 3)**
`test_concept_self_reference_skipped`: Concept's `wiki_related` includes its own `obj_id` → excluded from candidates → no `get_object` for self, no result entry.

**AC-C6 — Concept dedup no-op (ticket checkbox 3)**
`test_concept_dedup_no_op`: peer already in `wiki_contradictions` → no PATCH; `contradictions_detected == 0`.

**AC-C7 — Real-function concept-peer dispatch (SF-3, ticket checkbox 1)**
`test_concept_peer_uses_wiki_definition`: call the **real** `detect_contradictions(..., kind="concept")` (not monkeypatched) with a `target` carrying `wiki_related = [concept_peer_id]`; mock `get_object` to return a `wiki_concept` peer with populated `wiki_definition` and a distinct/empty `wiki_facts`. Assert the candidate JSON passed to `_call_ollama_prompt` has `"facts"` drawn from `wiki_definition` (value **present**) AND the `wiki_facts` text is **absent**. This is the only test that exercises the `_facts_key_for_peer` concept branch via the real function (AC-C1 is monkeypatched; AC-C8 only exercises the entity/`wiki_facts` fallback).

**AC-C8 — Mixed-kind peer uses peer's facts key (Option A, ticket checkboxes 1+3)**
`test_concept_mixed_kind_peer_uses_peer_facts_key`: real `detect_contradictions(..., kind="concept")` with `wiki_related = [entity_peer_id]`; mock `get_object` to return a `wiki_entity` peer (unwrapped dict per SG-7) with populated `wiki_facts`. Assert candidate `"facts"` is drawn from `wiki_facts` (not `wiki_definition`).

**AC-C9 — Multiple concept peers (SF-4, ticket checkbox 3)**
`test_concept_multiple_peers_contradict` (mirror of entity `test_multiple_peers_contradict`): concept target with two contradicting `wiki_related` peers → `contradictions_detected == 2`; 4 PATCHes. This case specifically guards against reading candidates from the wrong relation key (`wiki_relations` vs `wiki_related`) while writes still land.
*No concept variant of `test_anti_injection_preamble_present` is needed (SF-4): the contradiction prompt is shared across kinds, so the entity assertion already covers concept text.*

**AC-C10 — Empty/absent concept definition peer (SG-3, ticket checkbox 3)**
`test_concept_empty_definition_peer`: a concept peer whose `wiki_definition` is empty/absent does not crash and is not spuriously flagged (no `wiki_contradictions` PATCH for that peer).

### B-side rollback coverage (SG-4 — known gap, not a #325 requirement)
`_write_contradiction_links` is kind-agnostic and locked; the entity suite has no B-side rollback test either (pre-existing debt). Not added here. Noted as a known coverage gap to fold into the SG-1 follow-up ticket.

### Tests must be able to fail before implementation

New concept-path tests (AC-C1, AC-C3..C10) must fail against the current codebase (gate is `kind == "entity"`, no `kind` parameter). This validates each test exercises the new path.

---

## Implementation Plan

Core scope only (CS-1..CS-6, CS-9). Ordered ingest → tests → docs. No schema, lint, bootstrap, or migration step (those live in "Recommended Follow-Up").

1. **Ingest (CS-1..CS-6, CS-9)** — `src/anytype_llm_wiki/wiki/ingest.py`:
   - Add `_TEXT_KEY_BY_TYPE_KEY` constant + `_facts_key_for_peer` helper (cross-reference `remember.py:_type_for_kind`).
   - Add `kind: str = "entity"` keyword-only param to `detect_contradictions`.
   - Candidate line → `_rel_key(kind)`; peer-facts line → `_facts_key_for_peer(peer_obj)`.
   - Gate → `in ("entity", "concept")`; pass `kind=kind` at the call site; update the "entity-only (LD1)" comment.
   - Degraded warning → discriminator appended only on the non-entity path (CS-9).

2. **Tests** — `tests/wiki/test_ingest.py`:
   - Touch up all `fake_detect_*` stub signatures (`**kwargs`). `test_detection_degraded`'s expected warning is unchanged (entity stays bare per CS-9).
   - Extend fixtures: `_make_objects_shaped_search_response(kind=)`, `_make_peer_get_object_response(kind=)`.
   - Add AC-C1, AC-C3..C10 tests; run full `TestContradictionDetection` suite green.

3. **Docs** — after tests pass:
   - `README.md:175` — rewrite so detection fires for **both entity and concept** updates (cross-linked via `wiki_contradictions`), and **fix the severity to `critical`, not `High`** (SF-R2-1; actual severity `lint.py:500` / `test_lint.py:1197`). Note that `wiki_lint` surfacing for concepts is a planned **follow-up** (entity contradictions are flagged by `wiki_lint` today; concept contradictions are recorded and browsable in Anytype but not yet flagged by lint).
   - `README.md:237` — remove "and across Concepts" from the roadmap bullet (detection shipped).
   - `CHANGELOG.md` — entry: "Contradiction detection extended to `wiki_concept` updates; concept contradictions are detected and cross-linked via `wiki_contradictions` (#325). `wiki_lint` surfacing for concepts is a follow-up."

---

## Recommended Follow-Up (out of confined scope): lint surfacing of concept contradictions

This section is **NOT part of the #325 core.** It captures the surfacing affordance R1 raised (concept contradictions flagged by `wiki_lint` and markable-resolved) together with the R2 finding (BL-R2-1) that makes it a materially larger, separate unit of work. The lead recommends a **dedicated follow-up ticket**. Until it ships, concept contradictions are still recorded in `wiki_contradictions` and browsable in Anytype — they are simply not surfaced by `wiki_lint`.

### Why this is not a small additive change (BL-R2-1, verified)

The naïve plan — "add `wiki_last_reviewed` to the `wiki_concept` type and re-run bootstrap" — **does not work on any already-bootstrapped space** (i.e. the real aldeia-box wiki):

- `bootstrap.py:281-285`: for any `type_key` already present, the loop appends to `types_skipped` and `continue`s, **skipping `create_type` entirely**. `create_type` (286-302) is the **only** code path that links inline properties onto a type.
- `bootstrap.py:330-353`: the property loop only *reports* created/skipped properties and builds `prop_map`; it **never links a property onto an already-existing type**.
- `wiki_last_reviewed` already exists globally (declared on `wiki_entity`), so on re-bootstrap it lands in `pre_existing_prop_keys` → reported `properties_skipped: already_exists`. Nothing attaches it to `wiki_concept`.

So a CS-8-style lint gate would flag concept contradictions as `critical` while the concept type still lacks the `wiki_last_reviewed` field needed to mark them resolved — the exact broken UX this surfacing was meant to prevent.

### What the follow-up must deliver

1. **New bootstrap capability — ensure declared properties are linked onto existing wiki types.** An idempotent step that, per provisioned type, diffs declared-vs-live properties and links any missing ones via the Anytype type/property API. **The implementer must verify the Anytype `API-update-type` / property-link endpoint exists and behaves idempotently** — no current repo code path adds a property to an existing type (the v0.3.0 precedent added *tag options to an existing select property* via dedicated `_ensure_*` tag paths, which is not the same operation). This touches the bootstrap path for all types and carries its own review surface.
2. **Schema property (former CS-7).** Add `{"property_key": "wiki_last_reviewed", "name": "Wiki Last Reviewed", "format": "date"}` to the `wiki_concept` properties list in `types_schema.py` (mirror the entity entry exactly). Additive, not a data migration — existing concepts have no value → reads as unreviewed → flagged, the desired default. Detection's write-side guarantee is unaffected: `_write_contradiction_links` still never touches `wiki_last_reviewed`.
3. **Lint gate (former CS-8).** In `lint.py`, change the `contradiction_unresolved` gate from `tk == "wiki_entity"` to `tk in ("wiki_entity", "wiki_concept")` and fix the stale "wiki_entity only (SF9)" comment. The check body is otherwise unchanged: it reads `wiki_contradictions` and resolves via `wiki_last_reviewed` (`if contradictions and not last_reviewed`), with severity `critical`.
4. **Schema-version bump.** Bump `WIKI_SCHEMA_VERSION` (`"0.4.1"` at `types_schema.py:27` → next patch) so the additive property is versioned and the `wiki_schema_outdated` re-run prompt fires.
5. **MIGRATIONS.md note.** Under "Unreleased", document the re-bootstrap step and the new ensure-properties capability (match the existing v0.3.0 entry's prose format).
6. **AC-C11 — concept contradiction surfaces in lint.** `test_concept_contradiction_unresolved` in `test_lint.py`, mirroring the entity `test_contradiction_check_active`: a `wiki_concept` with `wiki_contradictions` set and null `wiki_last_reviewed` → `contradiction_unresolved` fires with severity `critical`; a concept with no contradictions does not fire; a concept with `wiki_last_reviewed` set does **not** fire. Requires extending `_make_concept` in `test_lint.py` (~157) with `wiki_contradictions` and `wiki_last_reviewed` params (mirroring `_make_entity` — the current `_make_concept` builds neither). This test must fail against current `lint.py` and depends on the schema property and bootstrap capability above.

This is a separate, larger unit of work than #325's confined detection extension. **Recommend a dedicated ticket.**

---

## Acceptance Criteria Checklist

Mapping to the three ticket checkboxes (aldeia-box#325). The confined core (CS-1..CS-6, CS-9) covers all three in full; lint surfacing is a separate follow-up beyond the literal checkbox text.

- [ ] **Ticket AC-1:** A newly-ingested Concept claim conflicting with an already-linked Concept is detected and cross-linked via `wiki_contradictions`. Covered by spec AC-C1; real-function concept-peer dispatch by AC-C7.
- [ ] **Ticket AC-2:** Existing Entity behaviour unchanged (regression-guarded). Covered by spec AC-C2 — real-call unit tests unchanged; monkeypatched tests get a one-line stub touch-up (SF-1/SF-2). The entity degraded-warning string is left bare (CS-9 appends `:concept` only on the concept path), so no entity behaviour changes.
- [ ] **Ticket AC-3:** Tests cover the Concept conflict path mirroring the Entity tests. Covered by AC-C3..C10 (concept create/degraded/self-ref/dedup/concept-peer-dispatch/mixed-kind/multiple-peers/empty-definition).

**For Decide:** lead recommendation is to ship this confined core and open a surfacing follow-up (next section). Jan may instead fold the follow-up back into #325 with the larger bootstrap scope understood.

---

## Open Questions

None blocking. The one open decision is the scope choice flagged for Jan at Decide: ship the confined core (#325) plus a dedicated surfacing follow-up (lead recommendation), or fold the surfacing follow-up back into #325 with the larger bootstrap-capability scope understood (see "Recommended Follow-Up"). If the follow-up is pursued, its open question is verifying the Anytype type/property-link API needed to attach a property to an existing type.

---

## Deferred Items

| Item | Rationale (concrete) | Tracking |
|------|----------------------|----------|
| SG-1 — unbounded peer fan-out (cap top-N / truncate per-peer text) | Pre-existing for entities; #325 inherits but does not enlarge the fan-out *count*. A cap is a cross-cutting change to the shared loop that would also alter entity behaviour — outside #325's confined scope. | Follow-up ticket |
| SG-2 / SF-6 deeper observability — debug-log on per-peer `get_object` skip and `_facts_key_for_peer` fallback | Pre-existing and equally silent for entities; per-peer logging touches the shared loop, a broader change than this extension. The cheap, in-scope win (kind-discriminated top-level warning) IS done (CS-9). | Follow-up ticket (same as SG-1) |
| SG-4 — B-side rollback test on a concept | `_write_contradiction_links` is kind-agnostic and locked; the entity suite has no B-side rollback test either — pre-existing debt, not a #325 requirement. | Known coverage gap, folded into the SG-1 follow-up |
| Contradiction detection between **unlinked** Objects via semantic pre-filter | Out of scope by ticket definition. | aldeia-box#328 |
