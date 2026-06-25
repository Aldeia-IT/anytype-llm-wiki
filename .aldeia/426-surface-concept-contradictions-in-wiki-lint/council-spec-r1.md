# Council Meeting — Post-spec (Round 1)

**Date:** 2026-06-25
**Ticket:** #426 — Surface concept contradictions in wiki_lint
**Phase reviewed:** spec
**Client:** anytype-llm-wiki (internal Aldeia fleet tooling — shared wiki memory MCP)

## Attendance

| Role | Present | Reason |
|------|---------|--------|
| Council Chair | Yes | moderator |
| Chief Security Officer | Yes | minimum roster |
| Chief Product Officer | Yes | minimum roster |
| Chief Technology Officer | Yes | minimum roster |
| QA Director | Yes | chair decision — destructive replace-not-merge PATCH + detailed test plan warrant a quality-gate review |
| Infrastructure Lead | Yes | chair decision — mandatory re-bootstrap migration + graph-corruption blast radius are operational concerns |
| Legal Counsel | No | internal fleet tooling; no PII, licensing, or regulatory dimension |
| Client Advocate | No | not a client project; consumers are the agent fleet + Jan |

## Context Presented

#426 surfaces concept-level contradictions through `wiki_lint`. Concept contradiction
*detection* shipped in #325 (records into `wiki_contradictions`), but `wiki_lint` only
surfaces *entity* contradictions today — so concept contradictions are "recorded-but-invisible"
to the fleet and Jan, who consume contradictions through `wiki_lint`, not manual Anytype
browsing. This ticket was the explicit council closure condition re-scoped out of #325.

The spec specifies four file:line-pinned change sites against post-#325 `main`:
1. **Schema** — add `wiki_last_reviewed` (date) to `wiki_concept`; bump `WIKI_SCHEMA_VERSION`
   0.4.1→0.4.2; add a `SYSTEM_PROP_KEYS` constant.
2. **New wiki_client methods** — `get_type` + `update_type` (`PATCH /v1/spaces/{id}/types/{type_id}`).
3. **Bootstrap reconcile** — read-modify-write loop linking declared-but-missing properties onto
   existing types. The high-risk section: Anytype `update-type` is REPLACE-not-merge (blast
   radius = every object of a type). Defended by three independent guards (monotonic-union,
   name/format-from-declared-schema, pagination/shape) + empty-payload refusal + audit log +
   regression test.
4. **Lint gate** — widen `contradiction_unresolved` from `wiki_entity`-only to
   `("wiki_entity","wiki_concept")` + docs (README/CHANGELOG/MIGRATIONS).

The spec was APPROVED through two internal review rounds (R1: 6 BLOCKING + 7 SHOULD-FIX, all in
§3; R2: two independent reviewers verified each resolution against code). One empirical gap (the
`get_type` *read*-side contract) is carried forward as a non-blocking impl/test-phase precondition;
the design is safe-by-construction regardless.

## Discussion

The council converged strongly and independently:

- **The `get_type` read-side gap was the dominant cross-functional theme** — raised independently
  by CSO (Advisory 1/2), CTO (A-1), Infra (A-1), and QA (A-2). The *write* contract
  (replace-not-merge, idempotent re-link) is verified live; the *read* contract (does raw
  `GET /types/{id}` return a complete, non-paginated `properties[]` with `name`/`format` per
  entry?) is not. The CTO sharpened the point: the pagination/shape guard and the name/format
  fallback both baseline off the *same* `get_type` read, so they defend against *advertised*
  truncation but not silent/unadvertised truncation — making the "safe regardless of probe"
  framing conditional on the probe also confirming property-set completeness and nested pagination.
  All four agreed the spec's disposition (carry forward, safe-by-construction) is acceptable at the
  spec gate **provided** the live probe (BL-6.4) becomes a hard entry condition before the
  reconcile PATCH is enabled.
- **QA surfaced a verified factual error in the spec** (A-1): the Test Plan (`spec.md:494-497`) and
  the R1 lead spot-check (`review-r1.md:97`) both assert there is NO hardcoded `0.4.1` pin in
  `test_bootstrap.py` and instruct the test-writer NOT to edit one. The chair independently
  verified this is false — `tests/wiki/test_bootstrap.py:855-870` (`test_wiki_schema_version_is_041`)
  hard-asserts `WIKI_SCHEMA_VERSION == "0.4.1"`. The §1 bump to 0.4.2 will deterministically break
  it. This is an inherited error that propagated through both R1 and R2 unnoticed.
- **CPO and CTO both explicitly declined to split** the ticket. The four changes form one
  dependency chain with a deliberate safety coupling (the lint gate and reconcile MUST ship
  together, else existing spaces fire un-clearable `critical`). Splitting would create a
  half-finished user journey that breaks an existing health signal.
- **Infra confirmed near-zero conventional deployment risk** (no new service, daemon, store, or
  steady-state resource draw) and verified the failure/recovery model against code: the reconcile
  runs entirely before both schema-version markers, so a mid-loop `update_type` failure leaves the
  marker unstamped and a clean re-run recovers with no manual cleanup.
- **CSO confirmed no new trust boundary** — `get_type`/`update_type` reuse the existing Anytype API
  key and transport; data is internal fleet content, not regulated PII. Coordinated with Infra: no
  conflict.

## Findings

### BLOCKING
None.

### ADVISORY
1. **[CSO-1 / CTO-A1 / Infra-A1 / QA-A2 — 4-way convergence] Complete the `get_type` read-side live
   probe (BL-6.4) as a hard entry condition before the reconcile PATCH ships.** Issue a raw
   `GET /v1/spaces/{id}/types/{type_id}` against a bootstrapped type in `wiki-validation-throwaway`,
   and record in `research.md`: (a) the exact per-property field set (`key`/`property_key`, `name`,
   `format`), (b) whether `properties[]` is ever paginated (`pagination.has_more`) **and**
   completeness/nested-pagination behavior. At least one reconcile mock must mirror the *actual*
   observed shape — otherwise the three safety guards are tested against a fictional contract.
2. **[QA-1 — verified by chair] Spec contains a factual error: `test_bootstrap.py:868` DOES hardcode
   `WIKI_SCHEMA_VERSION == "0.4.1"`.** The Test Plan (`spec.md:494-497`) and `review-r1.md:97`
   wrongly claim no such pin exists and tell the test-writer not to edit one. The §1 bump to 0.4.2
   will break `test_wiki_schema_version_is_041`. The test-phase worker MUST update this test (and
   run `grep -rn "0.4.1" tests/` to confirm no other pin) regardless of the spec's stale instruction.
3. **[CSO-2 / QA-A2] Add an explicit `pagination.has_more is True` → no-PATCH abort test.** The
   pagination/shape guard is the sole destructive-path defense against the unverified read contract;
   the current Test Plan covers union/no-op/never-drops/partial-failure-recovery but not a dedicated
   paginated-read abort case.
4. **[CTO-A3 / QA-A3 / Infra-A3] `test_reconcile_partial_failure_recovers_on_rerun` must assert the
   version marker is UNSTAMPED after the failing run**, not merely that a re-run recovers. It is the
   sole automated guard on the load-bearing marker-ordering invariant — treat as a pre-merge gate.
5. **[QA-A4] Confirm the three fail-first tests go RED on a meaningful assertion**, not merely on an
   ImportError/KeyError from a missing symbol.
6. **[CPO-1 / Infra-A2] Enforce the migration sequencing at release, not just in the spec.**
   Lint gate (§4) + reconcile (§3) ship together; "re-run `wiki_bootstrap` is REQUIRED" must be in
   the deploy runbook, not only MIGRATIONS.md, so no operator hits an un-clearable `critical`. The
   optional lint guidance-warning (deferred) can be a fast-follow.
7. **[CTO-A2] Pin the empty/None `properties` payload refusal inside `update_type` itself**, not only
   in the §3 caller, so the destructive PATCH can never be issued regardless of call site.
8. **[CSO-3] Ensure the SG-e INFO-level union audit log (emitted before each destructive PATCH) is
   durably captured** in deployment so a corruption event can be reconstructed post-hoc.

## Decomposition

None. Both the CPO and CTO explicitly considered and declined a SPLIT RECOMMENDATION. The four
change sites form a single dependency chain with a deliberate safety coupling (lint gate + bootstrap
reconcile must ship together to avoid an un-clearable `critical` on existing spaces). The reconcile's
generalization to all six `WIKI_TYPES` is correct forward-design, not scope creep. Combined scope is
within safe single-PR / single-impl-lead bounds.

## Resolutions

The council accepted, after discussion, that the carried-forward `get_type` read-side probe is an
acceptable spec-gate disposition (safe-by-construction) rather than a BLOCKING gap — conditioned on
Advisory 1 being honored as a hard impl/test entry condition. No member's concern was withdrawn; all
concerns are recorded as advisories to carry into the test/impl phase.

## Recommendation

**Recommended target:** test
**Confidence:** high
**Rationale:** Zero BLOCKING findings; the spec is implementation-ready, well-researched, and
defends its one genuine risk (replace-not-merge graph corruption) with fail-closed defense-in-depth.
The next phase in the test-before-impl pipeline is `test`. The eight advisories are work-instructions
for that phase — most materially, QA's verified `0.4.1` test-pin error (Advisory 2) and the
`get_type` read-side probe (Advisory 1) — and are recorded in a spec addendum so the test/impl lead
treats them as acceptance criteria.
**Dissent:** None.
