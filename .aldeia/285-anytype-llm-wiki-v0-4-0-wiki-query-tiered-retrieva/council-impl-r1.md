# Council Meeting — Post-impl (Round 1)

**Date:** 2026-06-05
**Ticket:** #285 — anytype-llm-wiki v0.4.0 — `wiki_query` (tiered retrieval: index-navigation + vector-augmented + synthesis + file-back)
**Phase reviewed:** impl
**Client:** anytype-llm-wiki (self-owned, open-source MIT; Python/uv MCP server; Qdrant + Ollama; local-first; dual audience — internal Aldeia dogfood (primary) + public community tool (secondary))

## Attendance

| Role | Present | Reason |
|------|---------|--------|
| Council Chair | Yes | moderator / verdict synthesis |
| Chief Security Officer | Yes | minimum roster; file-back injection-amplifier, SF8 scrub uniformity, SSRF posture, shared-core blast radius |
| Chief Technology Officer | Yes | minimum roster; the two highest-risk surfaces (N1 relation-clobber, Decision-2 filter), addendum C1/A1 corrections, reviewer diligence |
| QA Director | Yes | minimum roster; 20-AC coverage, suite green/regression, doc/operational ACs with no test backstop |
| Chief Product Officer | Yes | minimum roster; user value (closing the compile→query loop), scope discipline, onboarding/doc quality (CPO-15/16) |
| Legal Counsel | Yes | minimum roster; confirm the "not materially triggered" posture still holds for shipped code (licensing, file-back vault writes, external transmission, provenance, PII) |
| Infrastructure Lead | Yes | repo domains = infrastructure + agent-operations; finite-timeout backstop, operator-log surfacing, 32GB envelope, failure-mode degradation, release gates |
| Client Advocate | Yes | non-aldeia-box repo; dual-audience; internal-dogfood-first discipline, owner-vault data-integrity risk, community first-experience |

Final delivery gate (post-impl → done): full council seated per the Phase-2 "last chance before release" rule. Legal seated this round (was absent at spec/test councils) to confirm the no-trigger conclusion against the actually-shipped code.

## Context Presented

The impl phase delivered the `wiki_query` MCP tool + `wiki-query` CLI subcommand — the read-and-synthesize path that closes the "compile once, query later" loop (`src/anytype_llm_wiki/wiki/query.py`, ~950 lines: pre-checks → enumerate/count → tier select → 1-hop neighborhood → bounded synthesis → file-back read-merge-write → WikiLog), the shared `semantic_search_core` extraction into `indexer.py` (Decision-2 nested multi-type filter), six v0.4.0 config resolvers + `.env.example`, the synthesis prompt, docs (README quick-start + How-it-works + Security note; `docs/known-limitations.md` §7/§8; CHANGELOG v0.4.0 + release checklist), and replacement test coverage.

In-phase review: 5 parallel specialists → APPROVED WITH CONDITIONS (0 CRITICAL, 1 MAJOR, 11 MINOR); fix round (`9b30aa6`) resolved the MAJOR (QueryResult error-return contract) + 5 MINOR. Lead independently verified the green suite (query+fetch 60 passed/5 skipped; full non-live 514 passed / 0 failed / no regressions). Jan's standing directive: the impl team MUST honor the post-test council findings (`spec-addendum-post-test-r1.md`).

The council's job was governance — strategic readiness for delivery — not line-level re-review (that happened in-phase). Each member independently verified the deliverable against real source rather than trusting summaries.

## Discussion

**Jan's directive — post-test addendum honored (verified by Chair + every relevant specialist).** Independent verification confirmed all binding `spec-addendum-post-test-r1.md` items are present in code: C1 `from .embedder import embed_query` in `indexer.py:13`; A1 `semantic_search_core` builds its client via the `_qdrant()` factory (`indexer.py:48`); the six config resolvers ⇄ six `.env.example` entries in sync; `docs/known-limitations.md` §7 reindex caveat; finite httpx timeout + slow-synthesis log signal; `error_category` + `filterexpression_fallback` >500-row warning surfaced to `logger.warning`; the file-back injection-amplifier note in README + query.py docstring + the `_maybe_file_back` control point; and the live-smoke + p95 release gates transcribed onto the CHANGELOG checklist.

Three load-bearing surfaces converged across members:

- **N1 relation-clobber integrity (CTO ↔ CSO ↔ QA).** The spec/test phases' central technical concern is genuinely honored, not renamed. CTO verified line-for-line that `query.py` never calls `_write_bidirectional_relations`; reciprocals use explicit read-merge-write off a FRESH write-time read (`_refetch_for_writeback`) with `prior ∪ [query_id]`; forward `wiki_drew_from` targets cached fetched object-ids, never LLM titles. QA confirmed the replacement N1 test (`test_query_fetch_paths.py:122`) returns a non-empty live prior `["e1","e2"]` distinct from the enumeration snapshot, so the guard is non-vacuous — a `_write_bidirectional_relations`-style overwrite would produce `[query_id]` only and fail. All three agreed the one residual is the LIVE relation-element wire shape (unverifiable in-sandbox), correctly bound as a release gate.

- **Reviewer diligence / skipped-test substitution (CTO ↔ QA).** Both independently confirmed the 5 skipped `test_query.py` tests are genuinely unsatisfiable under respx 0.23.1 (no-arg catch-all shadows the URL-specific route — first-match-and-break) and that the `test_query_fetch_paths.py` replacements are equivalent-or-stronger (single-dispatcher routing exercising the full call path). The in-phase MAJOR-1 finding (synth-error path leaking the sentinel into `answer`/`sources_consulted`, diverging from spec.md:240) was confirmed a genuine code-grounded catch and confirmed fixed at `query.py:614-616`. The review is trustworthy.

- **Security + operational degradation (CSO ↔ Infra ↔ Legal).** CSO confirmed SF8 scrubbing is now uniform across all egress strings, the SF1 clean-synthesis gate + min-sources(3)/min-words(100) is a sufficient structural bound on the amplifier loop, and the shared-core extraction introduces no new attack surface. Infra confirmed every failure mode degrades to a pinned non-hanging sentinel, the finite timeout is the true anti-hang backstop, and the 32GB envelope is protected (synthesis reuses the resident extraction model; input caps enforced). Legal confirmed zero new dependencies (`pyproject.toml`/`uv.lock` diff empty), no external transmission beyond the pre-existing localhost/opt-in-remote path, file-back writes only the user's own vault with explicit opt-in disclosure — the "not materially triggered" posture holds. CSO/Infra/Legal explicitly noted there is no daylight between their domains on the load-bearing controls.

**Net-new finding (CPO ↔ Client Advocate, cross-cut to QA).** Two members independently surfaced the same previously-unflagged issue: the README top-level framing is stale across v0.3.0→v0.4.0. The status banner (`README.md:5`), quick-start version banner (`README.md:78`), Roadmap (`README.md:426-437`), and the `docs/known-limitations.md:1` title still say "v0.2.0 (preview)… ingestion arrives in v0.3.0" and list `wiki.ingest`/`wiki.query` as "in design" — directly contradicting the in-body sections that fully document the shipped loop. The in-body `wiki_query` docs are excellent (CPO confirmed CPO-15 How-it-works depth and CPO-16 explicit `--file-back` demo both satisfied); only the surrounding front-door copy is stale. Both members framed this as a community-surface / brand issue affecting the secondary audience only (internal dogfood unaffected), docs-only with no code risk, and explicitly **non-gating** to their sign-off — a pre-community-tag checklist item.

## Findings

### BLOCKING
None. All eight members (chair + seven specialists) signed off with zero blocking findings.

### ADVISORY
1. **[CPO / Client — verified by Chair] (MEDIUM) Stale v0.2.0 front-door framing.** README status banner (`:5`), quick-start version banner (`:78`), Roadmap (`:426-437`, plus the `:414` provenance note "v0.2.0 ships as a git tag"), and `docs/known-limitations.md:1` title still describe a v0.2.0 search-only preview whose ingest/query are "in design", contradicting the shipped v0.4.0 loop and the CHANGELOG. Accumulated debt across three releases; #285 makes it acute because it completes the headline loop. Docs-only, no code risk. **Action: refresh banners + roadmap + known-limitations title to v0.4.0 before any community tag.** Pair with the existing release checklist.
2. **[CSO / CTO / QA / Infra / Client — unanimous] (HIGH-stakes, release gate) Live relation-shape pin + live-smoke + p95.** The N1 read-merge-write and the Decision-2 nested-`should`-in-`must` filter are proven only against mocks. The one wire contract with no in-sandbox verification is the live `get_object` relation-element shape: if it matches neither mocked form, the reciprocal merge reads an empty prior set and silently re-introduces the N1 clobber — **silent relation-data loss in the owner's own Anytype vault**. Correctly scoped on the CHANGELOG release checklist (`:63-72`): run the live smoke once against real Qdrant v1.17.0 + Aldeia's vault, and capture maintainer-measured p95 < 5s on Mac Mini M4, **internal-dogfood-first, before any tag**. Not a code defect; a release-execution gate the maintainer owns. Client Advocate's sharpening: because the dogfood tag itself exposes the owner's production vault to the file-back write path, the live smoke is a hard precondition for **even the internal tag**, not only the community tag.
3. **[CTO] (LOW) Spec-doc WikiLog pre-check contradiction remains live at HEAD.** `spec.md:234/362/387` say a schema/patch pre-check failure writes a WikiLog "if Anytype up"; the approved tests + code (`query.py:424-433`) write NO WikiLog on those paths. Code follows the authoritative tests (correct precedence — "fix the spec doc, no code change" is the right call), but the impl-worker flagged this and the doc-fix half was never executed. **Action: one-line spec edit; non-blocking, docs follow-up.**
4. **[Infra / Client / CSO] (LOW) O(N) `list_objects` enumeration scaling cliff not tracked.** Every `wiki_query` enumerates the whole wiki on both tiers; the file-back loop monotonically grows the wiki, trending toward the p95 ceiling over months of dogfooding. Correct at current scale. Prior councils asked to "log a v0.5.0 follow-up to cache the count"; no such ticket is filed and it is absent from `known-limitations.md`. **Action: file the v0.5.0 follow-up + add one known-limitations line.** Deferred-debt tracking, not a release blocker.
5. **[CSO] (LOW) `sources_consulted[].title` echoes the un-policed object name** (`query.py:602`) whereas the prompt path uses the `[REDACTED]`-policed name. Display surface only (cannot influence synthesis). Future defense-in-depth, no action this release.
6. **[Legal] (LOW) Consent-banner wording coverage.** `wiki_query` synthesis now shares the pre-existing opt-in remote-LLM transport (`WIKI_EXTRACT_ENDPOINT`); confirm the existing first-run consent banner wording covers "synthesis", not only "extraction". Docs-completeness nit, owner discretion. Also: at community release, keep announcement messaging within the MIT "AS IS / verify before relying" posture (don't market answers as "authoritative").
7. **[Client] (LOW) Incomplete client context.** `engagement.md` + `market.md` absent from `.aldeia/context/`; did not impair this review (self-owned project, unambiguous owner). Noted for completeness.

## Resolutions

- The N1 relation-clobber risk (the spec council's central concern) was independently re-confirmed genuinely pinned by CTO, CSO, and QA against the real assertions and real source — not renamed. No member sought to re-open it; all agreed the residual live-shape pin is correctly a release gate.
- The in-phase MAJOR-1 + MINOR-1..5 conditions were confirmed resolved in `9b30aa6` by CTO, QA, and Client via independent reads. The 4 deferred MINOR items were confirmed sound (notably declining to seed the per-run cache from enumeration summaries — a correctness risk, not an optimization).
- Legal's seating resolved the open question of whether the file-back vault-write or the shared synthesis transport materially changed the compliance posture: it does not. CSO and Legal confirmed their domains are mutually consistent; no separate legal escalation.
- The only net-new finding (stale v0.2.0 front-door framing) was raised independently by CPO and Client, verified by the chair, and agreed by both raisers to be non-gating docs-hygiene for the pre-community-tag checklist — not a code re-spin.
- No contradictions required resolution; the security, engineering, quality, product, operational, legal, and client assessments were mutually consistent. No member cast a veto.

## Recommendation

**Recommended target:** `done` (final delivery gate — create PR; Jan reviews + merges)
**Confidence:** high
**Rationale:** The implementation is review-clean (in-phase APPROVED WITH CONDITIONS → fix round resolved the MAJOR + 5 MINOR), regression-free (514 passed / 0 failed), and faithfully honors the spec plus both binding addenda — including every item of Jan's directed `spec-addendum-post-test-r1.md` (C1 `embed_query` import, A1 `_qdrant()` factory, six resolvers, docs, finite-timeout + slow-synth signal, operator-log surfacing, amplifier note, release gates). All 20 ACs are verified satisfied by code (not only by tests), and the two highest-risk surfaces (N1 read-merge-write, Decision-2 multi-type filter) are provably non-vacuous in CI. Eight members signed off with zero BLOCKING findings.

**Pre-tag obligations the maintainer owns at the `done`/release step (none gate PR creation, all must precede the v0.4.0 tag):**
1. Run the live smoke against real Qdrant v1.17.0 + Aldeia's own vault to pin the live relation-element shape (ADVISORY-2) — hard precondition for even the internal dogfood tag, since that tag exposes the owner's production vault to the file-back write path.
2. Capture maintainer-measured p95 < 5s on Mac Mini M4 (ADVISORY-2).
3. Refresh the stale v0.2.0 README banners + Roadmap + known-limitations title to v0.4.0 (ADVISORY-1).
4. One-line spec-doc fix for the WikiLog pre-check contradiction (ADVISORY-3) and file the v0.5.0 enumeration-count-cache follow-up (ADVISORY-4) — housekeeping, may trail the tag.

**Dissent:** None.
