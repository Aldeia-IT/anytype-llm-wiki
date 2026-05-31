# Council Meeting — Post-impl (Round 1)

**Date:** 2026-05-31
**Ticket:** #234 — v0.2.0 tag-prep checklist (anytype-llm-wiki, first public OSS release)
**Phase reviewed:** impl (verification + handoff phase)
**Client:** anytype-llm-wiki (Aldeia-IT)

## Attendance

| Role | Present | Reason |
|------|---------|--------|
| Council Chair | Yes | moderator |
| Chief Security Officer | Yes | minimum; SECURITY.md / supply-chain / data-posture owner |
| Legal Counsel | Yes | minimum; licensing, positioning, copyleft-scan owner |
| Chief Product Officer | Yes | minimum; README "shine", positioning, release readiness |
| QA Director | Yes | minimum; ran the local check battery to verify claims |
| Chief Technology Officer | Yes | minimum; publish-guard, dependency bounds, reviewer diligence |
| Infrastructure Lead | Yes | chair decision — release pipeline + ops surface (release.yml, launchd, log rotation) |
| Client Advocate | Yes | chair decision — first public OSS release; Jan's reputational stake + adopter first-impression |

Full council seated: this is the final delivery gate for the company's first public open-source release.

## Context Presented

#234's impl phase was a **verification + handoff** pass, not greenfield code. The substantive code (#140 v0.2.0 wiki modules, #231 CI/supply-chain hardening) is already merged to `origin/main` and was reviewed in its own pipelines. This phase: assembled the public README, fixed the SECURITY.md CRA date, added the `PYPI_PUBLISH_ENABLED` publish guard, bumped to 0.2.0 with dependency upper bounds, closed two doc nits, ran the local check battery, and produced a pre-tag handoff with seven maintainer-only gates.

The prior **product council (R1) vetoed cutting the public `v0.2.0` tag** pending live-environment verification, and routed to Decide. Jan + the lead then did an interactive cleanup pass that resolved the three product-council BLOCKING items. **The decision before this council is therefore narrow: may the collateral PR merge to `main`?** "Advancing" = merging; cutting the public tag remains a separate, maintainer-gated, Jan-owned act.

The branch is **15 commits ahead / 0 behind `origin/main`** — a clean, fast-forwardable PR, no rebase needed (the large local `main...HEAD` diffstat was vs a stale local `main` ref; against `origin/main` the PR is just #234's collateral).

## Discussion

Strong cross-functional convergence. All three product-council BLOCKING items were independently re-verified as **resolved** by multiple members:

- **CRA date (CSO's prior BLOCKING):** `SECURITY.md:79` now reads "11 September 2026"; voluntary-alignment hedging intact, no "CRA compliant" claim. CSO confirmed.
- **"First" superlative (Legal's prior BLOCKING):** gone from README/CHANGELOG in the market-primacy sense (`README.md:3`, `CHANGELOG.md:18`); surviving "first" usages are benign/temporal. Positioning now defensible against the `positioning-verification.md` prior-art record (`wethegreenpeople/anytype-mcp`), which the README comparison table now lists openly. Legal, CPO, CA concurred.
- **Stale README (CPO's prior BLOCKING):** README is now the real v0.2.0 doc — source-install only (`uv sync`, no PyPI), working `doctor → wiki-bootstrap → run server` quick-start, accurate 3-tool MCP table, coherent v0.2.0/v0.3.0 roadmap, no internal `aldeia-box#`/branch leaks (grep-verified by three members). CPO and CA judge it "shines" for launch.

**QA independently RAN the battery** (not just read the self-report): `uv run pytest -q` → **255 passed / 22 skipped / 3 xfailed** (matches claim exactly); `uv lock --locked` → exit 0; `uvx bandit==1.9.4 -r src/` → "No issues identified" (1667 LOC). Regression risk LOW — the #234 diff touches **zero `src/` files**.

**CTO verified the new technical work** against the code: the publish guard `if: ${{ inputs.skip_publish != true && vars.PYPI_PUBLISH_ENABLED == 'true' }}` (`release.yml:123`) correctly makes git-tag-only safe (a `v*` tag runs audit/build/attest green, publishes nothing when the var is unset; no edge publishes unintentionally). Dependency upper bounds all sit above locked versions (fastmcp 3.2.0<4, httpx 0.28.1<1, qdrant 1.17.1<2, psutil 7.2.2<8) — no silent downgrade. Dev-doc claims (source-install MCP command, "FastMCP v3") accurate. Two doc nits genuinely fixed in 387e80e.

**The substantive new findings are all tag-gated, not merge-gating — but several are concrete, cheap, and pipeline-doable, and two contradict the phase summary's "tag battery clean" claim:**

- **Legal RAN the actual pip-licenses tag-gate and it FAILS** (exit 1): `docutils:0.22.4` carries a GPL Trove classifier and trips `--fail-on="GPL"`. Legal verified there is **no real copyleft contamination** — the only GPL file in docutils is an unused Emacs editor config (`rst.el`); the package is public-domain + BSD; **AGPL-clean** (critical for a network-served MCP). But a `v*` tag push would turn the **first public release's CI red**. The impl summary confirmed the gate's *presence* but never *executed* it against the resolved tree — "the gate exists" ≠ "the gate passes."
- **Infra found the shipped auto-reindex launchd plist is broken-by-default:** `com.aldeia.anytype-llm-wiki-reindex.plist:21` hardcodes a `uv tool install` interpreter path (`~/.local/share/uv/tools/...`) that does not exist under the documented `uv sync` source install. The dogfood's headline continuous-indexing feature fails silently every 30 min for anyone following the README. Cheap fix (use `uv run --directory` / project `.venv`).
- **CTO:** the `PYPI_PUBLISH_ENABLED` guard — the single new control protecting against accidental publish — has **zero test coverage** in the 482-line `test_ci_config.py`; a future edit could weaken it undetected.
- **CPO + CA:** `CONTRIBUTING.md:22-30` project-structure tree is stale — omits the entire `wiki/` subpackage (bootstrap, doctor, cli, ...) that implements the two headline v0.2.0 features. Public-facing file.
- **CPO (new):** `MIGRATIONS.md:26,40,54` use bare `anytype-llm-wiki ...` commands that aren't on PATH under source install; README correctly prefixes `uv run`. Same first-copy-paste-fails class, migrated to a secondary doc.
- **CSO + CA + QA + Legal:** SECURITY.md commits to a 72h-ack SLA via a GitHub private-vuln-reporting channel and an org-profile email that **are not yet operable** (no public email on the Aldeia-IT org profile; private reporting toggle unverified). Maintainer/repo-settings gate.

Members agreed unanimously that **none of these block the merge** — the merged collateral is honest and the architecture sound. They are pre-tag items. The chair's synthesis (below) weighs whether the cheap, pipeline-doable subset should be closed on this branch before the ticket — whose entire purpose is *tag-prep* — is called done.

## Findings

### BLOCKING (for the public `v0.2.0` tag — none block the PR merge)

1. **[Legal] pip-licenses tag-gate fails on `docutils` GPL classifier** — `release.yml:60` / `audit.yml:51` `--fail-on="GPL;AGPL;SSPL;EUPL"` exits 1 on `docutils:0.22.4`. No actual copyleft (only the unused `rst.el` Emacs config is GPL; AGPL-clean). A `v*` tag would make the first public release's CI red. **Action (pipeline-doable):** add a code-commented, auditable per-package waiver (`--ignore-packages docutils`) citing the rst.el-only rationale + COPYING URL. Do not broaden the fail-on tokens.
2. **[Infra] auto-reindex launchd plist interpreter path is wrong for the documented install** — `com.aldeia.anytype-llm-wiki-reindex.plist:21` points at a `uv tool install` path absent under `uv sync`; continuous indexing fails silently. **Action (pipeline-doable):** repoint to `uv run --directory <repo>` / project `.venv/bin/python3`.
3. **[CSO; +CA, +QA, +Legal] SECURITY.md reporting channels not yet operable** — committed 72h-ack SLA routes to a GitHub private-vuln-reporting path (toggle unverified) and an org-profile email that is currently absent. **Action (maintainer/repo-settings):** enable at least one live channel before tag.
4. **[Legal, +CSO] "No telemetry / data stays local" claim requires live egress verification** before the public claim ships (`README.md:36,40-55`). **Action (maintainer/live-env).**
5. **[Infra, QA, CSO] Remaining maintainer-only live gates** — `verify-anytype-writes.sh` run + `patch-decision.md`; `doctor` strict exit-0; p95<30s bootstrap on the Mac Mini M4; `wiki-bootstrap --space-id <real>` demo; validate the *guessed* `wiki_client.py` REST endpoints (`/properties`, `/properties/{key}/options`) against the live API. **Action (maintainer/live-env).**

### ADVISORY

1. **[CTO] Publish guard has no regression test** — add a `test_ci_config.py` assertion that the publish step's `if:` contains both `vars.PYPI_PUBLISH_ENABLED == 'true'` and `inputs.skip_publish != true`. Pipeline-doable; recommended before tag.
2. **[CPO; +CA] CONTRIBUTING.md project-structure tree stale** (`CONTRIBUTING.md:22-30`) — omits the `wiki/` subpackage. Public file; pipeline-doable. (Prior addendum #11.)
3. **[CPO] MIGRATIONS.md bare-command prefix** (`MIGRATIONS.md:26,40,54`) — prefix with `uv run` or add a note. Pipeline-doable.
4. **[Legal, CSO] NOTICE transitive-license reconciliation** — `NOTICE:16-19` lists 4 direct deps of an 82-package tree but self-discloses the scope (`NOTICE:57-59`); adequate to merge. Regenerate a fuller license summary before tag; confirm MPL-2.0 `certifi` (file-level copyleft, MIT-compatible, no action).
5. **[Legal; +CA, +QA] Copyright-holder entity name** — LICENSE/NOTICE say "Aldeia IT" (internally consistent); `business.md` registers "Aldeia IT Consulting"; pyproject author is the individual. **Jan's legal call** — not guessed. Reconcile once before tag.
6. **[Infra] `environment: pypi` on the shared build job** (`release.yml:74`) — benign now, but once the maintainer adds required-reviewer protection (per `docs/releasing.md`), every git-only tag build will pause for approval. Split `uv publish` into its own job before that setup. CTO concurs.
7. **[Infra] reindex.log has no rotation rule** — launchd reindex writes `~/Library/Logs/.../reindex.log` every 30 min with no newsyslog/logrotate coverage; unbounded slow growth. Add a fragment line.
8. **[CPO] Official `anyproto/anytype-mcp` differentiation unused** — "we add semantic search the official MCP lacks" is a sharp, true value prop missing from the comparison table. Marketing upside.
9. **[CTO] No persisted impl-audit artifact** — the "four-lens tag-gate audit" cited in the phase summary left no committed review file (narrative-only). Conclusions independently re-verified correct; flagged so future verification phases persist their audit.

## Resolutions

- All three product-council R1 BLOCKING items (CRA date, "first" superlative, stale README) **independently confirmed resolved** by multiple members. No prior finding reopened.
- Merge safety is **not in dispute** — unanimous SIGN OFF WITH ADVISORIES on merging the collateral PR. The merged collateral is honest, regression-safe (zero `src/` changes), and battery-verified.
- The phase summary's "tag battery clean" framing is recorded as **overstated**: the pip-licenses gate was never executed (it fails on docutils) and a shipped sample (the reindex plist) is broken-by-default. No conclusion was wrong, but the evidence base for the "clean" claim was incomplete.

## Recommendation

**Recommended target:** `impl` (rework — one short pass on this branch to close the cheap, pipeline-doable tag-blockers, then merge)
**Confidence:** high on findings; medium on routing
**Rationale:** Every member signed off that the collateral PR is **safe to merge** and that the new findings are tag-gated, not merge-gating. The chair concurs the merge is low-risk. **However, this ticket's entire purpose is tag-prep**, and the council surfaced four cheap, unambiguous, pipeline-doable defects that block the tag and that the impl phase missed or overclaimed: the failing pip-licenses gate (docutils waiver), the broken-by-default auto-reindex plist, the stale CONTRIBUTING tree, and the bare MIGRATIONS commands — plus the trivial publish-guard test (ADVISORY-1). Closing these on the existing branch is one inexpensive impl pass and yields a genuinely tag-ready branch; merging now instead fragments the same fixes into a fresh follow-up ticket after the branch is gone, and hands Jan a "done" ticket whose shipped collateral still contains a red CI gate and a silently-broken launchd job. The remaining gates (#3 channels, #4 egress, #5 live-env, ADVISORY-5 entity name) are genuinely Jan/maintainer-owned and carry forward to the tag-cut regardless of routing.

**Alternative (valid):** if Jan prefers velocity, merge the PR now (target `done`) and track the cheap fixes + maintainer gates as a tag-cut punch-list — the council unanimously deems the merge itself safe. The chair recommends rework only because the cheap fixes are pipeline-doable on the live branch and directly complete the ticket's stated mandate.

**Dissent:** None on merge-safety (unanimous). The advance-vs-rework routing is a chair synthesis judgment, not a member disagreement.
