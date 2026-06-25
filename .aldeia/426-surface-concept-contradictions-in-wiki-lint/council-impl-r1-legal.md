# Council Impl Review R1 — Legal Counsel

**Ticket:** #426 — Surface concept contradictions in wiki_lint
**Phase:** Post-implementation governance review (legal / regulatory / compliance / licensing / privacy)
**Reviewer:** Legal Counsel (General Counsel), Aldeia-IT review council
**Date:** 2026-06-25
**Project:** anytype-llm-wiki (dual-purpose: Aldeia-IT internal KB + public OSS tool for the Anytype community)

---

## Summary

This is a small, self-contained internal feature change with no externally novel surface. It (1) adds
one declared property (`wiki_last_reviewed`, a date) to the `wiki_concept` schema and bumps
`WIKI_SCHEMA_VERSION` 0.4.1 → 0.4.2; (2) adds two thin HTTP wrapper methods (`get_type`, `update_type`)
to `WikiClient` that call the existing local Anytype REST API over the same already-authorized
transport/key; (3) widens an existing lint gate by one tuple element so concept contradictions are
surfaced exactly as entity contradictions already were; and (4) updates public-facing docs
(README, CHANGELOG, MIGRATIONS, new deploy-runbook).

From a legal/compliance standpoint the change is clean:

- **No new dependencies.** No change to `pyproject.toml`, `requirements.txt`, or any lockfile —
  zero OSS license-compatibility surface introduced. The repo LICENSE remains MIT
  (Copyright (c) 2026 Aldeia IT). No GPL/AGPL contamination risk.
- **No new data collection, no new PII, no new telemetry.** The feature operates entirely on
  knowledge already stored by the user in their own Anytype space, read via the local API. It
  surfaces contradictions that the #325 detection pipeline already recorded; it adds one date field
  and one health-check signal. No data leaves the machine that did not already. The off-machine
  egress path (`WIKI_EXTRACT_ENDPOINT`, consent-gated per `compliance.md`) is untouched.
- **No new third-party service.** `get_type` / `update_type` call the same Anytype local REST API
  (`/v1/spaces/{id}/types/{type_id}`) already used by `create_type` / `list_types` / `update_object`.
  No new ToS surface beyond what the project already operates under.
- **Public-facing docs are accurate and non-misleading.** The README correctly removes the stale
  "not yet flagged by wiki_lint" surfacing-gap clause and now states concept-contradiction surfacing
  is live; CHANGELOG and MIGRATIONS accurately describe the 0.4.2 bump, the REQUIRED re-bootstrap,
  and the un-clearable-`critical` failure mode. These are honest and complete.

I find no licensing, privacy, regulatory, IP, or contractual concern that rises to BLOCKING. One
ADVISORY note (data-integrity / operational disclosure) is recorded for documentation.

---

## Findings

### BLOCKING

None.

### ADVISORY

**A1 — Replace-not-merge data-destruction footgun is an operational/integrity matter; ensure the
deploy-runbook capture requirement is treated as binding for the public release.**

- **Description.** The reconcile path's central risk (an `update_type` PATCH under Anytype's
  replace-not-merge semantics can destroy all user properties on a type, across every Object of that
  type, if a malformed/partial union is sent) is engineered against in depth (four guards + audit
  log) and the impl team reports zero correctness/security defects. From a legal lens this is not a
  privacy or licensing issue — it is a **data-integrity** matter that, for the *public* OSS release,
  touches user-data-loss exposure. The MIT license already disclaims warranty and liability
  ("AS IS", no liability) which substantially covers the OSS distribution. The new
  `docs/deploy-runbook.md` correctly mandates durable capture of the `wiki_reconcile …` audit log
  line. For Aldeia-IT's *internal* use over its own business KB, the same runbook should be honored
  operationally so any corruption event is post-hoc reconstructable.
- **Legal basis.** MIT license warranty/liability disclaimer (covers OSS users); internal
  data-stewardship / business-continuity best practice (no external/client contractual SLA is
  implicated — the project is free, no-revenue, no client deliverable per `business.md`).
- **Recommended action.** No release blocker. Confirm the deploy-runbook's audit-log-capture
  requirement is observed for Aldeia-IT's own spaces; no public-facing legal change needed. This is
  a CSO/operational crossover — flagging to CSO for the data-protection/integrity angle.

**A2 — Migration sequencing creates a transient un-clearable `critical` state; disclosure is
adequate, recommend it stays prominent.**

- **Description.** Running the new `wiki_lint` on a space not yet re-bootstrapped yields a
  `critical` finding with no field to clear it. This is fully and prominently disclosed in
  MIGRATIONS.md (a "⚠️ Sequencing matters" callout) and docs/deploy-runbook.md ("golden rule"). For
  an OSS tool, accurate disclosure of a known operational sharp edge is the relevant standard, and it
  is met. No misrepresentation risk.
- **Legal basis.** Truth-in-documentation / no-misleading-statements (consumer-protection-adjacent
  good practice for public software); MIT warranty disclaimer.
- **Recommended action.** None required — disclosure is accurate and prominent. Maintain it in the
  same prominence in the eventual tagged 0.4.2 release notes.

---

## Crossover notes

- **CSO:** A1 (replace-not-merge data-destruction risk and the audit-log durable-capture mandate) is
  a security/data-protection crossover. The security review reportedly rated the risk LOW with
  zero defects; legal concurs there is no privacy or breach-notification implication (no PII flow,
  no new data egress, local-only). Flagging for CSO awareness of the integrity/audit angle only.

---

## Sign-off

**YES — signed off (no veto).**

**Rationale.** This change introduces no new dependency (zero OSS-license-compatibility surface;
MIT license intact and uncontaminated), no new data collection or PII, no new telemetry, and no new
third-party service or ToS surface — it reads/writes the same user-owned Anytype data via the same
already-authorized local API. GDPR/LGPD posture is unchanged because no new personal-data processing
is introduced; the local-first, consent-gated egress model in `compliance.md` is untouched. The
public-facing artifacts (README/CHANGELOG/MIGRATIONS/deploy-runbook) are accurate and non-misleading
for an open-source release, correctly retiring the prior "not yet flagged" disclosure and honestly
documenting the REQUIRED re-bootstrap and its sharp edge. The only residual concern (a data-integrity
footgun in the reconcile PATCH) is an engineering/operational matter already defended in depth,
disclosed in docs, and covered by the MIT warranty/liability disclaimer for OSS users — ADVISORY,
not blocking. No legal, regulatory, IP, or contractual obstacle to shipping publicly.
