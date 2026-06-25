# Research: Surface concept contradictions in wiki_lint (#426)

**Author:** dev-lead (live-verification; the gating probe requires Anytype MCP access unavailable to
the technical-researcher subagent). **Date:** 2026-06-24.
**Baseline:** post-#325 `main` (lead merged `origin/main` into this branch — see spec-scope.md).

---

## 1. Gating question (verified): can an existing Anytype type gain a property idempotently?

**YES — verified live** against the `wiki-validation-throwaway` space
(`bafyreif52zwqdm3vd4gvensmfvthncmwlnlhqi3brxezjdh5nhwsuxhesq.meysp1f5qul1`) via the `anytype` MCP.

### Probe transcript (create scratch type → exercise update-type → delete)
1. `API-create-type` key=`wiki_probe_426`, properties `[wiki_definition(text), wiki_status(select)]`.
   → live type props: `[tag, backlinks (system, auto-added), wiki_definition, wiki_status]`.
2. `API-update-type` sending **only** `[wiki_contradictions(objects)]`.
   → live type props became `[tag, backlinks, wiki_contradictions]`. **`wiki_definition` and
   `wiki_status` were DROPPED.**
3. `API-update-type` sending the full union `[wiki_definition, wiki_status, wiki_contradictions]`.
   → all three present; **`wiki_definition` retained its ORIGINAL property id** (`…dohmam3l`) →
   re-sending an existing key **links** the existing space-level property, does not duplicate.
4. `API-update-type` repeating the identical union → byte-identical result, same ids → **idempotent
   no-op**.
5. `API-delete-type` `wiki_probe_426` → cleaned up.

### Verified contract (the central correctness constraints for the spec)
- **`update-type` REPLACES the user-defined property set.** Any declared property omitted from the
  call is removed from the type. **System properties** (`tag`, `backlinks`, created_date, creator,
  links — Anytype-managed) are auto-preserved and need not be sent.
- **Consequence — the new bootstrap capability MUST be read-modify-write:** for each provisioned wiki
  type, `get_type` (or reuse the `list_types` entry) → read its live property keys → compute the
  declared-but-missing set from `WIKI_TYPES` → if non-empty, call `update_type` with the **union**
  (live user properties + missing declared ones), each as `{key, name, format}`. Sending only the
  delta would silently destroy existing properties — a graph-corruption footgun.
- **Re-sending existing keys links, not duplicates** (stable property id) → the union call is safe
  and idempotent. When the missing set is empty, **skip the call entirely** (no-op, no wasted write).
- `API-update-type` request `properties[]` items require `{key, name, format}`; `format` enum
  includes `objects`, `date`, `text`, `select`, `multi_select`, etc. (matches `WIKI_TYPES` formats).
- The MCP/REST endpoint is `PATCH /v1/spaces/{space_id}/types/{type_id}` (mapped to `API-update-type`).
  `type_id` (not `type_key`) is required — resolve it from the existing `list_types` result bootstrap
  already fetches (`bootstrap.py:271`).

> This closes #325's open question (#325/spec.md §384: "implementer must verify the Anytype
> `API-update-type` / property-link endpoint exists and behaves idempotently"). It does, with the
> replace-not-merge caveat above.

---

## 1b. Read-side probe (BL-6.4 / council Advisory 1 / addendum item 2) — VERIFIED

**Date:** 2026-06-25 (test phase, dev-lead via `anytype` MCP).
The §1 probe verified the *write* contract. This closes the carried-forward *read* contract:
the exact `get_type` (raw `GET /v1/spaces/{id}/types/{type_id}`) response shape, against a
bootstrapped wiki type in `wiki-validation-throwaway`
(`bafyreif52zwqdm3vd4gvensmfvthncmwlnlhqi3brxezjdh5nhwsuxhesq.meysp1f5qul1`).

Probed type `wiki_t_2` (`bafyreibtkkasylnmyatcdeb5s65mavjqhdc5bwush4cmmcyg53skwsrpum`), a
bootstrapped wiki-style type carrying a system+user property mix.

### Observed `get_type` response (verbatim shape)
```json
{"type": {
  "object": "type", "id": "bafyrei…rpum", "key": "wiki_t_2", "name": "T2",
  "plural_name": "T2s", "icon": null, "archived": false, "layout": "basic",
  "properties": [
    {"object":"property","id":"bafyrei…ipba","key":"tag","name":"Tag","format":"multi_select"},
    {"object":"property","id":"bafyrei…3mke","key":"backlinks","name":"Backlinks","format":"objects"},
    {"object":"property","id":"bafyrei…gn7m","key":"wiki_excerpt","name":"Excerpt","format":"text"},
    {"object":"property","id":"bafyrei…6cum","key":"wiki_domain_tags","name":"Domain Tags","format":"multi_select"}
  ]
}}
```

### Verified read contract (the test mocks MUST mirror this)
- **Envelope:** the response wraps the type in a top-level `"type"` key →
  `resp.json()["type"]` (spec §2 `get_type` is correct).
- **Per-property field set:** each entry carries `object`, `id`, **`key`** (NOT
  `property_key`), **`name`**, **`format`**. So on the read side the accessor is `p["key"]`
  and `name`/`format` ARE present per entry. (The spec's tolerant `p.get("key") or
  p.get("property_key")` is correct — live data uses `key`.)
- **Pagination: NONE.** The single-type `get_type` response has **no `pagination` key** and
  no nested pagination on `properties[]`; the array is returned inline and complete. (Only the
  *list*-types response carries a top-level `pagination` block; `get_type` does not.) →
  the §3 pagination/shape guard (`pag.get("has_more") is True`) never fires on a real read,
  so the guard is a defensive backstop, exercised only by a synthetic mock (addendum item 3 /
  Advisory 3). System props (`tag`, `backlinks`) ARE echoed in the read and must be filtered
  via `SYSTEM_PROP_KEYS` before building the union (spec §3 does this).

### Consequences for the test phase
- **Normal/success `get_type` mock** → mirror the shape above: `{"type": {"id","key","properties":[{object,id,key,name,format}, …]}}`, **NO `pagination` key** (this is the real contract — addendum item 2's "at least one mock mirrors the actual observed shape").
- **Pagination-abort mock** (addendum item 3) → a *synthetic* `{"type": {"key":…, "pagination": {"has_more": true}}}` or a `get_type` missing the `properties` key, to drive the guard → assert reconcile ABORTS with a `warnings[]` entry and NO `update_type` PATCH. Note in the test that this shape is synthetic (the live API does not paginate single-type reads) — the guard defends against an unadvertised future change.

---

## 2. Current-main integration map (verified by reading the files post-merge)

### 2a. Detection — already done (#325), no change needed
`ingest.py:944` `if kind in ("entity", "concept")` gates `detect_contradictions` + `_write_
contradiction_links`. Concept candidates traverse `wiki_related` (vs entity `wiki_relations`) and read
`wiki_definition` (vs entity `wiki_facts`) via the #325 `_facts_key_for_peer` / `_REL_KEY_BY_KIND`
helpers. Peer reads go through `get_object` (the proven path). **#426 adds NO detection code.**

### 2b. Surfacing gap — the core of #426
`lint.py:487-503`, finding "(d) `contradiction_unresolved` (Critical)":
```python
# (d) contradiction_unresolved (Critical) — active; wiki_entity only (SF9).
if tk == "wiki_entity":
    contra_prop = _prop(o, "wiki_contradictions")
    contradictions = _parse_relation_elements(contra_prop.get("objects")) if contra_prop else []
    reviewed_prop = _prop(o, "wiki_last_reviewed")
    last_reviewed = reviewed_prop.get("date") if reviewed_prop else None
    if contradictions and not last_reviewed:
        findings.append(_finding("critical", "contradiction_unresolved", o, space_id,
            f"{len(contradictions)} unresolved contradiction(s) — set wiki_last_reviewed to resolve"))
```
**Change:** `tk == "wiki_entity"` → `tk in ("wiki_entity", "wiki_concept")`; correct the stale
"wiki_entity only (SF9)" comment. Body is otherwise reusable as-is — it reads `wiki_contradictions`
(objects, bare-ID strings per mem0 56845bac) and resolves via `wiki_last_reviewed`. Severity is
`critical` (note: README/server docstrings historically said "High" — #325 already corrected README;
actual code is `critical` at `lint.py:500`).

### 2c. Schema gap — `wiki_concept` lacks the resolve field
`types_schema.py` `wiki_concept` properties: definition, open_questions, related, sources, domain_tags,
**wiki_contradictions** (present), status — **no `wiki_last_reviewed`.** `wiki_entity` has it
(`:97`). Without it, lint would flag concept contradictions `critical` with no way to mark them
resolved (the broken UX #325 §380 warned against).
**Change:** add `{"property_key": "wiki_last_reviewed", "name": "Wiki Last Reviewed", "format": "date"}`
to `wiki_concept`; bump `WIKI_SCHEMA_VERSION` (0.4.1 → next, e.g. 0.4.2) since the declared schema grows.

### 2d. Bootstrap gap — cannot provision a property onto an existing type
`bootstrap.py:279-285`: existing types are `continue`d with `types_skipped: already_exists` — the
inline create-and-link path (`create_type`) is the ONLY place properties get linked, so it never runs
for an existing type. `bootstrap.py:330-353` only *reports* properties created/skipped at the space
level; it never links one onto a live type. → On an already-bootstrapped space, adding
`wiki_last_reviewed` to the `wiki_concept` schema does nothing without a new capability.
**Change:** add an idempotent "reconcile declared properties onto existing types" step (read-modify-
write `update_type`, §1). `wiki_client.py` has `create_type`/`list_types`/`list_properties` but **no
`update_type`** — add a thin `update_type(space_id, type_id, payload)` wrapper (mirror `create_type`).

### 2e. wiki_client method inventory
`wiki_client.py`: `create_type` (:18), `create_property` (:25), `create_tag` (:36), `list_types`
(:119), `list_properties` (:123), `list_tags` (:127). **Add `update_type`.** It maps to
`API-update-type` / `PATCH …/types/{type_id}`.

---

## 3. Test surface (verified against current tests)
- `tests/wiki/test_lint.py`: `_make_entity` (:117) already takes `wiki_last_reviewed` (:124) and
  builds the `wiki_contradictions`/`wiki_last_reviewed` props; `_make_concept` (:157) takes neither.
  **Extend `_make_concept` to mirror `_make_entity`** (add `contradictions`/`wiki_last_reviewed`
  params), then add `test_concept_contradiction_unresolved` mirroring the entity contradiction test:
  concept w/ contradictions + null reviewed → fires `critical`; w/ reviewed set → does not fire; w/o
  contradictions → does not fire. **Must fail against current `lint.py`** (entity-only gate).
- `tests/wiki/test_bootstrap.py`: add coverage for the reconcile step — given an existing type missing
  a declared property, bootstrap calls `update_type` with the union (existing + missing) and reports
  it; given a type already complete, **no `update_type` call** (idempotent no-op); existing properties
  are never dropped. Use the existing fake/stub client pattern in that file.

## 4. Risks / watch-items for the spec
- **Replace-not-merge footgun** (§1): the reconcile step must send the union, never the delta. This is
  the single highest-risk correctness point — call it out explicitly with a regression test asserting
  pre-existing properties survive.
- **System-property handling:** do not attempt to send Anytype system props (`tag`, `backlinks`,
  `created_date`, `creator`, `links`) — they are auto-managed. The union is over *declared wiki*
  properties + whatever user/wiki properties `list_types` reports for the type (excluding system ones
  if the API echoes them; the probe showed system props are re-added regardless, so sending only the
  wiki-declared union is sufficient and safest).
- **Schema-version bump** triggers bootstrap's `schema_upgrade` path (`bootstrap.py` upgrade detection
  via WikiLog `wiki_schema_version`). Ensure the reconcile step runs on the upgrade path so existing
  spaces actually get the new property.
- **Idempotency / no wasted writes:** skip `update_type` when the missing-property set is empty.
- Keep all peer/object reads on `get_object`/`list_objects` (proven path); do not read relation arrays
  off search responses (mem0 8f597af8).

## 5. Sources
- Live Anytype MCP probe (this session) — `wiki-validation-throwaway` space.
- `#325/spec.md` "Recommended Follow-Up" (§368-389) — the surfacing blueprint and BL-R2-1 finding.
- Current-main source: `lint.py`, `bootstrap.py`, `types_schema.py`, `wiki_client.py`, `ingest.py`.
- Mem0: 8f597af8 (search vs get_object), 56845bac (objects-format bare IDs), a2d84e10 (#325 council
  closure-condition pattern), 06f09aa7 (select/multi_select id write shape).
