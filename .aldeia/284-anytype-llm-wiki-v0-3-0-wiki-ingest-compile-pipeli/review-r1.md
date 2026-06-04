# Spec Review — #284 v0.3.0 `wiki_ingest` increment (Round 1)

**Date:** 2026-06-03
**Spec:** `.aldeia/284-anytype-llm-wiki-v0-3-0-wiki-ingest-compile-pipeli/spec.md`
**Reviewers:** completeness/QA, technical/architecture, security (3 parallel sub-agents) + lead consolidation & spot-check
**Method:** Each reviewer read the increment spec, the master spec (#140), the research, and the codebase. Lead independently verified the load-bearing code claims (B1, B2, B3, SF1, the `_max_version` shape).

## Verdict: NEEDS REVISION

The spec is fundamentally strong — locked constraints match `patch-decision.md` verbatim, the three decisions are resolved with implementable mechanisms, rejected approaches are explicitly deprecated, and ~all bootstrap/client/schema code citations are accurate. But there is **one genuine load-bearing design flaw** (the dedup guard re-opens the very gap it closes), **one unstated hard prerequisite** (the schema version constant is still `"0.2.0"`), **one reachable crash** (direct key access on the new empty-body path), and **two locked constraints that ship with no AC/test** (silent-regression risk). All are fixable in one round.

Lead spot-check confirmations (code-grounded):
- `src/anytype_llm_wiki/wiki/types_schema.py:25` → `WIKI_SCHEMA_VERSION = "0.2.0"` (B1 confirmed).
- `src/anytype_llm_wiki/chunker.py:18-19` → `object_id = obj["id"]; space_id = obj["space_id"]` direct subscript; current early-return on empty markdown (line 15-16) means these never execute for empty-body objects *today* — the new property path makes them reachable (B3 confirmed).
- `src/anytype_llm_wiki/wiki/bootstrap.py:123-129` → `_max_version(a, b)` is a 2-arg helper, not a scanner (SF6 confirmed).
- `WIKI_EXTRACT_ENDPOINT` has zero references in `src/` (net-new); `scrub_credentials` exists in `wiki/util.py` and is applied in `doctor.py` (SF1 confirmed).

---

## BLOCKING

### B1 — `WIKI_SCHEMA_VERSION` is `"0.2.0"` in code; the entire marker/migration design assumes `"0.3.0"`
**Source:** technical reviewer B1 (lead-verified).
**Where:** spec §4.2 migration steps, AC-M4, AC-M5, §10.2 V4; code `types_schema.py:25`.
**Why it blocks:** Decision 2's migration logic, the `is_upgrade` detection (`bootstrap.py:251-254`), AC-M4 (“WikiLog shows 0.2.0 and code is 0.3.0 → `wiki_schema_outdated`”), and V4 (writes `{"text": "0.3.0"}`) all require the running code's version to be `"0.3.0"`. Until the constant is bumped, a v0.2.0 space compares `0.2.0`-vs-`0.2.0` (equal → proceeds, no upgrade), and AC-M4 cannot pass.
**Fix:** Add an explicit implementation step + §7.1 modified-files row + §10 checklist item: "bump `types_schema.WIKI_SCHEMA_VERSION` to `\"0.3.0\"`." Make it a named prerequisite of Decision 2.

### B2 — The dedup guard re-opens the gap it closes (load-bearing design flaw)
**Source:** technical reviewer B3 (lead-confirmed from spec text).
**Where:** spec §4.1 "Dedup guard" (emit property chunks *only when markdown body empty/absent*) vs §5.1 ("the body at initial create-time may contain content … body PATCH silently ignored on update") and the §4.1 flowchart `B -->|yes| C`.
**Why it blocks:** Sequence: (1) `wiki_ingest` creates an Entity *with* a non-empty body (§5.1 permits this); (2) body chunks emit, object retrievable; (3) a later re-ingest updates `wiki_facts` via property PATCH — the **only** durable update path — but cannot refresh the body; (4) `chunk_object` still sees a non-empty (now-stale) body → the guard suppresses property chunks → the updated facts are **never indexed**. The guard guarantees the property gap stays open for any wiki object created with a body. This defeats Decision 1 on the update path — the precise failure v0.3.0 must fix.
**Fix (recommended — option b):** Mandate that `wiki_ingest` creates wiki Entity/Concept/Comparison/Query objects with an **empty body** (properties-only on create). This makes "empty body" the invariant for ingest-authored wiki objects, so the dedup guard is sound: empty-body wiki objects → property chunks; manually-created-with-body objects → body chunks (unchanged). Update §4.1, §5.1, and the flowchart; add an AC: "wiki objects created by `wiki_ingest` have an empty markdown body; their knowledge is retrievable solely via property chunks across create AND update." (Alternative, if create-with-body is required for some reason: always emit property chunks regardless of body and accept harmless overlap — but option b is cleaner and aligns with §5.1's "properties are the only reliable embedding surface across the lifecycle.")

### B3 — Chunker direct key access (`obj["id"]`, `obj["space_id"]`) is now reachable on the empty-body path → `KeyError` crashes the reindex loop
**Source:** technical reviewer B2 + completeness G3 (lead-verified).
**Where:** spec §4.1 chunk-metadata shape vs code `chunker.py:18-19`; `indexer.py:75` calls `chunk_object(obj)` with no guard.
**Why it blocks:** Today the early-return on empty markdown (`chunker.py:15-16`) means `obj["id"]`/`obj["space_id"]` never execute for empty/property-only objects. The new property path executes precisely for those objects. If a `get_object(format=md)` response (shape unverified — see V1) lacks `space_id`, the direct subscript raises `KeyError`, crashing the whole reindex. The spec's printed shape already uses `.get("space_id","")` — make that a *required* hardening and update the existing direct-access lines to tolerate a missing `space_id`/`id` on the property path.
**Fix:** Spec must mandate defensive `.get(...)` access (with sensible fallbacks) in the extended `chunk_object`, and state the property-chunk path must not assume `space_id` is present. Add a test (`test_property_chunk_missing_space_id_tolerated`).

### B4 — §5.1 "no body-PATCH content path ships" is a locked constraint with NO AC and NO test
**Source:** completeness reviewer B1.
**Where:** spec §5.1, §Appendix row 1; absent from §8/§9.
**Why it blocks:** This is the most consequential locked constraint (master "Primary path" deleted). The spec says impl/test workers "must NOT implement a body-update path," but nothing verifies it — a contributor re-adding a `body` key to an update `update_object` call would pass all tests. A deprecated path with no guard test silently regresses.
**Fix:** Add **AC-L1**: "On the re-ingest/update path, `update_object` is invoked with a `properties` payload only — no `body`/`markdown` key in any update PATCH. Verify via mock-spy on `update_object` call args across update-path tests." Add the matching §9 test row.

### B5 — §5.2 client-side type-filtering constraint has NO AC and NO test → wrong-type false-positive upserts
**Source:** completeness reviewer B2.
**Where:** spec §5.2, §Appendix row 2; absent from §8/§9.
**Why it blocks:** `filter_expression: no_op` means `client.search(filter={"type_key":...})` returns all types. If entity resolution relies on it, a same-name object of the *wrong* type gets matched and updated (writing entity facts onto a concept) — a correctness failure. No AC asserts the Python-side post-filter is applied.
**Fix:** Add **AC-L2**: "Given `client.search` returns mixed-`type.key` objects, `resolve_entity` steps 1-2 only consider objects whose `type.key == type_key`; a same-name object of a different type is NOT matched/updated." Add a §9 test feeding a mixed-type result set.

---

## SHOULD-FIX

### SF1 — `WIKI_EXTRACT_ENDPOINT` credential scrub is mentioned in prose but not pinned as an AC+test
**Source:** security reviewer SF1 (lead-verified: `WIKI_EXTRACT_ENDPOINT` net-new, `scrub_credentials` exists).
**Where:** spec §6 (prose row), §10.1 checklist line; absent from §8. Master anchors §Token handling ~1808, §LLM extraction data exfiltration ~1836 ("startup log emits `extraction_endpoint`").
**Why:** `WIKI_EXTRACT_ENDPOINT` may carry hosted-API userinfo / `?api_key=`. The master design prints the active extraction endpoint at startup — exactly the unscrubbed-print risk the Mem0 lesson warns about. The control exists (`util.scrub_credentials`, with the scheme-less-userinfo fix) but the v0.3.0 spec does not force the new print through it via a test.
**Fix:** Add **AC-S1**: "The startup log/banner emitting the active extraction endpoint passes the value through `scrub_credentials`; regression test sets `WIKI_EXTRACT_ENDPOINT=https://user:KEY@host/v1?api_key=SEKRET` and asserts the emitted line contains neither `KEY`, `SEKRET`, nor `user:...@`." If a doctor extraction-endpoint check is added, it must scrub too.

### SF2 — Property-embedding widens the corpus to attacker-influenced free-text; residual injection risk unacknowledged; confirm sanitizer covers property VALUES not just names
**Source:** security reviewer SF2.
**Where:** spec §4.1 "Blast-radius safety" (argues *key*-scoping only); §8.2 AC-P*; master §Extraction Prompt Structure ~1310-1372 (name-policy is name-only; bidi/control-char sanitizer covers "names and properties" ~1810).
**Why:** Injected text rejected as a *name* can still land in `wiki_facts`/`wiki_description`, get embedded by the new chunker path, be retrieved by `semantic_search`, and feed a downstream LLM. The increment widens the embedding surface (property values previously never indexed) without restating the acceptance.
**Fix:** Add a sentence to §4.1 Blast-radius: property values are attacker-influenced; the bidi/control-char sanitizer (master ~1810) is applied to property values on write; semantic prompt-injection in retrieved description/facts feeding a downstream LLM is an **accepted residual risk** per master README trust note (~1372). Confirm an AC (extend AC#16 or add one) asserts the sanitizer is applied to property *values*, not only names.

### SF3 — §8.1 AC#8 restatement drops `objects_skipped: []` present in master AC#8
**Source:** completeness reviewer S1.
**Where:** spec §8.1 AC#8 vs master AC#8 (~line 828).
**Fix:** Restore `objects_skipped: []` to the AC#8 restatement (or annotate "[full master response shape applies]").

### SF4 — AC-M1 conflates two mutually-exclusive outcomes; the Option (b-1) fallback ships untested
**Source:** completeness S3 + technical (marker design).
**Where:** spec §8.3 AC-M1; §9.3 covers only Option (a) (`test_bootstrap_patches_collection_on_fresh_space`).
**Fix:** Split into **AC-M1a** (Option a — Collection marker) and **AC-M1b** (Option b-1 — `wiki:schema-marker` WikiLog singleton create + read-by-name), gated on V4. Add a §9.3 test for the b-1 path so the fallback is not shipped untested.

### SF5 — V2-gate failure silently breaks update-path reindex; only the create path has an end-to-end AC
**Source:** completeness S4 + technical S-series.
**Where:** spec §4.1 V2 / §10.2 V2 (fail-action = "file a ticket"); AC-P2 covers create only.
**Why:** If property PATCH does not bump `last_modified_date`, incremental reindex never re-embeds re-ingested knowledge — Decision 1 fails on the update path with no AC catching it.
**Fix:** Add an AC (`@live`) asserting re-ingest of an existing entity re-embeds updated `wiki_facts` end-to-end (ties to B2's fix), OR elevate V2-fail to a release-blocking gate with a concrete remediation (full-reindex trigger) rather than "file a ticket."

### SF6 — `_read_schema_version` fallback must reuse the scan loop, not call the 2-arg `_max_version`; reconcile AC-M3 wording
**Source:** technical reviewer S2 (lead-verified `_max_version` is 2-arg).
**Where:** spec §4.2 / §7.2 `_read_schema_version`; AC-M3; code `bootstrap.py:123-129` (`_max_version`) and `:248-249` (the scan loop `for obj … _max_version(found, _found_schema_version(obj))`).
**Fix:** State that `_read_schema_version`'s fallback reproduces the `_found_schema_version` + `_max_version` scan-loop pattern (bootstrap.py:248-249). Note the current scan iterates **all** objects (not just `wiki_log`); reconcile AC-M3's "across all `wiki_log` objects" wording with the chosen behavior (filter to `type.key=="wiki_log"` or accept scan-all).

### SF7 — Collection-first read can return a stale marker, undercutting "single authoritative value"
**Source:** technical reviewer S3.
**Where:** spec §4.2 read order (Collection wins unconditionally).
**Fix:** Have `_read_schema_version` return `max(collection_value, wikilog_max)` for robustness, OR explicitly state Collection wins unconditionally and accept the stale-marker risk with rationale.

### SF8 — Make §5.2 prescriptive: always apply the Python post-filter; drop the decorative `filter=` arg
**Source:** technical reviewer S5 (verified `client.search` exists, returns `data` list, translates `{"type_key":...}` to a no-op FilterExpression).
**Where:** spec §5.2 ("drop the filter arg **or** apply post-filter").
**Fix:** Change either/or to prescriptive: always apply `o.get("type",{}).get("key")==type_key` client-side; drop the `filter=` arg so the code does not imply server-side scoping works.

### SF9 — Run V4 before authoring marker tests/impl so only the selected option ships (avoid dual live designs)
**Source:** completeness reviewer S2.
**Where:** spec §4.2 (both options fully live), §10.2 V4, §12.
**Why:** Shipping both designs "ready to pivot" is the dual-path shape the spec's own §5.1/Appendix deprecates. The V4 selector is concrete, but sequencing it at pre-release invites test/impl divergence.
**Fix:** State V4 is run **before** marker test-writing/impl (not at pre-release), so only the selected option's code+tests are authored and the loser is deleted, not shipped dormant. If V4 cannot run that early, require the test suite to assert exactly one mechanism is present in shipped code (guard the other is absent).

---

## SUGGESTION

- **G1 (completeness G1):** "AC #13" is overloaded — Decision 2 cites master **v0.2.0** AC#13 (`_outdated`, ~line 743) while §8.1 AC#13 is the inherited v0.3.0 "bidirectional rollback." Disambiguate every "AC #13" citation as "master v0.2.0 AC#13" vs "v0.3.0 AC#13."
- **G2 (completeness G2):** §8.1 AC#14 "[Delta…]" annotation is a non-delta — master AC#14 already says "on the root Collection." Reword to "[Confirms Decision 2 home; resolves v0.2.0 WikiLog divergence]."
- **G3 (security S1):** `wiki_facts` unbounded growth across re-ingests → unbounded chunks for one object. Single-operator threat model makes it low severity; either note as accepted or add a per-property soft cap + `wiki_facts_truncated` warning on the update path.
- **G4 (technical G2/G3):** Citation hygiene — domain-tag loop is `bootstrap.py:331-372` (not 367); the V1 fail-action merge point is the `obj_summary`/`obj` call site `indexer.py:69-75` (not `40-45`, which is `_get_last_modified`). Also `_find_root_collection` (`bootstrap.py:482-485`) matches **name-only** (impl-review-r2 NIT-1); the version-read path must add a `type.key=="collection"` guard so an unrelated object named "Wiki" isn't adopted.
- **G5 (technical S4):** Decision 3 brings `wiki_action` forward from v0.5.0; `docs/known-limitations.md:65` still says "v0.5.0." The §11 docs table already plans to close #3 — ensure the note lands. The bootstrap WikiLog write to extend is `bootstrap.py:410-418` (`_build_props_list` maps `select`→`{"key":…,"select":value}` at ~449-450, so the tag-id payload shape is correct).

---

## Things checked and found GOOD (no action)
- §5.1/5.2/5.3 locked constraints match `patch-decision.md` and `known-limitations.md` exactly.
- Qdrant payload `type_key` filter works (the step-3 embedding sweep is sound).
- `create_tag` / `create_object` / `update_object` / `list_properties` / `list_tags` signatures match the spec's calls; `prop_map`, `TAG_COLOR_PALETTE` (10 entries, `[:5]` valid), `_split_large`/`MAX_CHUNK_CHARS`, `_found_schema_version` (reads `text` or `select`, tolerates real array shape) are all real.
- The 8-key allowlist members are all `format: text` in `types_schema.py`; `wiki_excerpt` correctly excluded; WikiLog non-knowledge text props correctly excluded.
- SSRF (AC#4, AC#17), name-policy/`is_central`/fenced-source defenses, and the fcntl-flock `multiprocessing.Process` test requirement are inherited unchanged and not weakened.
- The schema-marker PATCH and `wiki_action` tag writes are best-effort/non-fatal — no new failure-to-fail-closed path on content writes.

## Round-2 scope
Address all BLOCKING (B1-B5) and SHOULD-FIX (SF1-SF9); apply SUGGESTIONs G1-G5 (cheap, all spec-text). Re-review will verify the dedup-guard redesign (B2), the two new locked-constraint ACs (B4/B5), and the schema-version bump prerequisite (B1).
