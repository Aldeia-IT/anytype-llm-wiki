# Council Meeting — Post-impl (Round 2)

**Date:** 2026-05-31
**Ticket:** #234 — v0.2.0 tag-prep checklist (anytype-llm-wiki, first public OSS release)
**Phase reviewed:** impl (rework pass following council-impl-r1)
**Client:** anytype-llm-wiki (Aldeia-IT)

## Attendance

| Role | Present | Reason |
|------|---------|--------|
| Council Chair | Yes | moderator |
| Chief Security Officer | Yes | minimum; license/supply-chain gate, NOTICE, SECURITY.md, egress claim |
| Legal Counsel | Yes | minimum; docutils waiver, NOTICE reconciliation, positioning, copyright entity |
| Chief Product Officer | Yes | minimum; README/CONTRIBUTING/MIGRATIONS, differentiation note |
| QA Director | Yes | minimum; re-ran the check battery + mutation-tested the new guard test |
| Chief Technology Officer | Yes | minimum; publish-guard test, release.yml job split, dependency bounds |
| Infrastructure Lead | Yes | chair decision — launchd plist, log rotation, release pipeline split |
| Client Advocate | Yes | chair decision — first public OSS release; verifying Jan's "address ALL" instruction was honored |

Full council re-seated: this is the final delivery gate for the company's first public open-source release, and Jan issued an explicit rework instruction that the council must confirm was satisfied.

## Context Presented

Council R1 found the collateral PR **unanimously merge-safe** but flagged cheap, pipeline-doable tag-blockers (a failing/vacuous license gate, a broken-by-default launchd plist, a stale CONTRIBUTING tree, bare MIGRATIONS commands) plus advisories. Jan routed the ticket back to impl: *"Re-work for Implement phase. See council findings and address ALL recommendations before opening a PR."*

The impl-worker executed a rework pass (5 commits, `8436b75..HEAD`, docs/CI/config only — **zero `src/` changes**) closing every pipeline-doable R1 item. The branch is **21 commits ahead / 0 behind `origin/main`** — a clean fast-forward PR.

The decision before this council is narrow: **did the rework honor Jan's instruction — are all pipeline-doable R1 recommendations genuinely closed, with no regression — and is the branch now ready to advance to PR/merge?** Cutting the public `v0.2.0` tag remains a separate, maintainer-gated, Jan-owned act.

## Discussion

Strong cross-functional convergence — **all seven members independently verified their R1 findings against the actual files (not the audit self-report) and signed off.** QA and CA re-ran the highest-risk gates themselves.

- **License/supply-chain gate (B1) — RESOLVED (CSO, Legal, QA, CA all re-ran it).** Both `release.yml:73` and `audit.yml:64` now use project-scoped `uv run` (85 pkgs) with an auditable `--ignore-packages docutils` waiver (code comment + COPYING cross-ref); `--fail-on="GPL;AGPL;SSPL;EUPL"` tokens un-broadened. Independently reproduced: **exit 0 with waiver, exit 1 without (docutils the sole hit)** — the gate is now both *effective* and *passing*. CSO and Legal independently audited the full 85-package tree and confirmed **no AGPL/SSPL/EUPL anywhere** — decisive for a network-served MCP. The rework also fixed a lead-discovered latent defect R1 missed: the prior `uvx` form scanned only ~3 packages (a vacuous no-op).
- **launchd plist (B2) — RESOLVED (Infra).** `ProgramArguments` repointed from the phantom `uv tool install` path to absolute-`uv` + `run --directory <repo>`, matching the README cron form; plist header + README launchd block consistent. Silent-failure-every-30-min defect closed.
- **Publish-guard test (A1) — RESOLVED (CTO, QA mutation-tested).** `tests/test_ci_config.py:254 TestPublishGuard` asserts both `vars.PYPI_PUBLISH_ENABLED == 'true'` and `inputs.skip_publish != true`. QA confirmed by mutation that deleting either token makes the test FAIL — genuinely non-vacuous.
- **Publish job split (A6) — RESOLVED (CTO, Infra).** `audit → build → publish`; `environment: pypi` now gates ONLY `publish` (`release.yml:150`), so unattended git-tag-only builds never pause once required-reviewer protection is added. Artifact handoff SHA-pinned (`upload-artifact@…` v4.6.2, `download-artifact@…` v4.3.0, both verified against upstream tags), `if-no-files-found: error`, permissions minimal-correct per job, guard expression preserved verbatim.
- **CONTRIBUTING tree (A2), MIGRATIONS prefix (A3), NOTICE inventory (A4), log rotation (A7), anyproto differentiation (A8) — all RESOLVED (CPO, Infra, Legal, CSO).** Public collateral verified to still "shine" — working first-copy-paste, coherent roadmap, no internal `aldeia-box#`/branch leaks, honest non-superlative differentiation.
- **QA battery (re-run):** 256 passed / 22 skipped / 3 xfailed (+1 = the new guard test); `uv lock --check` exit 0; **zero `src/` files** in the diff → regression risk LOW.

**Two NEW pipeline-doable advisories surfaced — neither blocks the merge, but both are cheap and directly within this ticket's tag-prep mandate:**

- **[CTO-ADV] `docs/releasing.md` is now stale on the exact point the A6 split changed.** `docs/releasing.md:31,38-40,198` still describe a single `build-and-publish` job carrying `environment: pypi` that "pauses the publish job." The reworked `release.yml` has no environment on `build` and a separate gated `publish` job. The operator runbook a maintainer reads **at tag-cut** now actively misdescribes which job is reviewer-gated. This is doc-drift introduced/exposed by the rework itself — same class as the doc fixes this pass already closed.
- **[Legal-ADV] `caio 0.9.25` shows `License: UNKNOWN`** in the NOTICE inventory (`NOTICE:96`). Independently verified Apache-2.0 (PyPI/Repology) — a pip-licenses metadata-read artifact, not an unlicensed dep; the `--fail-on` gate does not trip on `UNKNOWN`. Cosmetic, but shipping an `UNKNOWN` line in a public attribution file invites an adopter's auditor to raise a question we already know the answer to. One-line note resolves it.

The Client Advocate's sign-off was explicitly **conditional on the PR body carrying the Jan-owned tag-cut punch-list**, with **A5 (the public LICENSE copyright-entity name) called out as the one pre-tag legal decision Jan should not skip** ("Aldeia IT" on LICENSE/NOTICE vs registered "Aldeia IT Consulting" vs the individual author).

## Findings

### BLOCKING (for the public `v0.2.0` tag — none block the PR merge)

Unchanged from R1; all remain maintainer/live-env owned and correctly carried forward (verified NOT silently dropped):
1. **[CSO; +CA, +QA, +Legal] SECURITY.md reporting channels not yet operable** — enable GitHub private vulnerability reporting + publish an org-profile contact email before tag.
2. **[Legal, +CSO] "No telemetry / data stays local" claim** (`README.md:36,42-49`) — requires live egress verification before the public claim ships. Prose is well-hedged; the headline still needs the live check.
3. **[Infra, QA, CSO] Remaining maintainer-only live-env gates** — `verify-anytype-writes.sh` + `patch-decision.md`; `doctor` strict exit-0; p95<30s bootstrap on the Mac Mini M4; `wiki-bootstrap --space-id <real>` demo; validate the guessed `wiki_client.py` REST endpoints against the live API; cross-host bootstrap dedup probe.

### ADVISORY

1. **[CTO — NEW] `docs/releasing.md` release runbook describes the pre-A6 combined `build-and-publish`/`environment: pypi` job** (`docs/releasing.md:31,38-40,157,198`) — reconcile to `audit → build → publish` with `environment: pypi` on `publish` only. Pipeline-doable; the operator reads this at tag-cut.
2. **[Legal — NEW] `caio 0.9.25` `License: UNKNOWN` in NOTICE** (`NOTICE:96`) — add a one-line note that caio is Apache-2.0 (field unread by pip-licenses), or override it. Cosmetic; gate stays green.
3. **[Legal, +CA — carry-forward] Copyright-holder entity name (A5)** — Jan's legal call; top of the tag-cut punch-list, not to be guessed.
4. **[CTO, +QA — minor] `TestPublishGuard` is a whole-file substring assertion**, not scoped to the publish step's `if:`. Holds today (sole occurrence); consistent with the file's static-assertion convention. No action required.

## Resolutions

- **All four R1 pipeline-doable BLOCKING/ADVISORY tag-blockers (B1, B2, A2, A3) and the closable advisories (A1, A4, A6, A7, A8, A9) are independently confirmed RESOLVED** by multiple members reading the actual files; several re-ran the objective gates. No prior finding reopened; no regression introduced (zero `src/` changes, full battery green).
- **Merge safety is not in dispute** — unanimous SIGN OFF on advancing the collateral toward PR/merge.
- The five remaining open items (R1 BLOCKING 1–3, A5) are confirmed **legitimately Jan/maintainer-owned** (repo settings, live env, legal-entity decision) — none is work the pipeline dodged.
- **Two new pipeline-doable advisories** (CTO docs/releasing.md drift; Legal caio NOTICE note) emerged and are the basis for the chair's routing.

## Recommendation

**Recommended target:** `impl` (one final short rework pass on this branch to close the two new pipeline-doable advisories, then open the PR)
**Confidence:** high on findings (unanimous, independently re-verified); medium on routing
**Rationale:** Every member signed off that the collateral is **safe to merge** and that all R1 pipeline-doable recommendations are genuinely closed. The chair concurs the merge is low-risk. **However, Jan's explicit instruction was "address ALL recommendations before opening a PR,"** and this round surfaced two new pipeline-doable recommendations — one of them (`docs/releasing.md` drift) is a *direct consequence of this rework* that leaves the release runbook actively contradicting the release workflow on the exact axis this tag-prep ticket exists to get right. Closing both is one inexpensive pass and yields a genuinely tag-prep-complete branch with no internal contradictions; merging now instead ships a self-contradicting operator runbook and an `UNKNOWN`-license line in a public NOTICE, then fragments the same two fixes into a follow-up after the branch is gone. This mirrors the R1 reasoning that resolved the first batch of cheap tag-blockers on-branch. The PR, when opened, must carry the Jan-owned tag-cut punch-list (R1 BLOCKING 1–3 + A5), with **A5 (public LICENSE entity name)** flagged as the pre-tag legal decision Jan should not skip.

**Alternative (valid):** if Jan prefers velocity, advance to `done` / open the PR now and track the two new advisories on the tag-cut punch-list — the council unanimously deems the merge itself safe. The chair recommends the short rework only because both items are pipeline-doable on the live branch, one is a release-runbook correctness defect, and Jan's standing instruction is to close all recommendations before the PR.

**Dissent:** None on merge-safety or on the resolution of all R1 items (unanimous). The advance-vs-rework routing is a chair synthesis judgment, not a member disagreement.
