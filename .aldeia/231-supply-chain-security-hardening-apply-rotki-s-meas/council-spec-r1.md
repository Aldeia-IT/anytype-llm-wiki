# Council Meeting — Post-spec (Round 1)

**Date:** 2026-05-30
**Ticket:** #231 — Supply-Chain Security Hardening (apply rotki's measures)
**Phase reviewed:** spec
**Client:** anytype-llm-wiki (open-source MCP server; Python/uv; public repo, MIT; owned by Aldeia IT)

## Attendance

| Role | Present | Reason |
|------|---------|--------|
| Council Chair | Yes | moderator / synthesis |
| Chief Security Officer | Yes | minimum — supply-chain threat model is the core of this spec |
| Chief Product Officer | Yes | minimum — scope discipline + deferral decisions |
| Chief Technology Officer | Yes | minimum — technical accuracy + reviewer-diligence check |
| Infrastructure Lead | Yes | CI/CD + deployment-risk work (chair decision; also in-phase reviewer R1/R2) |
| Legal Counsel | Yes | public PyPI publishing + dependency license-compatibility (chair decision) |
| QA Director | Yes | AC coverage/testability + next-phase routing guidance (chair decision) |
| Client Advocate | No | anytype-llm-wiki is Aldeia's own internal/OSS tool, not an external client engagement; CPO covers reputation/community value |

## Context Presented

The spec applies rotki's seven supply-chain hardening measures to a Python/uv-only repo
that currently has **no CI at all**. It is therefore greenfield CI bootstrap + hardening in
one. Deliverables: `ci.yml` (merge-gate: `uv lock --check` + frozen install + pytest on a
3.11/3.13 matrix, cache on), `release.yml` (tag-gate: `pip-audit` → tag-vs-pyproject version
guard → cache-free `uv build` → provenance attestation → OIDC `uv publish` behind a `pypi`
GitHub Environment, with a `workflow_dispatch`/`skip_publish` dry-run path), `audit.yml`
(weekly `pip-audit`), `dependabot.yml`, an exact `[build-system] requires` hatchling pin,
and docs (`dependency-intake.md`, `releasing.md`) plus CONTRIBUTING/README edits. The spec
went through two in-phase specialist review rounds (R1: 1 BLOCKING + 10 SHOULD-FIX + 4
SUGGESTION; R2: double-APPROVED with residual one-line items applied inline by the lead) and
entered council as APPROVED with zero open findings. PyPI publishing is roadmap, not yet
live; the publish workflow is authored now but inert until a `v*` tag + manual one-time
PyPI/Environment setup.

## Discussion

The council converged quickly. No member raised a blocking concern, and the cross-cutting
themes were operational/rollout discipline rather than design defects:

- **Fail-open `pypi` Environment** (CSO, Infra, QA all independently): the single
  highest-consequence control is fail-open by default — if the Environment is auto-created
  without protections, any `v*` tag publishes unreviewed. All three agreed the spec's
  elevation of this to a hard, `gh api`-verifiable AC5 prerequisite is the *right* mitigation,
  and all three recommended hardening the verification from an eyeball check into a scriptable
  `gh api ... --jq` assertion that exits non-zero (and ideally a CI assertion in `release.yml`).
- **Greenfield merge-gate rollout risk** (Infra + QA, the most important shared finding):
  introducing CI to a repo with none means the very next PR is gated on `uv lock --check` +
  3.11/3.13 matrix pytest. If the committed `uv.lock` is drifted or the suite isn't green on
  both interpreters, `main` goes red immediately. The spec/phase-summary does not confirm the
  current suite passes on both 3.11 and 3.13. Both flagged this as the top impl-acceptance gate.
- **Reviewer diligence** (CTO): confirmed R2 was a genuine verification pass (fixes located in
  the spec body, SHA pins verbatim from research, `uv version --short`/`uv export` executed
  live), not a rubber-stamp. The lead's inline-fix of two documentation-grade residual
  SHOULD-FIX items (instead of a third review round) was judged defensible and transparent.
- **Scope** (CPO): the "apply rotki's measures" ticket is in reality "stand up the project's
  CI/CD foundation + hardening." This is a justified precondition (you cannot apply the
  measures to CI that doesn't exist), not scope creep — but the deliverable is larger than the
  title implies, and the deferred OSS-hygiene scanners (bandit/pip-licenses/gitleaks) +
  SECURITY.md must be tracked as real follow-up tickets so "deferred" doesn't become "dropped."
- **Legal** (Counsel): proportionate review found no material legal issues — see Findings.
- **Test-phase routing** (QA): with no application logic and deliverables that are YAML/config/
  docs, a conventional test-writing phase has little to bite on; QA recommended scoping any
  test phase to durable static-assertion checks (actionlint + SHA-pin grep + YAML-invariant
  assertions), or folding that verification into impl. This echoes the spec lead's own
  recommendation to route toward implementation.

## Findings

### BLOCKING
None.

### ADVISORY
1. **[CSO/Infra/QA] Make the AC5 fail-open Environment check a scriptable hard gate.** Convert
   the `gh api repos/.../environments/pypi` verification into a `--jq` one-liner that exits
   non-zero unless `required_reviewers` is non-empty AND a `v*` deployment tag rule exists.
   Consider a self-enforcing assertion step in `release.yml` and capturing the output as a
   release-gate artifact. (Mitigation already partially present; this hardens it.)
2. **[Infra/QA] Greenfield merge-gate rollout must be sequenced.** Before/as `ci.yml` lands,
   confirm `uv lock --check` passes and `pytest` is green on **both** Python 3.11 and 3.13,
   so introducing CI does not immediately red-line `main`. This is the top impl-acceptance item.
3. **[CTO] Re-resolve the three *used* action SHAs + the hatchling pin at implementation time.**
   `actions/checkout`, `astral-sh/setup-uv`, `actions/attest-build-provenance`, and
   `hatchling==` (spec's `1.27.0` is illustrative; current latest is newer) must be
   re-resolved and `uv lock` re-run at author time. Do NOT add the two unused pins
   (`pypa/gh-action-pypi-publish`, `actions/setup-python`) — their omission is deliberate.
4. **[CPO] File follow-up ticket(s) for the deferred work** — the bandit/pip-licenses/gitleaks
   OSS-hygiene scanner suite and the SECURITY.md-at-first-public-tag item — before this ticket
   closes, so the deferral is tracked rather than lost.
5. **[CPO] Retitle the PR/ticket** to reflect "establish CI + supply-chain hardening" so future
   audit/roadmap reviews don't mistake this for a small security tweak. (Hygiene.)
6. **[QA] Scope the test phase to durable static assertions, or fold into impl.** If a test
   phase runs, scope it to `actionlint` + SHA-pin coverage grep + a `tests/`-level YAML-invariant
   check (cache flags, 3.11/3.13 matrix present, `id-token: write` + `environment: pypi`
   present, no `PYPI_TOKEN`, `dependency-intake.md` contains its 7 sections). Do not manufacture
   unit tests for OIDC/provenance/publish, which can only be exercised by real side effects;
   those stay runbook/dry-run verified.
7. **[CSO/CPO] Accepted residual risks — noted, no action.** Tag-gated (not merge-gated)
   pip-audit with a ≤7-day weekly-audit window; `--no-dev` release audit with full-tree only
   weekly; unfrozen hatchling transitive build deps; 7-day cooldown as human convention. All
   explicitly named, bounded, and paired with compensating controls in the spec; reasonable to
   ACCEPT at this project's stage/cadence. Renovate `minimumReleaseAge` is the documented path
   to convert the cooldown convention into an enforced control later.

## Resolutions

No member withdrew a finding; there were no contradictions to resolve. The CTO explicitly
cleared the reviewer-diligence question (R2 was genuine verification, inline-fix defensible).
The CSO and Infra Lead aligned that the fail-open Environment is acceptable *because* its
closure is made auditable, not assumed. All advisories are non-blocking and actionable in the
next phase(s).

## Recommendation

**Recommended target:** `test`
**Confidence:** high (advance); the test-vs-impl routing nuance is flagged for the
decision-maker.
**Rationale:** The spec is APPROVED unanimously with zero blocking findings and is unusually
implementation-ready (it ships exact, SHA-pinned YAML). Per canonical phase order the next gate
is `test`; the council recommends advancing rather than skipping a gate. However, the council
(QA Director leading, echoed by the spec lead) records that a *conventional* test-writing phase
has little to act on here — the deliverables are YAML/config/docs with no application logic.
The council endorses **either** (a) a lightweight test phase scoped to durable static-assertion
checks (advisory 6), **or** (b) routing directly to impl with that static-assertion + green-suite
verification folded into impl acceptance — at the decision-maker's discretion. The
impl-acceptance requirements in advisories 1–6 are captured in the spec addendum
(`spec-addendum-post-spec-r1.md`) so they are honored regardless of which route is taken.
**Dissent:** None.
