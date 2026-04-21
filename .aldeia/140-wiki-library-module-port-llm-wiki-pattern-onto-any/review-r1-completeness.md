# Completeness Review — Wiki Library Module (r1)

**Reviewer:** completeness-reviewer
**Date:** 2026-04-22

## Summary

The spec is unusually thorough and well-structured for a first SPEC promotion: problem context, personas, per-version scope/MoSCoW/acceptance-criteria/deliverables/risks/pre-release checklists, three Mermaid diagrams (ingest, query, lint), explicit configuration table, explicit threshold values, single-canonical-path decisions for risky API calls, and an Appendix A with runnable verification protocols. It largely satisfies the completeness checklist. However, there are a small number of real gaps — most notably an undefined return-shape for `wiki_bootstrap` (the v0.2.0 primary deliverable), an undefined `BootstrapResult`/`LintReport.warnings`, no behaviour for what happens when `reindex_anytype` itself fails during auto-reindex, and two acceptance criteria that are not independently testable as written (the "under 15 minutes" quick-start promise and the "first Anytype-native" positioning claim). There are also a handful of vague quantifiers and two minor contradictions between sections. None of these blockers are architectural; all are scoping/wording gaps that should be closed before implementation starts on v0.2.0.

## Findings

### BLOCKING

1. **Section: Proposed Solution > MCP Tool Interface Design / Delivery Phases > v0.2.0 — Missing `wiki_bootstrap` return-shape schema.**
   Issue: `wiki_ingest`, `wiki_query`, `wiki_lint` all have a concrete JSON schema defined (IngestResult, QueryResult, LintReport). `wiki_bootstrap` does not. The spec only says the tool "responds with a structured summary listing every object created, every property created" and "WikiLog receipt in all responses" but never enumerates the shape. Acceptance criterion v0.2.0#2 requires reporting each element as "already exists, skipped" — the structure of that report is unspecified. This is the v0.2.0 primary deliverable and implementers cannot write the tool or its tests without it.
   Recommendation: Add a `BootstrapResult` JSON schema parallel to `IngestResult`, minimally: `space_id`, `types_created[]`, `types_skipped[]`, `properties_created[]`, `properties_skipped[]`, `tags_created[]`, `tags_skipped[]`, `root_collection_deeplink`, `wiki_log_id`, `warnings[]`, `status`.

2. **Section: v0.3.0 > Ingest pipeline step 8 + Configuration > `WIKI_AUTO_REINDEX` — Undefined failure behaviour when the post-ingest reindex call fails.**
   Issue: Step 8 says "Call `reindex_anytype(space_id=space_id)` post-ingest (configurable, default: enabled)". The Failure modes table covers "Anytype 500" and "Qdrant unreachable" for `wiki_ingest` but not what happens if `reindex_anytype` returns an error or times out AFTER successful object creation. Is the ingest `status: "ok"` or `"partial"`? Is a retry scheduled? Is the WikiLog amended? Users will see fresh Source objects that are not yet searchable via `semantic_search`, which directly impacts the "Query compounding" guarantee in v0.4.0.
   Recommendation: Add explicit behaviour: ingest returns `status: "ok"` (objects created successfully) but adds a `reindex_failed` warning with the reindex error detail; WikiLog notes the reindex failure; documentation tells user to run `reindex_anytype` manually. Or, alternatively, specify that reindex failure downgrades `status` to `"partial"`. Either choice is fine; it must be chosen.

3. **Section: Success Criteria + Acceptance Criteria — "Quick-start promise" and "Karpathy parity" criteria are not independently testable as written.**
   Issue: Two acceptance criteria use prose success statements that cannot be mechanically evaluated:
   - v0.2.0 Success: "a contributor following README-only instructions can run `wiki.bootstrap(space_id=...)` in under 5 minutes from a fresh clone" — who measures this? Against which machine baseline? How many trials? Pass/fail rule?
   - v0.3.0 Success: "Karpathy parity: a Wikipedia article URL produces a committed set of Entity/Concept/Source objects with ≥ 2 relations each on completion" — which Wikipedia article? "Parity" with what specifically?
   Recommendation: Specify the exact fixture URL (e.g., `https://en.wikipedia.org/wiki/Mamba_(deep_learning_architecture)`), the minimum counts (e.g., ≥1 Source, ≥3 Entity, ≥2 Concept, every object ≥2 relations), the evaluator (the v0.3.0 pre-release checklist owner), and the trial protocol (single run counts as pass). For the quick-start, either drop the "5 minute" target from acceptance criteria and move it to aspirational prose, or define a concrete measurement protocol (e.g., reference hardware = Mac Mini M4, prerequisites met = Anytype + Qdrant + Ollama running, measured from first `wiki-bootstrap` command to return).

4. **Section: Proposed Solution > Type Schema + Operational Considerations > Configuration — `wiki_contradictions` property is defined on Entity/Concept but no ingest behaviour is specified for populating it.**
   Issue: `wiki_contradictions` appears in the Entity and Concept type definitions (line 238, 248) and is referenced by the Lint "Unresolved contradiction" check (line 504). But the Ingest Pipeline section (v0.3.0) does not describe when or how `wiki_contradictions` is populated. Karpathy's pattern and the Research Summary both call out "Document both positions, flag for review, never silently overwrite" — but the extraction prompt schema (lines 980-987) does not emit contradiction claims, and step 4 of the ingest pipeline only describes create/update, never contradiction handling. Without this, the Lint check at v0.5.0 will never fire in practice.
   Recommendation: Either (a) extend the extraction prompt and IngestResult to detect and record contradictions explicitly (a new output field, e.g. `contradictions: [{from: str, to: str, basis: str}]`, and a step in the pipeline that writes them to `wiki_contradictions`); or (b) explicitly mark contradiction population as deferred to a later version and remove the Lint check from v0.5.0's Must list until then.

### SHOULD-FIX

1. **Section: Proposed Solution > Ingest pipeline flowchart vs. prose step 4b — Contradictory resolution thresholds.**
   The Mermaid flowchart (line 304) branches on "embedding similarity ... >= upsert threshold", "0.70-upsert threshold", and "< 0.70". Prose step 4b says "If no exact match: embedding similarity check via bge-m3 against existing wiki objects of the same type" and step 4d says "If match below auto-upsert threshold but above the duplicate-surfacing floor (0.70): add to `objects_skipped` as `duplicate_proposed`." These are consistent, BUT the `WIKI_UPSERT_THRESHOLD_TITLE=0.92` default (line 1105) is never used in the resolve_entity pseudocode (lines 938-964), which only applies the embedding threshold. The pseudocode skips title similarity entirely after the exact-match step. Either the title threshold is unused (remove from config) or the pseudocode is wrong (add a title-fuzzy step between step 1 and step 2).
   Recommendation: Clarify whether title fuzzy matching happens (and where), or remove `WIKI_UPSERT_THRESHOLD_TITLE` from the config table.

2. **Section: v0.5.0 Lint > `potential_duplicates` + Configuration — Threshold inconsistency.**
   Line 508 says potential duplicates are reported at "similarity 0.70–upsert threshold". The Lint example schema (line 488) shows `similarity_score: 0.87`. The config defines `WIKI_DUPLICATE_SURFACE_FLOOR=0.70` and `WIKI_UPSERT_THRESHOLD_EMBEDDING=0.85`. So the valid range for `potential_duplicates` is 0.70–0.85, yet the example shows 0.87 which would trigger auto-upsert, not duplicate surfacing. Small but confusing for implementers.
   Recommendation: Adjust the example `similarity_score` to 0.78 or similar in the schema sample.

3. **Section: Proposed Solution > MCP Tool Interface + Delivery Phases — `WikiLog receipt in all responses` promise is not consistently honored.**
   Line 526 says "Every tool returns enough information (WikiLog ID + deeplink + structured status) to reconstruct what happened." IngestResult has `wiki_log_id`. QueryResult does NOT have a `wiki_log_id` field (schema lines 410-422). LintReport does NOT have a `wiki_log_id` (schema lines 469-495). BootstrapResult is unspecified (see BLOCKING #1). This is an under-delivered claim or an inconsistent schema set.
   Recommendation: Add `wiki_log_id` and `wiki_log_deeplink` to QueryResult and LintReport schemas, or soften the convention in the MCP Tool Interface Design section ("IngestResult includes wiki_log_id; other tools log to stderr only").

4. **Section: User Experience > Workflows > Workflow 2 step 7 / Delivery Phases v0.3.0 — Auto-reindex default contradiction.**
   Workflow 2 step 7 says "User calls `reindex_anytype(space_id=...)` after ingest... (This step may be automated by the ingest tool as a post-ingest call if configured.)" implying opt-in. The Configuration table (line 1108) shows `WIKI_AUTO_REINDEX` default = `true` (opt-out). The two frames disagree on the user's default expectation.
   Recommendation: Update Workflow 2 step 7 to "The ingest tool automatically calls `reindex_anytype` post-ingest (disabled by setting `WIKI_AUTO_REINDEX=false`)."

5. **Section: Boundary Conditions — Unstated empty / overflow limits for extraction input.**
   Line 977 shows `INPUT <source content, truncated to N tokens>` but `N` is never defined. The Ingest flowchart has `C_ERR[[DATA ERROR pdf/js/paywall]]` for unsupported content but no explicit handling for: (a) source > N tokens (truncation strategy? chunked extraction? warn?), (b) source == empty text / whitespace only, (c) extraction returns `summary: "empty_source"` as the prompt instructs (line 994) — what does the ingest pipeline do? Create a Source object with no derived entities? Skip the Source entirely?
   Recommendation: Define `WIKI_EXTRACT_MAX_TOKENS` in the config table with a reasoned default (e.g., 32k for qwen2.5:7b context, reserve 4k for response). Define behaviour on empty-source extraction: create Source object, 0 entities/concepts, WikiLog entry with `reason=empty_source`, ingest `status: "ok"` (not "partial" — successful handling of an empty source is still success).

6. **Section: Security Considerations > SSRF protections — Resource limits missing for fetch.**
   The SSRF code correctly blocks private IPs but says nothing about response size limits, connection timeouts, or total fetch time caps. A public URL returning a 10GB response, a slow-loris response, or an HTTP 200 with `Content-Type: video/*` is not handled. These are practical DoS and resource-exhaustion concerns on Jan's Mac Mini.
   Recommendation: Specify `httpx.Timeout` values (suggest: 10s connect, 30s read) and a max response size (suggest: 10MB); truncate and warn, or reject with `[DATA ERROR] source_too_large`.

7. **Section: v0.2.0 Acceptance criteria vs. Security > Auth scope — Write-token scope is an acceptance criterion but its pass rule is missing.**
   Line 599 Must: "write-token scope verified". Line 610 AC#7: verification script runs. But there is no explicit AC saying "tool returns an unambiguous auth-scope-insufficient error pointing to the remediation". The current AC#4 handles "Anytype not running" but not "Anytype running but token insufficient for type creation".
   Recommendation: Add AC: "`wiki_bootstrap` called with a read-only token returns `[CONFIG ERROR] insufficient_token_scope` and points to Anytype Settings → API for regeneration."

8. **Section: Mermaid diagrams — Only two of the three promised diagrams are ingest/query — the third (lint) is present. But the query flow could not recover from Qdrant outage in Tier 2, and this is not reflected in the diagram.**
   The `Failure modes per tool` table (line 1133) says Qdrant outage "falls back to Tier 1 if threshold allows, else `[API ERROR]`". The Query flowchart (lines 381-397) has no decision node for Qdrant availability after choosing Tier 2.
   Recommendation: Add a Qdrant-failure branch from node F (vector_augmented) that either falls back to E (index-navigation) with a warning or returns API ERROR, matching the behaviour described in prose.

9. **Section: Entity Resolution Semantics — Non-breaking-hyphen test case is mentioned but NFC + casefold does NOT normalize U+2011 (non-breaking hyphen) to U+002D (hyphen-minus).**
   Acceptance criterion v0.3.0#6: "Normalized-title resolution matches... 'BGE‑M3' (non-breaking hyphen) to the same entity." The `normalize_title` steps (lines 918-931) explicitly say "we deliberately do NOT strip punctuation or hyphens". NFC does not collapse U+2011 → U+002D. This AC will fail as implemented.
   Recommendation: Either extend `normalize_title` to explicitly map common hyphen/dash variants (U+2010, U+2011, U+2012, U+2013, U+2014) to U+002D before casefolding — and update the docstring — OR drop the non-breaking-hyphen case from the AC.

10. **Section: Concurrent Ingest Policy — Stale lock auto-replacement is unsafe as written.**
    Line 1122: "if the recorded PID is not alive ... the lock is considered stale and silently replaced." On a multi-user Mac or a restarted process, PID reuse is possible: a new unrelated process may happen to have the same PID as the former lock holder. `os.kill(pid, 0)` returning success does not prove it is the same ingest process.
    Recommendation: Also record and check `started_at`. If the recorded `started_at` is older than the OS boot time (via `psutil.boot_time()` or `uptime`), the lock is stale regardless of PID. Alternatively record a session-unique token and use `fcntl.flock`/`portalocker` rather than relying on PID liveness.

11. **Section: Delivery Phases > v0.4.0 Dependencies — v0.4.0 depends on v0.3.0 but the spec says "Query can technically run against a manually populated wiki but is only useful once ingest exists."**
    Line 730-731: the dependency is listed but softer than it appears. If v0.4.0 "can technically run" against a hand-seeded wiki, the test fixtures for v0.4.0 MUST support hand-seeding (they should anyway for hermeticity). Is seeding done via direct Anytype API, via a test-only helper, via cassettes? This affects v0.4.0 testability.
    Recommendation: Name the seeding mechanism. Likely answer: `tests/wiki/test_query.py` uses `WikiClient.create_object` directly (via respx mocks) to construct a synthetic 199/200/201-object fixture.

12. **Section: Open Questions — OQ#3 (Extraction model default) Must-resolve is v0.3.0 pre-release, but the Config table at line 1103 already commits to `qwen2.5:7b` today.**
    If the question is genuinely open, the default should be left undefined or marked provisional-with-review. If it's committed, the OQ should be closed (or downgraded to a validation task). Consistency matters for reviewers tracking open issues.
    Recommendation: Align — either mark the config default `qwen2.5:7b *(provisional — see OQ#3)*` with the current explicit parenthetical (already done on line 1103, good) AND explicitly note in OQ#3 that the default is a placeholder until v0.3.0 testing; OR close OQ#3 and make it a note rather than an open question.

### SUGGESTION

1. **Section: Proposed Solution > Type Schema — Consider documenting the relationship between `wiki_relations` on Entity and `wiki_related` on Concept.**
   Entity uses `wiki_relations`; Concept uses `wiki_related`. Both are "objects" properties linking to Entity/Concept. The naming divergence is not motivated. Either unify (both use `wiki_relations`) or note in the schema comment "deliberately distinct property keys to disambiguate graph queries" so implementers don't file a consistency bug.

2. **Section: Implementation Plan > Module Layout — `wiki/__init__.py` "public exports" line says `wiki_bootstrap, wiki_ingest, wiki_query, wiki_lint` but these are MCP tool names; they should be exported as regular Python functions with those names, OR the `__init__.py` should export the internal function names. The wording blurs the two concerns.**
   Minor; clarify in the comment what gets re-exported.

3. **Section: Observability — The "extraction_endpoint" field is logged at ingest startup but no redaction rule is given. If the endpoint URL contains an API key in a query string (some hosted providers allow this), it leaks to stderr.**
   Suggest adding: "URL query strings and userinfo components are stripped before logging."

4. **Section: Delivery Phases > v0.5.0 Dependencies — Phrase "may ship before v0.3.0/v0.4.0 if implementation parallelism allows" conflicts with opening of Delivery Phases: "v0.5.0 may start in parallel with v0.3.0/v0.4.0 but cannot tag until v0.2.0 is tagged."**
   The opening is clearer. Consider tightening v0.5.0 to match the opening phrasing exactly.

5. **Section: Appendix A — Cleanup is not specified for the verification script's write test.**
   A1 creates a marker in an existing object body; if PATCH body works, the object's content has been overwritten. Consider: run against a dedicated ephemeral test object created at the top of the script, deleted at the end. Currently the script uses `$ANYTYPE_OBJECT_ID` as if it were a sacrificial target. Document this or create a throwaway.

6. **Section: User Experience > Workflows — Workflow 1 step 4 says "Anytype deeplinks to each new Type are included in the response" but the Anytype type-level deeplink URL format has not been defined in the spec.**
   Object deeplinks follow `anytype://object/{space_id}/{object_id}`. Type deeplinks may follow a different format (e.g., `anytype://type/{space_id}/{type_key}`). Please either define it explicitly or state that type-level deeplinks will fall back to opening the space root until the format is confirmed.

7. **Section: Success Criteria — v0.3.0 mentions "Karpathy parity" but no v0.3.0 performance budget is given.**
   v0.2.0 has < 30s, v0.4.0 has < 5s, v0.5.0 has < 60s. v0.3.0 has no wall-clock budget. Ingest of a long arxiv paper with Ollama+7B extraction could easily take minutes. Suggest either a soft target ("< 2 min p95 for a 10k-word source on reference hardware") or explicit "no wall-clock SLO in v0.3.0; latency is a tuning task in v0.6+".

8. **Section: Market Analysis — "To our knowledge, the first Anytype-native LLM wiki" claim is hedged with a verification step, good. Suggest also building in a fallback positioning line in case verification finds a prior art, so the README change is a one-file swap rather than a rewrite.**

9. **Section: Operational Considerations > Observability — No log-level / verbosity knob is documented.**
   Suggest `WIKI_LOG_LEVEL` env var (info | debug) so operators can opt into `progress` events without code changes. Minor DX improvement.

10. **Section: Deferred Items — "Refactor `anytype_client.py` and `wiki_client.py` to share a base session" is listed. Suggest noting the concrete follow-up ticket number once filed, for traceability.**

## What's done well

- Per-version Scope/MoSCoW/Acceptance/Deliverables/Dependencies/Risks/Pre-release/Tests structure is consistent across all four versions and makes the spec trivially checkable.
- The single-canonical-path decisions for PATCH body and FilterExpression, backed by a committed verification script with a decision file, eliminate the most common cause of "spec ships two code paths." The Council ADVISORY cross-references show the review loop has been internalized.
- Three Mermaid diagrams (ingest, query, lint) cover the three non-trivial flows. The boundary test at 199/200/201 is explicit.
- Security Considerations is unusually complete for a SPEC — SSRF code sketch with IP ranges, token handling, `pip-audit` CI gate, LLM data exfiltration documented in three places (README, log, first-run banner).
- Entity Resolution Semantics section with the `normalize_title` contract, worked pseudocode, and explicit thresholds is a strong contributor-onboarding anchor.
- Error message design table (line 124) with three categories and concrete message patterns is rare in early specs and will pay back in support cost.
- Open Questions section ties each question to a "Must resolve by" version and the verification decision file, giving a clear gating rule for releases.
- Contributor's Map at the top gives new contributors an ordered reading path and calls out the additive nature of the module (v0.1.0 code is untouched).
- Deferred Items section is thorough and explains *why* each item is deferred — not merely that it is.
