# Council Meeting — Post-test (Round 1)

**Date:** 2026-06-05
**Ticket:** #285 — anytype-llm-wiki v0.4.0 — `wiki_query` (tiered retrieval: index-navigation + vector-augmented + synthesis + file-back)
**Phase reviewed:** test
**Client:** anytype-llm-wiki (open-source MIT; dual audience: internal Aldeia dogfood + public community tool)

## Attendance

| Role | Present | Reason |
|------|---------|--------|
| Council Chair | Yes | moderator / verdict synthesis |
| QA Director | Yes | minimum roster; phase owner — acceptance-criteria coverage + test strictness |
| Chief Technology Officer | Yes | TDD-red correctness, the unverified relation wire-contract, shared-tool blast radius, reviewer diligence |
| Chief Security Officer | Yes | injection-fence + SSRF tripwire + relation-write data-integrity test adequacy |
| Infrastructure Lead | Yes | repo domains = infrastructure + agent-operations; failure-mode coverage, 32GB resource envelope, synthesis timeout |
| Client Advocate | Yes | non-aldeia-box repo; dual audience; community-surface (docs) + dogfood-first discipline |
| Chief Product Officer | No | test phase does not change product strategy; CPO carry-forward items (docs, file_back demo) already captured in the post-spec addendum and re-checked by Client Advocate |
| Legal Counsel | No | not materially triggered — MIT, local-first, no PII beyond user-authored notes, no new data store or external-transmission surface (unchanged since spec council) |

## Context Presented

The test phase produced a TDD-red suite for v0.4.0 `wiki_query` in `tests/wiki/test_query.py` (2784 lines): 59 CI-runnable tests + 1 skip-gated live smoke test. The suite went through two in-phase review rounds — R1 (NEEDS CHANGES) caught five vacuous "a do-nothing stub would pass" assertions; R2 (APPROVED) verified all five resolved with line citations. The four test-phase addendum items from the post-spec council (QA-12 Tier-2 candidate-fetch-failure, QA-13 threshold-boundary parametrization, CSO-1 realistic multi-vector injection, CTO-6 dual-shape relation parser + live SF5) were folded in. Phase summary recommends advancing; the watcher routed to this council before Decide.

The council's job was governance, not line-level re-review (that happened in-phase): is this suite a faithful, strict TDD-red gate for the impl phase, and are the carry-forward impl-phase obligations clearly enough specified to gate downstream?

## Discussion

The council independently verified the deliverable rather than trusting the review summaries. Multiple members re-ran the suite (`59 failed, 1 skipped, 1 deselected`) and confirmed it fails for the RIGHT reason (`ModuleNotFoundError: anytype_llm_wiki.wiki.query`, missing `semantic_search_core` / config resolvers) with zero collection errors, and that the existing suite is untouched (454 passed). Three load-bearing surfaces converged:

- **Relation-write data integrity (CTO ↔ CSO ↔ QA).** The N1 relation-clobber (the spec phase's central technical concern) is genuinely pinned: `test_reciprocal_relation_read_merge_write` pre-seeds `wiki_relations=["e1","e2"]` and asserts the reciprocal PATCH carries `["e1","e2", query_id]` — a `_write_bidirectional_relations`-style overwrite would produce `[query_id]` only and fail. CTO confirmed against real source (`ingest.py:287-320`) that `_patch_relation` full-overwrites, so the spec's read-merge-write resolution is technically correct. `test_drew_from_uses_cached_ids_not_titles` proves relation targets come from cached fetched IDs, not LLM-hallucinated titles. The residual: the merge test exercises a *mocked* relation shape; if the live `get_object` shape differs from both mocked forms, the read-merge could merge an empty prior set and silently re-introduce the clobber. All three members agreed this is correctly bound by addendum item-4 (impl must pin the live shape and add it to the fixture) plus the skip-gated live smoke test — an impl/release gate, not a test-phase blocker.

- **Test strictness / stub-passing (QA ↔ CTO).** Both confirmed the R1→R2 cycle was substantive, not a rubber-stamp: R1 found five real defects (AC#5 signature-only multi-type tests a `return []` stub would pass; injection fence asserted at the wrong boundary; implicit no-WikiLog assertion; SSRF catch-all defeating its own tripwire; QA-12 soft status disjunction), and R2 verified each fix behaviorally. QA independently confirmed the AC#5 fix now seeds a real in-memory Qdrant and asserts `len(results) > 0` against the actual nested AND-of-OR filter — the strongest CI proof short of live Qdrant.

- **Security + operational degradation (CSO ↔ Infra).** CSO verified the injection-fence test inspects the prompt at the `_call_ollama_synthesis` transport boundary (not `synthesize` wholesale), confirms a three-vector payload lands INSIDE the `<context>` fence and is ABSENT before it, and that the SSRF tripwire is now allowlist-only. Infra verified every operational failure mode degrades to a pinned, non-hanging status sentinel (Qdrant-down 199→ok / 200→error, Anytype-down total-enumeration error with no WikiLog write, Tier-2 candidate-fetch → `status: partial`, partial-neighborhood downgrade), the 32GB envelope is protected (synthesis reuses the resident extraction model; input caps behaviorally tested), and the mocked 5s latency gate is correctly distinguished from the production SLO.

**Chair verification (independent):** confirmed the CTO's correction to addendum item-11 against real source — `indexer.py:13` is `from .embedder import embed` (NOT `embed_query`); `embed_query` is imported by `server.py:9`. The behavioral multi-type test monkeypatches `_idx_mod.embed_query` (test line 1844), so the impl MUST add `from .embedder import embed_query` to `indexer.py` during the `semantic_search_core` extraction, and `semantic_search_core` MUST construct its Qdrant client via the `_qdrant()` factory, or the in-memory behavioral tests fail at the monkeypatch with `AttributeError`. This is a net-new, actionable impl requirement that corrects an erroneous existing addendum item — captured in the post-test spec addendum.

## Findings

### BLOCKING
None. All six members (chair + five specialists) signed off with zero blocking findings.

### ADVISORY
1. **[CTO — verified by Chair] (HIGH) Addendum item-11 / CTO-5 is factually wrong and must be corrected for impl.** `embed_query` is NOT imported by `indexer.py` (it imports only `embed`); it lives in `server.py:9`. The behavioral multi-type test monkeypatches `_idx_mod.embed_query`, so the impl must add `from .embedder import embed_query` to `indexer.py` when extracting `semantic_search_core`, and `semantic_search_core` must build its client via the `_qdrant()` factory — otherwise the in-memory tests fail with `AttributeError` on the monkeypatch target. Corrected in `spec-addendum-post-test-r1.md`.
2. **[QA / Infra / Client] Doc + operational impl ACs have no automated test backstop.** Addendum items 6, 7 (README quick-start `bootstrap→ingest→query` + explicit `file_back=True` demo, "How it works" with the reindex-latency caveat, `docs/known-limitations.md`), item 8 (`WIKI_SYNTH_TIMEOUT` decision + slow-synthesis log signal), and item 10 (`error_category` + `filterexpression_fallback` >500-row warning surfaced to operator logs, not only the per-query `QueryResult`) cannot be asserted by this suite. They must be verified by manual review at the impl gate, not assumed covered.
3. **[QA / CTO / CSO / Client] Live relation-shape pin (addendum item-4 / CTO-6) is the one unverified wire contract.** If the live `get_object` relation-element shape differs from both mocked forms, the impl MUST fold the real shape into the fixture so `test_reciprocal_relation_read_merge_write` exercises a non-empty prior set — otherwise the N1-clobber guard could pass vacuously, risking silent relation-data loss in the user's own Anytype vault. Binding impl/release gate.
4. **[CSO] File-back injection-amplifier security note (addendum item-9 / CSO-2) still owed at impl.** Impl must add the one-sentence threat-model note to Security Considerations naming the file-back loop as an injection amplifier, bounded by the SF1 clean-synthesis gate + min-sources(3)/min-words(100).
5. **[Infra / Client] Release-gate items 12, 13 must be transcribed onto the actual v0.4.0 release checklist** (not left only in the addendum): live smoke test against real Qdrant v1.17.0 + Aldeia's own vault, internal-dogfood-first / community-tag-second; maintainer-measured p95 < 5s on Mac Mini M4 (the mocked 5s gate is a no-pathology check, not the SLO).
6. **[CSO / Infra] Watch-items, no action this phase.** Qdrant at-rest encryption (consistent with localhost-only acceptance; re-evaluate only if Qdrant is exposed beyond localhost); always-on O(N) `list_objects` enumeration is a scaling cliff as the file-back loop grows the wiki (log a v0.5.0 follow-up to cache the count); the SSRF tripwire is structurally weaker than its name but acceptable given no user-supplied URLs today.
7. **[Client] (LOW) Incomplete client context.** `engagement.md` and `market.md` are absent from `.aldeia/context/`; did not impair this review (self-owned open-source project, unambiguous owner). Noted for completeness.

## Resolutions

- The N1 relation-clobber risk (the spec council's central concern) was independently confirmed genuinely pinned by CTO, CSO, and QA against the real test assertions and real `ingest.py` source — not merely renamed. No member sought to re-open it.
- The five in-phase R1 stub-passing findings were confirmed resolved with behavioral depth by both QA and CTO via independent reads of the real test code (not the review summaries).
- No member raised a new blocking concern. No contradictions required resolution; the security, engineering, operational, quality, and client assessments were mutually consistent. The only net-new finding (the `embed_query` import correction) was verified by the chair and folded into a post-test spec addendum.

## Recommendation

**Recommended target:** `impl` (next phase in SDLC order after test)
**Confidence:** high
**Rationale:** The test suite is review-clean (in-phase R2 APPROVED; council re-verified 0 BLOCKING), fails correctly for the right reason (59 red, zero collection errors), introduces zero regression (454 passing), and encodes the spec contract with behavioral depth on the two highest-risk surfaces (the N1 read-merge-write and the shared `semantic_search` nested-filter change). All 20 ACs and all four test-phase addendum items map to CI-runnable tests. The impl phase must honor the carry-forward acceptance/exit criteria — the corrected `embed_query`/`_qdrant` extraction requirement (advisory 1), the doc + operational ACs with no test backstop (advisory 2), the live relation-shape pin (advisory 3), the file-back amplifier security note (advisory 4), and the release-gate items (advisory 5) — all consolidated in `spec-addendum-post-test-r1.md`. The watcher enforces autonomy policy on the recommended target.
**Dissent:** None.
