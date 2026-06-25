# Council Impl Review R1 — Chief Security Officer

**Ticket:** #426 Surface concept contradictions in wiki_lint
**Reviewer:** Chief Security Officer (governance / strategic posture)
**Date:** 2026-06-25
**Scope:** Post-implementation security posture for public open-source release. Strategic, not line-by-line (the technical security-reviewer already cleared the diff at LOW risk, 0 critical/major in `impl-review-r1.md`).

## Summary

The deliverable's only material security surface is the **replace-not-merge graph-corruption footgun**: Anytype's `update-type` PATCH REPLACES a type's property set, so a wrong reconcile payload could silently delete every user property across all objects of a type. The implementation treats this as a destructive operation and defends it in depth. The posture is sound and the defenses are layered, tested, and auditable:

1. **Union-send** (live user props + missing declared props, never the bare delta).
2. **Monotonic-union guard** — aborts if the computed union would shrink the live user set.
3. **Empty/None refusal pinned inside `update_type` itself** (raises `ValueError`), so a `{"properties": []}` PATCH is impossible from any call site, not just the reconcile caller.
4. **Read-side abort guards** — malformed envelope (KeyError/TypeError), non-dict shape, missing `properties`, and `pagination.has_more` all abort that type with a visible `warnings[]` entry and issue NO PATCH. A partial read can never drive a destructive replace.
5. **SG-e INFO audit log** of the exact union emitted immediately before every PATCH, with the deploy runbook mandating durable capture.
6. **Regression test** asserting pre-existing properties are never dropped, plus dedicated pagination/missing-key abort tests and a partial-failure-recovery test.

The fail-safe direction is correct throughout: every ambiguous read aborts the destructive path rather than guessing. The version marker is stamped only after the full reconcile loop, so a mid-loop failure leaves the space recoverable on a clean re-run (idempotent). No new trust boundary, no new secrets/credentials — `update_type`/`get_type` reuse the existing Anytype API key and transport.

The lint-gate extension (adding `wiki_concept` to the contradiction check) reads untrusted contradiction-relation data but only computes `len(contradictions)` and checks for the presence of a `wiki_last_reviewed` date. Contradiction content is never interpolated into a shell, query, eval, or any executed context. **No injection vector.**

## Findings

### BLOCKING
None.

### ADVISORY

**A-1 — Audit log durability depends on operator follow-through (accepted risk).**
The SG-e audit line (`wiki_reconcile type=... adding=... union_keys=...`) is the sole post-hoc forensic record reconstructing exactly what union was sent before each high-blast-radius PATCH. It is INFO-level application log output; durable capture is mandated in `docs/deploy-runbook.md` but not technically enforced — an operator who runs bootstrap with INFO suppressed or discards console output loses the forensic trail. Acceptable for an open-source tool where deployment logging is the operator's responsibility, and the runbook is explicit. *Risk accepted.* Recommended action: none required for ship; consider (future) emitting the union into the structured `result` payload so it is captured wherever bootstrap output is retained, independent of log level.

**A-2 — Blast radius is real but bounded and well-defended (accepted risk, documented).**
Should every defense be bypassed by an unforeseen API contract change, the failure mode is destruction of user properties across all objects of a wiki type. The live read-side probe (CSO-1, research.md) confirms the current contract has no pagination on single-type reads, so the pagination guard defends a hypothetical future change rather than an observed one — correctly documented as such in the test. The residual risk is an Anytype API change the guards do not anticipate; the audit log + idempotent re-bootstrap + monotonic guard make this recoverable/diagnosable rather than silent. *Risk accepted* given the depth of defense and the throwaway-space validation discipline.

**A-3 — S-MINOR-1 / S-MINOR-2 from the technical review (already dispositioned).**
Duplicate-live-key inflation of the monotonic guard (not a data-loss path) and whole-run abort on PATCH HTTP error (correct fail-safe, idempotent recovery) were reviewed and are correct trade-offs. No security action.

## Addendum-item verification

- **CSO-1 (spec-addendum-post-spec item 2) — `get_type` read-side live probe recorded in research.md: DONE.** research.md §1b records the verbatim live `get_type` response shape against `wiki-validation-throwaway`: per-property field set carries `key` (not `property_key`), `name`, `format`; and crucially **pagination NONE** for single-type reads. The success-path reconcile mock mirrors this real shape; the pagination-abort mock is explicitly flagged as synthetic (defending an unadvertised future change). The "safe-by-construction" disposition the spec council accepted was contingent on this probe — it landed.

- **CSO-2 (spec-addendum-post-spec item 3) — explicit pagination-abort test: DONE (two tests).** `test_reconcile_pagination_abort_warns_no_patch` (get_type returns `pagination.has_more is True`) and `test_reconcile_missing_properties_key_aborts` (no `properties` key) both exist in `tests/wiki/test_bootstrap.py` and assert ABORT + `warnings[]` + NO `update_type` PATCH. The sole destructive-path defense against an unverified read contract now has dedicated coverage.

- **CSO-3 (both addenda, items 8 / 5) — durable audit-log capture in deploy runbook: DONE.** `docs/deploy-runbook.md` has a dedicated "Durably capture the reconcile audit log" section quoting the exact SG-e log line, explaining the replace-not-merge blast radius, and mandating ("MUST capture this `wiki_reconcile ...` log line durably") shipping it to the central log store rather than relying on ephemeral console output. See A-1 for the residual (accepted) enforcement gap.

All three CSO addendum items honored.

## Sign-off

**YES.** Security posture is sound: the single material risk (replace-not-merge graph corruption) is defended in depth, empirically validated against the live API contract, regression-tested on the destructive path, and made diagnosable via a durably-captured audit log; no new trust boundary, no secrets, and no injection vector in the lint gate. Zero blocking findings.
