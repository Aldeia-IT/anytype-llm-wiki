# Council Review — Test Phase (R1) — Infrastructure Lead

**Ticket:** #426 — Surface concept contradictions in wiki_lint
**Phase reviewed:** test (test→impl advancement)
**Client:** anytype-llm-wiki (internal Aldeia fleet tooling — shared wiki-memory MCP)
**Date:** 2026-06-25
**Reviewer:** Infrastructure Lead

## Mandate

Operational readiness, resource impact, deployment/migration risk for advancing
test→impl. Verified against actual files in the worktree; suite run locally.

## Verification performed

- Ran `uv run --extra dev pytest tests/wiki/ -q` → **16 failed, 593 passed, 16
  skipped, 2 xfailed**. The 16 failures are the intended fail-first/regression
  tests; no previously-passing test regressed. (The phase-summary cites 711
  passed / 39 skipped for the full `tests/` suite; the delta here is purely
  because I scoped to `tests/wiki/`. Same 16 intended failures, consistent.)
- Read both reconcile-safety tests in full: `test_reconcile_no_op_when_complete`
  (`tests/wiki/test_bootstrap.py:2332`) and
  `test_reconcile_partial_failure_recovers_on_rerun` (`:2698`).
- Verified the marker-ordering invariant against source: the existing-types
  branch where reconcile lands (`src/anytype_llm_wiki/wiki/bootstrap.py:281-285`)
  executes *before* both schema-version stamps (root-Collection PATCH at `:419`,
  WikiLog stamp at `:446`). The invariant holds by construction in current code.
- Inspected `MIGRATIONS.md`, `CHANGELOG.md`, `README.md`, and `docs/releasing.md`.

---

## Findings

### ADVISORY — Migration idempotency and the marker-ordering invariant ARE adequately guarded (PASS, no action)

This is the load-bearing operational concern for this ticket, and it is covered.

- **No-op on a fully-reconciled space** — `test_reconcile_no_op_when_complete`
  (`:2332`) seeds a live `wiki_concept` already carrying all eight declared
  properties (including `wiki_last_reviewed`) and asserts **zero** PATCH calls to
  `/types/` (`:2389`) AND `types_reconciled == []` (`:2395`). This pins true
  idempotency — a re-run on a migrated space issues no destructive write. Good.

- **Partial-failure recovery with marker UNSTAMPED** (addendum item 4) —
  `test_reconcile_partial_failure_recovers_on_rerun` (`:2698`) makes
  `update_type` raise `HTTPStatusError` on the 2nd type and asserts three things:
  (A) the error propagates out of `wiki_bootstrap` (`:2827`); (B) — the critical
  one — the schema-version marker is **not** stamped to `0.4.2` after the failing
  run, by sniffing the WikiLog PATCH payload for `wiki_schema_version` (`:2734-2735`,
  `:2788-2797`, asserted `:2836`); (C) a clean re-run completes the remaining type
  (`:2871`). Assertion B is the **sole automated guard** on the
  marker-stamped-only-after-the-loop ordering invariant, and it is non-vacuous
  (it inspects the actual PATCH body, not a flag). This is exactly what the
  recovery model depends on: a mid-loop failure leaves the marker at the old
  version so a clean re-run re-enters the loop. No manual cleanup, no stranded
  state.

**Operational impact:** the migration is self-healing on retry. A failed
re-bootstrap is safe to simply re-run. No DB surgery, no partial-state recovery
runbook needed. **No action required at test phase.**

### ADVISORY — Resource impact is negligible and correctly bounded for the Mac Mini fleet

The reconcile adds, per bootstrap invocation: at most one `GET
/v1/spaces/{id}/types/{type_id}` per existing wiki type (6 types), and at most
one `PATCH` per type with a non-empty missing-set. For the 0.4.1→0.4.2 upgrade
that is **6 GETs + 1 PATCH** total (only `wiki_concept` has a missing property);
steady-state after migration is **6 GETs, 0 PATCH**.

- Memory: no change. No new service, daemon, process, or in-memory cache. The
  reconcile is request/response work inside the existing `wiki_bootstrap` call
  path.
- CPU: trivial — set differences over ~8 property dicts per type.
- Disk: none. No new log file, no new data store.
- API cost: zero LLM calls. The added calls are local Anytype API (same host,
  same key, same transport as every existing bootstrap call). `wiki_bootstrap` is
  an operator-invoked, infrequent command — not a hot path.
- Steady-state resource profile: **unchanged.** This does not compete for the
  32GB envelope. Nothing new runs continuously.

**Operational impact:** acceptable on the shared Mac Mini M4 with full margin.
**No action required.**

### ADVISORY — Mandatory-migration sequencing (item 7) is correctly carried as an IMPL/RELEASE requirement and is NOT silently dropped (confirmed)

This is the one genuinely dangerous operational property of the ticket: the new
lint gate fires `critical` for concept contradictions **regardless** of whether
`wiki_last_reviewed` exists on `wiki_concept`. A space that runs the new
`wiki_lint` without first re-running `wiki_bootstrap` would fire an
**un-clearable `critical`** — a stranded broken state. The lint gate (§4) and the
bootstrap reconcile (§3) MUST ship together.

I confirmed this requirement is **not** lost in the test→impl handoff:

- It is recorded as **authoritative spec** in
  `spec-addendum-post-spec-r1.md` item 7 ([CPO-1/Infra-A2]): ship-together +
  "re-running `wiki_bootstrap` is REQUIRED for existing spaces" must appear in
  the deploy runbook **in addition to** MIGRATIONS.md.
- It is restated in `spec.md §5` (MIGRATIONS.md note) and the Operational
  Considerations section.
- The test phase explicitly and **correctly** flagged it as not-testable-here and
  carried it forward to impl: `phase-summary-test.md` "Risks and Open Items"
  calls out items 7–8 as "for the IMPL phase / release owner ... correctly not
  tested."

This is the right disposition. Sequencing and runbook wording are release-time
controls, not unit-testable invariants. They are flagged in the one place Task
Intake reads as authoritative (the spec addendum), so the impl lead will see
them.

**However, two concrete gaps the impl phase MUST be told (carry-forward, not
test-phase blockers):**

1. **There is no operational deploy runbook file in this repo.** The only
   "runbook" is `docs/releasing.md`, which is a **PyPI-publish** runbook (OIDC
   trusted publishing, tag-gate) — it has zero migration/bootstrap content. The
   addendum's "deploy runbook" therefore has no existing home. The impl/release
   owner must either (a) add a migration/operations section to `docs/releasing.md`,
   or (b) create a dedicated deploy/operations runbook. Putting the "re-bootstrap
   REQUIRED" note only in MIGRATIONS.md would **not** satisfy addendum item 7.

2. **MIGRATIONS.md placement.** The 0.4.2 note must land in the "Upgrading to the
   next release (Unreleased)" section (`MIGRATIONS.md:89`), which today only
   documents the `prune-citations` cleanup. Precedent exists and is strong — the
   v0.3.0 section (`MIGRATIONS.md:60-75`) already uses the "**Re-run
   `wiki_bootstrap`** on each existing space before using `wiki_ingest`" pattern.
   For 0.4.2 the wording must be **stronger**: re-bootstrap is a *prerequisite for
   the new lint gate to be clearable*, not merely advisable, and must explicitly
   warn that running the new `wiki_lint` before re-bootstrapping produces an
   un-clearable `critical`.

**Recommended action (impl phase):** (i) write the MIGRATIONS.md 0.4.2 entry with
the un-clearable-`critical` warning; (ii) add the "re-bootstrap REQUIRED" note to
an actual operational runbook (extend `docs/releasing.md` or create one) — do not
rely on MIGRATIONS.md alone; (iii) ensure the impl-reviewer's AC#3 manual gate
verifies BOTH locations, not just the automatable README substring check.

### ADVISORY — Deployment / rollback risk profile (impl phase awareness)

No conventional deployment risk — no launchd plist change, no Docker/Colima
change, no new service, no service restart, no new port or network exposure, no
new watchdog or log-rotation need (no new long-running process or log file). This
is a library/CLI behaviour change inside an operator-invoked command.

The single non-trivial operational risk is the **replace-not-merge
graph-corruption footgun** on `update_type` (sending a delta instead of the full
union would wipe every user property on the type — blast radius = every object of
that type). The test suite defends this well: union-not-delta
(`test_reconcile_never_drops_existing_properties`), system-prop exclusion
(test-review F-2), pagination/shape abort (`TestReconcilePaginationAbort`), and
the empty/None-payload refusal inside `update_type` (`TestUpdateTypeGuard`,
addendum item 6). The read-side `get_type` contract was live-probed and the
success mock mirrors the real shape (`research.md §1b`, per phase summary).

**Rollback:** because the marker is stamped only after a clean loop, a failed
reconcile is rolled back simply by **re-running** `wiki_bootstrap` once the
transient cause clears — there is no forward-only migration to unwind. A
*successful* reconcile only ADDS a property key (never drops/reformats — §3 "out
of scope"), so it is non-destructive and needs no rollback. The impl phase should
preserve the marker-after-loop ordering (the test enforces it) and ensure the
SG-e INFO union audit log (addendum item 8) is durably captured by the
deployment's logging so any corruption event is reconstructable — this is the one
diagnostic dependency worth confirming at impl.

---

## Summary of carry-forward items for IMPL phase

| # | Item | Source | Status |
|---|------|--------|--------|
| 1 | Ship §3 reconcile + §4 lint gate **together** | addendum item 7 | flagged, honor at release |
| 2 | "Re-bootstrap REQUIRED" in a real deploy runbook (none exists today — `docs/releasing.md` is PyPI-only) **and** MIGRATIONS.md | addendum item 7 / Infra | new gap surfaced — impl must create/extend runbook |
| 3 | MIGRATIONS.md 0.4.2 entry in "Unreleased" section with explicit un-clearable-`critical` warning | spec §5 | impl |
| 4 | Preserve marker-stamped-after-loop ordering (test enforces) | addendum item 4 | guarded by test |
| 5 | Durably capture SG-e union audit log | addendum item 8 | impl/deployment |
| 6 | impl-reviewer AC#3 gate must check BOTH runbook and MIGRATIONS.md, not just README | spec AC#3 | impl review |

No new BLOCKING operational risk. The migration is self-healing on retry,
resource impact is negligible, and the one dangerous property (un-clearable
`critical` on un-migrated spaces) is correctly captured as an authoritative
release requirement and well-guarded by tests on the recovery path.

---

## Sign-off

**SIGN-OFF (advance test→impl).** Zero BLOCKING findings. Migration idempotency,
the marker-ordering recovery invariant, and resource bounds are verified against
the actual test code and source. The mandatory-migration requirement is correctly
carried forward as an impl/release item and is not silently dropped. The one
substantive carry-forward I add: **there is no operational deploy runbook in the
repo today** (`docs/releasing.md` is PyPI-publish only), so the impl/release owner
must create or extend one to satisfy addendum item 7 — MIGRATIONS.md alone is
insufficient. This is an impl-phase obligation, not a reason to hold the test
phase.
