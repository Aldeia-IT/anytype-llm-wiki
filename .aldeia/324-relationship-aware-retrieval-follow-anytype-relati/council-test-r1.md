# Council Meeting — Post-Test (Round 1)

**Date:** 2026-06-12
**Ticket:** #324 — Relationship-Aware Retrieval (follow Anytype relations)
**Phase reviewed:** test
**Client:** anytype-llm-wiki
**Branch tip:** 1aac7d7 (test phase: R1 NEEDS CHANGES + R2 APPROVED)

## Attendance

| Role | Present | Reason |
|------|---------|--------|
| Council Chair | Yes | moderator / verdict synthesis |
| QA Director | Yes | post-test minimum; AC coverage, test adequacy, regression risk |
| Chief Technology Officer | Yes | test-engineering quality + reviewer-diligence audit (root cause of prior short-circuit: aldeia-box#333) |
| Chief Security Officer | Yes | security-relevant test bindings (SF1 file-back bound, SF-B citation redaction, fan-out cap) |
| Legal Counsel | No | local single-tenant tool; no PII / third-party / regulatory surface in a test-suite delta |
| Chief Product Officer | No | no product/scope decision pending at the test gate; OQ1 (`wiki_subjects` retention) already resolved by Jan and ratified at post-spec council |
| Infrastructure Lead | No | no deployment/service-config change; fan-out latency bound already covered by spec Resource Impact + SG-6 (CTO routed ADVISORY-1 to infra-lead as an impl-phase follow-up) |
| Client Advocate | No | internal product feature; no external-audience artifact |

## Context Presented

The test phase produced a complete failing-test suite for the #324 delta (D1–D6),
covering all 12 acceptance criteria (AC1–AC12). Final suite state: **11 failed /
64 passed / 6 skipped** — 11 RED-NOW tests fail on missing D1–D6 behaviour, 5–6
GREEN-NOW forward-regression guards, 59 pre-existing tests still green.

The internal review cycle ran R1 (NEEDS CHANGES — one real BLOCKING: 6 Tier-2 stub
tests failed for the *wrong* reason via an early-exit "fails-forever" trap, plus 2
SHOULD-FIX soft assertions) → fixer commit `f725c7c` → R2 (APPROVED, full AC
traceability). This post-test council is the governance gate on that output, with
an explicit mandate (given aldeia-box#333) to audit whether the internal review was
genuinely diligent rather than a rubber-stamp.

## Discussion

All three officers ran the suite independently and verified against real worktree
source rather than trusting the review docs.

**Reviewer-diligence audit (CTO, lead charge).** The CTO reproduced the R1 BLOCKING
against the original test-writer commit `d4d746d`: all 6 named tests used
`list_resp = {"data": [_schema_obj()]}` where `_schema_obj().type.key == "collection"`,
which `_WIKI_TYPE_KEYS` filters out → `count = 0 < threshold` → Tier-1 → empty
`candidate_entries` → `_NO_SOURCES_ANSWER` early exit, so `stub_search` never fired.
A genuine fails-forever trap. R2's fix (seed `list_resp` with `wiki_entity` stubs so
Tier-2 is actually entered) is real: every one of the 6 now fails at a true #324
assertion *after* Tier-2 entry, and the `"No sources found…"` sentinel appears in
**zero** failure messages. **R1 was a genuine catch, not theater.** QA independently
reproduced the same conclusion.

**Test-to-source fidelity (CTO).** Four load-bearing claims spot-checked against the
real worktree all held: `_neighbor_ids_of` still returns a flat `list[str]` (query.py:679-687);
`_RELATION_KEYS` still lacks `wiki_sources` (query.py:53); the single-dispatcher respx
helpers (`_obj_id_from_request`, `_is_list_request`) exist as the spec describes; and
`query_max_neighbors()` is absent from config.py (AC10 fails with the intended
`ImportError`). The AC2 traversal target `wiki_sources` is a real schema property
(types_schema.py:93/109/124), not invented.

**Security-invariant bindings (CSO).** The three load-bearing security invariants are
each pinned by binding, non-tautological tests. AC7 (file-back seed-only, SF1 bound)
is a GREEN-NOW guard that genuinely fires file-back (anti-tautology assertion
`result.get("filed_back")` plus non-empty `wiki_drew_from`) and would FAIL on the
exact named SF-I regression (an impl that passes the combined `sources_consulted`
into `_maybe_file_back` would route neighbours into `wiki_drew_from`). AC11 (citation
redaction) is RED-NOW and correctly targets the `sources_consulted` citation path
returned *outside* the `<context>` fence — the new blast radius this delta opens —
not just the synthesis-context copy. AC5 (fan-out cap) binds **exactly** min(distinct,cap)
by asserting both which ids ARE fetched and that capped-out ids are fetched zero times.

**Convergent finding (QA + CTO, independently).** Both flagged that the D5 ordering
tests (AC4/AC5/AC9/AC12) bind the *outcome* but, in the current fixtures, discovery
order already equals D5 order: the rank-0 seed is always also the `object_id` winner,
and `relation_priority` is never exercised in isolation (every neighbour uses
`wiki_relations`, priority 0). An impl that performs D1+D4 over the *discovery-ordered*
list but **omits the `(seed_rank, relation_priority, object_id)` sort entirely** would
still turn these tests green. B3 — "list order is the sole carrier of relation
priority" — is asserted by zero tests. This is non-blocking for the test phase (the
tests are correctly RED and a spec-faithful impl passes), but it is a required
impl-phase gate and is carried forward as a spec addendum.

## Findings

### BLOCKING

None. All three officers signed off with zero blocking findings.

### ADVISORY

1. **[QA+CTO] D5 ordering tests bind outcome, not order-isolation.** AC4/AC5/AC9 pass
   under an impl that skips the D5 sort and relies on discovery order; `relation_priority`
   and the `object_id` tie-break are never made to diverge from `seed_rank`. → Addendum
   item AC-T1 (impl phase must add order-isolation tests).
2. **[CSO] Citation-path sanitization — candidate partition untested.** AC11 binds only
   the *neighbour* citation title through `_safe_object_name`; a faulty impl could
   sanitize neighbour titles while leaving *candidate/seed* titles raw in
   `sources_consulted` (pre-#324 seeds used raw `obj.get("name","")`, query.py:567-568).
   Low risk (seed names are also sanitized on the synthesis-context path at query.py:286),
   but the citation-path partition symmetry is unguarded. → Addendum item AC-T2.
3. **[QA] AC2 `wiki_subjects` traversal not binding.** `test_wiki_subjects_relation_traversed`
   reaches subjects as Tier-1 candidates (present in `list_resp`), not via traversal, so a
   regression dropping `wiki_subjects` from `_RELATION_KEYS` would not be caught (the
   constant guard only covers `wiki_sources`). `wiki_subjects` is the OQ1-retained edge. → Addendum item AC-T3.
4. **[QA] AC9 companion-vs-inline.** The spec said "extend test_query.py:1613"; the impl
   created a parallel `TestContextBudgetD5Extension` instead. Net coverage equivalent
   (explicit identity assertions exist), but the original `len(sources) <= 2` bound
   (test_query.py:1680) retains its now-ambiguous B3 meaning. Cosmetic; optionally add a
   pointer comment. No coverage loss.
5. **[CSO] SG-3 rank-0 dominance** remains an accepted risk valid only under the
   single-tenant local trust model. No invariant to guard this ticket; flag for
   re-evaluation if the deployment model ever becomes multi-tenant / untrusted-vault.
6. **[CTO] AC2 split across two files** (constant guard in test_query.py, traversal
   binding in test_query_fetch_paths.py) is sound; keep the two halves in lockstep if
   either is refactored.

## Resolutions

No findings were withdrawn during discussion. The three officers' positions were
independently consistent, and the central convergent advisory (D5 order-isolation)
was reached separately by QA and CTO before cross-comparison — raising confidence it
is a real coverage edge, not a single reviewer's idiosyncrasy. The reviewer-diligence
mandate from aldeia-box#333 is satisfied: the internal R1→R2 cycle was confirmed to
have caught a real defect by mechanism, reproduced independently by two officers.

## Recommendation

**Recommended target:** impl
**Verdict:** APPROVED — advance.
**Confidence:** high
**Rationale:** Unanimous officer sign-off, zero BLOCKING findings, an independently
reproduced suite (11 failed / 64 passed / 6 skipped; failures cite #324 assertions,
not import/early-exit artefacts), zero regressions across the full wiki suite (538
passing), and a genuinely diligent internal review confirmed against real source. All
12 ACs are pinned by binding tests; the three load-bearing security invariants (SF1
file-back bound, SF-B citation redaction, fan-out cap) are guarded by non-tautological
tests. The natural next SDLC phase is **impl**; the six advisories are carried forward
— the three actionable ones (AC-T1 D5 order-isolation, AC-T2 candidate-title
sanitization, AC-T3 `wiki_subjects` traversal binding) as a spec addendum the impl
phase MUST honor, the remainder as documentation/observation notes. Routing per
autonomy policy is the watcher's to enforce; if impl is not yet autonomous it gates at
Decide, where Jan confirms before implementation begins.
**Dissent:** None.
