# Council Meeting — Post-spec (Round 1)

**Date:** 2026-06-04
**Ticket:** #285 — anytype-llm-wiki v0.4.0 — wiki_query (tiered retrieval: index-navigation + vector-augmented)
**Phase reviewed:** spec
**Client:** anytype-llm-wiki (open-source MIT; dual-purpose: internal Aldeia knowledge search + public community tool)

## Attendance

| Role | Present | Reason |
|------|---------|--------|
| Council Chair | Yes | moderator / verdict synthesis |
| Chief Security Officer | Yes | minimum roster; injection + relation-write data-integrity surface |
| Chief Product Officer | Yes | minimum roster; increment value + scope discipline |
| Chief Technology Officer | Yes | minimum roster; verify locked technical decisions vs real source |
| Infrastructure Lead | Yes | repo domains = infrastructure + agent-operations; shared-tool blast radius, Mac Mini M4 resource budget |
| QA Director | Yes | test-plan-heavy spec (20 ACs → CI tests); next phase is test/impl |
| Client Advocate | Yes | non-aldeia-box repo; dual audience (internal + open-source community) |
| Legal Counsel | No | not materially triggered — MIT, local-first by default, no PII beyond user-authored notes, no new data store or external-transmission surface |

## Context Presented

v0.4.0 `wiki_query` is the increment that "closes the loop": it answers natural-language questions
over the wiki with cited sources via tiered retrieval (Tier 1 index-navigation below
`WIKI_INDEX_THRESHOLD`=200, Tier 2 vector-augmented at/above), 1-hop cached neighborhood traversal,
local Ollama synthesis, and optional file-back (writing the synthesis as a new `wiki_query` object
that becomes a future retrieval source — the compounding mechanism). It completes the 15-minute
community quick-start (bootstrap → ingest → query). Hard dependency on #284 (merged).

The spec (751 lines, 20 ACs, Status SPEC) went through 2 in-phase review rounds. R1 produced 11
BLOCKING (B1–B11) plus 11 SF items; R2 (APPROVED WITH CONDITIONS) caught one NEW BLOCKING (N1 — a
false code-grounding claim about `_write_bidirectional_relations` that would have clobbered
persisted relation arrays during file-back) and one SHOULD-FIX (N2 — AC#19/#20 unmapped to tests).
Both R2 conditions were resolved and lead-verified before this council convened.

## Discussion

The council's cross-functional focus converged on three load-bearing risk areas, each independently
confirmed resolved:

- **Relation-write data integrity (CSO ↔ CTO ↔ Infra ↔ QA).** The R2 N1 clobber bug was the meeting's
  central technical concern. CTO verified against real source (`ingest.py:316,321,292`) that
  `_write_bidirectional_relations` seeds from an empty in-run `linked` dict and `_patch_relation`
  full-overwrites — confirming the original R1 "appends to persisted state" claim was genuinely
  false. All four members agreed the spec's resolution (explicit read-merge-write at File-Back Gate
  step 4: `get_object` → SF5 dual-shape parse → `prior ∪ [query_id]` → `update_object`) closes the
  data-loss risk, with AC#16 and `test_reciprocal_relation_read_merge_write` pinning it. CTO raised
  the residual that the read-merge-write is non-atomic (lost-update window under concurrent
  reindex); Infra agreed it is acceptable on a single-operator box (degrades to `status: partial`).

- **Prompt-injection surface (CSO ↔ QA).** CSO confirmed the spec correctly identifies object
  *content* (not just names) as the real injection vector and fences all `WIKI_TEXT_PROPERTY_KEYS`
  content + names under a "DATA not INSTRUCTIONS" preamble, with relation targets sourced from
  cached fetched IDs (never LLM titles). CSO noted fence-based defense is probabilistic and the
  file-back loop is an amplifier (a poisoned synthesis filed back becomes a future source), bounded
  structurally by the SF1 clean-synthesis gate + min-sources/min-words. QA agreed the injection
  test should exercise a realistic multi-vector payload, not only the literal "ignore previous
  instructions" string. Both framed this as an impl/test-phase hardening item, not a blocker, given
  the local-first single-operator trust model.

- **Community-facing completeness (CPO ↔ Client Advocate).** Both flagged that the compounding loop
  — the headline value prop — only surfaces a filed answer after the *next* `reindex_anytype`, a UX
  gotcha that could read as "broken" to a first-time community user. Client Advocate additionally
  caught a spec internal inconsistency: Files Changed says "three new vars" while Configuration adds
  six (`WIKI_SYNTH_MAX_*` omitted from the summary). Neither is a design defect; both are
  documentation/consistency items for impl.

Infra and QA independently confirmed the operational and quality envelopes: synthesis reuses the
already-resident extraction model (no second model loaded into the 32GB), input is capped
(8192 tokens / 24 objects), every failure mode degrades cleanly without hanging or exhausting the
box, all 20 ACs map to CI-runnable (non-live) tests, the shared `semantic_search` tool has an
explicit backward-compat regression test, and the live smoke test is correctly additive.

## Findings

### BLOCKING
None. All six members signed off with zero blocking findings. The two prior-round conditions
(N1 BLOCKING, N2 SHOULD-FIX) are both resolved and code-verified in the current spec.

### ADVISORY
1. **[CSO]** Fence-based injection defense is probabilistic; the file-back loop amplifies a
   successful bypass (poisoned synthesis → future retrieval source). Bounded by SF1 + min-source/word
   gates. Track; strengthen the injection test with a realistic multi-vector payload.
2. **[CSO]** File-back amplifier is mitigated but not named in the spec's threat model — add one
   sentence to Security Considerations.
3. **[CSO]** Per-object head-only truncation is a budget control, not a security control — implementers
   should not treat it as injection defense-in-depth. (No action.)
4. **[CSO]** Qdrant stores derived synthesis content unencrypted at rest — consistent with the
   documented local-only acceptance; re-evaluate only if Qdrant is ever exposed beyond localhost.
5. **[CTO]** `embed_query` provenance imprecision: spec says "moved from server.py" but it lives in
   `embedder.py:22` (already imported by indexer.py). Treat as imported, no move needed. Cosmetic.
6. **[CTO/QA/Client]** 1-hop relation read-back element shape is the one unverified wire contract
   (no existing read-side code). Dual-shape parser + live smoke test mitigate. Pin the real shape via
   a live `get_object` before finalizing merge logic; add the real shape to the mocked fixture.
7. **[CTO]** Read-merge-write reciprocal write is non-atomic (lost-update window under concurrent
   reindex). Acceptable on a single-operator box; document the last-writer-wins nature.
8. **[Infra]** 600s synthesis timeout (inherited from `WIKI_EXTRACT_TIMEOUT`) is too long for an
   interactive tool. Consider a separate `WIKI_SYNTH_TIMEOUT` (~120s) or document the ceiling + add a
   slow-synthesis log signal. Bounded against true hang by `httpx` connect/read timeouts.
9. **[Infra]** Always-on O(N) `list_objects` enumeration on every query (both tiers) is acceptable on
   the M4 today but is a scaling cliff as the file-back loop grows the wiki. Surface the
   `filterexpression_fallback` >500 warning to operator logs; log a follow-up to cache the count.
10. **[Infra]** Shared `semantic_search` tool filter change has adequate CI regression tests but no
    live canary. Run the live smoke test once against real Qdrant v1.17.0 before release to confirm
    the nested-`should`-in-`must` construction on that version.
11. **[Infra]** Confirm `error_category` (config_error/api_error) returns are visible in operator
    logs, not only in per-query `QueryResult`.
12. **[QA]** Tier-2 candidate-fetch failure path (a Tier-2 candidate's `get_object` failing, distinct
    from a neighbor failing) has no named test. Add/extend coverage or document a shared code path.
13. **[QA]** Parametrize the Qdrant-down test at the exact threshold boundary (count=199 and =200) so
    the `count >= threshold` comparator is pinned on the failure path too.
14. **[QA]** `test_mocked_query_completes_under_5s` is a coarse no-pathology gate, not the production
    p95 SLO. Capture the maintainer-measured p95 < 5s on M4 as an explicit release-checklist item.
15. **[CPO/Client]** No AC covers documentation. The README quick-start + "How it works" and
    `docs/known-limitations.md` (named in scope, absent from Files Changed) are the highest-visibility
    community surface. Add a documentation acceptance criterion covering tiered retrieval, the
    compounding loop, and the reindex-then-retrievable latency caveat.
16. **[CPO]** File-back default (≥3 sources AND ≥100 words) is correct for steady-state but skews
    conservative on a fresh quick-start wiki — the compounding "aha" may not fire during onboarding.
    Have the README quick-start demonstrate `file_back=True` explicitly.
17. **[CPO]** Tier threshold default (200) is a reasonable engineering default but is asserted, not
    product-justified. A one-line README rationale would help community operators tune it.
18. **[Client]** Spec internal inconsistency: Files Changed (spec.md:656-657) says "three new vars"
    but Configuration (spec.md:503-512) adds six (`WIKI_SYNTH_MAX_*` resolvers omitted from the
    summary). Reconcile so `.env.example` and `config.py` ship in sync.
19. **[Client]** Internal-dogfood-first: run the live smoke test against Aldeia's own vault during
    Implement and pin the confirmed relation shape before any community release tag.

## Resolutions

- The single prior-round BLOCKING (N1 relation clobber) was confirmed genuinely resolved by all
  technically-relevant members (CSO, CTO, Infra, QA) against real source — not merely renamed. No
  member sought to re-open it.
- No member raised a new blocking concern. No contradictions between members required resolution;
  the security, engineering, operational, and quality assessments were mutually consistent (the
  file-back loop is simultaneously the product's value prop (CPO/Client), an injection amplifier to
  bound (CSO), and a wiki-growth/enumeration-scaling driver to watch (Infra) — all three framings
  agree it ships now with the noted watch-items).

## Recommendation

**Recommended target:** `test` (next phase in SDLC order after spec)
**Confidence:** high
**Rationale:** The spec is internally coherent, code-grounded (every load-bearing technical claim
independently verified against real source by the CTO), and review-clean (both R2 conditions
resolved and lead-verified). All 20 ACs map to CI-runnable tests; the #284 live-only-gate
anti-pattern was explicitly avoided. The test phase should fold in the actionable test-design
advisories (Tier-2 candidate-fetch path, threshold-boundary parametrization on the Qdrant-down path,
realistic injection payload, live relation-shape pin) captured in the spec addendum. The impl phase
should fold in the config-var reconciliation, documentation AC, and `WIKI_SYNTH_TIMEOUT`
consideration. The watcher enforces autonomy policy on the recommended target.
**Dissent:** None.
