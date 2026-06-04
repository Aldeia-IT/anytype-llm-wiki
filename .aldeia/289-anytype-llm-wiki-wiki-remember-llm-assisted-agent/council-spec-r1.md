# Council Meeting — Post-spec (Round 1)

**Date:** 2026-06-04
**Ticket:** #289 — `wiki_remember`: LLM-assisted agent memory-write MCP tool (anytype-llm-wiki v0.3.1)
**Phase reviewed:** spec
**Client:** anytype-llm-wiki (Aldeia-IT) — open-source MIT, local-first MCP server

## Attendance

| Role | Present | Reason |
|------|---------|--------|
| Council Chair | Yes | moderator |
| Chief Security Officer | Yes | minimum; LLM-write + prompt-injection surface |
| Chief Technology Officer | Yes | minimum; ~80% reuse claim + two cross-cutting code changes |
| Chief Product Officer | Yes | minimum; product value + scope discipline |
| QA Director | Yes | post-spec gate into the test phase; AC↔test-plan adequacy is load-bearing |
| Infrastructure Lead | Yes | domains are infrastructure/agent-operations; local-LLM resource impact + shared per-space lock |
| Client Advocate | Yes | non-aldeia-box repo; open-source community + Aldeia operators are the client |
| Legal Counsel | No | MIT, local-first, no new PII / data store / external-transmit surface (only pre-existing consent-gated endpoint). Not needed; documented. |

## Context Presented

The spec phase produced an APPROVED technical spec (~1640 lines) for `wiki_remember`, an LLM-assisted agent memory-write MCP tool. Pipeline: natural-language `knowledge` → extract → resolve against existing Anytype objects → **LLM consolidate** (merge reworded facts, supersede changed ones, dedupe, flag intra-entity conflicts) → bidirectional relations → audit WikiLog → reindex. v0.3.1; depends on shipped #284 (v0.3.0 ingest pipeline); precedes #285 (wiki_query). The value proposition over a dumb CRUD append (which already exists via the generic `anytype` MCP) is the LLM consolidation that keeps the knowledge base precise and deduplicated.

The spec went through two review rounds within the phase: R1 raised 9 BLOCKING + 16 SHOULD-FIX + 7 SUGGESTION (including two **code-grounded** blockers a document-only review would miss — `_write_wikilog` hardcoded name, and bootstrap tag-seeding that would silently zero-seed on a fresh space). R2 returned APPROVED after two re-reviewers verified every R1 resolution against live source. The CSO R2 sign-off was "APPROVED WITH CONDITIONS" where the conditions are impl-time test checks, not spec changes.

## Discussion

All six specialists independently verified load-bearing claims against the live codebase rather than the spec's self-description — CTO confirmed eight technical claims at file:line (reuse seams, the two cross-cutting changes' backward-compatibility, the missing `client.get_object` that justifies the §13.2 deferral); CSO verified the security primitives (`sanitize_property_value`, `scrub_credentials`, `space_ingest_lock`, `check_remote_endpoint_consent`); QA verified the two #284 regression seams; Infra confirmed the decisive operational fact that the shared lock is **fail-fast, not blocking**.

The most significant cross-functional convergence: **CPO and Client Advocate independently identified the same gap** — the non-conflict `supersede` path (D2) legitimately removes a prior fact from `wiki_facts`/`wiki_definition`, but the only durable record is the WikiLog `notes`, whose documented format (§11.4) records *conflicts* but not *supersessions*; `fact_actions[].supersedes` (which carries the removed old text) is explicitly NOT written to Anytype. Combined with the accepted residual that the LLM may wrongly supersede a correct fact (Open Question #1), this is the one destructive operation that is both silent and the least guarded — directly in tension with the spec's strong never-silently-overwrite posture for conflicts and never-guess posture for ambiguity. Both members judged it advisory (not blocking) but recommended it become a next-phase acceptance criterion.

Secondary cross-cutting threads: CSO and QA both independently insisted the two HARD GATES (consent-on-live-path, lock-on-entry-path) and the sanitize-on-write assertion (AC-R27) must drive the **real** `wiki_remember` entry point with spies at the entry boundary — an isolated-helper test must fail review. Infra and Client Advocate both flagged the operator-doc burden (per-space re-bootstrap, reindex cost, WikiLog growth, fail-fast back-pressure semantics) as needing to reach user-facing docs, not just the spec.

No contradictions between members. No member downgraded another's severity.

## Findings

### BLOCKING
None.

### ADVISORY
1. **[CPO + Client Advocate]** Non-conflict `supersede` silently deletes a prior fact with no durable audit record. WikiLog notes format (§11.4) records conflicts but not supersessions; `fact_actions[].supersedes` is not persisted. Highest-trust-cost operation for a memory product; least guarded. → next-phase AC (see addendum item 1).
2. **[Client Advocate / SF14]** `wiki_sources` overwrite-on-update replaces the provenance chain precisely on conflicted objects a reviewer will inspect. Conflict content preserved; source-link history lost. Cheap mitigation (record pre-overwrite source ids in WikiLog note OR emit a runtime warning) available without the deferred `get_object`. → next-phase AC (addendum item 2).
3. **[CSO]** The three security-critical exit checks must be promoted from soft impl-review notes to mandatory, named test-phase exit criteria: (a) hard-gate tests drive the real entry point; (b) exact `sanitize_property_value(consolidated_text)` byte-equals the `update_object` payload; (c) input gate proven to precede lock + LLM. → addendum items 3–5 (overlaps QA).
4. **[QA Director]** Eight test-phase fidelity guardrails (twice-driven AC-R6 convergence with stateful mock + zero `update_object` on call 2; conflict-flag independent of PATCH-skip gate; ambiguous-subject asserts NO write; bootstrap seeding asserts non-empty via prop_map key-fallback on a fresh space; tests must FAIL before impl; live tests marked `@pytest.mark.live`). → addendum items 3–7.
5. **[CTO]** Add an explicit regression assertion that `extract()` behavior is unchanged after the `_call_ollama_prompt` DRY refactor (it touches the shipped ingest path). Minor citation drift on the consent function line ranges (§8.2 vs G2) — fix opportunistically. → addendum item 8.
6. **[Infrastructure Lead]** Operator-doc requirements: per-space upgrade runbook; auto-reindex cost model + `WIKI_AUTO_REINDEX=false` mitigation; monotonic WikiLog growth + pruning; `ingest_in_progress` as expected fail-fast back-pressure; confirm existing Anytype backup is type-agnostic; document worst-case lock-hold (≤ 8 × `WIKI_EXTRACT_TIMEOUT`). → addendum item 9 (impl/docs phase).
7. **[CSO + Client Advocate]** `scrub_credentials` is a URL scrubber, not a general secret-pattern scrubber; the consent gate is notify-once non-interactive self-ack. Both accepted under the single-operator threat model; recommend one operator-facing doc sentence each. → addendum item 9.

## Resolutions

No findings were withdrawn during discussion — all advisories stand as recorded. The council unanimously agreed that none of the advisories rise to blocking the spec's advancement; all are appropriately resolved in the test/impl phases and are carried forward as acceptance criteria via the spec addendum (`spec-addendum-post-spec-r1.md`).

The legal-counsel non-attendance was unchallenged: the feature introduces no new data store, no new PII handling, and no new off-machine transmit beyond the pre-existing consent-gated `WIKI_EXTRACT_ENDPOINT` under an MIT license.

## Recommendation

**Recommended target:** test
**Confidence:** high
**Rationale:** The spec is APPROVED with zero BLOCKING/SHOULD-FIX findings after two code-grounded review rounds, and all six council lenses signed off. The architecture is sound, the ~80% reuse claim is verified accurate, scope is disciplined with every deferral justified, and the product-critical guardrails (never-silently-overwrite-conflicts, never-guess-on-ambiguity, convergent idempotency, audit trail) are present. The test phase should focus on: the cross-cutting supersede-audit and conflict-provenance criteria (addendum items 1–2), and the security/QA test-fidelity criteria that ensure the hard gates and sanitization are proven against the real entry point (addendum items 3–8). Operator-doc items (item 9) carry into the impl/docs phase.
**Dissent:** None.
