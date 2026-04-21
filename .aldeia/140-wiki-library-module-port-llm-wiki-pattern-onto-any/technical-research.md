# Technical Research: Wiki Library Module

**Date:** 2026-04-13
**Researcher:** technical-researcher
**Ticket:** #140

---

## T1: anytype-rag Architecture

**Answer:** anytype-rag is a Python MCP server exposing two tools — `semantic_search` and `reindex_anytype` — backed by a Qdrant vector store with Ollama/bge-m3 embeddings. It is read-only with respect to Anytype: it only fetches objects and indexes their content.

### MCP Tools Exposed

| Tool | Parameters | Purpose |
|---|---|---|
| `semantic_search` | `query` (str), `space_id?` (str), `types?` (list[str]), `limit?` (int, default 10) | Embed query, run cosine search in Qdrant, filter by space/type, return top-N chunks with scores |
| `reindex_anytype` | `space_id?` (str) | Incremental reindex of all or one space into Qdrant |

Results include: `object_name`, `object_id`, `type` (type_key), `heading`, `text` (500-char truncated), `score` (4dp float).

### Anytype API Interaction

- **Protocol:** REST over HTTP, `httpx` client
- **Base URL:** `http://127.0.0.1:31012` (configurable via `ANYTYPE_API_URL`)
- **Auth:** `Authorization: Bearer <key>`, `Anytype-Version: 2025-11-08` headers
- **Endpoints used:**
  - `GET /v1/spaces` — list all spaces
  - `GET /v1/spaces/{space_id}/objects` — paginated object listing (offset/limit, 100/page)
  - `GET /v1/spaces/{space_id}/objects/{object_id}?format=md` — fetch full object with markdown body
- The client fetches objects in a paginated loop until `pagination.has_more = false`.
- Objects are fetched first as summaries (list endpoint), then individually for markdown content.

### Embedding/Indexing Pipeline

1. **State tracking:** JSON file at `~/.local/share/anytype-rag/index_state.json`. Maps `{space_id: {object_id: last_modified_date}}`.
2. **Change detection:** Compare `last_modified_date` property from object summary against stored state. Unchanged objects are skipped.
3. **Chunking** (`chunker.py`):
   - Splits markdown body by headings (##, ###, ####) into `(heading, body)` pairs.
   - Content before first heading is captured as a headingless chunk.
   - Sections exceeding `MAX_CHUNK_CHARS=1500` (~375 tokens) are split by paragraphs, then hard-split if needed.
   - Each chunk gets metadata: `object_id`, `space_id`, `object_name`, `type_key`, `heading`, `text`.
4. **Embedding** (`embedder.py`): Batch POST to `http://127.0.0.1:11434/api/embed`, model `bge-m3`, returns 1024-dim vectors.
5. **Qdrant upsert:** Each chunk becomes a `PointStruct` with a fresh UUID, the embedding vector, and the metadata payload.
6. **Deletion cleanup:** On reindex, old vectors for a changed object are deleted by `object_id` filter before re-inserting. Vectors for objects no longer present in Anytype are also deleted.

### Module Structure

```
src/anytype_rag/
├── __init__.py
├── config.py         — env var loading + typed constants (API URLs, keys, model config, state path)
├── anytype_client.py — REST API client (list_spaces, list_objects, get_object)
├── chunker.py        — markdown chunking with heading-based splitting
├── embedder.py       — Ollama batch embedding client
├── indexer.py        — incremental indexer orchestration + Qdrant management
└── server.py         — FastMCP server, exposes the two MCP tools
```

Entry points (defined in `pyproject.toml`, not read directly but implied): `anytype-rag` → `server.main()`, `anytype-rag-reindex` → standalone reindex script.

**Key constraint:** The codebase is entirely read-only with respect to Anytype. No write endpoints are used. Extending to a write-capable wiki module requires adding Anytype write calls (object create/update, type create, property create, tag create).

---

## T2: Anytype API — Type and Relation Creation

**Answer:** The Anytype REST API (v2025-11-08) supports full programmatic CRUD for Types, Properties, Tags, and Objects. Type creation is fully supported. "Relations" in Anytype's API terminology are called **Properties** of format `objects` (object-reference links). There is no separate "Relation" endpoint — inter-object links are modeled as properties of type `objects`.

### Full API Surface (v2025-11-08)

The API is served at `http://127.0.0.1:31012/v1` (same port as anytype-rag uses). Organized by resource:

**Auth** (2 endpoints)
- `POST /v1/auth/challenges` — initiate 4-digit challenge
- `POST /v1/auth/api_keys` — exchange challenge+code for bearer token

**Search** (2 endpoints)
- `POST /v1/search` — global search across all spaces
- `POST /v1/spaces/{space_id}/search` — space-scoped search

**Spaces** (4 endpoints): GET list, POST create, GET one, PATCH update

**Members** (2 endpoints): GET list, GET one

**Lists/Collections** (4 endpoints): add objects, remove objects, get views, get view objects

**Objects** (5 endpoints):
- `POST /v1/spaces/{space_id}/objects` — create
- `GET /v1/spaces/{space_id}/objects/{object_id}` — get (with `?format=md`)
- `PATCH /v1/spaces/{space_id}/objects/{object_id}` — update (name, markdown body, icon, type_key, properties)
- `DELETE /v1/spaces/{space_id}/objects/{object_id}` — archive
- `GET /v1/spaces/{space_id}/objects` — list (paginated)

**Types** (5 endpoints):
- `POST /v1/spaces/{space_id}/types` — **create custom type**
  - Body: `{name, plural_name, layout (basic|profile|action|note), icon, properties[]}`
  - `properties[]` is an array of `PropertyLink` — associates existing properties with the type
- `GET /v1/spaces/{space_id}/types` — list
- `GET /v1/spaces/{space_id}/types/{type_id}` — get one
- `PATCH /v1/spaces/{space_id}/types/{type_id}` — update
- (implied DELETE from CRUD pattern — verify at implementation time)

**Properties** (5 endpoints):
- `POST /v1/spaces/{space_id}/properties` — **create property** (experimental flag, may change)
  - Body: `{format, name, key?, tags?[]}`
  - `format` values: `text`, `number`, `select`, `multi_select`, `date`, `files`, `checkbox`, `url`, `email`, `phone`, `objects`
  - `tags[]` — inline tag creation for `select`/`multi_select` formats, array of `{name, color, key?}`
- `GET /v1/spaces/{space_id}/properties` — list
- `GET /v1/spaces/{space_id}/properties/{property_id}` — get
- `PATCH /v1/spaces/{space_id}/properties/{property_id}` — update (name, key only)

**Tags** (5 endpoints — for managing select/multi_select option sets):
- `POST /v1/spaces/{space_id}/tags` — create tag (name, color, key?)
- `GET /v1/spaces/{space_id}/tags` — list tags
- `GET /v1/spaces/{space_id}/tags/{tag_id}` — get
- `PATCH /v1/spaces/{space_id}/tags/{tag_id}` — update (name, color, key)
- (implied DELETE — verify at implementation time)

Also: `POST /v1/spaces/{space_id}/properties/{property_id}/tags` — scoped tag creation for a specific property.

**Templates** (2 endpoints): list for type, get one.

### Key Finding: "Relations" = Objects-Format Properties

There is no dedicated `POST /relations` endpoint. In the Anytype API, inter-object links are modeled as properties with `format: objects`. When creating or updating an object, you set these via `ObjectsPropertyLinkValue`:

```json
{
  "key": "sources",
  "objects": ["<object_id_1>", "<object_id_2>"]
}
```

This is the programmatic equivalent of Anytype's "Object" relation type in the UI.

### Experimental Warning

The Properties create/update endpoints carry a warning: *"Properties are experimental and may change in the next update."* As of API version 2025-11-08, this caveat applies to property creation. Plan for potential breaking changes between API versions.

### Property Object_Types Constraint: Not Available

The OpenAPI schema for `CreatePropertyRequest` does **not** include an `object_types` filter field. There is no way to constrain an `objects`-format property to only accept objects of specific type(s) via the API. Type constraints on relation targets must be enforced at the application layer.

---

## T3: Bidirectional Relations

**Answer:** True bidirectional relations are not yet natively supported. The Anytype UI shows a `Backlinks` system property that auto-populates (showing what links to the current object), but this is read-only metadata — not a writable, symmetric two-way relation. For the wiki module, bidirectionality must be managed at the application layer by writing the link property on both objects explicitly.

### How Relations Work

- **In the API:** Properties of format `objects` store an array of object IDs. When object A's property lists object B's ID, that's a directed link A→B.
- **Backlinks system property:** Anytype's desktop client automatically tracks inbound links and exposes them via a `Backlinks` read-only system property. This is visible in the UI and can be seen in sets/filters. Whether it's queryable via the REST API's filter expressions requires verification, but the community confirms it exists as a system relation.
- **True bidirectionality status:** As of mid-2024 through the current version, automatic two-way sync of a single relation (like Notion's synced relations) is unimplemented. An Anytype team member stated it was "on our sight for this year" in April 2023 but remained on the backburner through at least mid-2024.

### Constraints Confirmed

- **Cardinality:** All object-type properties are many-to-many. There is no API-enforced one-to-one or one-to-many cardinality constraint.
- **Type constraints on targets:** The `objects` property format accepts any object ID; no type filtering is enforced by the API. Application-layer validation required.
- **Traversal depth:** There is no graph-traversal query in the REST API. Fetching a "relation neighborhood" (object + its linked objects + their links) requires N+1 REST calls.

### Implication for Wiki Module

The wiki module's `Entity.relations → Entity` links must be written bidirectionally by the ingest pipeline at write time. When creating a link from Entity A → Entity B, the pipeline must also write the reciprocal on B. The Backlinks system property provides a fallback check but should not be relied on as the primary relation store for programmatic access.

---

## T4: Tag Properties

**Answer:** Tag/select properties are fully manageable via API. The tag option set (the closed list of choices for a `select` or `multi_select` property) can be created and updated programmatically. Tags are scoped to a space (not per-property), so all select/multi_select properties in a space share the same tag pool, selected by key.

### How Tag Properties Work

- **In Anytype's model:** A `select` property lets the user choose one tag from a predefined set. A `multi_select` property allows choosing multiple. The "closed" nature means only predefined tags are valid — you cannot enter arbitrary freetext.
- **Tag creation:** `POST /v1/spaces/{space_id}/tags` with `{name, color, key?}`. Colors available: grey, yellow, orange, red, pink, purple, blue, ice, teal, lime.
- **Inline creation:** When creating a property via `POST /v1/spaces/{space_id}/properties`, you can pass `tags: [{name, color}]` to create the option set in the same call.
- **Scoped creation:** `POST /v1/spaces/{space_id}/properties/{property_id}/tags` creates a tag for a specific property.
- **Listing:** `GET /v1/spaces/{space_id}/tags` returns all tags in the space.
- **Update:** `PATCH /v1/spaces/{space_id}/tags/{tag_id}` allows renaming, recoloring, or changing the key.

### Closed-Option Enforcement

The API enforces the closed set: objects can only be assigned tag values that exist in the space's tag registry. This satisfies the wiki module's requirement for a tag taxonomy enforced at the data layer.

### Bootstrap Workflow

The wiki module's type schema bootstrap can:
1. Create properties with inline tags in a single `CreatePropertyRequest` call.
2. Or create tags first, then create properties referencing the tag keys.

Both approaches work. The inline approach is simpler for initial schema setup.

---

## T5: Semantic Search Integration

**Answer:** The existing Qdrant pipeline integrates cleanly with new wiki object types. New Types (Entity, Concept, Comparison, Query, WikiLog) are indexed automatically on the next reindex cycle, identified by their `type_key` in the Qdrant payload. The current change-detection mechanism (timestamp-based) is sufficient for detecting when wiki objects are updated. There is no real-time webhook/event stream in the Anytype API, so re-embedding on object change requires polling (existing launchd/cron reindex schedule) or explicit reindex calls from the wiki pipeline.

### How New Types Integrate

The indexer stores `type_key` in each Qdrant point's payload. The `semantic_search` tool accepts a `types: list[str]` filter, which maps to `type_key` values. Once wiki types exist in Anytype and are indexed:

- `semantic_search(query, types=["entity"])` → searches only Entity objects
- `semantic_search(query, types=["concept", "entity"])` → Entity + Concept
- No code changes needed in the indexer or search tool for new types

The only change needed is ensuring the wiki types' `type_key` values are known and passed correctly. These are determined when types are created via the API (stable camel_case keys as of v2025-05-20).

### Change Detection for Re-embedding

- The indexer reads `last_modified_date` from object properties in the list response.
- When the wiki pipeline updates an Entity object (e.g., adds new facts), Anytype sets a new `last_modified_date`.
- On the next reindex call, the indexer detects the changed timestamp, fetches the updated markdown, deletes old vectors, and re-embeds the new content.
- This satisfies the open question from the ticket: **embedding refresh is confirmed** — it happens automatically on the next reindex for any updated object.

### No Real-Time Hooks

The Anytype REST API (v2025-11-08 OpenAPI spec) contains **no webhook, event stream, SSE, or subscription endpoint**. There is no way to be notified when an object changes without polling. The existing launchd plist (`com.aldeia.anytype-rag-reindex.plist`, every 30 minutes) handles this. The wiki ingest pipeline can also call `reindex_anytype` explicitly after writing objects, giving near-real-time freshness without relying on the schedule.

### Relation Neighborhood Retrieval for Query Pipeline

The `wiki.query` pipeline needs to fetch "relevant objects + their relation neighborhoods." This requires:
1. `semantic_search` → get candidate object IDs
2. `GET /v1/spaces/{space_id}/objects/{object_id}` per candidate → full object with properties
3. For each `objects`-format property, fetch the linked object IDs

This is N+1 REST calls per candidate. The Anytype REST API has no graph-traversal endpoint. For the query pipeline, this means limiting the depth to 1 hop (direct relations only) or accepting the N+1 overhead. The lint suite's orphan and stale detection requires listing all objects of relevant types, which is feasible via `GET /v1/spaces/{space_id}/objects` with type filtering or via `semantic_search` with empty query and type filter.

### Property-Predicate Queries for Lint

The `GET /v1/spaces/{space_id}/lists/{list_id}/views/{view_id}/objects` endpoint supports dynamic property-based filtering (e.g., `?updated[lt]=2025-01-01`). However, this requires an existing Collection/Set view in Anytype. An alternative is to fetch all objects of the wiki types and apply date filtering client-side. The API also supports `POST /v1/search` with `FilterExpression` supporting `lt`, `gte`, `empty`, `nempty`, etc. — this is the cleaner approach for lint queries.

---

## Feasibility Assessment

### What Is Fully Supported

- **Programmatic type creation:** `POST /v1/spaces/{space_id}/types` — full CRUD available. The wiki type schema (Entity, Concept, Comparison, Query, WikiLog, Source) can be bootstrapped via API.
- **Programmatic property creation:** `POST /v1/spaces/{space_id}/properties` — all formats including `objects`, `select`, `multi_select`, `text`, `date`, `checkbox`. Marked experimental but available.
- **Tag taxonomy creation:** `POST /v1/spaces/{space_id}/tags` and inline tag creation in `CreatePropertyRequest` — the closed-option requirement is fully achievable.
- **Object CRUD:** Full create/update/delete (archive) via API. Wiki objects (Entity, Concept, etc.) can be created and updated programmatically.
- **Type filtering in semantic search:** `semantic_search(query, types=["entity"])` works with zero code changes. Qdrant payload already stores `type_key`.
- **Embedding refresh on object update:** Confirmed — the existing timestamp-based incremental indexer handles this automatically.
- **Search with property predicates for lint:** `POST /v1/search` with `FilterExpression` supports the queries needed for orphan/stale detection.

### What Requires Application-Layer Workarounds

- **Bidirectional relations:** The API has no symmetric link primitive. The ingest pipeline must write links on both ends explicitly (A.relations=[B] and B.relations=[A]). This doubles write operations but is straightforward.
- **Type constraints on relation targets:** No API enforcement. Application layer must validate that an `Entity.relations` property only receives Entity IDs, for example.
- **Cardinality enforcement:** No API enforcement. All object properties are many-to-many.
- **Relation neighborhood traversal:** No graph query endpoint. Requires N+1 REST calls. Acceptable for the query pipeline at shallow depth.
- **Real-time re-embedding:** No webhooks. Acceptable via explicit reindex call after ingest, plus existing 30-minute launchd schedule.

### Key Risks

1. **Properties API is "experimental":** The `CreatePropertyRequest` endpoint is flagged experimental as of 2025-11-08. A breaking API change could require migration of the type schema bootstrap. Mitigate by keeping the bootstrap idempotent and checking for existing properties before creating.
2. **Tag scoping:** Tags are space-scoped in the API. If the tag taxonomy for the wiki (domain tags, status tags) conflicts with existing tags in the space, there may be collisions. Recommend using a `wiki_` key prefix for all wiki tags.
3. **No webhook means polling latency:** Objects updated by the wiki pipeline will only appear in semantic search after the next reindex. If the pipeline calls `reindex_anytype` explicitly post-write, this is a non-issue in practice.
4. **N+1 for relation neighborhoods:** The query pipeline reading linked objects will make many API calls. Rate limiting (HTTP 429) is a concern for large wikis. The ingest pipeline should cache fetched objects within a single run.
5. **Anytype desktop must be running:** The REST API runs only when the Anytype desktop app is active. On the agent server (Mac Mini), this is a deployment constraint — Anytype must be kept alive as a process.

---

## Sources

- [anytype-rag GitHub repository](https://github.com/Aldeia-IT/anytype-rag) — main repo, README, full source code
- [anytype-rag server.py](https://raw.githubusercontent.com/Aldeia-IT/anytype-rag/main/src/anytype_rag/server.py) — MCP tools implementation
- [anytype-rag anytype_client.py](https://raw.githubusercontent.com/Aldeia-IT/anytype-rag/main/src/anytype_rag/anytype_client.py) — REST API client
- [anytype-rag indexer.py](https://raw.githubusercontent.com/Aldeia-IT/anytype-rag/main/src/anytype_rag/indexer.py) — incremental indexer
- [anytype-rag chunker.py](https://raw.githubusercontent.com/Aldeia-IT/anytype-rag/main/src/anytype_rag/chunker.py) — markdown chunking
- [Anytype Developer Portal](https://developers.anytype.io/) — official API developer hub
- [Anytype OpenAPI spec v2025-11-08](https://raw.githubusercontent.com/anyproto/anytype-api/main/docs/reference/openapi-2025-11-08.yaml) — complete REST API schema (primary reference for T2-T4)
- [Create type endpoint](https://developers.anytype.io/docs/reference/2025-11-08/create-type/) — type creation API
- [Create property endpoint](https://developers.anytype.io/docs/reference/2025-05-20/create-property/) — property creation API (experimental)
- [Create tag endpoint](https://developers.anytype.io/docs/reference/2025-04-22/create-tag/) — tag creation API
- [Anytype API changelog](https://developers.anytype.io/docs/reference/changelog/) — version history, feature additions
- [anyproto/anytype-api GitHub](https://github.com/anyproto/anytype-api) — API developer portal source, openapi.config.ts
- [anyproto/anytype-mcp GitHub](https://github.com/anyproto/anytype-mcp) — official Anytype MCP server
- [Anytype Properties documentation](https://doc.anytype.io/anytype-docs/getting-started/types/relations) — user-facing property/relation docs
- [Anytype Linking Objects docs](https://doc.anytype.io/anytype-docs/getting-started/object-editor/linking-objects) — how object links work, backlinks
- [Backlinks community thread](https://community.anytype.io/t/backlinks-and-forward-links-system-relations/7784) — confirms backlinks implementation status
- [Bidirectional relations community thread](https://community.anytype.io/t/bidirectional-relations/8679) — confirms two-way relations not natively supported
- [Two-way relations Q&A](https://community.anytype.io/t/can-we-make-two-way-relations-for-object-relation-type/10063) — current workaround documented
- [Types and relations deep-dive (DeepWiki)](https://deepwiki.com/anyproto/anytype-heart/3.1-object-types-and-relations) — internal architecture analysis
- [Hermes llm-wiki SKILL.md](https://github.com/NousResearch/hermes-agent/blob/main/skills/research/llm-wiki/SKILL.md) — the skill being ported, policies and data model
- [Local API docs](https://doc.anytype.io/anytype-docs/advanced/feature-list-by-platform/local-api) — confirms API runs in desktop app on localhost, no webhooks
- [charlesneimog anytype-client property docs](https://charlesneimog.github.io/anytype-client/api/property/) — community client confirming property type list
