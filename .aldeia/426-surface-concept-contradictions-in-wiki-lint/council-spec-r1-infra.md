# Infrastructure Lead Council Assessment — Post-Spec R1 — #426

## Sign-off: APPROVE WITH CONDITIONS

## BLOCKING findings

None.

The replace-not-merge footgun — the only finding that could rise to BLOCKING on
operational grounds (blast radius = every object of a type) — is defended in depth
by three independent, code-level guards (monotonic-union, name/format-from-declared,
pagination/shape), an empty-payload refusal in `update_type`, an INFO audit log before
each PATCH, and a regression test. That is adequate mitigation for the risk; it does not
warrant a deployment block.

## ADVISORY findings

### A-1 — `get_type` read-side contract is unverified at sign-off time (deployment precondition, not a design gap)
- **Description.** The live probe (`research.md §1`) verified the *write* contract
  (`update-type` replace-not-merge, idempotent re-link) but never transcribed the raw
  `GET /v1/spaces/{id}/types/{type_id}` response: the exact per-property field set
  (`key`/`property_key`/`name`/`format` presence) and whether `properties[]` can be
  paginated. The spec is safe-by-construction regardless (BL-6 guards abort rather than
  issue a destructive PATCH on a malformed/truncated read), and the probe is recorded as
  a carried impl/test-phase precondition (spec Open Questions, BL-6.4).
- **Operational impact.** If the live `properties[]` *is* paginated and `get_type` (a
  single un-paginated `c.get`, unlike every other list helper that routes through
  `_paginated_get`) silently truncates, the pagination guard converts the hazard into a
  visible `reconcile_skipped` warning + `types_skipped` entry rather than corruption — so
  the worst realistic outcome is a no-op reconcile that leaves the space firing `critical`
  on concept contradictions until fixed. The mitigation is sound but degrades to
  "reconcile silently does nothing on that type."
- **Recommended action.** Treat the BL-6.4 live probe as a hard gate on the impl/test
  phase, recorded in `research.md`, BEFORE the reconcile ships to any production space. The
  lead has Anytype MCP access. This is a deployment precondition, not a re-spec.

### A-2 — Migration sequencing is correct but operationally unforgiving; surface it in the deploy runbook, not only MIGRATIONS.md
- **Description.** §4 (lint gate) and §3 (reconcile) MUST ship together, and every existing
  space MUST re-run `wiki_bootstrap` or the new gate fires `critical` for every concept
  contradiction with no `wiki_last_reviewed` field to clear it (broken UX, Problem Statement
  #1). The spec documents this in MIGRATIONS.md (REQUIRED, prerequisite).
- **Operational impact.** On the single Mac Mini fleet, multiple spaces exist (validation
  throwaway, plus live agent wiki spaces). A deploy that lands the code but where an operator
  forgets to re-bootstrap a given space produces a space stuck emitting `critical` health
  signals — noisy, and erodes trust in `wiki_lint`. The failure is recoverable (re-bootstrap
  is idempotent) and non-destructive, so it is ADVISORY not BLOCKING.
- **Recommended action.** Add the re-bootstrap step to the actual deployment/cutover runbook
  for this change (enumerate every space that must be re-bootstrapped post-deploy), not only
  to MIGRATIONS.md. Consider the deferred optional lint guidance-warning (SF-4) if operator
  error proves common.

### A-3 — Failure/recovery model is sound; confirm the partial-reconcile recovery test is a hard pre-merge gate
- **Description.** I verified the ordering invariant against the code: the existing-types
  branch (`bootstrap.py:281-285`, where reconcile is inserted) runs entirely BEFORE both
  schema-version markers — the root-collection PATCH (`bootstrap.py:419-424`) and the WikiLog
  stamp (`:446-458`). A mid-loop `update_type` failure propagates through `_run_bootstrap`,
  is caught and categorized by the wrapper (`bootstrap.py:229-246`, returning a structured
  `[API ERROR]`/`error_category` result), and leaves the marker unstamped at the old version.
  A clean re-run re-enters the loop and completes the remaining types. Each per-type reconcile
  is independently idempotent. This is the correct design.
- **Operational impact.** Recovery is "re-run `wiki_bootstrap`" with no manual cleanup — the
  best possible recovery story. The only way to break it is to move the marker before the loop,
  which the spec explicitly forbids.
- **Recommended action.** Ensure `test_reconcile_partial_failure_recovers_on_rerun` (spec Test
  Plan, SF-3) is treated as a hard pre-merge gate, since it is the sole automated guard on the
  load-bearing ordering invariant.

### A-4 — Resource and observability impact is negligible; no new watchdog/backup/launchd work required
- **Description.** The reconcile adds at most one extra `GET` per existing wiki type per
  bootstrap (6 types) plus at most one `PATCH` per type with a missing prop (one PATCH on the
  0.4.1->0.4.2 reconcile, zero thereafter). Steady state = 6 GETs on a no-op bootstrap.
- **Operational impact.** No change to the Mac Mini M4 32GB steady-state memory, CPU, or disk
  profile. No new service, no new daemon, no new endpoint, no Colima/Docker change, no launchd
  plist change. `wiki_bootstrap` remains an on-demand MCP call, not a long-running process —
  so no new watchdog check, no new log file requiring rotation, no new ntfy failure mode. No
  new data store, so existing PostgreSQL/backup coverage is unaffected. The schema change lives
  in Anytype (the wiki backing store), whose backup posture is unchanged by this ticket.
- **Recommended action.** None required. Confirm the INFO audit log (`wiki_reconcile type=...
  union_keys=...`, SG-e) lands on the same logger as the rest of bootstrap so it is captured by
  existing log handling; given the destructive-PATCH blast radius this single INFO line per PATCH
  is sufficient observability — no alerting needed for an on-demand operator-initiated call.

## Rationale

This change introduces no new service, daemon, endpoint, data store, or steady-state resource
draw on the shared Mac Mini, so there is no deployment-infrastructure risk in the conventional
sense; the operational risk is entirely concentrated in a single destructive PATCH path
(`update_type`, replace-not-merge) and the mandatory re-bootstrap migration. Both are well
defended: three independent code-level guards plus an empty-payload refusal make the PATCH
safe-by-construction, and the verified version-marker-after-loop ordering invariant gives a
clean, idempotent, no-manual-cleanup recovery from any mid-loop failure. I sign off conditional
on (1) the BL-6.4 `get_type` read-side live probe being completed and recorded before the
reconcile reaches any production space, (2) the partial-failure recovery test being a hard
pre-merge gate, and (3) the re-bootstrap step being captured in the deploy runbook for every
existing space, not just MIGRATIONS.md.
