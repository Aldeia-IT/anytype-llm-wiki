# CTO Spec Review — #323 Retrieval Metadata Filters / Type-Tag Scoping (Round 1)

**Reviewer:** CTO (review council)
**Date:** 2026-06-12
**Scope:** Spec-phase technical-accuracy & codebase-alignment audit of
`spec.md`, drawing on `research.md`, verified against the worktree source.

I verified claims directly against the codebase and the installed
qdrant-client (1.18.0) rather than taking the spec's word. Findings below
each cite the file/line or command checked.

---

## What I verified clean (credit where due)

- **Qdrant wire contract (§6.1, §6.3) — VERIFIED CORRECT.** Ran
  `importlib.metadata.version("qdrant-client")` → `1.18.0`. Confirmed
  `DatetimeRange(gte="2026-01-01T00:00:00Z")` coerces ISO strings to
  `datetime` via Pydantic; `Range` would not. `PayloadSchemaType.KEYWORD`
  (`keyword`) and `.DATETIME` (`datetime`) exist. `inspect.signature`
  confirms `create_payload_index(collection_name, field_name,
  field_schema=..., field_type=..., wait=True, ...)` — the spec's use of
  `field_schema=` (not legacy `field_type=`) is correct. Bad date strings
  raise `pydantic.ValidationError` — the §9.1 probe-and-reraise approach is
  sound.
- **AC-F2 test ↔ §6.2 construction — VERIFIED CONSISTENT.** I mentally and
  literally executed the nested `Filter(should=[FieldCondition(type_key,
  MatchValue)])` build from §6.2 and ran the AC-F2 assertion logic against
  it: `hasattr(c, "should")` is True, `c.should` is truthy, and
  `{c.match.value for c in c.should}` yields `{"wiki_entity",
  "wiki_concept"}`. The #289-style mismatch is NOT present here. Good.
- **No-filter regression (§6.2 / AC-F1) — VERIFIED.** Current
  `indexer.py:50-62` already produces `search_filter = None` when `must` is
  empty, and the new params are all guarded by `if param:`. The byte-identical
  claim holds, including the existing nested-`should` path (untouched when
  `types` is None).
- **Date-extraction contract (§7.2) — VERIFIED.** `_get_last_modified`
  (`indexer.py:105-110`) reads `last_modified_date` from `properties[].date`,
  and `reindex` already calls it successfully on `list_objects` summaries
  (`indexer.py:134`). The property is present at index time. `get_object`
  returns `resp.json()["object"]` (`anytype_client.py:52`), which carries
  `properties`. Date extraction is functional.
- **`select` shape (§7.2) — VERIFIED.** `lint.py:388-389` and `:519-526`
  confirm `{"select": {"id","name","color"}}`; reading `.get("name")` is
  correct.

---

## BLOCKING

### B1 — `source_type` filter on `wiki_query` is structurally inert (always empty)

**Verified:** `grep -n "_WIKI_TYPE_KEYS" src/anytype_llm_wiki/wiki/query.py`
→ line 50: `_WIKI_TYPE_KEYS = ("wiki_entity", "wiki_concept",
"wiki_comparison", "wiki_query")`. `wiki_source` is **not** a member.
`grep wiki_source_type src/anytype_llm_wiki/wiki/types_schema.py` → line 81:
`wiki_source_type` is a `select` property defined **only** on the
`wiki_source` type (the WIKI_TYPES block, lines 71-82). No other type carries
it.

**What I found:** `wiki_query` only ever retrieves objects whose type is in
`_WIKI_TYPE_KEYS` — and it enforces that filter both in Tier 2 (passing
`types=list(_WIKI_TYPE_KEYS)` to `semantic_search_core`, `query.py:449`) and
in Tier 1 (`wiki_objects = [o for o in all_objects if _type_of(o) in
_WIKI_TYPE_KEYS]`, `query.py:418-421`). Since `wiki_source` is excluded from
both tiers, **no chunk reachable by `wiki_query` can ever carry
`source_type`.** The §8.2 Tier-1 predicate (`_has_source_type`) will return
`False` for every object, and the Tier-2 `source_type` filter will match zero
points. The spec exposes `source_type` on `wiki_query` (§5.2) and asserts in
§8.2 it is functional — it is not.

**Impact:** A `wiki_query(..., source_type="url")` call silently returns an
empty / no-sources answer for ALL inputs. This is exactly the "accepted-but-
inert parameter is a footgun" failure mode the spec itself argues against for
`domain_tags` in D4 — yet it ships the same footgun for `source_type` on
`wiki_query`. The spec's own §1.2 narrative ("chunks from wiki_source carry
this; entity/concept do not") is correct but the spec then fails to connect it
to the fact that `wiki_query` never sees `wiki_source` objects at all.

**Recommended fix (pick one):**
1. **Drop `source_type` from `wiki_query`'s surface** (keep it on
   `semantic_search`, which is the general tool that *can* retrieve
   `wiki_source` chunks). Update §5.2, §8.2, §8.4, and the AC-F10 mapping.
   This is the cleanest and matches the spec's own D4 reasoning.
2. OR add `wiki_source` to the type set `wiki_query` retrieves when
   `source_type` is requested — but this changes wiki_query's retrieval
   semantics materially and is almost certainly not intended. Not recommended
   without Jan's explicit ratification.

The test phase cannot write a satisfiable positive AC-F10 source_type
assertion against `wiki_query` as currently specified, so this must be
resolved before the test phase.

---

### B2 — `semantic_search` retrieves `wiki_source` chunks? Unverified availability assumption for the only tool where `source_type` is non-inert

**Verified:** `semantic_search_core` (`indexer.py:20-82`) applies no implicit
type filter — it searches all chunks in the collection. So `semantic_search`
(unlike `wiki_query`) *can* match `wiki_source` chunks, making `source_type`
potentially functional there. That part is fine.

**What I could not confirm:** The spec assumes `wiki_source` objects are
chunked and indexed into Qdrant in the first place. `chunk_object` emits
chunks from either a markdown body or the allowlisted
`WIKI_TEXT_PROPERTY_KEYS` (`chunker.py:13-16`):
`{wiki_facts, wiki_description, wiki_definition, wiki_open_questions,
wiki_dimensions, wiki_verdict, wiki_question, wiki_answer}`. **None of the
`wiki_source` properties** (`wiki_url`, `wiki_file_path`, `wiki_excerpt`,
`wiki_ingested_at`, `wiki_source_type`) are in that allowlist
(`types_schema.py:76-81`). So a `wiki_source` object with no markdown body
produces **zero chunks** and is never indexed — meaning even on
`semantic_search`, `source_type="url"` would match nothing unless
`wiki_source` objects reliably carry a markdown body.

**Impact:** If `wiki_source` objects are body-less (excerpt-in-property only),
the `source_type` filter is inert on BOTH tools, which would collapse the
entire D2 value proposition. The spec never verifies that `wiki_source`
objects reach Qdrant. This is the central premise of the whole `source_type`
half of the ticket and it is unverified.

**Recommended fix:** Before implementation, verify (against a live space or by
reading the ingest write path) whether `wiki_source` objects carry a markdown
body that survives `chunk_object`. If they rely on `wiki_excerpt` (a property
not in `WIKI_TEXT_PROPERTY_KEYS`), the chunker change in scope must ALSO add
`wiki_excerpt` to the indexable property allowlist, or `source_type` filtering
is dead on arrival. Add an explicit AC that a `wiki_source` object yields >=1
chunk carrying `source_type`. (Note AC-F8's test fixture hand-feeds a
`markdown` body to the source object — it would pass while real `wiki_source`
objects produce no chunks. The test is not representative.)

---

## SHOULD-FIX

### S1 — `_WIKI_TYPE_KEYS` includes `wiki_comparison`, but the spec's D1 narrative lists a 4-tuple that omits it inconsistently

**Verified:** `query.py:50` → `("wiki_entity", "wiki_concept",
"wiki_comparison", "wiki_query")`. Spec §3 D1 (line ~106) quotes the tuple
correctly as `("wiki_entity", "wiki_concept", "wiki_comparison",
"wiki_query")`. **This one is actually consistent** — but note that
`wiki_comparison` carries none of `wiki_source_type`/`wiki_ingested_at`, and
its only indexable text comes from `wiki_dimensions`/`wiki_verdict`
(`chunker.py:13-16` allowlist ∩ `types_schema.py:120-124`). The `types` filter
on `wiki_query` is functional for all four members; no issue there. I flag
only that the spec's §3 example "`types=["wiki_entity", "wiki_source"]` is
silently narrowed" uses `wiki_source` as the dropped example, reinforcing the
B1 confusion that `wiki_source` is somehow query-reachable. Recommend changing
the example to a clearly non-wiki key (e.g. `"page"`) to avoid implying
`wiki_source` participates.

### S2 — Unused import `MatchAny` declared in the pinned wire contract (§6.1)

**Verified:** §6.1 imports `MatchAny` ("IN operator — used for type_key and
source_type"), but the §6.2 reference implementation uses neither — it builds
the type filter with the legacy nested `Filter(should=[... MatchValue ...])`
and `source_type` with a single `MatchValue`. `MatchAny` is never used in any
spec code block. The research (research.md:100-110) explicitly noted both the
nested-`should` and the cleaner `MatchAny` form are equivalent and left the
choice open; the spec silently kept the verbose form but still imports
`MatchAny`.

**Impact:** A literal implementation produces an unused import (linter
failure — this repo runs ruff). The §6.1 comment also misdescribes reality
("used for type_key and source_type") — neither uses `MatchAny`.

**Recommended fix:** Either (a) drop `MatchAny` from §6.1 and fix the comment,
or (b) commit to `MatchAny(any=list(types))` for the type filter and
`source_type` and update §6.2 + the AC-F2 test (the AC-F2 test currently keys
off `c.should`, which would break under `MatchAny`). I recommend (a) —
keeping the existing nested-`should` pattern preserves the verified AC-F2
alignment and avoids touching the regression-sensitive type path.

### S3 — Tier-1 `last_modified_date` read path differs from the verified property shape

**Verified:** Two different read shapes exist in the codebase for this field:
- `indexer._get_last_modified` (`indexer.py:107-109`) reads it from
  `properties[].date` where `key == "last_modified_date"`.
- `lint.py:508` reads it as a **top-level** key: `o.get("last_modified_date")`.

The spec's §8.3 Tier-1 predicate uses the `properties[].date` form (matching
`_get_last_modified`), which is the right choice for objects returned by
`list_objects`/`get_object`. **However**, the spec never reconciles the
`lint.py` top-level-key usage, which suggests the field may ALSO be surfaced
at top level in some response shapes. If `list_objects` summaries expose
`last_modified_date` only at top level (and `_get_last_modified` happens to
return `"unknown"` fallback in reindex without anyone noticing), the Tier-1
property-list scan could silently find nothing and filter out all objects.

**Recommended fix:** Verify against a live `list_objects` response which shape
carries `last_modified_date` (top-level vs `properties[]`). If both, the
Tier-1 predicate should check top-level first (mirroring `lint.py:508`) then
fall back to the property list. Add an AC fixture that mirrors the REAL
`list_objects` shape, not a hand-built one.

### S4 — AC-F8 / AC-F9 fixtures are not representative of real ingest output

**Verified:** AC-F8 (spec lines ~827-838) feeds `chunk_object` an object with
an explicit `"markdown": "# Body\nContent here."`. Real `wiki_source` objects
are authored by the ingest pipeline and (per B2) likely store prose in
`wiki_excerpt`, not a markdown body. AC-F9 similarly relies on
`wiki_facts` being in the allowlist (it is — `chunker.py:13`), so AC-F9 is
representative; AC-F8 is not.

**Impact:** AC-F8 will pass green while the real-world `wiki_source` path
produces zero chunks (B2). A passing test that misrepresents production is the
#289 lesson restated.

**Recommended fix:** After resolving B2, make AC-F8's fixture match how
`wiki_source` objects are actually produced (body vs `wiki_excerpt` property).

---

## SUGGESTION

### G1 — `_ensure_collection` index creation runs on every `reembed_object` call

§6.3 calls `create_payload_index` for 4 fields unconditionally inside
`_ensure_collection`, which runs at the top of `reembed_object`
(`indexer.py:198`) — i.e. on every single-object update. Idempotent and cheap
per the research, but on a real Qdrant server this is 4 synchronous
`wait=True` index calls per object re-embed. Consider gating index creation to
the `reindex` path only, or a one-time guard, to avoid per-object overhead on
the hot update path. Advisory; not blocking.

### G2 — In-memory Qdrant `UserWarning` on payload indexes

The spec notes (§6.3, §10.1) that in-memory Qdrant emits a `UserWarning` that
indexes have no effect. The fake `create_payload_index` is a no-op, so unit
tests are fine, but any test using a real `:memory:` client will emit warnings.
If the suite runs with `-W error`, this becomes a failure. Recommend the test
phase confirm the suite's warning filter config.

### G3 — Spec §1.1 / non-goal contradiction is well-handled

Credit: the spec correctly identifies and surfaces the ticket's
non-goal-vs-AC contradiction and routes it to Jan as OD-1/OD-2 rather than
papering over it. The D4 deferral of `domain_tags` (verified: `wiki_domain_tags`
is defined in `types_schema.py:80,94,110` but I found no write path —
consistent with the spec's claim) is the right call. No action needed.

---

## Verdict

**NEEDS REVISION** — B1 (the `source_type` filter on `wiki_query` is
structurally inert because `wiki_source` is excluded from `_WIKI_TYPE_KEYS`,
verified at `query.py:50` and `types_schema.py:81`) and B2 (unverified whether
`wiki_source` objects are chunked/indexed at all, given the
`WIKI_TEXT_PROPERTY_KEYS` allowlist at `chunker.py:13-16` excludes every
`wiki_source` property) mean a core deliverable of the ticket would ship
non-functional and the downstream test phase cannot write satisfiable positive
assertions for it. The Qdrant wire contract, no-filter regression, AC-F2
alignment, and date-extraction contract are all verified sound — the spec is
strong on the parts it verified and weak precisely where it asserted
functionality without tracing the data path end-to-end. Resolve B1/B2 (and
S1–S4) and this is approvable.
