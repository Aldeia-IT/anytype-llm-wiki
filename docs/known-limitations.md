# Known limitations (v0.2.0)

This document records behaviors that are understood, accepted for the v0.2.0
internal/foundation tranche, and tracked for reconciliation before the public
release and/or v0.3.0. Each item notes the source (a live verification run on
Anytype local API `2025-11-08`, or the post-implementation review
`impl-review-r2.md`).

## 1. Cross-host bootstrap dedup relies on Anytype-side `type_key`, not the file lock

`wiki_bootstrap` serializes concurrent runs **on a single host** with an
`fcntl.flock` advisory lock under `WIKI_LOCK_DIR`. `fcntl.flock` is **local to
one machine** — two different hosts bootstrapping the *same shared vault* at the
same time will not see each other's lock.

The cross-host safeguard is therefore **Anytype-side idempotency**, not the
file lock:

- **Types** are keyed by a space-unique `type_key`; creating an existing key
  links/returns the existing type rather than duplicating (verified live).
- **Domain tags** are de-duplicated by name within the `wiki_domain_tags`
  property before creation.
- **Root "Wiki" collection** is detected by name and reused.

What is **not** cross-host safe: the **WikiLog** audit entries (one is appended
per run by design — see §2) and any genuinely concurrent first-create race
window on the Anytype server. In practice the recommended operating model is to
bootstrap a shared vault from **one** host. A true two-host concurrent probe was
not run (requires two machines sharing one vault).

**Status:** accepted for v0.2.0. Re-evaluate if multi-host concurrent bootstrap
becomes a supported workflow.

## 2. The schema-version marker lives on the WikiLog, and WikiLog entries accumulate

(`impl-review-r2.md` SHOULD-FIX-1 / ADVISORY-1.)

- The spec (§Schema Compatibility, AC #13) specifies that the **root Collection**
  carries `wiki_schema_version`. The current implementation stamps the version on
  the per-run **WikiLog** object instead, because the system `collection` type
  did not reliably persist a custom property (and the create-type `layout` enum
  has no `collection` option for a wiki-owned collection type).
- Consequently every `wiki_bootstrap` run appends a **new** WikiLog entry, and
  each carries the version marker. Upgrade detection (`_max_version` across all
  objects) is **correct** regardless (it selects the highest version), but:
  - the "idempotent / zero duplicates" property does **not** apply to the WikiLog
    marker object itself; and
  - this diverges from the spec's "marker on the root Collection" wording.

**Status:** acceptable for v0.2.0 in isolation — no shipped consumer reads the
marker until v0.3.0+. **Must be reconciled before v0.3.0** by either (a)
implementing the spec as written (stamp the long-lived root Collection and
restore the upgrade-path PATCH) or (b) amending the spec/ACs with spec-writer
sign-off. Tracked as a follow-up.

## 3. `wiki_action` is not written on the bootstrap WikiLog entry

(`impl-review-r2.md` SHOULD-FIX-2.)

`wiki_action` is a `select` property. Writing a select value requires a
pre-existing tag (option) id; the bootstrap WikiLog write omits it rather than
fail. The spec defines `wiki_action` as the primary WikiLog discriminator
(grouped on by the v0.5.0 lint). No v0.2.0 consumer depends on it.

**Status:** tracked for the version that first reads WikiLog (v0.5.0). Fix is to
create the `wiki_action` "bootstrap" tag during bootstrap and reference its id.

## 4. Anytype ignores PATCH of an object `body` (returns 2xx, does not persist)

(verify-anytype-writes.sh → `patch-decision.md`: `patch_body_updates:
silently_ignored`.)

A `PATCH /v1/spaces/{id}/objects/{id}` with a `body` field returns success but
the re-read does not reflect the change on API `2025-11-08`. The module's
recorded `implementation_path` is therefore `fallback_properties_only`: durable
content must be written via **properties** (or the object's initial create
`body`), never via a `body` PATCH. PATCH of a **property** (e.g. `name`) works.

## 5. Anytype search ignores the `type_key` FilterExpression

(verify-anytype-writes.sh → `patch-decision.md`: `filter_expression: no_op`.)

`POST /v1/spaces/{id}/search` with
`filter={"condition":"and","filters":[{"key":"type_key","condition":"eq",...}]}`
returns the **same** result set as an unfiltered query (an impossible type also
returned the full set). Type-scoped server-side search is therefore **not**
effective with the current filter shape on API `2025-11-08`.

This does **not** affect the v0.2.0 MCP `semantic_search` tool, which queries
**Qdrant** vectors (with optional client-side filtering), not Anytype's search
endpoint. `WikiClient.search(... filter={"type_key": X})` should not be relied
on for type scoping until the correct filter contract is confirmed.

**Status:** tracked for the version that uses Anytype-native filtered search.
