# Council Meeting — Post-test (Round 1)

**Date:** 2026-06-12
**Ticket:** #323 — Retrieval metadata filters: type + date scoping for `wiki_query` / `semantic_search`
**Phase reviewed:** test
**Client:** anytype-llm-wiki (Aldeia-IT/anytype-llm-wiki)

## Attendance

| Role | Present | Reason |
|------|---------|--------|
| Council Chair | Yes | moderator |
| QA Director | Yes | minimum; central to a test-phase gate (AC coverage, test adequacy, regression risk) |
| Chief Technology Officer | Yes | test↔spec wire-contract fidelity, satisfiability, reviewer diligence |
| Chief Product Officer | Yes | open CPO findings (product.md tag overclaim → #336), de-scope integrity |
| Infrastructure Lead | Yes | forced one-time re-embed migration (F11) is the highest operational risk |
| Chief Security Officer | No | only test-targeted security item (CSO-5 cross-tier equivalence) is satisfied; remaining items (CSO-6 date-validation trust boundary) are impl-targeted; writing tests introduces no new security surface |
| Legal Counsel | No | no privacy/licensing/regulatory surface; all evaluation local, no egress (spec §14) |
| Client Advocate | No | internal agent-operations/infra tooling; CPO covers user-value and the OSS-community lens |

## Context Presented

The test phase wrote a complete failing-test suite for the type+date metadata-filter
feature (the ratified subset of #323 after Jan's Decide adjudication: OD-1 ACCEPTED —
ship date filtering via additive `last_modified_date` payload + forced one-time re-embed;
OD-2 ACCEPTED as de-scope — `source_type`/`domain_tags` deferred in full to follow-up #336).

Deliverables: 21 new tests across `tests/test_indexer.py`, `tests/test_chunker.py`,
`tests/wiki/test_query.py` — 15 failing (missing impl) + 6 regression guards. The suite
pins the spec §6 wire contract (`Filter(should=[FieldCondition(MatchValue)])` not `MatchAny`;
`DatetimeRange` not `Range`; `gte`/`lte` not `gt`/`lt`), the D3 migration (schema-version
bump forces full re-embed + marker stamp), and the two spec-addendum exit criteria
(CTO-4/CSO-4 genuinely-runnable AC-F1b/F10b Tier-2 enumeration; CSO-5 cross-tier date
equivalence). In-phase test-review verdict: APPROVED with one SHOULD-FIX (state-file
isolation leak) fixed inline (commit c88218e).

## Discussion

All four members ran the suite independently and reproduced the **15 failed / 101 passed /
11 skipped** split exactly. Each verified that every new test fails for a
missing-implementation reason (TypeError on missing kwargs, ImportError on missing
predicates, AttributeError on `config.PAYLOAD_SCHEMA_VERSION`, AssertionError on missing
payload/chunk behavior) — none is a test-code defect or unsatisfiable mock.

- **QA ↔ CTO** converged on the addendum exit criteria being genuinely met: the
  `anytype_enum_fixture` named in the spec was aspirational (a pytest fixture cannot inject
  routes into an active `@respx.mock` context), and the test-writer's per-test respx route
  setup mirroring `TestRetrieval` is the sound, equivalent realization — the AC-F1b/F10b
  guards remain non-vacuous (capture `types` kwarg on monkeypatched `semantic_search_core`,
  assert set-equality with the live `_WIKI_TYPE_KEYS`).
- **CTO** independently validated the CSO-5 `gt is None` exclusivity assertion is
  non-tautological by running `DatetimeRange.model_fields` (`gt` is a real field): an impl
  wrongly using exclusive `gt=` would populate it and fail the test. CTO also surfaced an
  additional genuine guard the in-phase review under-stated — F6b/F6c run with no respx mock
  active, so a non-short-circuiting `wiki_query` would hit a real `list_objects` HTTP call and
  land on `api_error` instead of the asserted `config_error`, enforcing the §9.2
  "validate-before-client-construction" ordering.
- **Infra** focused on the migration: F11a pre-seeds matching `last_mod` so only the version
  bump can force re-embed, then asserts `objects_indexed==1` + upsert + marker stamped to 2;
  F11b asserts the no-bump incremental skip (`objects_indexed==0`). Confirmed F7a/F7b prove
  payload indexes are created on the reindex path only, never the `reembed_object` hot path.
- **Infra ↔ CTO ↔ QA** all confirmed the previously-flagged state-file isolation leak in
  `test_reindex_creates_payload_indexes` is fixed (now patches `INDEX_STATE_FILE`/
  `INDEX_STATE_DIR` to `tmp_path`, commit c88218e) — no test mutates the real machine state
  file. This was the one finding that could have been BLOCKING; it is cleared.
- **CPO** verified scope discipline: no test exercises `source_type`/`domain_tags` as a live
  filter param (the only occurrences are a negative assertion guarding `source_type` out of
  the index set, tagged "deferred to #336"). De-scope integrity holds — #336 exists and is
  referenced. CPO carried forward Jan's finding 1 (product.md overclaim) as an impl/doc exit
  criterion, judged correctly NOT to block the test→impl transition.

## Findings

### BLOCKING
None.

### ADVISORY
1. **[CPO-1]** `.aldeia/context/product.md:15` advertises "Metadata filtering — Filter by
   space, object type, **tags**" — a capability v1 will not deliver (tag/source filtering
   deferred to #336). Documentation-truth issue, not a test-suite-correctness issue. Carry as
   a concrete **impl exit criterion**: soften the line and ship the §15 release note stating
   tag/source filtering is unavailable in v1, linking #336. (This is Jan's explicit CPO
   finding 1 from the Decide ratification.)
2. **[CPO-traceability]** The spec body cites the deferral generically ("D6 / single follow-up
   ticket"); only the test artifacts carry the literal "#336". Backfill "#336" into spec §12
   DEFERRED rows and §3 D6 for self-documenting traceability. Low priority.
3. **[CTO-ADV1]** `wiki_query` must insert date/type-intersection validation as an **early
   return before** `AnytypeReadClient`/`WikiClient` construction (current code builds clients
   at `query.py:371-372` before any validation). The F6b/F6c tests enforce this, but it is a
   non-obvious ordering requirement — flag to the implementer so validation lands in the right
   place and returns `config_error`, not `api_error`.
4. **[Infra-A1/A2]** The forced backfill is the only state-mutating op and runs with no atomic
   write/lock on the state file and no cron overlap guard; interrupt-safety (marker stamped
   only after loop completion) is a design invariant not directly unit-tested. Operational, not
   unit-testable — mitigated by the Infra-7/9 deployment-doc exit criteria already recorded in
   `spec-addendum-post-spec-r1.md`.
5. **[QA-A1/A2]** AC-F3 (space_id scoping) reuses the pre-existing test rather than a new one;
   the §6.2 `must`-list refactor touches the space_id clause — impl should confirm the existing
   space_id test still passes post-refactor. AC-F11b currently red via the same missing-constant
   AttributeError; impl should confirm it goes genuinely green (not merely non-erroring) after
   the constant is added.

## Resolutions

The one residual risk that could have been BLOCKING — a test mutating the real machine state
file (`~/.local/share/anytype-llm-wiki/state.json`) — was raised as a SHOULD-FIX by the
in-phase review, fixed inline (commit c88218e), and independently re-confirmed fixed by both
Infra and CTO during this meeting. No member withdrew a finding under discussion; all four
arrived at sign-off independently and converged.

The Infra-7/9 (deployment sequencing + post-deploy verification) and CSO-6 (§14 cross-ref)
items are already recorded as impl exit criteria in `spec-addendum-post-spec-r1.md` and are
not re-litigated here.

## Recommendation

**Recommended target:** impl
**Confidence:** high
**Rationale:** Unanimous sign-off, zero BLOCKING findings. The test suite is a faithful,
non-vacuous, executable encoding of the approved spec's wire contract — red where it should be
(every failure impl-gated), green where it should be (6 load-bearing regression guards). The
two mandated addendum exit criteria are genuinely met, the highest-risk element (the forced
re-embed migration) is well-covered with full state-file isolation, the de-scoped filters are
correctly absent, and the in-phase review demonstrated real codebase verification rather than a
rubber-stamp. Implementation has an unambiguous contract to build against. The advisory items
are impl/doc exit criteria (carried forward in `spec-addendum-post-test-r1.md`), not gate
blockers.
**Dissent:** None.
