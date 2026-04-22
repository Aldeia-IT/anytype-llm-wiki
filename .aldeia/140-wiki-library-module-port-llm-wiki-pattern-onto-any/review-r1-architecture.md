# Architecture Review — Wiki Library Module (r1)

**Reviewer:** spec-architecture-reviewer
**Domain:** product + agent-operations
**Date:** 2026-04-22

## Summary

**Verdict: CHANGES REQUIRED before implementation.** The spec is generally well structured and largely coherent with the v0.1.0 codebase — the single-canonical-path discipline for PATCH and FilterExpression is clean, the 4-phase delivery order is sound, the `wiki/` subpackage layout is a reasonable extension of the existing flat module, and the claim that `semantic_search` / `reindex_anytype` already support new `type_key` values with zero code changes is verified in `src/anytype_llm_wiki/server.py:42` and the `chunker.py` payload shape. However, one acceptance criterion directly contradicts the `normalize_title` implementation given in the same spec (non-breaking hyphen U+2011 is not folded to U+002D by NFC or NFKC), the `wiki_client.py` vs `anytype_client.py` split introduces duplication that is worth resolving now rather than deferring, a couple of code snippets have small correctness issues, and the 12-file `wiki/` subpackage is over-structured relative to what v0.2.0 actually ships. None of these are architecturally fatal — the overall shape is right — but the normalization contract discrepancy is a BLOCKING correctness bug that must be fixed before v0.3.0 can be coded to the spec.

## Pattern Compliance

- **`wiki/` subpackage layout vs. existing flat module.** The existing layout at `src/anytype_llm_wiki/*.py` is flat (7 modules, all sibling files). The spec proposes `src/anytype_llm_wiki/wiki/*.py` as a nested subpackage. This is a deliberate break with the existing pattern but is defensible: it signals "this is a cohesive subsystem" and prevents 12+ new files polluting the top level. Coherent choice, call it out in the README.
- **Tool registration pattern.** The spec (lines 829–866) shows `@mcp.tool()` on four functions in `server.py`. This matches the existing `server.py:12` (`@mcp.tool() def semantic_search`) and `server.py:67` (`@mcp.tool() def reindex_anytype`) verbatim. PASS.
- **API client pattern coherence.** `anytype_client.py` uses per-call `with _client()` (new `httpx.Client` each call). The spec proposes `wiki_client.py` as a class with a **module-scoped** `httpx.Client` and a `close()` method. This is a real improvement for a write-heavy ingest path (connection reuse, keep-alive), not just a rename. See SHOULD-FIX #1 for the duplication concern.

## Integration Verification

- **Claim: "`type_key` filtering already supports new wiki types with zero code changes to `semantic_search`."** PASS. Verified at `src/anytype_llm_wiki/server.py:38–42` — conditions are built generically from whatever `types` list is passed in, and the payload key `type_key` in `indexer.py:95` comes straight from `chunker.py:21` (`obj.get("type", {}).get("key", "unknown")`). Any new Anytype type with a `wiki_entity`/`wiki_concept`/etc. key flows through automatically.
- **Claim: "`reindex_anytype` handles new wiki object types without modification."** PASS. `indexer.py:54` calls `list_spaces` and `list_objects` (both type-agnostic); chunking keys on `obj["type"]["key"]` with `"unknown"` fallback. No hardcoded type filter. Spec line 204 correctly cites `server.py` lines 38–42.
- **Claim: "`fastmcp>=2.0.0` is the framework."** PASS. Verified in `pyproject.toml:10`.
- **Claim: bootstrap creates "6 object Types" (Source, Entity, Concept, Comparison, Query, WikiLog).** Coherent with the schema section (lines 222–272). The Comparison-type justification (lines 256–257) is honest about the risk that it remains empty and commits to revisiting after v0.4.0 data — appropriate for v0.2.0 to ship a complete schema.
- **Claim: "domain_tags parameter replaces the default taxonomy" AND "re-running with an expanded list adds new tags without removing existing ones".** (Acceptance criterion 5, line 608.) These two statements are in tension: "replaces" on first call and "adds without removing" on re-run is reasonable, but only if the first-call semantics are actually additive-from-empty, not destructive. The spec does not specify what happens if `domain_tags` is passed on re-run with a tag that was in the first call's list but not the second — are those tags preserved or removed? Needs clarification. (SHOULD-FIX #2.)

## Verification Audit (codebase-grounded)

- **Python 3.11+ syntax of code snippets.** Mostly valid. Minor issues:
  - Line 887–889: `@contextmanager def space_ingest_lock(space_id: str) -> Iterator[None]: ...` — `Iterator` needs import from `collections.abc` or `typing`. Trivial but should be explicit in the signature module.
  - Line 1168–1169: `ipaddress._BaseAddress` is a private attribute (leading underscore). The proper public type is `ipaddress.IPv4Address | ipaddress.IPv6Address` or the common base via a broader return type. Not broken, but not clean public API. (SHOULD-FIX #3.)
  - Line 1173: `any(addr in net for net in _BLOCKED_NETS) or addr.is_private or addr.is_loopback or addr.is_link_local` — this is correct but the `is_private` check is redundant with the RFC1918 networks already in `_BLOCKED_NETS`. Not a bug, just belt-and-suspenders.
- **File paths match the repo or the spec's own proposals.**
  - `src/anytype_llm_wiki/{server,anytype_client,indexer,chunker,embedder,config}.py` (line 24): all exist.  PASS.
  - `src/anytype_llm_wiki/__init__.py`: exists (empty). PASS.
  - `scripts/verify-anytype-writes.sh`: does NOT exist in the repo today. Spec acknowledges this — it's a v0.2.0 deliverable. Consistent.
  - `.aldeia/140-wiki-library-module-port-llm-wiki-pattern-onto-any/patch-decision.md`: does not yet exist; created by the verification script. Consistent.
  - `tests/wiki/`: does not exist; v0.2.0 creates it. Consistent.
- **Function/type-signature consistency.** Tool signatures in the "Public API" block (lines 829–867) match the per-pipeline signatures in the flow sections (lines 320–327, 400–407, 460–466). PASS.
- **`WikiClient` improvement over `anytype_client.py`.** PASS (real improvement). The existing `_client()` factory returns a fresh `httpx.Client` per call (`anytype_client.py:16–17`). For write-heavy ingest (tens of Type/Property/Object creates per bootstrap, N entity updates per ingest), module-scoped client + keep-alive is a genuine performance win. However, the fact that `anytype_client.py` is left alone (Deferred Items, line 1330) means the repo ships two divergent patterns for the same API — see SHOULD-FIX #1.
- **Entity-resolution pseudocode uses real Anytype API endpoints.**
  - Line 944 `client.search(space_id, query=candidate_title, filter={"type_key": type_key})` — aligns with the POST `/v1/search` / `/v1/spaces/{space_id}/search` endpoint used in the verification script (spec lines 1406, 1419). Coherent, though the filter shape shown here is the simplified `{"type_key": ...}` and the real API expects `{"condition": "and", "filters": [...]}` (per the verification script at spec line 1425). The pseudocode is illustrative, not literal. PASS with note that `WikiClient.search` has to translate.
  - Line 951 `qdrant_nearest(...)` is a placeholder — there is no such function in v0.1.0; must be defined in `wiki/` or reuse `server.py:semantic_search` internals directly. Mark as illustrative.
- **`normalize_title` contract vs claimed edge cases.** **FAIL — BLOCKING.** Spec line 667 (acceptance criterion) and line 1267 (test plan) claim that `normalize_title` must match `"bge-m3"`, `"Bge-M3"`, `"BGE‑M3"` (non-breaking hyphen U+2011), and `"  BGE-M3  "` to the same entity. The implementation at line 915–931 uses `unicodedata.normalize("NFC", raw).casefold()` + whitespace collapse. NFC does NOT fold U+2011 (non-breaking hyphen) to U+002D (ASCII hyphen-minus). I verified this empirically: `NFC("BGE‑M3").casefold() == "bge‑m3"` and `NFC("BGE-M3").casefold() == "bge-m3"` — these strings are not equal. NFKC is closer but still does not help: NFKC maps U+2011 to U+2010 "HYPHEN", which is also not U+002D. To satisfy the acceptance criterion, the function must either (a) add a punctuation-normalization step that maps U+2010/U+2011/U+2012/U+2013/U+2014 (and non-breaking and fullwidth variants of the ASCII hyphen) to U+002D, or (b) drop the non-breaking-hyphen claim from the acceptance criteria. Pick one and align both. See BLOCKING #1.
- **Mermaid diagram syntactic validity.** Three `flowchart TD` diagrams (lines 289–317, 381–397, 443–457). All use valid Mermaid node, edge, and decision syntax. The double-brackets `[[DATA ERROR<br/>ssrf_blocked]]` at line 294 and similar is valid subroutine-shape syntax. Diagram edge label at line 304 (`>= upsert threshold`) will render because Mermaid is forgiving about `>=`, but a more portable form would be `&gt;=` or a paraphrase; still PASS.
- **Mermaid diagram fidelity to the described flow.**
  - Ingest diagram: node L "Page threshold — 2+ sources or central" misses a path. The prose at step 4e (line 361) says "Create object if entity appears in 2+ sources OR is central to this source. Skip otherwise." The diagram matches. PASS.
  - Query diagram: matches the tiered retrieval prose. PASS.
  - Lint diagram: node order (E asymmetric before F orphans) matches the check order in the lint table.
- **Threshold "200 inclusive" decision rule.** Line 429 says "mode flips at 200 inclusive" and line 386 (diagram) reads `count >= WIKI_INDEX_THRESHOLD`. Boundary tests at line 716–717 assert `retrieval_mode="index_navigation"` at 199 and `"vector_augmented"` at 200 and 201. Self-consistent. PASS.

## Findings

### BLOCKING

1. **Entity resolution — `normalize_title` contract contradicts its own acceptance criterion.** (Section: Entity Resolution Semantics + v0.3.0 Acceptance Criteria + Test Plan.)
   - **Issue:** Acceptance criterion 6 (spec line 667) and test plan ingest bullet (spec line 1267) both assert that `"BGE-M3"` and `"BGE‑M3"` (U+2011 non-breaking hyphen) resolve to the same entity via `normalize_title`. The pseudocode at spec lines 915–931 uses `unicodedata.normalize("NFC", raw).casefold()` — empirically, NFC does not fold U+2011 to U+002D (verified: `NFC("BGE‑M3").casefold()` = `"bge‑m3"`, NOT `"bge-m3"`; NFKC produces `"bge‐m3"` with U+2010 which is still a different codepoint from `-`). The function as specified will fail its own acceptance criterion on the non-breaking-hyphen case.
   - **Recommendation:** Add a Unicode hyphen/dash normalization step to `normalize_title` — map U+2010, U+2011, U+2012, U+2013 (en dash), U+2014 (em dash), U+2212 (minus), and fullwidth variants to U+002D before the casefold+whitespace steps. Then add a unit test that explicitly enumerates all six codepoints. Alternatively, drop the non-breaking-hyphen claim from the acceptance criterion — but the hyphen variants are a real entity-resolution pain point, so adding the mapping is the right call. State in the docstring that punctuation characters other than dash-like glyphs are *not* normalized ("GPT-4" vs "GPT 4" remain distinct, as the current docstring correctly says).

### SHOULD-FIX

1. **Two divergent Anytype HTTP client patterns in the same package.** (Section: Architecture Overview / Deferred Items.)
   - **Issue:** v0.2.0 introduces `wiki/wiki_client.py` (class, module-scoped `httpx.Client`, write-capable) while `anytype_client.py` (read-only, per-call client) is intentionally left untouched (Deferred Items, spec line 1330). Once `wiki_client.py` supports `get_object` / `list_objects` / `search` (which it must, for entity resolution at ingest time), the two clients duplicate headers, timeout config, error handling, and base URL logic. This is path-of-least-resistance in v0.2.0 and honest about it, but it sets up a six-month-long drift problem.
   - **Recommendation:** Either (a) commit to extracting a small shared base — `_BaseAnytypeClient` with headers/timeout/base URL — in v0.2.0 so `anytype_client.py` and `WikiClient` both inherit; this is maybe 30 LOC, or (b) add a concrete deadline (e.g., "consolidate by v0.4.0") to the Deferred Items entry rather than the open-ended "v0.3.x+ follow-up ticket may unify them". The current split will silently rot as write paths outgrow read paths.

2. **Idempotency semantics of `domain_tags` on re-bootstrap are ambiguous.** (Section: Type Schema / v0.2.0 Acceptance Criteria.)
   - **Issue:** Line 282 says "re-running with an expanded list" is idempotent-additive. Line 608 says custom `domain_tags` "replaces" the default taxonomy. What happens if a user runs `bootstrap(domain_tags=[A,B,C])` then re-runs `bootstrap(domain_tags=[A,B])` (smaller list)? Are tags removed? Preserved? The spec does not say. Given the closed-option enforcement is Anytype's job and objects may already reference C, the right semantics are almost certainly "union only, never delete" — but state it explicitly and test it.
   - **Recommendation:** Add a single sentence to the "Tag taxonomy" prose: "Re-bootstrap with `domain_tags` is union-only; existing tags are never removed, even if absent from the new list." Add a corresponding unit test.

3. **`ipaddress._BaseAddress` is a private symbol.** (Section: Security Considerations / SSRF protections.)
   - **Issue:** Line 1168–1169 type annotation uses `ipaddress._BaseAddress`. This is a private module attribute and mypy/pyright will flag it; it can change between Python versions.
   - **Recommendation:** Change the return type annotation to `ipaddress.IPv4Address | ipaddress.IPv6Address`, which is the documented public type of `ip_address()`.

4. **Entity resolution pseudocode filter shape does not match the real Anytype filter shape.** (Section: Entity Resolution Semantics.)
   - **Issue:** Line 944 shows `filter={"type_key": type_key}` but the real Anytype POST /search filter body (spec line 1425–1432) is `{"condition": "and", "filters": [{"key": "type_key", "condition": "eq", "value": ...}]}`. The prose is illustrative, but a reader trying to implement to the spec will write the wrong shape.
   - **Recommendation:** Either replace the pseudocode filter with the canonical shape, or add a one-line `# WikiClient.search translates this to the Anytype FilterExpression shape` comment above the call, pointing at the verification script's example.

5. **`wiki_ingest.domain_hint` semantics are under-specified.** (Section: Ingest Pipeline.)
   - **Issue:** Line 326 comment says `"optional tag to pre-apply (e.g. 'wiki_ai-research')"`. But the ingest pipeline must validate this against the closed-option taxonomy created at bootstrap — what happens if the user passes a `domain_hint` that is not in the bootstrapped `domain_tags`? Error? Auto-add? Silently drop?
   - **Recommendation:** One sentence in the ingest steps (around step 4): "If `domain_hint` is not a member of the space's `wiki_domain_tags` taxonomy, return `[CONFIG ERROR]` naming the valid tag set." Mirrors the closed-option contract.

6. **The `wiki/` subpackage is over-structured for the v0.2.0 shippable slice.** (Section: Module Layout.)
   - **Issue:** Spec proposes 12 files in `src/anytype_llm_wiki/wiki/` across v0.2.0–v0.5.0. v0.2.0 alone ships 8 of these (`__init__.py`, `wiki_client.py`, `types_schema.py`, `bootstrap.py`, `config.py`, `locks.py`, `normalize.py`, `cli.py`) plus `tests/wiki/` with 5 test files. For a single tool (`wiki_bootstrap`), this is heavy. `locks.py` and `normalize.py` are shipped in v0.2.0 despite not being exercised until v0.3.0 (line 585–586 acknowledges this: "shipped early for test coverage"). The risk isn't code size — it's that v0.2.0 becomes hard to review because most of its surface has no caller.
   - **Recommendation:** Either (a) merge `locks.py` and `normalize.py` into `wiki/util.py` (one file, two functions) in v0.2.0 and split them out in v0.3.0 when they have callers — cheaper to review, and the acceptance tests still exercise them, or (b) acknowledge the "ship with no caller" pattern explicitly in the v0.2.0 Scope (in) as "API stability seeding" so a reviewer knows why `normalize.py` exists without an ingest call site. Option (b) is lower-cost.

7. **Bootstrap schema section does not list `wiki_log` type_key explicitly.** (Section: Type Schema.)
   - **Issue:** The schema enumerates 6 types but only lists property keys (e.g., `wiki_url`, `wiki_description`). The `type_key` values (presumably `wiki_source`, `wiki_entity`, `wiki_concept`, `wiki_comparison`, `wiki_query`, `wiki_log`) are never spelled out as literal identifiers. Spec line 427 does reference `wiki_entity`, `wiki_concept`, `wiki_comparison`, `wiki_query` — but `wiki_source` and `wiki_log` are inferred. The lint `object_counts` key names at line 473 are `entity`/`concept`/`comparison`/`query`/`wiki_log`/`source` — inconsistent (no `wiki_` prefix except on `wiki_log`).
   - **Recommendation:** Add an explicit `type_key:` line under each type heading in the schema section. Align `object_counts` keys to the canonical type_keys.

8. **FilterExpression fallback "list-objects with property query params and client-side filtering" is hand-waved.** (Section: Query Pipeline.)
   - **Issue:** Line 437 proposes a fallback for Tier 1 if FilterExpression is a no-op. "list-objects with property query params and client-side filtering" implies pulling every wiki object and filtering in Python. For a 200-object wiki this is fine; for a 10,000-object wiki it is not. The spec never tests this path because v0.2.0 verification presumably pins the primary path.
   - **Recommendation:** Add a one-line note: "If the fallback path is selected, `wiki_query` warns via `warnings` when the returned set size exceeds 500 and recommends upstream filter use." Or: commit to re-running verification as part of each release pre-flight so the fallback never actually ships.

### SUGGESTION

1. **The WikiLog "append-only" claim deserves one sentence on update semantics.** Spec calls the WikiLog "append-only" (line 265, 200). But WikiLog objects use normal Anytype Objects — nothing prevents an operator from manually editing them. The append-only property is an operational convention, not enforced. Worth stating: "Append-only is a convention. The lint suite does not check for retroactive WikiLog edits."

2. **Consider a `wiki_status` lint check in v0.5.0.** The schema defines `wiki_status: active | archived | stub` for Entity/Concept (lines 241, 250) but the lint suite does not check for long-lived `stub` entries. A "stub older than 30 days" Medium-severity check would fit naturally with the 7 existing checks.

3. **The `html2text` / `markdownify` dependency choice is decided without a comparison.** Line 354 mentions `markdownify` (v0.3.0 dep); the review prompt flags `html2text` as an alternative. Both are actively maintained, MIT-licensed, and pure Python. `markdownify` is more modern and produces cleaner output for modern HTML; `html2text` has more config knobs for compatibility. A one-sentence rationale ("chose markdownify for cleaner code-block and list handling on arxiv HTML") would protect against future second-guessing. No blocking concern — pymupdf (deferred) is also unambiguously the right Python PDF parsing choice when PDFs are added.

4. **Phased-delivery integration points are called out but not diagrammed.** The spec explicitly states v0.4.0 depends on v0.2.0 + content (v0.3.0) and v0.5.0 can parallel v0.3.0/v0.4.0 but tags last. A one-line dependency graph (Mermaid or ASCII) at the top of "Delivery Phases" would make the tag-order rule unmissable.

5. **The "first Anytype-native LLM wiki" claim verification is a v0.2.0 README prerequisite, not a blocking task.** Line 177 correctly gates the claim behind verification. Suggestion: add the verification step to the v0.2.0 pre-release checklist (line 628–634) — currently the checklist only covers code artifacts, not the positioning claim.

## What's done well

- **Single-canonical-path discipline.** The PATCH body / FilterExpression decision rule (lines 370–376 and 437) — verify once, pick one, never ship dual paths — is exactly right and directly addresses an "OSS-scrutiny" concern. The `patch-decision.md` record + reviewer-enforces-match convention is strong.
- **Verification script scheduled before code.** `scripts/verify-anytype-writes.sh` ships in v0.2.0 before any PATCH-dependent code lands in v0.3.0. This is the correct ordering and the spec is explicit about it.
- **Phased MoSCoW per version.** Each version has scope-in, scope-out, Must/Should/Won't, acceptance criteria, deliverables, dependencies, risks/mitigations, pre-release checklist. The template is applied consistently across v0.2.0 → v0.5.0. Very readable.
- **The `type_key`-based extension story.** The architectural bet — "Anytype's existing type_key payload means `semantic_search` and `reindex_anytype` work for new wiki types with zero code change" — is verified against the codebase and is the cleanest possible integration point. Worth keeping that claim foregrounded in the README.
- **SSRF protections are specified with code, not handwaved.** `_BLOCKED_NETS`, redirect loop, DNS-rebinding acknowledgment as a stated limitation — this is the correct level of specificity for a published OSS security surface.
- **Concurrent ingest policy is specific and shippable.** Per-space file lock, PID-based stale detection, `contextmanager` for release-on-exception, explicit cross-host limitation. This is what good v0.3.0-level specifications look like.
- **Tiered retrieval with a configurable threshold and a boundary test.** The 199/200/201 boundary test is correctly foregrounded; the threshold is an env var, not a hardcoded constant; the decision rule (`count >= WIKI_INDEX_THRESHOLD`) is unambiguous.
- **Open Questions have owning versions.** Every OQ has a "Must resolve by vX.Y" — this is the right way to keep unknowns from silently crossing release boundaries.
- **The Comparison type's self-critique.** Line 256–257 acknowledges Comparison may stay empty and commits to revisiting after v0.4.0 data. Honest self-assessment of schema decisions is rare in spec docs.
