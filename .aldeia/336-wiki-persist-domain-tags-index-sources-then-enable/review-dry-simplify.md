# DRY + Simplification Review — aldeia-box#336

**Scope:** `git diff main...HEAD -- src/` (chunker.py, config.py, indexer.py, server.py, wiki/ingest.py, wiki/query.py, wiki/remember.py)
**Verdict:** Clean overall. No CRITICAL or MAJOR findings. A handful of MINOR observations, most of which are arguably justified by the spec/existing-pattern constraints.

Note: the `indexer.py` atomic-state-write + `_reindex_lock` hunks in this diff are NOT #336 work — they come from a separately-merged commit (`c849fae`, #342). They are out of scope for this review and are not assessed below.

---

## Resolver duplication (primary focus) — PASS, with one MINOR

**Confirmed: no inline duplication of resolver logic across ingest.py / remember.py / query.py.**
- `_resolve_select_tag` and `_resolve_multi_select_tags` live in `ingest.py` (the single home, §D1). `remember.py` imports both (`remember.py:42-43`) and the old inline `_resolve_select_tag` body was correctly deleted, leaving only a re-export comment (`remember.py:126-128`). `lint.py`'s `from .remember import _resolve_select_tag` still resolves. `_create_source` in ingest.py calls the local copy directly. This matches the §D1 decision exactly. Good.
- `_resolve_wiki_source_type_tag` (`remember.py:137-140`) is a thin one-line wrapper delegating to `_resolve_select_tag` — not duplication.

### MINOR-1 — Three resolvers share an identical "find prop_id, then list_tags, then match, degrade-on-error" skeleton
- **Files:** `ingest.py:304-330` (`_resolve_wiki_action_tag`), `ingest.py:333-362` (`_resolve_select_tag`), `ingest.py:365-395` (`_resolve_multi_select_tags`)
- **Issue:** All three repeat the same ~8-line preamble:
  ```python
  props = client.list_properties(space_id)
  prop_id = None
  for p in props:
      if isinstance(p, dict) and p.get("key") == property_key:
          prop_id = p.get("id")
          break
  tags = client.list_tags(space_id, prop_id or property_key)
  ```
  plus the identical `except httpx.HTTPError / except Exception` degrade tail. Only the name→id matching differs (single name, single name w/ param, list of names).
- **Assessment:** This is real structural duplication, but two factors make it a deliberate MINOR rather than a fix-now:
  1. `_resolve_wiki_action_tag` predates #336 — the pattern was already established and #336 followed it (consistency over de-dup, which the simplifier checklist explicitly endorses: "don't suggest changes that would break consistency").
  2. The functions return different shapes (`tuple[str|None, bool]` vs `tuple[list[str], bool]`), so a shared helper would need to return the raw `{name: id}` map and let callers project — a modest win.
- **Optional fix** (only if a 4th resolver ever appears): extract a private `_load_tag_name_to_id(client, space_id, property_key) -> tuple[dict, bool]` that does the prop-lookup + list_tags + degrade handling once; the three resolvers become trivial projections over its result. Not required for this PR.

---

## Tier-1 predicate / chunker extraction duplication — PASS, one MINOR

The brief asked specifically about copy-paste between the two Tier-1 predicates and the chunker extraction.

### MINOR-2 — Property-scan + select/multi_select name extraction is repeated in 3 places
- **Files:** `chunker.py:52-67` (source_type + domain_tags extraction), `query.py:304-326` (`_passes_source_type_filter`), `query.py:329-...` (`_passes_domain_tags_filter`)
- **Issue:** Each independently walks `obj.get("properties", [])`, guards `isinstance(prop, dict)`, matches `prop.get("key")`, then for select does `sel = prop.get("select"); sel.get("name")` and for multi_select does the `[t["name"] for t in multi if isinstance(t, dict) and t.get("name")]` comprehension. The multi_select name-extraction comprehension in particular is byte-identical between `chunker.py:64-66` and `query.py` domain-tags predicate.
- **Assessment:** MINOR. The two query.py predicates correctly mirror the existing `_passes_date_filter` (`query.py:281-301`) shape — a per-predicate property scan is the established #323 pattern, so keeping them as standalone predicates is the *consistent* choice. The chunker extraction lives in a different module/concern (read-time hydration vs. filter), so coupling it to query.py would be worse. I would not extract a cross-module helper here.
- **If anything:** the only de-dup worth considering is two tiny local helpers in query.py, e.g. `_select_name(prop)` / `_multi_select_names(prop)`, but given the date-filter precedent inlines its extraction too, leaving it inline is defensible and arguably more consistent. No change required.

---

## Simplicity checks requested by the brief — PASS

### `_chunk_to_payload` omit-when-absent (`indexer.py:90-98`)
As simple as it can be. Three parallel `if "x" in chunk: payload["x"] = chunk["x"]` lines, mirroring the pre-existing `last_modified_date` line exactly. No abstraction warranted for 3 keys. PASS.

### `semantic_search` OD-B default-exclude guard (`server.py:298-300`)
```python
effective_types = types
if types is None and not source_type:
    effective_types = list(_SEMANTIC_SEARCH_DEFAULT_TYPES)
```
Minimal and correct. The `types is None and not source_type` condition directly encodes the documented OD-B rule; the comment (server.py:293-297) justifies why a `source_type` filter suppresses the default. No simpler form without losing the explicit-types vs. source-type distinction. PASS.

### chunker stamping loops (`chunker.py:52-57`)
`if source_type is not None: for chunk...` / `if domain_tags: for chunk...` mirrors the existing `last_modified_date` loop above it. Consistent and clear. PASS.

---

## `_passes_source_type_filter` — implemented but not applied (called out in brief)

- **File:** `query.py:304-326`; non-application documented at `query.py:700-707`.
- **Assessment — keeping it is JUSTIFIED, but borderline.** Per spec §D10 / AC-T1-ST-NOOP this is an intentional documented no-op: `wiki_source` is never in `_WIKI_TYPE_KEYS`, so applying the predicate to entities/concepts (which lack `wiki_source_type`) would zero out all results — the exact surprising behavior the no-op contract forbids. The predicate's own docstring (`query.py:311-314`) explains it's kept for "cross-tier consistency and API completeness."
  - Pro-keeping: symmetry with `semantic_search` (which DOES use source_type), and it is referenced/asserted by the AC-T1-ST-NOOP tests, so it is not truly dead — removing it would drop test coverage of the predicate's semantics.
  - Against: it is the only one of the two predicates never wired into a code path; a future reader must read the docstring + the 700-707 comment to understand why.
- **Recommendation:** Keep as-is. The thorough inline comments (query.py:700-707) and docstring NOTE (query.py:311-314) adequately defuse the "why is this unused" question. This is the correct call for a documented no-op that is exercised by tests. NOT flagged as dead code.

---

## Consistency with #323 precedent — PASS

- New `_passes_source_type_filter` / `_passes_domain_tags_filter` faithfully mirror `_passes_date_filter` (same "missing field does not pass when filter set" semantics, same property-scan shape, same return-False-on-wrong-shape). 
- Filter-list normalization `source_type_filter = list(source_type) if source_type else []` (query.py:594-595) matches the date-conditional threading pattern.
- Conditional `_core_kwargs["domain_tags"] = ...` threading (query.py:648-649) matches the existing `ingested_after`/`ingested_before` conditional threading. 
- `validation` loop in server.py (server.py:285-291) and query.py (query.py:579-591) are parallel and minimal. PASS.

---

## Summary table

| Category | Status | Findings |
|----------|--------|----------|
| Resolver duplication (D1 home) | PASS | No inline dup; MINOR-1 shared skeleton (deferred, consistency-justified) |
| Predicate / chunker extraction dup | PASS | MINOR-2 repeated property-scan (consistency-justified) |
| `_chunk_to_payload` simplicity | PASS | — |
| `semantic_search` OD-B guard | PASS | — |
| Unused `_passes_source_type_filter` | PASS | Justified no-op, test-covered, well-documented |
| #323 consistency | PASS | — |

**No CRITICAL. No MAJOR. 2 MINOR (both deferrable; each is the consistent choice given existing patterns).**
