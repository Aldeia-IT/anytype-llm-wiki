# Spec Addendum — post-test council (R1)

**Source:** [`council-test-r1.md`](council-test-r1.md)
**Date:** 2026-05-31
**Target phase:** impl
**Status:** Authoritative — the implementation phase MUST honor these items as spec requirements.
**Relationship to prior addendum:** This refines and extends
[`spec-addendum-post-spec-r1.md`](spec-addendum-post-spec-r1.md). Where they overlap, both apply; this
file corrects one piece of handoff guidance (item 2 below) and adds three new impl deliverables.

## Additional / refined acceptance criteria for the impl phase

1. **[Council-ADV-1 — green-suite precondition, load-bearing] Verify the EXISTING app suite green on
   both 3.11 and 3.13 before `ci.yml` lands.** This restates addendum-r1 item 1 and is the single most
   important impl-acceptance gate. Independently run the pre-existing application tests
   (`tests/test_anytype_client.py`, `test_chunker.py`, `test_embedder.py`, `test_indexer.py`,
   `test_server.py`) under **both** Python 3.11 and 3.13 and confirm `uv lock --check` exits 0. Passing the
   21 static `test_ci_config.py` assertions is necessary but **NOT sufficient** — those assert config text,
   not a green app suite. If the suite is not green on both interpreters, fix that (or document the gap
   explicitly) before committing `ci.yml`, or `main` red-lines on day one.

2. **[Council-ADV-2 — handoff correction to addendum-r1 item 3] The `uv lock` re-sync is a non-issue for
   lockfile consistency; do not chase it.** Verified during council: `hatchling` does **not** appear in
   `uv.lock` (`[build-system] requires` is build-environment metadata outside the resolved dependency
   graph). Changing `["hatchling"]` → `["hatchling==X.Y.Z"]` does **not** alter `uv.lock` and does **not**
   break `uv lock --check`. Re-running `uv lock` is harmless but not load-bearing — the genuine day-one
   risk is item 1, not the lockfile. **Still required:** re-resolve the hatchling pin to **current-latest
   at author time** (the spec's `1.27.0` is illustrative and may be stale as of 2026-05-31), alongside
   re-resolving the three *used* action SHAs (`actions/checkout`, `astral-sh/setup-uv`,
   `actions/attest-build-provenance`) per addendum-r1 item 3.

3. **[Council-ADV-4 — new impl deliverable] Add an `actionlint` YAML-validity gate.** Add an `actionlint`
   invocation as a CI step (and/or a test) covering all three workflows (`ci.yml`, `release.yml`,
   `audit.yml`). The static suite asserts string presence, not YAML/Actions-schema validity; without
   `actionlint`, a structurally-broken-but-string-present workflow passes the presence tests yet fails at
   GitHub parse time = day-one red `main`. This was named first in addendum-r1 item 4 and spec-council
   advisory 6 and is not yet implemented anywhere.

4. **[Council-ADV-3 — new impl deliverable] Tighten the AC2 SHA-pin check to close the trailing-comment
   soft-pass.** The current `_assert_no_unpinned_uses` lookahead scans the whole line, so a tag-pinned
   action with a 40-hex string in `@<sha>` form inside its trailing comment
   (`uses: foo/bar@v4 # pinned-from @<sha>`) is not flagged. Anchor the check to the `uses:` reference
   token (e.g. require the value itself to match `\S+@[0-9a-f]{40}`, or strip the `# …` comment before
   applying the lookahead). Low likelihood, but this is the supply-chain control whose entire job is
   catching unpinned actions, so harden it in `tests/test_ci_config.py`.

5. **[Council-ADV-5 — carry forward addendum-r1 item 2] AC5 scriptable Environment hard-gate must ship in
   `docs/releasing.md`.** Land the exits-non-zero `gh api repos/Aldeia-IT/anytype-llm-wiki/environments/pypi
   … --jq` assertion (fails unless a `required_reviewers` rule with ≥1 reviewer exists AND a `v*`
   deployment-branch policy exists) as a mandatory, ordered, copy-paste first-release step. A self-enforcing
   hard-fail step inside `release.yml` is endorsed further hardening. The static suite intentionally cannot
   exercise this (live GitHub API); **there is currently no test even asserting `docs/releasing.md` exists**
   — the impl-reviewer must manually confirm the file ships with this gate.

6. **[Council-ADV-6 — impl-reviewer manual check] Confirm all seven intake-doc sections substantively.**
   The AC6 check is keyword-based (`release`, `license` are weak discriminators that can soft-pass on
   `SPDX-License-Identifier` headers or incidental prose). Accepted as-is to give the impl prose freedom;
   the impl-reviewer must eyeball that `docs/dependency-intake.md` genuinely contains all seven **checklist
   sections**, not just keyword hits.

## Chair phase-exit obligations (actioned by this council's chair; impl/closer to confirm)

7. **[Council-ADV-7 = addendum-r1 item 5] Deferred-work follow-up ticket(s).** Verified live during this
   council: no GitHub issues exist for the deferred bandit/pip-licenses/gitleaks OSS-hygiene scanner suite
   or the SECURITY.md/responsible-disclosure artifact (due at first public tag). The chair files a
   consolidated follow-up ticket at this phase exit so the deferral is tracked, not dropped. Gates #231
   **closure**, not the impl phase.

8. **[Council-ADV-8 = addendum-r1 item 6] Retitle the ticket/PR to true scope.** #231 still reads
   "Supply-chain security hardening (apply rotki's measures)," understating the greenfield CI/CD foundation
   actually stood up. Retitle the ticket; retitle the PR at PR-open. Hygiene, no code impact.

## Rationale

Items 1, 5, 6 carry forward the prior addendum's load-bearing gates that a static test phase structurally
cannot enforce, sharpened with the council's verification of where the real risk lives. Item 2 corrects a
handoff note that would otherwise send the impl chasing a non-issue (the `uv lock` re-sync) instead of the
genuine day-one gate (the green app suite on both interpreters). Items 3 and 4 are concrete, verifiable new
impl deliverables the council surfaced (a missing YAML-validity gate; a narrow but real soft-pass in the
supply-chain pin check). Items 7–8 are chair phase-exit obligations that have now survived two phase
boundaries unactioned and must not survive a third. None of these reopen the spec design — the council
APPROVED the test output unanimously with zero blocking findings — they direct the implementation to
execute the design's intent safely and keep the audit trail honest.
