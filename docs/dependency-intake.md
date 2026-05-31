# Dependency Intake Checklist

Every new third-party dependency (runtime, dev, or build-time) added to
`anytype-llm-wiki` must clear this checklist **before** it is merged into `main`.
The goal is supply-chain hygiene: each dependency is an entry into our trust
boundary, and a compromised or abandoned package is a direct path into the
release artifact and into our users' machines.

Work through the seven sections below in order. Record the outcome in the PR that
introduces the dependency (see section 7). A dependency that cannot pass a section
should be rejected, vendored, or reimplemented — not waved through.

---

## 1. Necessity (make-vs-buy / vendoring)

Before adding anything, justify the dependency itself.

- [ ] **Do we actually need it?** State the concrete problem the dependency solves.
      Is it on a hot path, or a one-off convenience that a few lines of our own
      code would cover?
- [ ] **Make vs. buy.** Estimate the cost of implementing the needed slice
      ourselves versus the ongoing cost of carrying the dependency (updates, CVEs,
      transitive surface). A small utility (left-pad-sized) is almost always
      cheaper to write than to depend on.
- [ ] **Scope of use.** Are we using a large library for a tiny fraction of its
      surface? If so, prefer a smaller focused package or a vendored snippet.
- [ ] **Vendoring option.** For small, stable, permissively-licensed code,
      consider vendoring (copying the source into the repo with attribution)
      instead of taking a runtime dependency. Vendoring removes the live
      update/CVE channel at the cost of manual maintenance — appropriate for
      small, rarely-changing code.

**Reject if:** the dependency is trivially replaceable, pulls in a large
transitive tree for marginal benefit, or duplicates something already in our
dependency set.

## 2. Maintainer health

Assess whether the project is alive and trustworthy.

- [ ] **Activity.** Recent commits, releases, and issue/PR responses. A package
      with no activity for a year carries higher abandonment and unpatched-CVE
      risk.
- [ ] **Reputation & ownership.** Who maintains it? Is it an individual, a
      foundation (PyPA, CNCF), or a company? Sudden ownership/maintainer changes
      are a known supply-chain attack vector — check for recent transfers.
- [ ] **Bus factor / succession.** More than one active maintainer is healthier
      than a single-person project. Note the risk explicitly if it is a solo
      project.
- [ ] **Community signals.** Stars/downloads are weak signals but useful in
      aggregate; an unusually high download count on a brand-new package is a
      typosquatting/confusion red flag.

**Reject if:** the project is abandoned, has an opaque or recently-transferred
owner, or shows signs of typosquatting the name of a popular package.

## 3. Release history (advisories & suspicious releases)

Inspect the package's track record on PyPI.

- [ ] **Advisory history.** Check the GitHub Advisory Database / OSV / PyPI for
      past CVEs and how quickly they were patched. A pattern of slow fixes is a
      negative signal.
- [ ] **Release cadence.** Steady, documented releases are good. A long-dormant
      package that suddenly publishes a new release — especially with new
      maintainers or new install-time scripts — warrants extra scrutiny.
- [ ] **Suspicious release content.** Look for newly-added `setup.py`/build
      scripts, post-install hooks, network calls, or obfuscated code introduced
      in a recent version. These are classic injection points.
- [ ] **Yanked versions.** Note any recently-yanked releases and why.

**Reject if:** the latest release shows install-time code execution, obfuscation,
or unexplained behavioral changes.

## 4. Transitive impact

Understand the full subtree the dependency drags in, not just the top-level name.

- [ ] **Dry-run the resolution.** Inspect the resolved tree without committing:
      ```bash
      uv add --dry-run <package>
      ```
      Review every NEW transitive package the resolver wants to pull in.
- [ ] **CVE scan the new tree.** After the dry run (or on a throwaway branch),
      run the audit over the resulting lockfile:
      ```bash
      uv export --format requirements-txt --all-extras > /tmp/req.txt
      uvx pip-audit -r /tmp/req.txt
      ```
- [ ] **Surface growth.** How many new transitive packages does it add? Each one
      is its own intake risk. A package that adds dozens of transitive deps for a
      single feature should be questioned.
- [ ] **Duplication / conflicts.** Does it pin versions that conflict with or
      duplicate existing dependencies?

**Reject if:** it introduces a transitive package with an open CVE, or balloons
the dependency tree disproportionately to its value.

## 5. License compatibility

The project is **MIT**-licensed. Every dependency's license must be compatible.

- [ ] **Identify the license** of the new package AND its new transitive deps
      (the `pip-licenses` step in the tag/audit workflows enforces this in CI).
- [ ] **MIT-compatible licenses** (permissive — acceptable): MIT, BSD-2/3-Clause,
      Apache-2.0, ISC, PSF, MPL-2.0 (file-level copyleft, generally acceptable for
      a library dependency).
- [ ] **Incompatible / blocked** (strong copyleft — **rejected by CI**): **GPL,
      AGPL, SSPL, EUPL**. These impose obligations incompatible with shipping an
      MIT-licensed package. The `pip-licenses --fail-on="GPL;AGPL;SSPL;EUPL"` gate
      will fail the build if one appears.
- [ ] **Unknown / missing license metadata.** Treat as a blocker until clarified —
      do not assume permissive. Note this is a **manual** blocker: the CI
      `pip-licenses --fail-on` gate only catches the named copyleft tokens, so an
      `UNKNOWN`/missing-license dependency passes CI and must be caught here by review.

**Reject if:** the dependency or any new transitive dep is GPL/AGPL/SSPL/EUPL, or
has unresolved/unknown license metadata.

## 6. Cooldown (7-day rule)

Fresh releases are the highest-risk window for supply-chain attacks (a
compromised maintainer account typically publishes a malicious release that is
caught and yanked within days).

- [ ] **Check the release date** of the exact version you intend to pin.
- [ ] **Defer if released less than 7 days ago.** Wait until the release is at
      least 7 days old before adopting it, giving the community time to detect and
      yank a malicious or broken release.
- [ ] This applies to **Dependabot PRs too** — do not merge a Dependabot bump for
      a release younger than 7 days. The cooldown is a manual convention (Dependabot
      cannot enforce it natively); honor it by hand.

**Reject (for now) if:** the target version is younger than 7 days — revisit after
the cooldown.

## 7. Decision record

Document the outcome so the intake is auditable.

- [ ] **Record the decision in the PR** that adds the dependency. Include:
      - The package name and exact pinned version.
      - A one-line justification (which section-1 need it satisfies).
      - The license and confirmation it is MIT-compatible (section 5).
      - The result of the transitive CVE scan (section 4).
      - Confirmation the 7-day cooldown was honored (section 6).
- [ ] **Commit the updated `uv.lock`** alongside the `pyproject.toml` change. CI
      enforces lockfile consistency via `uv lock --check`.
- [ ] If the dependency was **rejected**, record why (so the same package is not
      re-proposed without new information).

A dependency change without a decision record in its PR should not be approved.
