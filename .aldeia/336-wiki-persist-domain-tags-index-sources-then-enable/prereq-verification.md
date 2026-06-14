# Prerequisite Verification: multi_select / select GET-read shape (#336)

**Status: RESOLVED — verified live by the lead, 2026-06-13.** The #323 spec (§3 D6) and the #336
ticket both flagged the Anytype `multi_select` GET response shape as UNVERIFIED (the codebase has
never read `multi_select` values back). This note settles it against a live bootstrapped space.

## Method
Against space `llm-wiki-demo` (`bafyreicgapx77g7uml3437yahpjvjicszisjzc7u5hdelpfyopdo6atvle.h81a2ip0xaff`,
bootstrapped, schema current):
1. Created a throwaway `wiki_source` object with both a `select` (`wiki_source_type=document`) and a
   populated `multi_select` (`wiki_domain_tags=[ai, ml]`) set.
2. Re-read it via **`get_object`** (the proven path — per the #287 platform rule: never assume search
   responses hydrate; `get_object` is authoritative).
3. Confirmed the create-response serializer and the get-response serializer are **identical**.
4. Deleted the throwaway object.

The Anytype MCP server used here is a thin passthrough over the same local `/v1` object serializer the
repo's `AnytypeReadClient.get_object` consumes, so the JSON shape below is what the chunker will see.
**Impl-phase guard (carry forward):** add/keep a test that exercises the real repo client (or a fixture
captured from it) to re-confirm this shape, honoring the #287 "verify against the real client" rule.

## VERIFIED WRITE shape (round-tripped successfully)
```jsonc
// create_object / update_object properties[] entries:
{"key": "wiki_source_type", "select": "<tag_id>"}                 // single tag id string
{"key": "wiki_domain_tags", "multi_select": ["<tag_id>", "..."]}  // list of tag id strings
```
This matches the existing `select` write at `ingest.py:353` and `remember.py:192`. The
`multi_select` write is the **list-of-IDs** form — confirmed accepted by the API.

## VERIFIED READ shape (from get_object — tags are FULLY HYDRATED)
```jsonc
// select — value is a full tag object:
{"object":"property","key":"wiki_source_type","name":"Wiki Source Type","format":"select",
 "select":{"object":"tag","id":"bafy…","key":"document","name":"document","color":"grey"}}

// multi_select — value is a LIST of full tag objects:
{"object":"property","key":"wiki_domain_tags","name":"Wiki Domain Tags","format":"multi_select",
 "multi_select":[
   {"object":"tag","id":"bafy…","key":"ai","name":"ai","color":"grey"},
   {"object":"tag","id":"bafy…","key":"ml","name":"ml","color":"yellow"}
 ]}
```

## Consequences for the spec
1. **Chunker extraction needs NO ID→name resolution on read.** Tag objects carry `name` (and `key`)
   inline. Read directly:
   - `source_type = prop["select"]["name"]` (when `prop["key"]=="wiki_source_type"` and `select` present)
   - `domain_tags = [t["name"] for t in prop["multi_select"]]` (when `prop["key"]=="wiki_domain_tags"`)
   - Guard for absence/None (`prop.get("select")` may be `None`; `multi_select` may be missing/empty).
2. **Contrast with `objects` format** (e.g. `wiki_relations`, `creator`): that returns **bare ID
   strings** (`"objects":["bafy…"]`), NOT hydrated. Do not copy an `objects`-format reader for tags.
   The tag formats (`select`/`multi_select`) hydrate; the `objects` format does not.
3. **Payload stores tag NAMES** (`source_type: str`, `domain_tags: list[str]` of names). Filter inputs
   are names validated against the space taxonomy (`_domain_taxonomy` returns names), so names are the
   right join key. In this demo space `key == name` for all tags; the spec should still standardize on
   `name` (the user-facing label) and note key/name can differ if a future tag is renamed.
4. **Write side (persistence) resolves name→ID** before writing (the registry already does this for
   `select` via `_resolve_select_tag`). A new `multi_select` resolver returns a list of IDs for the
   `{"multi_select":[...]}` write. Read side does the inverse for free (hydrated names).
