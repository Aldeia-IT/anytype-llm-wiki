# Council Meeting — Post-spec (Round 1)

**Date:** 2026-06-05
**Ticket:** #286 — anytype-llm-wiki v0.5.0 `wiki_lint` (structural health check)
**Phase reviewed:** spec
**Client:** anytype-llm-wiki (open-source MCP server, MIT, Aldeia-IT)

## Attendance

| Role | Present | Reason |
|------|---------|--------|
| Council Chair | Yes | moderator |
| Chief Security Officer | Yes | minimum |
| Chief Product Officer | Yes | minimum |
| Chief Technology Officer | Yes | minimum |
| Infrastructure Lead | Yes | chair decision — infra/agent-ops domains; both R1 BLOCKINGs were perf/infra (Qdrant sweep, O(N) enumeration, ≤60s budget) |
| QA Director | Yes | chair decision — 15 ACs / 32 tests; R1 BLOCKINGs were test-satisfiability defects |
| Client Advocate | Yes | chair decision — client project with full context files; represents Jan's OSS / local-first goals |
| Legal Counsel | No | MIT-licensed, read-mostly tool, no new data/PII/credential surface or regulatory delta in this increment — no legal question to adjudicate |

## Context Presented

`wiki_lint(space_id, severity_threshold="all") -> LintReport` is the v0.5.0 increment that closes the Karpathy "maintain" loop (after ingest #284 / remember #289 / query #285). It enumerates all wiki objects (O(N)), runs a 10-check structural battery (asymmetric relations, orphans, pipeline-orphans, staleness, unreviewed/needs-review, oversized, empty-type, potential-duplicates, passive contradiction), and writes ONLY its own WikiLog receipt — it mutates no wiki objects.

It is an INCREMENT spec on master spec #140, locking five deltas (D1–D5) discovered/shipped since the master was written, each verified against the post-#303 codebase:
- **D1** — native `backlinks` is the PRIMARY O(1) inbound-relation source (reverses master OQ#7); O(N) reciprocal traversal is explicit fallback.
- **D2** — master's `stale_stub` check can never fire (no `stub` tag seeded); re-targeted to `stale_needs_review` (Medium, no schema bump).
- **D3** — new live HIGH `unreviewed_needs_review` check off the `needs-review` status `wiki_remember` already sets (the live, populated finding).
- **D4** — reuse of v0.4.0 infra (`_fetch_cached`, `_qdrant()`, `semantic_search_core`) verbatim.
- **D5** — schema v0.4.1 read-by-key; every wire contract pinned (verb + path + test mock).

The spec entered the council APPROVED at R2 (R1 was NEEDS REVISION with 2 BLOCKING, both perf/duplicate-sweep defects; the fix cycle resolved them and R2 verified against source). Jan's five pre-queue deltas map 1:1 to D1–D5.

## Discussion

The council converged on a single material issue from two independent directions.

- **CSO** verified the load-bearing security claims against source rather than prose: `semantic_search_core` → `embed_query` is an Ollama embedding call (text→vector, no generative prompt), so the duplicate sweep introduces **no prompt-injection vector**; `scrub_credentials` (util.py:98-141) strips URL userinfo + query/fragment only and does NOT redact bearer tokens, exactly as SF11's corrected wording states; `strip_control_chars` makes the SF12 truncation discipline sound. Read-mostly attack surface, no new credential/network/SSRF surface. Signed off.

- **CTO** spot-checked ~14 reused helpers at their exact cited line numbers (all present, compatible signatures, no invented helpers), confirmed the D2 `no-stub-tag` claim (bootstrap.py:57), the D5 wire contracts (search is POST; property-scoped two-step tag resolution; get_object GET `?format=md`), the SF5 age-derivation catch (`wiki_ingested_at` on `wiki_source` only), and the B1 fix correctness (the original defect — object-count `index_threshold()`=200 used as a 0–1 similarity bound — was a real value-semantics defect; the `[0.70, 0.85)` literal-band fix via new `_bounded_float` guard is correct and necessary). Reviewer diligence was source-grounded across R1/R2. Signed off. **One ADVISORY:** D1's `backlinks` field is the single load-bearing claim not verifiable from source (rests on a live-API session finding; only repo hit is a comment) — defensively designed with an explicit malformed-fallback, but the impl must confirm the real shape early and the live smoke must assert it.

- **Infrastructure Lead** confirmed both R1 BLOCKING fixes hold at the spec level and the deployment surface is clean (no schema bump, no migration, no new service/credential, doctor stays green). **But flagged (ADVISORY A1)** that R2 validated the ~51s non-sweep battery as honest and then treated the sweep as "gated, therefore handled" — missing that gating to `"all"` does not bound cost when **`all` is the default argument**. At N=500: 500 × 0.22s embeds ≈ 110s + 51s battery ≈ **~160s, ~3× the 60s budget**; budget is already blown at ~150–200 objects (the spec's own dogfooding scale). `WIKI_LINT_MAX_OBJECTS=2000` is 4–10× too high to protect the default path's wall-clock. Real impacts: MCP caller timeout on a 160s "hang," and ~110s of continuous bge-m3 inference saturating the shared Ollama that ingest/query/IronClaw depend on.

- **Client Advocate** independently reached the same issue from the client's seat and rated it **BLOCKING (CA-B1):** the most-typed call — bare `wiki_lint(space)` and any scheduled run — is the slowest, box-saturating path, advertising ≤60s in the README while running ~160s. On Jan's single constrained box this is a self-inflicted DoS against the shared local Ollama and a false perf claim under the Aldeia-IT OSS name. R1/R2 marked it "resolved" from a correctness lens (sweep bounded to one threshold value) and structurally could not catch that it's bound to the *default* value.

- **CPO** signed off on the product story (D3 live-finding design is the correct day-one value decision; passive contradiction check is right to ship now for cheap forward-compat as long as its passivity reaches the docs; double-count is a feature not confusion; report-only is correct; anti-bloat held at 458 lines / 15 ACs). The CPO advisories about documenting passive/heuristic behavior are consistent with the CA's reputation concern.

- **QA Director** built the AC↔test map independently: all 15 ACs map to ≥1 of the 33 named tests, all tests map to an AC, no orphans. Confirmed the R1 satisfiability defect is truly gone (the `[0.70, 0.85)` band makes the three duplicate tests satisfiable; scanned the other 30 for the same defect class — none). Signed off, carrying two test-authoring constraints into the test phase (below).

The chair notes the BLOCKING is reinforced by a **spec-internal contradiction**: the Performance Budget section states the non-sweep battery "is the part that must fit ≤60s" (implicitly conceding the sweep does not fit), while the tool signature makes the sweep default-on. The ≤60s/≤500 budget claim and the default-on sweep cannot both be true at N=500.

## Findings

### BLOCKING

1. **[Client Advocate, corroborated by Infrastructure Lead] CA-B1 — The default invocation is the slow, box-saturating path; it violates the spec's own ≤60s/≤500 budget.** The signature defaults `severity_threshold="all"`, and the Informational duplicate sweep is gated to `"all"` — so the default `wiki_lint(space)` call runs N sequential bge-m3 embeddings + N Qdrant queries on top of the ~51s get_object battery (~160s @ 500 objects, ~3× budget; blown at ~150–200 objects). This both (a) makes the advertised ≤60s/≤500 perf claim false on the default path, and (b) saturates the shared local Ollama on Jan's single box, contending with ingest/query/IronClaw. **Recommended resolution (council consensus direction):** make the Informational duplicate sweep **opt-in** rather than default-on, so the default run stays within the advertised budget and safe on the box (the sweep remains available via an explicit flag / a non-default threshold or a dedicated `WIKI_LINT_DUPLICATES=1`). Acceptable alternatives if the sweep stays default-on: ship the deferred sample cap (`WIKI_LINT_DUPLICATE_SAMPLE`) **now** AND correct the README/spec perf claim to state ≤60s holds for the non-sweep path only. The spec must also resolve the internal contradiction between the ≤60s budget statement and the default-on sweep.

### ADVISORY

1. **[CTO] backlinks field shape unverifiable from source** — D1's `obj["backlinks"]` rests on one live-API session finding (only repo hit is a comment in test_ingest.py). Defensively fenced by the malformed-fallback test, but the impl must confirm the real shape against a live `get_object` as task one, and the `@pytest.mark.live` smoke must assert it. (QA ADV-3 concurs — keep the live smoke alive.)
2. **[QA] AC13 tag-resolution two-step needs an explicit negative assertion** — add a test asserting NO call to space-level `/v1/spaces/{id}/tags`, so the exact #285/#289 wire defect cannot slip past a no-arg catch-all mock.
3. **[QA] Age-check fixtures must seed `wiki_ingested_at` on a linked `wiki_source`, not on the object** — per SF5 the property lives only on `wiki_source` (reached via `wiki_sources`). The `orphan` and `stale_needs_review` test fixtures as currently worded risk false-green against an impl that silently never fires the age gate. (`test_stale_check_fires` is already correct.)
4. **[CSO] Single shared sanitize+truncate helper for object text** — SF12's `strip_control_chars(...)[:N]` discipline only protects if every site routing object text into `detail`/`wiki_subject`/`wiki_notes` uses it; recommend the impl-phase security review gate on one shared helper.
5. **[CSO] Confirm tokens never interpolated into output strings** — "tokens never enter output" is a code invariant, not enforced by `scrub_credentials`; confirm error messages embedding a request URL are scrubbed and no header value is interpolated into returned/persisted strings.
6. **[CPO] Passive contradiction check must reach the README/docstring** — a green lint result reading as a guarantee is an operator-over-trust risk while the contradiction check is passive until #287; document the passivity, don't leave it spec-only.
7. **[CPO] Double-count detail legibility** — the two needs-review findings (High + Medium) on one object should make the shared-object relationship legible in their `detail` fields so the `summary` counts don't read as double-counting confusion.
8. **[CPO / CA] Keep `WIKI_LINT_DUPLICATE_SAMPLE` on the roadmap** — above the object cap the largest wikis get zero duplicate detection (acceptable now — only the Informational sweep is skipped, never High/Critical).
9. **[CA] Document the six knobs compactly with a "you don't need to set any of these" note** (brand voice: developer-facing, concise); **don't oversell `pipeline_orphan`** in docs — it is an honest ±300s heuristic with false negatives by design.
10. **[CTO] Cosmetic:** `indexer` is at package-root `indexer.py` (imported `from .. import indexer`), not `wiki/indexer.py`; cited line numbers are correct.

## Resolutions

- The duplicate-band correctness defect (R1 B1) and the uncapped-sweep concern (R1 B2) are genuinely resolved at the spec level — CTO, QA, and Infra each re-verified against source. The residual issue (CA-B1) is narrower and distinct: not whether the sweep is bounded, but that its bound is the *default* value, so the default path is the heavy one.
- No member's sign-off was withdrawn during discussion. The single BLOCKING is held per consolidation rules (a member's BLOCKING is never downgraded); Infra's matching ADVISORY is recorded as corroboration, not a dilution.
- Security, product, technical-accuracy, codebase-alignment, and test-traceability dimensions are all clean — the rework is tightly scoped to CA-B1 plus carrying the advisories forward.

## Recommendation

**Recommended target:** `spec`
**Confidence:** high
**Rationale:** One BLOCKING finding (CA-B1) requires a spec edit before the spec is a safe contract for the test/impl phases. The fix is small and the council has a clear consensus direction: make the Informational duplicate sweep opt-in so the default `wiki_lint(space)` call honors the advertised ≤60s/≤500 budget and does not saturate the shared local Ollama; failing that, ship the sample cap now and correct the perf claim. The spec must also remove the internal contradiction between the ≤60s budget statement and the default-on sweep. The spec-fixer should additionally fold ADVISORY-1 through ADVISORY-3 (backlinks live-confirm + live smoke assertion; AC13 negative assertion; age-check fixtures seed the source) as they tighten the test contract at near-zero cost; the remaining advisories are impl/test/docs guidance to carry forward. Everything else in the spec is council-approved and should not be reopened — resolve by tightening, not re-deriving.
**Dissent:** None. The five technical sign-offs and the Client Advocate's conditional approval are consistent: every member agrees the default path must honor the advertised budget; they differ only on whether that gap is a blocker (CA: yes; Infra: advisory). The chair holds it BLOCKING — a public tool advertising a perf budget its default invocation triples, on a single shared box, is a ship-stopper for an OSS reputation artifact.
