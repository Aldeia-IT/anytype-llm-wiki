# Contradiction Detection: Extend to Concepts (#325)

**Status:** SPEC
**Date:** 2026-06-18
**Author:** spec-writer worker (claude-sonnet-4-6); fix worker (claude-opus-4-8), R1
**Review rounds:** 1 (review-r1.md addressed)
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

### Scope: detection AND surfacing (R1 / BL-1)

The feature is not "write a `wiki_contradictions` link" — `README.md:175` defines it as objects being "cross-linked via `wiki_contradictions` **and left for review** (`wiki_lint` flags them)." A contradiction that is written but can never surface in `wiki_lint`, and can never be marked resolved, is a half-built feature.

The `contradiction_unresolved` (Critical) surfacing in `lint.py` is gated to `wiki_entity` only, and `wiki_concept` does **not** carry the `wiki_last_reviewed` property that lint uses to mark a contradiction resolved (verified: `types_schema.py` entity block has `wiki_last_reviewed`; concept block does not). So coherent delivery of #325 requires pulling the *surfacing* affordance into scope:

1. Extend the lint surfacing gate to concepts.
2. Add `wiki_last_reviewed` to the `wiki_concept` type so concept contradictions are *resolvable*, not just flaggable.

This is an additive, idempotent bootstrap change — **not** a data migration (existing concept objects simply have no `wiki_last_reviewed` value, which reads as "unreviewed = flagged", the desired default). It does revise the earlier "no schema change at all" claim; the spec now reflects the additive schema honestly (see Resource Impact / Deployment).

**For Decide:** the literal ticket ACs name only detection + cross-linking; the surfacing/schema additions are an in-scope coherence requirement surfaced explicitly here so Jan can veto or split at Decide. The detection-only subset (CS-1..CS-6) is fully separable from the surfacing subset (CS-7..CS-9) if a split is preferred.

---

## Research Summary

Research (`.aldeia/325-contradiction-detection-extend-to-concepts/research.md`, 2026-06-18) plus R1 review verification (`review-r1.md`) confirmed:

- The detection change sites (CS-1..CS-6) are accurate against `ingest.py` (gate ~920, signature ~533–540, candidate ~555, peer-facts ~570, call site ~922–924). `facts` genuinely carries concept `wiki_definition` text at the call site (~887/891).
- `_write_contradiction_links` is fully kind-agnostic (operates only on `wiki_contradictions`); the A/B rollback pattern, dedup-as-no-op, and `wiki_last_reviewed`-never-touched (write-side) guarantees are reused unchanged.
- `_rel_key` / `_REL_KEY_BY_KIND` already map `"concept"` → `"wiki_related"` (~`ingest.py:437`); reused unchanged.
- `peer_obj.get("type", {}).get("key")` is the verified way to read peer type from a `get_object` result (`anytype_client.py:44–52`).
- **R1 lead discovery:** `lint.py` gates `contradiction_unresolved` to `tk == "wiki_entity"` (comment "active; wiki_entity only (SF9)"), while the adjacent orphan and stale checks already use `tk in ("wiki_entity", "wiki_concept")`. And `wiki_concept` lacks `wiki_last_reviewed` (BL-1).
- **R1 lead discovery:** the monkeypatch `fake_detect_contradictions` stubs in `test_ingest.py` have signature `(new_facts, obj_id, target, space_id, client, read_client)` with no `kind` — they will raise `TypeError` once CS-6 passes `kind=kind` (SF-1/SF-2).
- `remember.py:_type_for_kind` (~226) already encodes the concept→`wiki_definition` mapping, keyed by `kind` (SF-5).

### Alternatives Considered

**Mixed-kind peers — Option B (same-kind peers only).** Restrict detection to peers of matching kind. Rejected: would silently skip cross-kind peers rather than compare them, leaving real contradictions undetected. `peer_obj.get("type", {}).get("key")` is always present on `get_object` responses, so reading the facts key from the peer's own type (Option A) has no implementation risk.

---

## Proposed Solution

Nine change sites across three source files. Detection extension (CS-1..CS-6, `ingest.py`), and surfacing/resolution affordance (CS-7 `types_schema.py`, CS-8 `lint.py`, CS-9 `ingest.py` degraded-warning discriminator). Tests, README, CHANGELOG, and MIGRATIONS.md are touched at the implementation step.

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

### CS-7 — Add `wiki_last_reviewed` to the `wiki_concept` type (`types_schema.py`, concept properties block, ~101–113) — BL-1

The entity type carries `wiki_last_reviewed` as the resolution affordance for `contradiction_unresolved`; the concept type does not. Mirror the entity entry's exact dict shape into the concept `properties` list:

```python
# Entity block already has (verified, ~types_schema.py:97):
{"property_key": "wiki_last_reviewed", "name": "Wiki Last Reviewed", "format": "date"},

# Add the identical entry to the wiki_concept properties list (after wiki_status, ~line 112):
{"property_key": "wiki_last_reviewed", "name": "Wiki Last Reviewed", "format": "date"},
```

This is additive and idempotent (bootstrap "idempotently creates types, properties"). It is **not** a data migration: existing concepts have no value → reads as unreviewed → flagged, the desired default.

**Schema version bump (verified gate behaviour).** `WIKI_SCHEMA_VERSION` is currently `"0.4.1"` (`types_schema.py:27`). Adding a property to a provisioned type is a schema change; per the established v0.3.0 precedent, bootstrap stamps the new version on the root Collection and `wiki_ingest` against an older-stamped space returns `wiki_schema_outdated` directing the operator to re-run bootstrap. Bump `WIKI_SCHEMA_VERSION` to the next patch (e.g. `"0.4.2"`) as part of this change site so the additive property is honestly versioned and the bootstrap-re-run prompt fires automatically. The implementer confirms the next-version value against the release at impl time.

**Write-side guarantee preserved (BL-1 requirement 5):** detection still writes only `wiki_contradictions`. `_write_contradiction_links` must continue to never touch `wiki_last_reviewed`. Adding the property to the schema does not change any write path — it only gives lint a key to read and the operator a field to set manually.

### CS-8 — Lint surfacing gate for concepts (`lint.py`, `contradiction_unresolved` check, comment "active; wiki_entity only (SF9)", ~490) — BL-1

```python
# Before
# (d) contradiction_unresolved (Critical) — active; wiki_entity only (SF9).
...
if tk == "wiki_entity":

# After
# (d) contradiction_unresolved (Critical) — active; entity+concept (#325).
...
if tk in ("wiki_entity", "wiki_concept"):
```

The body is unchanged: it reads `wiki_contradictions` and resolves via `wiki_last_reviewed` (`if contradictions and not last_reviewed`). With CS-7 providing `wiki_last_reviewed` on concepts, this body works identically for both types. Fix the stale "wiki_entity only (SF9)" comment.

### CS-9 — Kind-discriminated degraded warning (`ingest.py`, `result["warnings"].append("contradiction_detection_degraded")`, ~926) — SF-6

```python
# Before
result["warnings"].append("contradiction_detection_degraded")

# After
result["warnings"].append(f"contradiction_detection_degraded:{kind}")
```

So an operator can tell which path degraded (`contradiction_detection_degraded:entity` vs `:concept`) now that the degrade surface roughly doubles with concepts in scope. Note: the existing entity regression test asserts the warning string; its assertion must be updated to expect `contradiction_detection_degraded:entity` (see Test Plan), and the README/known-limitations wording referencing the warning, if any, updated.

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
| Non-blocking exception handler (`ingest.py`, ~925) | Detection must never block ingest (#287 hard constraint); only the warning *string* changes (CS-9), not the control flow |
| `contradiction_unresolved` check body (`lint.py`, ~491–503) | Only the `tk` gate changes (CS-8); the `wiki_contradictions` read and `wiki_last_reviewed` resolution logic are reused as-is |

---

## Resource Impact

Each Concept update that passes the gate adds O(linked-peers) `get_object` calls + one LLM call — identical shape to the existing entity path, inherited not enlarged (modulo SG-1 below).

**Schema change (revised from R0):** CS-7 adds one property (`wiki_last_reviewed`) to the `wiki_concept` type and bumps `WIKI_SCHEMA_VERSION`. This is an **additive, idempotent bootstrap change**, not a data migration — no backfill, existing objects keep working with an empty value. No new Anytype types or relations. No new dependency. Negligible additional load on the 32 GB Mac Mini.

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

**Deployment:** re-run `wiki-bootstrap` on existing spaces to provision the new `wiki_concept.wiki_last_reviewed` property and stamp the new schema version (idempotent, non-destructive, no backfill). `wiki_ingest` against an un-bootstrapped space returns `wiki_schema_outdated` directing the operator to re-run bootstrap — the same guard rail as prior schema bumps. Recorded in MIGRATIONS.md (see Implementation Plan step 5). No other deployment steps. Rollback is a git revert plus an optional (harmless) leftover property on the type.

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

**`_make_objects_shaped_search_response` (~1168):** add `kind: str = "entity"`:

```python
def _make_objects_shaped_search_response(
    obj_id, name, peer_id, existing_contradictions=None, kind="entity",
):
    rel_key   = "wiki_related"    if kind == "concept" else "wiki_relations"
    facts_key = "wiki_definition" if kind == "concept" else "wiki_facts"
    type_key  = "wiki_concept"    if kind == "concept" else "wiki_entity"
    ...
```

Existing call sites pass no `kind` → default `"entity"` → unchanged.

**`_make_peer_get_object_response` (~1204):** add `kind: str = "entity"` that sets `"type": {"key": "wiki_concept"}` and uses the `"wiki_definition"` property key when `kind == "concept"`. Existing call sites unaffected.

**`_make_concept` in `test_lint.py` (~157):** for CS-8 lint coverage, extend with `wiki_contradictions: list | None = None` and `wiki_last_reviewed: str | None = None` params, mirroring `_make_entity` — the current `_make_concept` builds neither property. (Verified: `_make_concept` has no contradictions/last-reviewed params today.)

### Regression guard tests (entity path)

All `TestContradictionDetection` tests (`test_ingest.py:1224+`) are entity-path tests. Because `detect_contradictions` gains `kind` keyword-only with default `"entity"`, the *real-call* unit tests are truly unchanged; the *monkeypatched* integration tests need the one-line stub touch-up above (and `test_detection_degraded` must update its expected warning string to `contradiction_detection_degraded:entity` per CS-9).

| Test | Guards | R1 touch-up |
|------|--------|-------------|
| `test_contradiction_bidirectional_write` | Bidirectional PATCH; no target GET | stub `**kwargs` |
| `test_no_detection_on_create` | Create branch → no detection call | none (no detection call) |
| `test_detection_degraded` | LLM failure → ingest continues; warning present | stub `**kwargs`; assert `:entity` (CS-9) |
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
All `TestContradictionDetection` entity tests pass after the **stub signature touch-up** (SF-1/SF-2): the real-call unit tests (`test_hallucinated_id_filtered`, `test_self_reference_skipped`) are unchanged; the monkeypatched integration tests get a one-line `**kwargs` stub edit and `test_detection_degraded` updates its expected warning to `:entity`. This remains the primary regression guard — corrected mechanism, not "unchanged across the board".

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

**AC-C11 — Concept contradiction surfaces in lint (BL-1, ticket checkbox 1)**
`test_concept_contradiction_unresolved` in `test_lint.py`, mirroring the entity `test_contradiction_check_active`: a `wiki_concept` with `wiki_contradictions` set and null `wiki_last_reviewed` → `contradiction_unresolved` finding fires with severity `critical`; a normal concept (no contradictions) does not fire; and a concept with `wiki_last_reviewed` set does **not** fire (mirror the entity resolution assertion). Uses the extended `_make_concept`.

### B-side rollback coverage (SG-4 — known gap, not a #325 requirement)
`_write_contradiction_links` is kind-agnostic and locked; the entity suite has no B-side rollback test either (pre-existing debt). Not added here. Noted as a known coverage gap to fold into the SG-1 follow-up ticket.

### Tests must be able to fail before implementation

New concept-path tests (AC-C1, AC-C3..C10) must fail against the current codebase (gate is `kind == "entity"`, no `kind` parameter). AC-C11 must fail against current `lint.py` (gate `tk == "wiki_entity"`) and depends on CS-7 (the concept type must carry `wiki_last_reviewed` for the resolution assertion). This validates each test exercises the new path.

---

## Implementation Plan

Ordered schema → ingest → lint → tests → docs.

1. **Schema (CS-7)** — `src/anytype_llm_wiki/wiki/types_schema.py`:
   - Add `{"property_key": "wiki_last_reviewed", "name": "Wiki Last Reviewed", "format": "date"}` to the `wiki_concept` properties list (mirror the entity entry exactly).
   - Bump `WIKI_SCHEMA_VERSION` (`"0.4.1"` → next patch, confirm value at impl time).

2. **Ingest (CS-1..CS-6, CS-9)** — `src/anytype_llm_wiki/wiki/ingest.py`:
   - Add `_TEXT_KEY_BY_TYPE_KEY` constant + `_facts_key_for_peer` helper (cross-reference `remember.py:_type_for_kind`).
   - Add `kind: str = "entity"` keyword-only param to `detect_contradictions`.
   - Candidate line → `_rel_key(kind)`; peer-facts line → `_facts_key_for_peer(peer_obj)`.
   - Gate → `in ("entity", "concept")`; pass `kind=kind` at the call site; update the "entity-only (LD1)" comment.
   - Degraded warning → `f"contradiction_detection_degraded:{kind}"`.

3. **Lint (CS-8)** — `src/anytype_llm_wiki/wiki/lint.py`:
   - `contradiction_unresolved` gate → `tk in ("wiki_entity", "wiki_concept")`; fix the "wiki_entity only (SF9)" comment to "entity+concept (#325)".

4. **Tests** — `tests/wiki/test_ingest.py` and `tests/wiki/test_lint.py`:
   - Touch up all `fake_detect_*` stub signatures (`**kwargs`); update `test_detection_degraded` expected warning to `:entity`.
   - Extend fixtures: `_make_objects_shaped_search_response(kind=)`, `_make_peer_get_object_response(kind=)`, `_make_concept(wiki_contradictions=, wiki_last_reviewed=)`.
   - Add AC-C1, AC-C3..C11 tests; run full `TestContradictionDetection` + lint contradiction suite green.

5. **Docs** — after tests pass:
   - `README.md:175` — replace "entity-only … (`wiki_concept` scope deferred)" with detection firing for both entity and concept updates, surfaced for both in `wiki_lint`.
   - `README.md:237` — remove "and across Concepts" from the roadmap bullet (shipped).
   - `CHANGELOG.md` — entry: "Contradiction detection + `wiki_lint` surfacing extended to `wiki_concept`; concept type gains `wiki_last_reviewed` (#325)."
   - `MIGRATIONS.md` — under the "Unreleased" section, add an additive-property note: re-run `wiki-bootstrap` to provision `wiki_concept.wiki_last_reviewed` and stamp the new schema version (idempotent, non-destructive, no backfill); `wiki_ingest` on an un-bootstrapped space returns `wiki_schema_outdated`. Match the existing MIGRATIONS.md prose format (see the v0.3.0 entry as the template).

---

## Acceptance Criteria Checklist

Mapping to the three ticket checkboxes (aldeia-box#325). The **surfacing/lint + schema** additions (BL-1) are noted explicitly as in-scope coherence work beyond the literal checkbox text.

- [ ] **Ticket AC-1:** A newly-ingested Concept claim conflicting with an already-linked Concept is detected and cross-linked via `wiki_contradictions`. Covered by spec AC-C1; real-function dispatch by AC-C7. **Plus (BL-1):** the cross-link surfaces in `wiki_lint` as `contradiction_unresolved` — AC-C11.
- [ ] **Ticket AC-2:** Existing Entity behaviour unchanged (regression-guarded). Covered by spec AC-C2 — real-call unit tests unchanged; monkeypatched tests get a one-line stub touch-up (SF-1/SF-2) and the degraded-warning string gains a `:entity` discriminator (CS-9).
- [ ] **Ticket AC-3:** Tests cover the Concept conflict path mirroring the Entity tests. Covered by AC-C3..C11 (concept create/degraded/self-ref/dedup/mixed-kind/multiple-peers/empty-definition/lint).
- [ ] **In-scope coherence (BL-1, flagged for Decide):** `wiki_concept` gains `wiki_last_reviewed` (CS-7) so concept contradictions are resolvable; `lint.py` surfacing gate extends to concepts (CS-8). Additive idempotent bootstrap + schema-version bump; documented in MIGRATIONS.md.

---

## Open Questions

None blocking. The BL-1 surfacing/schema additions are in-scope but flagged for Jan at Decide (he may veto/split into detection-only CS-1..CS-6 vs surfacing CS-7..CS-9). The exact next `WIKI_SCHEMA_VERSION` value is confirmed at impl time against the release.

---

## Deferred Items

| Item | Rationale (concrete) | Tracking |
|------|----------------------|----------|
| SG-1 — unbounded peer fan-out (cap top-N / truncate per-peer text) | Pre-existing for entities; #325 inherits but does not enlarge the fan-out *count*. A cap is a cross-cutting change to the shared loop that would also alter entity behaviour — outside #325's confined scope. | Follow-up ticket |
| SG-2 / SF-6 deeper observability — debug-log on per-peer `get_object` skip and `_facts_key_for_peer` fallback | Pre-existing and equally silent for entities; per-peer logging touches the shared loop, a broader change than this extension. The cheap, in-scope win (kind-discriminated top-level warning) IS done (CS-9). | Follow-up ticket (same as SG-1) |
| SG-4 — B-side rollback test on a concept | `_write_contradiction_links` is kind-agnostic and locked; the entity suite has no B-side rollback test either — pre-existing debt, not a #325 requirement. | Known coverage gap, folded into the SG-1 follow-up |
| Contradiction detection between **unlinked** Objects via semantic pre-filter | Out of scope by ticket definition. | aldeia-box#328 |
