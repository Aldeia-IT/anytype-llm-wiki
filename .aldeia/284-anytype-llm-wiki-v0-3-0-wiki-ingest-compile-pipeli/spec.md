---
name: anytype-llm-wiki-v0-3-0-wiki-ingest-compile-pipeli
status: DRAFT
issue: 284
repo: anytype-llm-wiki
target_repo: anytype-llm-wiki
date: 2026-06-03
author: spec-writer agent
parent_spec: 140-wiki-library-module-port-llm-wiki-pattern-onto-any
---

# anytype-llm-wiki v0.3.0 — `wiki_ingest` Compile Pipeline

**Status:** DRAFT
**Date:** 2026-06-03
**Author:** spec-writer agent
**Review rounds:** 0

---

## 1. Summary / Relationship to Master Spec

This is the **v0.3.0 increment spec** for `anytype-llm-wiki`. The master spec
(`.aldeia/140-wiki-library-module-port-llm-wiki-pattern-onto-any/spec.md`, status SPEC,
council-approved) is the authoritative design baseline for the entire module. It already
specifies `wiki_ingest` in depth (see sections: "Ingest Pipeline (wiki.ingest — v0.3.0)"
~line 345, "Entity Resolution Semantics" ~line 1177, "Extraction Prompt Structure" ~line
1306, "Schema Compatibility / Upgrade Story" ~line 1588, "Concurrent Ingest Policy" ~line
1572, "SSRF protections" ~line 1671, "Failure modes per tool" ~line 1637,
"Configuration" ~line 1539, and "v0.3.0 delivery phase ACs" ~lines 820-839).

This spec does NOT re-derive those designs. It:

1. Resolves the **three open decisions** the master spec deliberately left to "v0.3.0 time."
2. **Locks the now-verified Anytype API constraints** — collapses the master spec's conditional
   dual code paths to the single verified path, per `patch-decision.md` (2026-06-03).
3. **Adds the newly-discovered indexer property-gap requirement** — not in the master spec.
4. **Firms the v0.3.0 acceptance criteria**, adding ACs for the new/resolved items while
   inheriting the master spec's ACs 1-19 as the baseline.

Released so far: v0.1.0 (`semantic_search`, `reindex_anytype`); v0.2.0 (`wiki_bootstrap`,
`doctor`, verification script). v0.3.0 = this spec's implementation target.

---

## 2. Problem Statement

### 2.1 The Compile-Step Gap

v0.2.0 shipped the foundation: a typed wiki schema, bootstrap, doctor, and basic indexing.
There is no way to populate the wiki automatically. Karpathy's "compile once, query later"
premise requires ingestion — `wiki_ingest` is the compile step. Without it, every wiki object
must be hand-created (demonstrated in the `llm-wiki-test` space).

### 2.2 The Indexer Property Gap (NEW — release blocker)

Reproduced live (`llm-wiki-test`): `objects_checked: 22, objects_indexed: 0`. Root cause:
`chunker.py:chunk_object` chunks only `obj.get("markdown")` (the body returned by
`GET /objects/{id}?format=md`). Wiki objects store their knowledge in **properties**
(`wiki_facts`, `wiki_description`, `wiki_definition`, etc.), not in the body. So a freshly
curated wiki produces 0 chunks and is invisible to `semantic_search`. The entire retrievability
premise fails.

This gap is not in the master spec — it was discovered post-v0.2.0 during live curation. It is
a release blocker for v0.3.0 because `wiki_ingest` would write correct objects that remain
unretrievable.

### 2.3 Open Decision: Schema-Version Marker Home

Master spec (§Schema Compatibility, AC #13) specifies the **root Collection** carries
`wiki_schema_version`. v0.2.0 stamped it on per-run **WikiLog** objects because the system
`collection` type "did not reliably persist a custom property" (`known-limitations.md` #2).
v0.3.0 `wiki_ingest` is the first consumer that reads the marker on entry — a single
authoritative value is now required. The marker home must be reconciled.

### 2.4 Open Decision: `wiki_action` Select-Tag Pre-Creation

`wiki_action` is a `select` property on `wiki_log`. Writing a select value requires a
pre-existing tag option id. v0.2.0 dropped `wiki_action` silently on bootstrap WikiLog writes
(`known-limitations.md` #3, `impl-review-r2.md` SHOULD-FIX-2). v0.3.0 writes a WikiLog per
ingest and must populate `wiki_action = ingest`.

### 2.5 Locked Constraints (Post-Verification Findings)

`patch-decision.md` (Anytype API `2025-11-08`, recorded 2026-06-03) records three verified
facts that make the master spec's conditional code-path discussion obsolete:

- `patch_body_updates: silently_ignored` — body PATCH returns 2xx but the content is not persisted.
- `patch_property_updates: works` — property PATCH is the durable write mechanism.
- `filter_expression: no_op` — `type_key` FilterExpression in Anytype search returns the full
  result set regardless of filter value.

---

## 3. Scope

### In Scope

All items in master spec §v0.3.0 Scope (in) (~line 800), plus v0.3.0-specific additions:

| File | Nature |
|------|--------|
| `wiki/fetch.py` | New — URL fetching with SSRF protections and markdownify HTML→markdown |
| `wiki/extraction.py` | New — LLM extraction pipeline (Ollama / hosted), JSON schema validation, repair retry |
| `wiki/prompts/extraction.md` | New — committed extraction prompt (human-readable, versionable) |
| `wiki/ingest.py` | New — ingest orchestration |
| `wiki/cli.py` | Extend — `wiki-ingest` subcommand |
| `server.py` | Extend — register `wiki_ingest` tool |
| `pyproject.toml` | Extend — add `markdownify>=0.11.0,<0.12.0` and `pydantic>=2.6,<3.0` |
| `tests/wiki/test_ingest.py`, `test_fetch.py`, `test_extraction.py` | New |
| **`src/anytype_llm_wiki/chunker.py`** | **Extend (NEW to v0.3.0 scope) — property-embedding for wiki objects** |
| **`wiki/bootstrap.py`** | **Extend (NEW to v0.3.0 scope) — add schema-marker PATCH + `wiki_action` tag creation** |

The last two rows are additions beyond the master spec's v0.3.0 scope list, necessitated by the
indexer gap and the marker/tag decisions resolved in this spec.

### Out of Scope

Per master spec §v0.3.0 Scope (out): `wiki_query` (v0.4.0), `wiki_lint` (v0.5.0), automated
`wiki_contradictions` (v0.6.0), PDF / JavaScript-rendered sources, automatic comparison
creation, concurrent ingest of the same space.

---

## 4. Resolved Decisions

### Decision 1 — Indexer Property-Gap Closure

**Problem:** `chunker.py:chunk_object` (current implementation) reads only
`obj.get("markdown")`. Wiki objects authored via `wiki_ingest` store their knowledge in text
properties, not in the body. After ingest, 0 chunks are produced and the objects are invisible
to `semantic_search`.

**Why not "write a body at ingest time" (Approach a)?**
`patch-decision.md: patch_body_updates: silently_ignored`. Body content persists on object
CREATE (the initial body is stored), but a `body` PATCH is silently dropped. On the
re-ingest / update path, ingest can only update via property PATCH — the body cannot be
refreshed. Any knowledge written to the body at create-time becomes stale on first update.
**Approach (a) is explicitly rejected.** It cannot maintain body freshness on the update path
without delete-and-recreate (which breaks inbound Relations). This matches the Mem0 principle:
deprecate rejected approaches explicitly.

**Resolution — Approach (b): extend `chunker.py` only.**

The fix is a **purely additive change to `chunker.py`**. The indexer already calls
`chunk_object(obj)` where `obj` is the dict from `get_object`; both `list_objects` summary
objects and (likely) single-object GET responses carry a `properties[]` array. The chunker
extension reads `obj.get("properties", [])` and emits one chunk per allowlisted key with a
non-empty `text` value.

**`WIKI_TEXT_PROPERTY_KEYS` allowlist (module-level constant in `chunker.py`):**

```python
WIKI_TEXT_PROPERTY_KEYS = frozenset({
    "wiki_facts",         # wiki_entity — key facts bullet list
    "wiki_description",   # wiki_entity — synthesized description
    "wiki_definition",    # wiki_concept — concept definition
    "wiki_open_questions", # wiki_concept — unresolved questions
    "wiki_dimensions",    # wiki_comparison — comparison axes
    "wiki_verdict",       # wiki_comparison — synthesis conclusion
    "wiki_question",      # wiki_query — the question text
    "wiki_answer",        # wiki_query — the synthesized answer
})
```

`wiki_excerpt` (`wiki_source`) is **excluded** from this allowlist. The Source object's excerpt
is derived from the origin document body which is already chunked from the markdown body on
initial create. Including `wiki_excerpt` would double-index the opening content.
WikiLog properties (`wiki_subject`, `wiki_notes`, etc.) are excluded entirely — they are
operational metadata, not knowledge.

**Property-key to display-name heading map (embedded in `chunker.py` or a co-located constant):**

| Property Key | `heading` value |
|---|---|
| `wiki_facts` | `Facts` |
| `wiki_description` | `Description` |
| `wiki_definition` | `Definition` |
| `wiki_open_questions` | `Open Questions` |
| `wiki_dimensions` | `Dimensions` |
| `wiki_verdict` | `Verdict` |
| `wiki_question` | `Question` |
| `wiki_answer` | `Answer` |

**Chunk metadata shape** (identical to body chunks — no schema change to Qdrant):

```python
{
    "object_id":   obj["id"],
    "space_id":    obj.get("space_id", ""),
    "object_name": obj.get("name", ""),
    "type_key":    obj.get("type", {}).get("key", "unknown"),
    "heading":     "<display_name_from_map>",
    "text":        <property text value>,
}
```

**Dedup guard:** emit property chunks **only when the object's `markdown` body is empty or
absent**. If a non-empty body is present (e.g. on a manually created object with body content,
or the first-create body of a wiki object), the body chunks already cover the content. Property
chunks supply the structured representation for objects with blank bodies — the normal state
after property-only ingest.

**Chunk splitting:** Each property value is split by the existing `_split_large` function if it
exceeds `MAX_CHUNK_CHARS` (1500 chars). This is important for `wiki_facts`, which accumulates
bullet points across multiple ingests and may grow to several KB.

**Blast-radius safety:** The allowlist is explicitly scoped to `wiki_*` keys. An ordinary
Anytype note or page with properties like `name`, `description`, `status` will have none of its
property keys in `WIKI_TEXT_PROPERTY_KEYS`. The behavior of `chunk_object` for non-wiki objects
is unchanged. The `wiki_` prefix is reserved by the module.

**Pre-release verification items:**

- **V1 (MUST):** Confirm `GET /v1/spaces/{id}/objects/{id}?format=md` response includes
  `properties[]` in the returned object dict. Pass criterion: `get_object()` result contains a
  `"properties"` key that is a list. Fail action: add a step in the indexer (`indexer.py`) to
  carry the summary object's `properties[]` into the full-object dict before calling
  `chunk_object` — the indexer already has the summary at that point (`_get_last_modified` reads
  it from the summary, `indexer.py` lines 40-45).

- **V2 (MUST):** After a property PATCH (`update_object` with a `properties` payload), confirm
  `last_modified_date` is updated in the object returned by `list_objects`. Pass criterion:
  re-read via `list_objects`, compare `last_modified_date` before and after PATCH — the value
  must increase. Fail action: the incremental reindex (`indexer.py:_get_last_modified`) will
  miss property-only updates; a full-reindex trigger or a different change-detection field is
  required.

```mermaid
flowchart TD
    A["chunk_object(obj)"] --> B{markdown present\nand non-empty?}
    B -->|yes| C[emit body chunks\nexisting path unchanged]
    B -->|no| D[scan obj.get('properties',[])]
    D --> E{key in\nWIKI_TEXT_PROPERTY_KEYS?}
    E -->|no| F[skip — non-wiki or\nnon-embeddable property]
    E -->|yes| G{text value\nnon-empty?}
    G -->|no| F
    G -->|yes| H[split if > MAX_CHUNK_CHARS]
    H --> I[emit chunk with heading=display_name]
    C --> Z[return chunks]
    I --> Z
```

### Decision 2 — Schema-Version Marker Home Reconciliation

**Context:** The master spec (§Schema Compatibility, ~line 1590) specifies the root Collection
carries `wiki_schema_version`. v0.2.0 implemented the WikiLog stamp instead; the root
Collection in live spaces carries no `wiki_schema_version` property
(`impl-review-r2.md` gate table). v0.3.0 `wiki_ingest` is the first consumer that reads the
marker — a single authoritative value is now mandatory.

The key ambiguity: the v0.2.0 finding (`known-limitations.md` #2) says the system `collection`
type "did not reliably persist a custom property." Under the verified `patch_property_updates:
works` path, it is unclear whether this applies to system-typed objects (the PATCH is silently
dropped at the type-schema level) or whether the fix was simply not attempted. This cannot be
resolved without a live probe.

**Primary design — Option (a): stamp the root Collection (aligns with master spec and AC #13)**

After `_run_bootstrap` creates or locates the root Collection (`bootstrap.py` lines 374-387),
add a best-effort PATCH step:

```python
# bootstrap.py — after collection id is known
try:
    client.update_object(
        space_id,
        collection_id,
        {"properties": [{"key": "wiki_schema_version", "text": WIKI_SCHEMA_VERSION}]},
    )
except Exception as exc:
    logger.warning("wiki_schema_version_patch_failed", detail=str(exc))
    # WikiLog stamp (retained below) acts as fallback
```

The WikiLog stamp (`bootstrap.py:416`) is **retained as informational fallback** — do not
remove it.

**Schema-compat read order (used by `wiki_ingest` and all subsequent tools):**

```mermaid
flowchart TD
    A[schema compat check] --> B[list_objects to find root Collection\nname='Wiki', type.key='collection']
    B --> C{wiki_schema_version\nin collection properties[]}
    C -->|found| D[use as authoritative version]
    C -->|not found| E[scan all wiki_log objects\nfind _max_version across properties[]]
    E --> F{any version found?}
    F -->|found| G[use as fallback version\nv0.2.0 space or silent PATCH failure]
    F -->|not found| H[[CONFIG ERROR\nwiki_schema_missing]]
    D --> I{version comparison}
    G --> I
    I -->|older than code| J[[CONFIG ERROR\nwiki_schema_outdated]]
    I -->|equal| K[proceed]
    I -->|newer than code| L[warn and continue\nwiki_schema_newer]
```

**Migration for v0.2.0 spaces:**

1. First v0.3.0 `wiki_bootstrap` run scans objects, finds `wiki_schema_version=0.2.0` on a
   WikiLog (the fallback read path).
2. Detects `is_upgrade = True` (0.2.0 < 0.3.0), runs the upgrade path.
3. On completion, PATCHes the root Collection with `wiki_schema_version=0.3.0`.
4. All subsequent reads find the marker on the Collection (Option a) with the WikiLog as
   fallback.

For v0.2.0 spaces that run `wiki_ingest` before re-running `wiki_bootstrap`: the fallback read
path finds the WikiLog markers and returns `0.2.0`, which triggers `wiki_schema_outdated`,
directing the operator to run `wiki_bootstrap` — which is then safe to run (bootstrap handles
outdated schema as informational, not fatal; master spec §Schema Compatibility ~line 1599).

**Fallback design — Option (b-1): idempotent single-named WikiLog marker**

If pre-release gate V4 (see §10) confirms that custom property PATCH on the system `collection`
type is silently dropped (V4 fails), the implementation pivots to Option (b-1):

- On first bootstrap, create one canonical "schema marker" WikiLog entry with a stable object
  name `wiki:schema-marker` using the existing `create_object` path for `wiki_log` type.
- On re-bootstrap, detect this marker by name (search for `wiki_log` objects named
  `wiki:schema-marker`) and PATCH its `wiki_schema_version` property via `update_object`.
- On upgrade, PATCH the same named marker object.
- `_found_schema_version` reads from the named marker (primary), falls back to
  `_max_version` over all `wiki_log` objects (handles spaces before Option b-1 was adopted).

The `wiki_log` type is wiki-owned (not a system type), so custom properties are guaranteed to
persist. This avoids the collection-type PATCH uncertainty entirely.

**Option (b-1) is the deterministic fallback.** Implementation must be ready to pivot; the
pre-release gate V4 decides which ships. This resolves `known-limitations.md` #2 and
`impl-review-r2.md` SHOULD-FIX-1 / ADVISORY-1.

### Decision 3 — `wiki_action` Select-Tag Pre-Creation

**Problem:** `wiki_action` is a `select` property on `wiki_log`. Writing a select value
requires a pre-existing tag option id (not a name). v0.2.0 dropped `wiki_action` silently on
bootstrap WikiLog writes because no tag was pre-created (`known-limitations.md` #3,
`impl-review-r2.md` SHOULD-FIX-2).

**Resolution: create all five `wiki_action` tag options during `wiki_bootstrap`.**

Bootstrap already creates `wiki_domain_tags` options via `create_tag` in a tag-creation loop
(`bootstrap.py:331-367`). The same infrastructure handles `wiki_action` tags with union-only
re-bootstrap semantics (detect existing tags by name, skip already-present, create missing).

**Full enum to create:** `ingest`, `query`, `lint`, `bootstrap`, `archive`
(all five; later tool versions inherit them without additional bootstrap changes).

**Bootstrap call sequence (added to `_run_bootstrap`):**

```python
action_pid = prop_map.get("wiki_action")
if action_pid:
    existing = {t["name"] for t in client.list_tags(space_id, action_pid)}
    for value, color in zip(
        ["ingest", "query", "lint", "bootstrap", "archive"],
        TAG_COLOR_PALETTE[:5],  # cycle from existing palette
    ):
        if value not in existing:
            client.create_tag(space_id, action_pid, {"name": value, "color": color})
    all_tags = client.list_tags(space_id, action_pid)
    action_tag_id_map = {t["name"]: t["id"] for t in all_tags}
    # use action_tag_id_map["bootstrap"] when writing the bootstrap WikiLog
```

**In `wiki_ingest` — WikiLog write with `wiki_action = ingest`:**

```python
# ingest.py — resolve ingest tag id before WikiLog write
try:
    action_pid = prop_map.get("wiki_action")
    action_tag_id = None
    if action_pid:
        all_tags = client.list_tags(space_id, action_pid)
        action_tag_id = {t["name"]: t["id"] for t in all_tags}.get("ingest")
except Exception:
    action_tag_id = None  # degraded: WikiLog written without wiki_action

log_props = [...]
if action_tag_id:
    log_props.append({"key": "wiki_action", "select": action_tag_id})
else:
    result["warnings"].append(
        "wiki_action_tag_not_found: WikiLog written without action discriminator"
    )
# WikiLog is always written regardless
```

**Tag-resolution failure must NOT abort ingest.** The WikiLog is always written (degraded-but-
written behavior). Failure adds a warning to `IngestResult.warnings`. This matches the existing
error-tolerance pattern in `bootstrap.py:429-434`.

**Backward compatibility:** v0.2.0 spaces have no `wiki_action` tags. Running `wiki_ingest`
against a v0.2.0 space that has not been re-bootstrapped: `list_tags` returns empty,
`action_tag_id = None`, WikiLog is written without `wiki_action` (same state as v0.2.0). The
schema-compat check enforces that `wiki_bootstrap` must be run before `wiki_ingest` on an
outdated-schema space — after re-bootstrap, all five tags exist.

This resolves `known-limitations.md` #3 and `impl-review-r2.md` SHOULD-FIX-2.

---

## 5. Locked Constraints

These are verified facts from `patch-decision.md` (Anytype API `2025-11-08`, 2026-06-03).
They are not assumptions — they are recorded API behavior. The master spec carried conditional
code paths pending verification; verification is complete. **One path ships.**

### 5.1 Body PATCH Is Silently Ignored — Properties Only

**Verified:** `patch_body_updates: silently_ignored`. Implementation path:
`fallback_properties_only`.

**Impact on `wiki_ingest`:** all content updates (entity descriptions, facts, concept
definitions) use **property PATCH only**. The markdown `body` field in an `update_object` call
is never used for content; if present it will be silently dropped. The master spec (§Ingest
Pipeline ~line 440-447) included both "Primary path — PATCH body works" and "Fallback path —
PATCH body silently ignored" as conditional branches. **The Primary path branch is explicitly
deleted from the implementation.** Only the fallback path ships.

This is the Mem0 principle in practice: deprecate rejected approaches explicitly. Test writers
and impl workers must NOT implement a body-update path.

**Impact on chunker:** the body at initial create-time may contain content (the v0.1.0/v0.2.0
behavior was to create with a body). On re-ingest / update, the body cannot be refreshed.
Property chunks (Decision 1) are therefore the only reliable embedding surface for wiki objects
across their full lifecycle.

### 5.2 Type-Key FilterExpression Is a No-Op — Client-Side Filtering

**Verified:** `filter_expression: no_op`. A `type_key` FilterExpression in Anytype's search
API returns the full result set regardless of the filter value.

**Impact on entity resolution** (master spec §Entity Resolution Semantics pseudocode,
~lines 1259-1302):

The pseudocode at steps 1 and 2 calls `client.search(space_id, ..., filter={"type_key":
type_key})`. Because this filter is a no-op, **both calls return all objects regardless of
type**. The implementation must filter client-side in Python after receiving the result set:

- **Step 1 (normalized-title exact match):** fetch candidates, then filter by
  `normalize_title(o["name"]) == normalized` AND `o.get("type", {}).get("key") == type_key`
  in Python.
- **Step 2 (title-fuzzy match):** fetch all same-type objects by calling
  `client.search(space_id, query="")` and filtering client-side by
  `o.get("type", {}).get("key") == type_key` before iterating over them for `SequenceMatcher`.
- **Step 3 (embedding similarity sweep):** uses the **Qdrant payload `type_key` filter**,
  which works correctly (Qdrant payload filters are not affected by the Anytype FilterExpression
  no-op). The Qdrant query passes `type_key=type_key` as a payload filter in the vector search.

This must be made explicit in `wiki/ingest.py` — the `client.search` calls in the resolution
function must not pass `filter={"type_key": ...}` expecting Anytype to scope the results;
that argument should either be dropped or the post-filter must be applied unconditionally.

### 5.3 Property PATCH Works — Durable Write Mechanism

**Verified:** `patch_property_updates: works`. Property PATCH via `update_object(space_id,
object_id, {"properties": [...]})` persists and reads back from `list_objects`.

**Impact:** property updates are the single durable mechanism for all content written by
`wiki_ingest` on the update path. This also means Decision 2 Option (a) (PATCH
`wiki_schema_version` on the root Collection) is plausible if the system collection type
allows custom property linking.

---

## 6. Design References

The following table maps each `wiki_ingest` design concern to the master spec section that
governs it. This spec does not re-derive those designs. Where a v0.3.0 delta applies, it is
noted.

| Concern | Master spec section | v0.3.0 delta |
|---------|-------------------|--------------|
| Ingest data flow (Mermaid) | §Ingest Pipeline (wiki.ingest — v0.3.0) ~line 345 | No change |
| `wiki_ingest` MCP tool signature | §Ingest Pipeline ~line 379 | Add `wiki_action` tag resolution step in pipeline |
| IngestResult schema | §Ingest Pipeline ~line 391 | No change |
| Ingest pipeline steps 1-9 | §Ingest Pipeline ~lines 416-438 | Step 4 entity resolution: type filter must be client-side (§5.2); step 7 WikiLog must include `wiki_action` (Decision 3) |
| PATCH update path | §Ingest Pipeline ~lines 440-447 | **Primary path deleted.** Only fallback (properties-only) ships. See §5.1. |
| URL fetch + SSRF protections | §SSRF protections ~line 1671 | No change; `scrub_credentials` applies to extraction endpoint in startup log |
| `markdownify` HTML→markdown | §Ingest Pipeline step 2 ~line 419 | No change |
| Extraction prompt + JSON schema validation | §Extraction Prompt Structure ~line 1306 | No change |
| Extraction retry + repair | §Extraction Prompt Structure ~line 1368 | No change |
| `normalize_title` contract | §Entity Resolution Semantics ~line 1177 | No change |
| Entity resolution pseudocode | §Entity Resolution Semantics ~lines 1259-1302 | Steps 1-2: client-side type filter required (§5.2). Step 3: Qdrant payload filter works correctly |
| Bidirectional relations + rollback | §Ingest Pipeline step 6 ~line 428; AC #13 | No change |
| WikiLog always written | §Ingest Pipeline step 7 ~line 429 | Add `wiki_action = ingest` (Decision 3); tag-resolution failure: degraded-but-written |
| Concurrent ingest lock (fcntl.flock) | §Concurrent Ingest Policy ~line 1572 | No change; tests MUST use `multiprocessing.Process` (Mem0 learning) |
| Schema-compat read + upgrade | §Schema Compatibility / Upgrade Story ~line 1588 | Marker read order updated: Collection first, WikiLog fallback (Decision 2, §4.2) |
| Configuration env vars | §Configuration ~line 1539 | No change for new v0.3.0 vars; `wiki_action` tags covered by bootstrap |
| Failure modes table | §Failure modes per tool ~line 1637 | Add: `wiki_action_tag_not_found` warning (degraded WikiLog) |
| Resource impact | §Resource Impact ~line 1617 | No change |
| Security: token handling + scrub | §Token handling ~line 1806 | Startup log printing active extraction endpoint must apply `scrub_credentials` |
| Name-policy regex | §Token handling / bidi sanitization ~line 1810 | No change |
| `domain_hint` validation | §Ingest Pipeline ~line 389 | No change |
| Post-ingest reindex | §Ingest Pipeline step 8 ~line 430 | No change; auto-reindex triggers `chunk_object` which now includes property chunks |
| Observability / structured logger | §Failure modes ~line 1643 | No change |

---

## 7. Implementation Plan

### 7.1 Files to Add or Change

**New files** (per master spec §v0.3.0 Scope):
- `src/anytype_llm_wiki/wiki/fetch.py`
- `src/anytype_llm_wiki/wiki/extraction.py`
- `src/anytype_llm_wiki/wiki/prompts/extraction.md`
- `src/anytype_llm_wiki/wiki/ingest.py`
- `tests/wiki/test_ingest.py`, `tests/wiki/test_fetch.py`, `tests/wiki/test_extraction.py`

**Modified files:**
- `src/anytype_llm_wiki/wiki/cli.py` — add `wiki-ingest` subcommand
- `src/anytype_llm_wiki/server.py` — register `wiki_ingest` tool
- `pyproject.toml` — add `markdownify>=0.11.0,<0.12.0`, `pydantic>=2.6,<3.0`

**Modified files (new to v0.3.0 scope):**
- `src/anytype_llm_wiki/chunker.py` — add `WIKI_TEXT_PROPERTY_KEYS`, extend `chunk_object`
- `src/anytype_llm_wiki/wiki/bootstrap.py` — add schema-marker PATCH + `wiki_action` tag creation

### 7.2 Key Function Signatures and Extensions

**`wiki_ingest` tool (server.py / wiki/ingest.py)**

As specified in master spec §Ingest Pipeline ~line 379 — no signature change:

```python
def wiki_ingest(
    source: str,                     # URL or absolute file path
    space_id: str,                   # Anytype space ID
    domain_hint: str | None = None,  # optional domain tag pre-apply
) -> dict:  # IngestResult shape
```

**`chunk_object` extension (chunker.py)**

The existing signature is unchanged. The extension reads `properties[]` from the object dict:

```python
def chunk_object(obj: dict) -> list[dict]:
    """
    Returns a list of chunk dicts. Emits body chunks if markdown is present
    and non-empty. Emits property chunks from WIKI_TEXT_PROPERTY_KEYS if
    the markdown body is empty or absent. Each chunk carries:
      {object_id, space_id, object_name, type_key, heading, text}
    Property chunks use heading = WIKI_PROPERTY_HEADING[key].
    """
```

New module-level constants added to `chunker.py`:

```python
WIKI_TEXT_PROPERTY_KEYS: frozenset[str]  # the 8-key allowlist (see §4.1)
WIKI_PROPERTY_HEADING: dict[str, str]    # key → display name map (see §4.1)
```

**`_run_bootstrap` additions (wiki/bootstrap.py)**

Two additions after the existing property/type creation loop:

1. Schema-version marker PATCH on root Collection (Option a, best-effort):
```python
def _patch_schema_version_on_collection(
    client: WikiClient,
    space_id: str,
    collection_id: str,
    version: str,
) -> bool:
    """PATCH wiki_schema_version onto the root Collection. Returns True on success.
    Caller wraps in try/except; failure is non-fatal (WikiLog stamp is retained)."""
```

2. `wiki_action` tag creation (idempotent, union-only):
```python
def _ensure_wiki_action_tags(
    client: WikiClient,
    space_id: str,
    prop_map: dict[str, str],
) -> dict[str, str]:
    """Create missing wiki_action select tag options.
    Returns a name→id mapping for all five tags.
    Raises nothing — caller logs warning on failure."""
```

**Schema-compat read helper (bootstrap.py or a shared util)**

```python
def _read_schema_version(
    client: WikiClient,
    space_id: str,
) -> str | None:
    """Read wiki_schema_version using the two-step read order:
    1. Root Collection properties[] (Option a primary).
    2. _max_version over wiki_log typed objects (fallback).
    Returns the version string or None if not found."""
```

This helper is used by the schema-compat check on every tool entry (wiki_ingest, wiki_query,
wiki_lint).

---

## 8. Acceptance Criteria

### 8.1 Inherited from Master Spec v0.3.0 ACs (1-19)

These ACs are inherited verbatim from master spec §v0.3.0 ACs (~lines 820-839). Notes on
deltas due to locked constraints are appended in brackets.

1. `wiki_ingest(source=<arxiv_url>, space_id=<id>)` creates ≥ 1 Entity and ≥ 1 Concept with
   bidirectional relations, and a Source object.
2. Ingesting the same URL twice updates existing objects (0 created, ≥ 1 updated) — idempotence
   above upsert threshold.
3. A partial failure produces a WikiLog entry, coherent `objects_created/objects_updated/
   warnings` response, and `status: "partial"`.
4. A URL 302-redirecting to `127.0.0.1:31012` is rejected with `[DATA ERROR] ssrf_blocked`.
5. Concurrent ingest against the same space is rejected with `[DATA ERROR] ingest_in_progress`;
   concurrent call against a different space succeeds. Test uses `multiprocessing.Process` to
   hold the flock in a second process. `threading.Thread` or async mock is insufficient.
   **[Mem0 learning: fcntl tests must use multiprocessing.Process.]**
6. Normalized-title resolution matches all rows of the dash-fold table (§Entity Resolution
   Semantics ~line 1232), including 10 codepoints: U+2010, U+2011, U+2012, U+2013, U+2014,
   U+2212, U+FE63, U+FF0D, U+00AD, U+2015.
7. Malformed extraction JSON triggers one repair attempt before failing.
8. Empty-source ingest returns `status: "ok"`, Source created, `objects_created: []`,
   `warnings: ["empty_source"]`, WikiLog notes `empty_source`.
9. Post-ingest `reindex_anytype` failure: `status: "ok"`, `reindex_failed` warning, WikiLog
   `wiki_notes` matches, created objects present in Anytype.
10. `domain_hint` not in space taxonomy → `[CONFIG ERROR] invalid_domain_hint` before fetch.
11. Ollama model not pulled → `[CONFIG ERROR] ollama_model_not_pulled` before Source creation.
12. Prompt-injection test per master spec AC #12: injected-name object not created with
    `is_central=true`; name-policy-rejected name (with `"system:"` prefix) never created.
    **[No delta]**
13. Bidirectional relation rollback: if either direction fails, both are rolled back; WikiLog
    records `relation_rollback` event. **[No delta]**
14. `wiki_schema_version` newer than running code → `warn`-level log `wiki_schema_newer`, tool
    continues. **[Delta: seeded on root Collection per Decision 2, not arbitrary object]**
15. Missing or malformed `patch-decision.md` → `[CONFIG ERROR] patch_decision_missing_or_invalid`
    before any write. **[No delta]**
16. Extraction output containing U+FEFF, U+2028, U+2029, or Unicode tag characters
    (U+E0020–U+E007F) in entity/concept name → `name_policy_rejected`. **[No delta]**
17. DNS-rebinding tripwire: controlled-resolver fixture → `ssrf_blocked`. **[No delta]**
18. AC MAY be scoped to v0.6.0+: re-ingest after partial failure reuses existing Source (no
    duplicate). Pre-release checklist records choice. **[No delta]**
19. All new tests green; full test suite green; `pip-audit` clean; `bandit -r src/` clean.

### 8.2 New ACs — Indexer Property-Gap Closure (Decision 1)

**AC-P1:** A curated `wiki_entity` object with a non-empty `wiki_facts` property and an empty
markdown body produces **at least one chunk** from `chunk_object`. The chunk's `heading` field
equals `"Facts"` and its `text` field matches the `wiki_facts` value.

**AC-P2:** After `wiki_ingest` creates a new Entity (with `wiki_facts` populated) and auto-
reindex completes, `semantic_search` on a query semantically related to that entity's facts
returns the entity in the result set (i.e. the indexer property gap is closed end-to-end).
This AC requires live Anytype + Qdrant + Ollama (mark `@pytest.mark.live`).

**AC-P3:** A non-wiki Anytype object (no `wiki_*` properties) passed to `chunk_object` produces
**zero property chunks** — its existing behavior is unchanged (blast-radius safety).

**AC-P4:** A `wiki_entity` object with a **non-empty markdown body** passed to `chunk_object`
produces body chunks only — no property chunks are emitted (dedup guard). Property chunks are
only emitted when the body is empty or absent.

**AC-P5:** A `wiki_facts` value exceeding `MAX_CHUNK_CHARS` (1500 chars) produces **more than
one** property chunk (split behavior).

**AC-P6:** `wiki_excerpt` (a `wiki_source` property) is **not** present in
`WIKI_TEXT_PROPERTY_KEYS`. A `wiki_source` object with `wiki_excerpt` populated and no body
produces zero property chunks from the allowlist.

### 8.3 New ACs — Schema-Version Marker (Decision 2)

**AC-M1:** After `wiki_bootstrap` on a clean space, the root Collection object (name=`"Wiki"`,
type=`collection`) carries `wiki_schema_version = WIKI_SCHEMA_VERSION` in its `properties[]`
array as returned by `list_objects` [Option (a) path]. If Option (a) PATCH fails silently (V4
gate fails), the fallback schema-marker WikiLog object named `wiki:schema-marker` carries
`wiki_schema_version = WIKI_SCHEMA_VERSION` [Option (b-1) path].

**AC-M2:** `_read_schema_version(client, space_id)` returns the correct version string when
the root Collection carries `wiki_schema_version` (primary read path).

**AC-M3:** `_read_schema_version(client, space_id)` falls back to the WikiLog `_max_version`
scan when the root Collection `properties[]` contains no `wiki_schema_version` key. Returns the
highest version across all `wiki_log` objects.

**AC-M4:** For a v0.2.0 space (WikiLog marker present, collection no marker): `wiki_ingest`
schema-compat check returns `wiki_schema_outdated` (because WikiLog shows `0.2.0` and code is
`0.3.0`), and the error message correctly directs the operator to run `wiki_bootstrap`.

**AC-M5:** Re-running `wiki_bootstrap` on a v0.2.0 space (upgrade path) successfully PATCHes
the root Collection with `wiki_schema_version = "0.3.0"` and subsequent `_read_schema_version`
returns `"0.3.0"` from the Collection's `properties[]` (verified by re-reading via
`list_objects`). Tests mock the `update_object` call to assert it is invoked with the correct
payload.

### 8.4 New ACs — `wiki_action` Select Tag (Decision 3)

**AC-T1:** After `wiki_bootstrap`, `list_tags(space_id, wiki_action_pid)` returns **all five**
tags: `ingest`, `query`, `lint`, `bootstrap`, `archive`.

**AC-T2:** Re-running `wiki_bootstrap` (idempotent run) on a space that already has all five
`wiki_action` tags does NOT create duplicates. `list_tags` still returns exactly five tags.

**AC-T3:** The WikiLog written by `wiki_bootstrap` carries `wiki_action = bootstrap` (the
`bootstrap` tag id is in the `select` field of the WikiLog's `properties`).

**AC-T4:** The WikiLog written by `wiki_ingest` carries `wiki_action = ingest` (the `ingest`
tag id is in the `select` field).

**AC-T5:** If `list_tags` raises an exception during `wiki_ingest`'s tag-resolution step, the
ingest **does not abort**. The WikiLog is written without `wiki_action`, and
`IngestResult.warnings` contains a string matching `"wiki_action_tag_not_found"`.

---

## 9. Test Plan

### 9.1 Inherited Test Coverage (master spec §v0.3.0 Deliverables / Test Plan)

The following test areas are specified in the master spec and are inherited without change:
URL fetch with respx; SSRF rejection; file fetch; extraction happy + malformed + repair paths;
entity resolution (dash-fold parametrized, 10 codepoints); bidirectional relation rollback;
partial-failure path; prompt-injection; DNS-rebinding tripwire; `patch-decision.md` pre-check;
bidi / control-char name policy; concurrent lock (multiprocessing.Process — see AC #5);
partial-state idempotency (AC #18 disposition recorded in pre-release checklist).

### 9.2 New Tests — Chunker Property Embedding

**File:** `tests/test_chunker.py` (extend existing) or `tests/wiki/test_chunker.py` (new).

| Test | Description |
|------|-------------|
| `test_property_chunk_emitted` | wiki_entity obj with `wiki_facts` populated, no body → 1+ chunks, heading="Facts" |
| `test_all_allowlist_keys_emit_chunks` | parametrized over all 8 keys; each yields chunk with correct heading |
| `test_non_wiki_property_not_emitted` | obj with only `description`, `status` (non-wiki keys) → 0 property chunks |
| `test_body_present_dedup` | obj with non-empty markdown + `wiki_facts` → body chunks only, no property chunks |
| `test_wiki_excerpt_excluded` | wiki_source obj with `wiki_excerpt` populated, no body → 0 chunks |
| `test_oversized_wiki_facts_split` | `wiki_facts` value of 3000 chars → 2+ chunks |
| `test_empty_property_not_emitted` | allowlisted key present but `text` is empty string → not emitted |

### 9.3 New Tests — Schema Marker Read Order

**File:** `tests/wiki/test_bootstrap.py` (extend existing).

| Test | Description |
|------|-------------|
| `test_read_schema_version_from_collection` | `list_objects` returns collection with `wiki_schema_version` → `_read_schema_version` returns it |
| `test_read_schema_version_fallback_to_wikilog` | collection has no `wiki_schema_version`; WikiLog objects carry versions → `_max_version` returned |
| `test_read_schema_version_none_when_absent` | no collection marker, no WikiLog markers → returns None |
| `test_bootstrap_patches_collection_on_fresh_space` | `update_object` is called with `wiki_schema_version` payload on the collection id |
| `test_bootstrap_upgrade_from_v020` | mock `list_objects` to return v0.2.0 WikiLog marker, no collection marker → upgrade path runs, `update_object` called |
| `test_wiki_ingest_outdated_schema_returns_config_error` | `_read_schema_version` returns `"0.2.0"`, code is `"0.3.0"` → `[CONFIG ERROR] wiki_schema_outdated` |

### 9.4 New Tests — `wiki_action` Tag Creation and Resolution

**File:** `tests/wiki/test_bootstrap.py` (extend); `tests/wiki/test_ingest.py` (extend).

| Test | Description |
|------|-------------|
| `test_bootstrap_creates_all_five_action_tags` | fresh space → `create_tag` called for each of 5 values; `list_tags` returns 5 |
| `test_bootstrap_action_tags_idempotent` | all 5 tags already exist → `create_tag` NOT called for any of them |
| `test_bootstrap_wikilog_carries_bootstrap_action` | bootstrap WikiLog `properties` includes `{"key": "wiki_action", "select": <bootstrap_id>}` |
| `test_ingest_wikilog_carries_ingest_action` | ingest WikiLog `properties` includes `{"key": "wiki_action", "select": <ingest_id>}` |
| `test_ingest_action_tag_resolution_failure_writes_wikilog` | `list_tags` raises → ingest completes, WikiLog written, `wiki_action_tag_not_found` in warnings |

### 9.5 Concurrency Test Requirement (Mem0 Learning)

The concurrent-ingest test (AC #5) MUST use `multiprocessing.Process` to acquire the flock in
a second process. A `threading.Thread` or `asyncio.gather` against a mocked lock does not
exercise the kernel-held flock (the actual liveness mechanism). This is a Mem0 learning from
the v0.2.0 test design.

---

## 10. Pre-Release Checklist

### 10.1 Inherited from Master Spec v0.3.0 Checklist (~lines 857-874)

- [ ] Verification script rerun if any Anytype version bump since v0.2.0.
- [ ] `pytest tests/` all green.
- [ ] `pip-audit` clean; `bandit -r src/` clean; `pip-licenses` scan clean (no GPL/AGPL/SSPL/EUPL).
- [ ] Ingest of 3 representative sources (short article, long paper, local markdown) run by hand.
- [ ] WikiLog verified in Anytype app (including `wiki_action = ingest`).
- [ ] README v0.3.0 configuration table with `qwen2.5:7b` (32GB) and `qwen2.5:3b` (16GB) defaults.
- [ ] Wikipedia fixture pinned to `archive.org` snapshot; extraction spot-check on both model defaults.
- [ ] AC #18 partial-state idempotency disposition recorded (ship resume OR document duplicate-Source workaround).
- [ ] Credential-scrubbing regression tests run (`QDRANT_API_KEY`, `WIKI_EXTRACT_ENDPOINT`).
- [ ] `.env.example` updated for v0.3.0 vars.
- [ ] CHANGELOG.md v0.3.0 entry; `MIGRATIONS.md` v0.3.0 section.
- [ ] NOTICE file regenerated (markdownify + pydantic; beautifulsoup4 + six transitive — all MIT).
- [ ] Git tag `v0.3.0`; PyPI publish (first public PyPI release).

### 10.2 New Pre-Release Gates (v0.3.0)

**V1 (MUST — indexer property gap):** Run `GET /v1/spaces/{id}/objects/{id}?format=md` on a
live wiki Entity object. Inspect the response dict for a `"properties"` key.

- Pass: `"properties"` key is present and is a list. Implementation can read `properties[]`
  directly from the `get_object` response in `chunk_object`.
- Fail: `"properties"` key is absent. Implementation must carry the summary object's
  `properties[]` into `chunk_object` via the indexer (add a merge step in `indexer.py` before
  calling `chunk_object`, using the summary dict already in scope at `indexer.py:~75`).

**V2 (MUST — change detection for property-only updates):** After running
`update_object(space_id, object_id, {"properties": [{"key": "wiki_facts", "text": "..."}]})`,
re-read the object via `list_objects` and compare `last_modified_date` before and after.

- Pass: `last_modified_date` is updated (later timestamp). Incremental reindex detects
  property-only updates correctly via `_get_last_modified`.
- Fail: `last_modified_date` is unchanged. The incremental reindex will miss property-only
  updates. A full-reindex trigger (or a different change-detection mechanism) is required; file
  a follow-up ticket.

**V3 (SHOULD — end-to-end property indexing):** After the chunker extension is implemented,
run `reindex_anytype` on the `llm-wiki-test` space (which has 22 wiki objects). Confirm
`objects_indexed > 0`. The original reproduction of the gap was `objects_checked: 22,
objects_indexed: 0` — this must invert.

- Pass: `objects_indexed >= 1` for wiki Entity/Concept objects.
- Fail: still 0. Debug the `properties[]` availability issue (V1 failure path) before
  proceeding.

**V4 (MUST — schema marker home):** After `wiki_bootstrap` runs on a fresh space, execute:

```python
client.update_object(
    space_id,
    collection_id,  # the root "Wiki" collection id
    {"properties": [{"key": "wiki_schema_version", "text": "0.3.0"}]},
)
# then re-read via list_objects
collection_summary = next(
    o for o in client.list_objects(space_id)
    if o.get("name") == "Wiki" and o.get("type", {}).get("key") == "collection"
)
version = next(
    (p["text"] for p in collection_summary.get("properties", [])
     if p.get("key") == "wiki_schema_version"),
    None,
)
assert version == "0.3.0"
```

- Pass: `version == "0.3.0"`. **Option (a) ships as the primary design.** The root Collection
  is the authoritative marker home.
- Fail: `version is None` or not `"0.3.0"`. **Pivot to Option (b-1).** The implementation uses
  the idempotent single-named WikiLog marker (`wiki:schema-marker`). Update this spec section
  accordingly and record the decision in `known-limitations.md` #2 update.

---

## 11. Docs to Update

| Document | Update required |
|----------|----------------|
| `README.md` | Extend "How it works" with ingest diagram (the Mermaid from master spec §Ingest Pipeline); add extraction config table (`WIKI_EXTRACT_MODEL` defaults: qwen2.5:7b / qwen2.5:3b); add trust/privacy note for `WIKI_EXTRACT_ENDPOINT` off-machine; add retrievability note (property-indexing explained for operators) |
| `CHANGELOG.md` | v0.3.0 entry: `### User-visible changes` (wiki_ingest available, property-indexing closes retrieval gap) and `### Internal changes` (chunker extended, bootstrap marker/tag additions) |
| `MIGRATIONS.md` | v0.3.0 section: WIKI_SCHEMA_VERSION bump; re-run `wiki_bootstrap` sufficient; schema-marker location change (Collection vs. WikiLog) documented; no data backfill required |
| `.env.example` | Add v0.3.0 vars: `WIKI_EXTRACT_MODEL`, `WIKI_EXTRACT_ENDPOINT`, `WIKI_EXTRACT_MAX_INPUT_TOKENS`, `WIKI_FETCH_MAX_BYTES`, `WIKI_FETCH_EXTRA_PORTS`, `WIKI_UPSERT_THRESHOLD_TITLE`, `WIKI_UPSERT_THRESHOLD_EMBEDDING`, `WIKI_DUPLICATE_SURFACE_FLOOR`, `WIKI_AUTO_REINDEX` |
| `NOTICE` | Regenerate: add `markdownify` (MIT) and `pydantic` (MIT); verify `beautifulsoup4` and `six` transitive entries |
| `docs/known-limitations.md` | **#2 (schema marker):** update to record chosen mechanism (Option a or b-1 depending on V4 gate) and mark resolved once v0.3.0 ships. **#3 (wiki_action tags):** mark resolved — all five tags created by bootstrap, `wiki_ingest` writes `wiki_action = ingest`. Items #4 and #5 remain unchanged (already documented; no new implications from v0.3.0). |

---

## 12. Open Questions / Deferred

### Provisional Thresholds (Tune at Pre-Release)

The entity-resolution thresholds (`WIKI_UPSERT_THRESHOLD_TITLE=0.92`,
`WIKI_UPSERT_THRESHOLD_EMBEDDING=0.85`, `WIKI_DUPLICATE_SURFACE_FLOOR=0.70`) are provisional
defaults inherited from the master spec (§Ingest Pipeline ~line 424). They have not been
empirically validated against bge-m3 similarity on actual wiki entity pairs. Tune during
v0.3.0 testing against the Wikipedia fixture and real-world sources; record tuned values in
the pre-release notes. This is master spec OQ#3-style deferred work.

### V4 Gate Outcome (Design Branch Selection)

The specific implementation of schema marker home (Option a or b-1) depends on the outcome of
live gate V4. Both designs are fully specified in §4.2. Implementation must be ready to ship
either; the pre-release live run picks one and the choice is recorded in `known-limitations.md`.

### AC #18 Partial-State Idempotency Disposition

Whether re-ingest after a partial failure reuses the existing Source (v0.3.0 scope) or is
deferred to v0.6.0+ (with duplicate-Source lint workaround) is a pre-release decision. Pick
one and record in the v0.3.0 pre-release notes (master spec AC #18 ~line 838 provides both
options and the disposition language).

### V1 Failure Path (Indexer Architecture)

If V1 gate reveals that `get_object(format=md)` does not include `properties[]`, the indexer
(`indexer.py`) must be extended to merge the summary object's `properties[]` into the full-
object dict before calling `chunk_object`. This is a small, well-bounded change (the summary
dict is in scope at the relevant call site) but it is not pre-authorized in the master spec's
v0.3.0 scope. Track as a conditional implementation item; document the V1 result in the
pre-release notes.

### Extraction Quality Calibration

Extraction quality for `qwen2.5:7b` (default) vs. `qwen2.5:3b` (16GB fallback) is spot-
checked at pre-release against the pinned Wikipedia fixture. If the 3B model produces
consistently fewer entities or more malformed JSON, the README recommendation may need to
strengthen the 16GB advisory. Formal extraction quality metrics are deferred to v0.4.0+.

---

## Appendix: Summary of Constraint Deprecations

The following master spec constructs are **explicitly deprecated for v0.3.0 implementation**
(they must not appear in shipped code):

| Deprecated construct | Master spec location | Reason |
|---------------------|---------------------|--------|
| PATCH `body` for content updates | §Ingest Pipeline ~line 444 ("Primary path — PATCH body works") | `patch_body_updates: silently_ignored` (verified) |
| `type_key` FilterExpression passed to Anytype search API expecting type-scoped results | §Entity Resolution Semantics pseudocode steps 1-2 ~lines 1270-1285 | `filter_expression: no_op` (verified); client-side filtering required |
| Unbounded WikiLog accumulation as the sole schema-version marker | `known-limitations.md` #2 | Decision 2 (§4.2) — root Collection primary; named WikiLog singleton fallback |

Per the Mem0 learning: deprecated approaches must be named and deleted, not left as inactive
branches. Test writers and impl workers must not implement these paths.
