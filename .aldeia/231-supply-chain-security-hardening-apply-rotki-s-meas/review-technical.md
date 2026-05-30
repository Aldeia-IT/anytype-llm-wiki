# Technical / Completeness Review — Spec #231 (Supply-Chain Security Hardening)

**Reviewer:** CTO review council (technical accuracy + AC traceability)
**Date:** 2026-05-30
**Spec under review:** `.aldeia/231-supply-chain-security-hardening-apply-rotki-s-meas/spec.md`
**Verdict:** APPROVED WITH CONDITIONS

---

## Verification performed (evidence, not opinion)

| Claim checked | Method | Result |
|---|---|---|
| No Node/Rust ecosystem in repo | `ls package.json Cargo.toml pnpm-lock.yaml` | All absent — confirms pnpm/cargo N/A is honest |
| No `.github/` exists (greenfield CI) | `ls -la .github` | Absent — confirms "CI from scratch" framing |
| `uv.lock` present (lockfile gate is real) | `ls uv.lock` | Present (259 KB) |
| `src/anytype_llm_wiki` layout | `ls src/` | Matches `[tool.hatch.build.targets.wheel]` packages |
| 5 SHA pins carried verbatim from research → spec | `grep -c <sha>` on both files | All 5 SHAs present in both, identical strings |
| Wheel filename `anytype_llm_wiki-0.1.0` | `grep version pyproject.toml` | version=0.1.0; filename consistent |
| PyPI publishing is roadmap (not live) | `grep PyPI README.md` | `- [ ] npm / PyPI publishing` (unchecked) — deferral honest |
| `dev` is an *extra*, not a dependency-group | `grep dependency-groups pyproject.toml`; `grep dev uv.lock` | No `[dependency-groups]`; uv.lock shows `provides-extras = ["dev"]`, `marker = "extra == 'dev'"` |
| `uv sync --frozen --all-extras --dev` behavior | `uv sync ... --dry-run` (uv 0.10.8) | Runs without error (79 pkgs), but `--dev` is a no-op here |
| Tag-gate prose vs diagram vs workflow | `grep bandit/gitleaks/license` spec | Prose claims more than the workflow implements |

---

## AC Traceability Matrix (built independently)

| AC | Concrete deliverable in spec | Verification method in spec | Status |
|----|------------------------------|------------------------------|--------|
| AC1 — Lockfile-frozen installs in CI for every ecosystem | `ci.yml`: `uv lock --check` + `uv sync --frozen`; `release.yml`: `uv sync --frozen` | Open PR mutating `pyproject.toml` w/o `uv lock`; expect non-zero (§AC1 detail, §Test Plan) | COVERED. Single-ecosystem handled honestly (see Finding 5) |
| AC2 — All Actions pinned to full SHAs | Every `uses:` in ci/release/dependabot pinned `@<40hex> # vX.Y.Z` | `grep -r 'uses:' .github/workflows/ \| grep -v '@[0-9a-f]\{40\}'` → zero lines | COVERED. SHAs verified verbatim against research |
| AC3 — Release builds cache-free | `release.yml` `enable-cache: false` on both jobs | Inspect for `enable-cache: false`; confirm ci.yml has `true` | COVERED |
| AC4 — Build-provenance attestation (where applicable) | `release.yml` `attest-build-provenance subject-path: dist/*` | `gh attestation verify <wheel> --repo ...` exit 0 after test tag | COVERED; "where applicable" deferral honest (PyPI roadmap) |
| AC5 — OIDC Trusted Publishing (where applicable) | `uv publish` + `id-token: write` + `environment: pypi`; PyPI pending-publisher manual step documented | grep no `PYPI_TOKEN`; grep `id-token: write` + `environment: pypi` | COVERED; manual prerequisite called out honestly |
| AC6 — Dependency-intake checklist documented | `docs/dependency-intake.md` + CONTRIBUTING.md pointer | Both files exist; CONTRIBUTING references the doc | COVERED |

**All six ACs map to a concrete deliverable AND a verification method.** No AC is dodged. The "where applicable" framing on AC4/AC5 is handled honestly: the spec authors the publish/attest workflow now, tag-gated, and documents the one-time PyPI pending-publisher step that must precede the first real release — it does not pretend publishing is live, nor does it skip the AC.

---

## Findings

### BLOCKING

None. The spec is technically sound on every AC, SHAs are verified and carried verbatim, and the deferrals are honest.

---

### SHOULD-FIX

**SF-1 — `uv sync --frozen --all-extras --dev` is incorrect/redundant for this repo's `pyproject.toml`.**
*Section:* §1 (line 141), Mermaid diagram (line 118), `ci.yml` spec (line 441), `release.yml` spec (line 494), Open Question #2.
*Verified:* `pyproject.toml` defines `dev` under `[project.optional-dependencies]` (an **extra**). There is no `[dependency-groups]` table and no `[tool.uv] dev-dependencies`. `uv.lock` confirms: `provides-extras = ["dev"]` and `marker = "extra == 'dev'"`. The uv `--dev` flag targets the **dev dependency-group**, which does not exist here; the `dev` test dep is already pulled in by `--all-extras`. `uv sync --frozen --all-extras --dev --dry-run` ran without error (uv 0.10.8) only because `--dev` is the default/no-op — it is silently meaningless, not correct-by-design.
*Impact:* Misleading guidance baked into both workflow files and propagated to CONTRIBUTING. If a future maintainer migrates `dev` to a real `[dependency-groups]` table, the flag semantics flip and the existing intent becomes ambiguous. Low runtime risk today; documentation-correctness and forward-maintenance risk.
*Fix:* Use `uv sync --frozen --all-extras` (drop `--dev`) consistently in §1, the diagram, `ci.yml`, `release.yml`, and Open Question #2. If the project intends dev tooling to live in a uv dependency-group later, make that an explicit migration note rather than pre-emptively passing `--dev`.

**SF-2 — Tag-gate prose overpromises relative to the implemented workflow (internal inconsistency).**
*Section:* Design Principle prose (line 102) vs Mermaid diagram (lines 123-128) vs `release.yml` spec (lines 449-506).
*Verified:* Line 102 states the tag-gate runs "dependency vulnerability audit, **static security analysis, license check**, cache-free build, provenance attestation, OIDC publish." `grep` shows the only security/audit tool anywhere in the actual `release.yml` is `uvx pip-audit`. There is no bandit (static analysis), no pip-licenses (license check), no gitleaks. The Mermaid diagram and the workflow are mutually consistent (audit → build → attest → publish), but the prose at line 102 is not.
*Impact:* The spec claims controls it does not deliver. This is exactly the kind of "should work / expected to" hedge the council flags. Research §Q7 (lines 524-528) and prior council guidance (mem0 0ae961bc, cited in spec-scope) explicitly list bandit/gitleaks/pip-licenses as tag-gating steps — so the omission is a real scope decision, not an oversight, but the prose doesn't reflect the decision.
*Fix:* Either (a) bring the prose into line with the workflow — tag-gate = "dependency vulnerability audit (pip-audit), cache-free build, provenance attestation, OIDC publish" — and add an explicit note that bandit/gitleaks/pip-licenses are deferred (with rationale), or (b) add the three steps to `release.yml`. Given the spec is scoped to the rotki measures and these tools are flagged in research/council guidance, (a) with an explicit "deferred to a follow-up CI-hardening ticket" note is acceptable and keeps scope tight — but the inconsistency must be resolved, not left.

**SF-3 — `uv build` in `release.yml` does not require a prior `uv sync --frozen` install.**
*Section:* `release.yml` build-and-publish job (lines 493-497).
*Verified:* The job runs `uv sync --frozen --all-extras --dev` immediately before `uv build`. `uv build` builds the sdist/wheel in an isolated build environment using the `[build-system]` requires (`hatchling`); it does not need the project's runtime/dev deps installed into `.venv`. Installing all 79 packages before a build adds time and, more importantly, pulls dependency code into the release runner that the build itself does not use — slightly enlarging the release job's attack surface, which is contrary to the spec's own least-privilege/cache-free hardening intent.
*Impact:* Minor. Wasted CI time on the release path and a small, avoidable surface increase on the most security-sensitive job. Not wrong, just not minimal.
*Fix:* Drop the `uv sync` step from `build-and-publish`; `uv build` is sufficient. If a build-time check (e.g., version sanity) needs deps, scope it explicitly. Keep `uv sync --frozen` in the `ci.yml` test job where it is genuinely needed.

---

### SUGGESTION

**SG-1 — Resolve Open Questions before/at impl handoff; two are genuinely answerable now.**
*Section:* Open Questions 1-3.
- OQ#2 (`--all-extras` vs `--extra dev`) is effectively answered by SF-1: standardize on `uv sync --frozen --all-extras` in CI and `uv sync --all-extras` for local dev. This should be resolved in the spec, not left to the implementer.
- OQ#1 (runbook location) is a low-stakes editorial choice; fine to leave to the implementer, but state a default ("CONTRIBUTING.md unless it exceeds ~X lines") so the impl worker doesn't guess. CONTRIBUTING.md is currently short (54 lines) — recommend folding the one-time PyPI/Environment setup into it directly.
- OQ#3 (Dependabot uv bug) genuinely depends on live issue status — appropriate to leave open with the documented fallback.

**SG-2 — `uv export --no-dev` for the audit is correct, but note the audit scopes to runtime deps only.**
*Section:* `release.yml` audit job (line 472).
The audit uses `uv export --format requirements-txt --no-dev` → `pip-audit -r`. This audits production deps only (correct for a release gate — dev/test CVEs don't ship). Worth one sentence in the spec confirming this is intentional, so a reviewer doesn't read the `--no-dev` as an accidental gap.

**SG-3 — Mermaid `astral-sh/setup-uv` node (CACHE) is orphaned in the merge-gate subgraph.**
*Section:* Mermaid diagram lines 116-120, 133.
The `CACHE` node has no edges; only `LC --> INSTALL --> TEST` is drawn. Minor diagram polish — either connect `CACHE --> LC` or drop the node. Does not affect correctness.

**SG-4 — README provenance snippet uses a hardcoded `0.1.0` / `X.Y.Z` mix.**
*Section:* Implementation Plan step 7 (lines 727-730) vs §4 (line 246).
The README snippet uses `X.Y.Z` (good, generic) while §4 and Test Plan use the concrete `0.1.0`. Consistent enough; just confirm the consumer-facing README example stays version-generic.

---

## Dimension-by-dimension assessment

- **AC traceability:** Sound. All 6 ACs → deliverable + verification. "Where applicable" deferrals (AC4/AC5) handled honestly and not dodged.
- **Technical accuracy:** Strong. All 5 SHAs verified identical between research and spec; annotated-tag dereference for `pypa/gh-action-pypi-publish` correctly carried (`cef2210…`, not the tag-object SHA). uv command semantics largely correct — the one real defect is `--dev` (SF-1). Mermaid trust-flow and event-trigger diagrams are accurate; one orphaned node (SG-3).
- **Single-ecosystem handling:** Honest. pnpm and cargo are marked N/A with a verified justification (no `package.json`/`Cargo.toml`). AC1's "every package ecosystem" is satisfied by covering the only ecosystem that exists. No over- or under-claiming.
- **Completeness / event model:** Merge-gate (`push`+`pull_request` to `main`) vs tag-gate (`push: tags: v*`) is unambiguous and correctly wired in the workflow YAML. Open Questions are mostly genuine; OQ#2 should be resolved now (SG-1).
- **Scope discipline:** Mostly disciplined. SECURITY.md is correctly *referenced as deferred* (mem0 c942da7e) without being created — appropriate, not creep. The one slip is SF-2: the prose references "static security analysis, license check" that the deliverable doesn't implement.
- **Implementability:** Good. The Implementation Plan is ordered with explicit dependencies and parallelization notes; an impl worker can execute it. SF-1/SF-3 should be corrected so the worker doesn't bake the defects in.
- **Testability:** Strong. Concrete grep-based verifications for AC2/AC3/AC5, a `workflow_dispatch skip_publish` dry-run path for exercising build+attest without a live PyPI push, and `act` for local validation. The "test without real publish" problem is genuinely solved.

---

## Sign-off

**APPROVED WITH CONDITIONS.**

The spec is technically accurate, the verified SHAs are carried through verbatim, the single-ecosystem scoping is honest, and every acceptance criterion maps to a concrete deliverable and a verification method. No blocking technical inaccuracies.

Conditions for advancing to implementation:
1. **SF-1:** Replace `uv sync --frozen --all-extras --dev` with `uv sync --frozen --all-extras` everywhere (the `dev` group does not exist; `dev` is an extra). Resolve Open Question #2 accordingly.
2. **SF-2:** Reconcile the tag-gate prose (line 102) with the implemented `release.yml` — either drop the "static security analysis, license check" claim with an explicit deferral note, or add the steps. Do not ship the inconsistency.
3. **SF-3:** Remove the unnecessary `uv sync` before `uv build` in the release job (or justify it explicitly).

SF-1 and SF-2 are correctness/honesty issues and should be fixed in the spec before the impl worker starts; SF-3 is a minor hardening improvement that can be folded into implementation. Suggestions are optional polish.

Findings: 0 BLOCKING, 3 SHOULD-FIX, 4 SUGGESTION.
