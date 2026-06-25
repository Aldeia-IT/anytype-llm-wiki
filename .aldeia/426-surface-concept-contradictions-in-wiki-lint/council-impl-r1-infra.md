# Council Impl Review R1 — Infrastructure Lead (#426)

**Reviewer:** Infrastructure Lead
**Date:** 2026-06-25
**Phase:** post-implementation governance review (operational readiness, resource impact, deploy/migration risk — NOT code review)
**Verdict:** SIGN-OFF — YES (1 ADVISORY of note, 0 BLOCKING)

---

## Summary

#426 is an operator-driven, on-demand change. `wiki_bootstrap` and `wiki_lint` are invoked
manually as CLI subcommands (`anytype-llm-wiki wiki-bootstrap|wiki-lint`, dispatched from
`server:main` → `wiki/cli.py:SUBCOMMANDS`) or as MCP tools. Neither runs as a long-lived service,
launchd job, or scheduled task, so there are **no plist changes, no Colima/Docker changes, no
service restart, and no new always-on memory consumer**. The Mac Mini steady-state resource profile
is unchanged. There is nothing here that competes for the 32 GB outside the brief moment an operator
runs the command.

The central operational risk — running the new `wiki_lint` against a space that has not been
re-bootstrapped yields an **un-clearable `critical`** finding — is real, but it is mitigated exactly
as the addenda require: the lint gate (§4) and the bootstrap reconcile (§3) ship together in one
change, MIGRATIONS.md "Unreleased" carries an explicit sequencing warning, and a new operational
`docs/deploy-runbook.md` states re-bootstrap is REQUIRED before linting. I verified all three.

The one operational gap worth recording (ADVISORY-1): the SG-e union audit log
(`logger.info("wiki_reconcile ...")`, `bootstrap.py:605-608`) does NOT reach the console under the
runbook's own documented invocation, because the CLI configures no logging handler and the root
logger defaults to WARNING. The runbook's "capture this line durably / do not rely on ephemeral
console output" instruction is therefore unsatisfiable as shipped. This is not a deployment blocker
(the destructive PATCH is defended in depth and the *keys added* are recoverable from
`--json` `types_reconciled`), but the runbook overstates an observability guarantee the code does
not currently deliver.

---

## Findings

### BLOCKING

None.

### ADVISORY

**ADVISORY-1 — SG-e audit log is not actually observable under the documented CLI invocation.**
- **Description:** The reconcile emits its union audit line at INFO level
  (`bootstrap.py:605` `logger.info("wiki_reconcile type=%s adding=%s union_keys=%s", ...)`).
  The CLI entry point (`wiki/cli.py:main`, lines 418-421) calls `args.func(args)` with **no**
  `logging.basicConfig`/handler/level setup, and there is no `basicConfig`/`dictConfig` anywhere in
  the package (`grep` across `src/` returns nothing). Python's root logger defaults to WARNING and
  routes INFO through no handler, so the `wiki_reconcile ...` line is silently dropped when an
  operator runs `uv run anytype-llm-wiki wiki-bootstrap`. The runbook
  (`docs/deploy-runbook.md`, "Durably capture the reconcile audit log") instructs the operator to
  capture exactly this line and "do not rely solely on ephemeral console output" — but the line
  never reaches the console to begin with.
- **Operational impact:** Low-to-moderate. The full `union_keys[]` payload sent to the destructive
  `update_type` PATCH (the single piece of forensic data CSO-3 / spec-addendum item 8 wanted retained
  for post-hoc corruption reconstruction) is not captured anywhere durable under the documented
  workflow. The *keys added per type* are still recoverable: `--json` mode prints the full result
  dict including `types_reconciled` with `properties_added` (`cli.py:73`, `bootstrap.py:159/610`).
  But the complete union actually transmitted — the thing that matters if a replace-not-merge PATCH
  corrupts a type — is only in the unemitted INFO line. The blast radius of the underlying PATCH is
  large (every Object of a type), which is precisely why the audit log exists; it is also why the
  in-depth read-side guards (monotonic-union, pagination/shape, SYSTEM_PROP_KEYS filter, empty-payload
  ValueError) keep this advisory rather than blocking.
- **Recommended action (any one, before relying on the runbook in anger):** Either (a) have the CLI
  bootstrap path enable INFO logging to a durable destination (e.g. `logging.basicConfig(level=INFO)`
  or a `--verbose`/`--log-file` flag in `wiki/cli.py`, mirroring the root-logger emit idiom already
  used at `extraction.py:362-373`); or (b) add `types_reconciled` with the full union to the
  human-readable bootstrap printout (`cli.py:_cmd_bootstrap`, ~line 77-100) and tell operators to run
  with `--json` and tee to a file; or (c) soften the runbook's claim to direct operators to
  `--json | tee` capture and stop promising the INFO line is available. Option (a) is the cleanest
  honoring of CSO-3 / spec-addendum item 8. None of these gate this deployment.

---

## Addendum verification

### spec-addendum-post-spec-r1.md (Infra-relevant items)

- **Infra-A1 (item 2) — `get_type` read-side live probe is a hard entry condition.** Honored at the
  test/impl phase per `phase-summary-impl.md` (reconcile mocks updated to mirror the real 7-property
  `wiki_concept` shape; guards tested against the observed contract). Outside the infra mandate to
  re-verify; noted as satisfied upstream. No operational objection.
- **Infra-A2 (item 7) — migration sequencing enforced at release; "re-run wiki_bootstrap is REQUIRED"
  must appear in the deploy runbook in addition to MIGRATIONS.md.** HONORED. The lint gate (§4,
  `lint.py`) and reconcile (§3, `bootstrap.py`) are in the same change/branch. MIGRATIONS.md and the
  new `docs/deploy-runbook.md` both state re-bootstrap is REQUIRED. Verified below.
- **Infra-A3 (item 4) — strengthen partial-failure recovery test (marker UNSTAMPED after failure).**
  Honored upstream; `test_reconcile_partial_failure_recovers_on_rerun` asserts the marker is not
  stamped, and the impl phase confirmed the guard has teeth (perturbation test, per
  `phase-summary-impl.md`). I independently confirmed the structural invariant operationally: the
  reconcile loop runs at `bootstrap.py:288-292`, the collection/WikiLog version stamps occur at
  `bootstrap.py:428+` and `:455+` — strictly AFTER the loop. A mid-loop `update_type` failure leaves
  the marker unstamped, so a clean re-run re-enters and completes. Recovery procedure is sound.

### spec-addendum-post-test-r1.md (Infra-relevant items)

- **Infra-3 (item 3) — migration sequencing + deploy runbook.**
  - *New operational deploy runbook required (MIGRATIONS.md alone insufficient).* HONORED.
    `docs/deploy-runbook.md` is a NEW file (54 lines), distinct from `releasing.md` (PyPI-only). It
    states re-running `wiki_bootstrap` is "REQUIRED (not optional) for every existing space" and
    MUST run before `wiki_lint`, with an explicit 3-step ordered sequence (deploy → re-bootstrap all
    spaces → then lint) and a "why the ordering is load-bearing" section naming the un-clearable
    `critical`. Clear and adequate. The runbook's CLI commands are valid: `wiki-bootstrap` and
    `wiki-lint` are real registered subcommands (`wiki/cli.py:SUBCOMMANDS` lines 21-27).
  - *MIGRATIONS.md note in "Unreleased" warning explicitly about the un-clearable `critical`.*
    HONORED. New "Schema 0.4.2" subsection under "Upgrading to the next release (Unreleased)" with a
    `⚠️ Sequencing matters` callout stating verbatim that running `wiki_lint` before re-bootstrapping
    "yields an un-clearable `critical` finding" with "no field to set to resolve them," and that the
    gate and reconcile ship together for this reason. Follows the v0.3.0 precedent. Explicit and clear.
  - *Gate + reconcile ship together.* HONORED — both in this branch/change.
- **Item 5 (CSO-3 / Infra) — durable audit log.** PARTIALLY HONORED. The SG-e INFO line exists in
  source (`bootstrap.py:605-608`) and the runbook documents the durable-capture obligation. But under
  the documented CLI invocation the line is not emitted (no logging config; root defaults to WARNING).
  See ADVISORY-1. The *intent* is met (audit line present, obligation documented); the *observability
  plumbing* is not. Non-blocking, but the runbook overstates what the code delivers today.
- **Item 1 (marker-ordering guard has teeth):** confirmed upstream + structurally above.
- **Items 2, 4 (docs prose; `update_type` ValueError refusal):** honored per diff and impl summary
  (CHANGELOG 0.4.2 entry present; README surfacing-gap clause replaced with "now flagged ... live";
  `update_type` raises `ValueError` on empty/None properties). Within CTO/QA/CPO domains; no infra
  objection.

---

## Resource Impact assessment

- **Memory (32 GB shared):** No change to steady-state. No new always-on process, no new service, no
  new Colima/Docker container. Bootstrap is a short-lived operator-invoked process. APPROVED.
- **CPU (M4):** Negligible, transient. One extra `GET /types/{id}` per existing wiki type per
  bootstrap (~6 GETs for a typical space) and at most one `PATCH` per type with a missing prop. For
  0.4.1→0.4.2 that is ~6 GETs + 1 PATCH, once per space. Steady-state after reconcile is the 6 GETs;
  PATCHes are skipped on a reconciled space. APPROVED — the spec's "negligible" claim is accurate.
- **Disk / SSD:** No new local data store, no new log file (the audit line, when emitted, rides
  existing stderr/console). No new backup surface on the Mac Mini. The graph mutation lands in
  Anytype (external store), not on local disk. APPROVED.
- **API / external cost:** Anytype local API only — no LLM calls, no paid external services on the
  reconcile path. Same API key/transport as existing bootstrap calls (no new auth surface; concurs
  with CSO domain). APPROVED.
- **Verdict:** The +1 GET per existing type and +≤1 PATCH per type with missing props is acceptable
  and does not change the resource profile.

## Deployment / failure / dependency assessment

- **Launchd / Docker / restart:** None required. No service to restart. No cascade risk to
  PostgreSQL/Ollama/Caddy/ntfy/IronClaw — the change touches an on-demand CLI/MCP tool only.
- **Migration steps:** Documented in both MIGRATIONS.md and the new runbook with an explicit ordered
  sequence. Adequate.
- **Rollback:** Reconcile is additive and idempotent (union-send preserves existing properties; only
  ADDS missing keys; format-mismatch correction explicitly out of scope). Re-running is safe. A
  mid-loop failure leaves the version marker unstamped → clean re-run recovers (verified ordering).
  No destructive rollback procedure needed.
- **Failure modes / data durability:** The replace-not-merge footgun is the only durability risk, and
  it is defended in depth (monotonic-union guard, pagination/shape guard, SYSTEM_PROP_KEYS filter,
  empty/None `ValueError` refusal, regression test). Partial failure is visible (`warnings[]` +
  `types_skipped`) and non-cascading. Graph durability is Anytype's responsibility (external store);
  no new local WAL/backup obligation introduced.
- **Monitoring / alerting:** No new watchdog or ntfy alert is warranted — there is no new service or
  endpoint to health-check. The only monitoring concern is forensic capture of the union, covered by
  ADVISORY-1.

---

## Sign-off

**YES — sign off on deployment. 0 BLOCKING, 1 ADVISORY.**

**Rationale:** This change introduces no new always-on service, no plist/Colima/Docker change, no
restart, and no steady-state memory/CPU/disk cost — the Mac Mini's 32 GB envelope is untouched. The
one genuine operational hazard, the un-clearable `critical` from running `wiki_lint` before
re-bootstrapping, is mitigated exactly as the addenda demand: gate and reconcile ship together,
MIGRATIONS.md "Unreleased" carries an explicit sequencing warning, and a clear new operational deploy
runbook states re-bootstrap is REQUIRED before linting (Infra-A2 / Infra-3 honored). The
destructive-PATCH blast radius is defended in depth, and recovery on partial failure is structurally
sound (marker stamped strictly after the reconcile loop). The single advisory is that the SG-e union
audit log is emitted at INFO but the CLI configures no logging handler, so it is not observable under
the runbook's own documented invocation — the runbook overstates an observability guarantee. That is
a follow-up to harden (enable INFO capture, or print `types_reconciled` in human output, or soften the
runbook to `--json | tee`), not a reason to hold the release.
