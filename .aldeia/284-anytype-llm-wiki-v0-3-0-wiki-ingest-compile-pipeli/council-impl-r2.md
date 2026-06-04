# Council Meeting — Post-impl (Round 2)

**Date:** 2026-06-04
**Ticket:** #284 — anytype-llm-wiki v0.3.0 wiki_ingest compile pipeline
**Phase reviewed:** impl (narrow council-directed rework of R1 BLOCKING-L1)
**Client:** anytype-llm-wiki (open-source, dual-purpose: internal Aldeia KB + public PyPI release)

## Attendance

| Role | Present | Reason |
|------|---------|--------|
| Council Chair | Yes | moderator |
| Legal Counsel | Yes | authority who raised the sole R1 BLOCKING; must verify its resolution |
| QA Director | Yes | owns the verbatim-fixture gate + full-suite verification ("green-masks-broken-promise" history) |
| Chief Technology Officer | Yes | engineering-regression diligence on the rework |
| Chief Security Officer | Carried | R1 sign-off stands; data-flow accuracy (security-adjacent) now corrected — no implementation change since |
| Chief Product Officer | Carried | R1 advance-sign-off stands; no scope/product change in rework |
| Infrastructure Lead | Carried | R1 sign-off stands; rework touches no ops surface (Qdrant backup remains a tag-time gate) |
| Client Advocate | Carried | co-raised CA-B1 in R1 (same finding as Legal-L1); resolution verified by Legal on their behalf |

**Attendance rationale.** R1 was a full eight-member council with independent suite runs + five falsification experiments; six of seven members signed off to advance to PR and **no member opposed advancing once BLOCKING-L1 was fixed** (council-impl-r1.md, Dissent: None). The directed rework reopened nothing in the implementation — it is an 8-line, Legal-pre-blessed documentation/fixture correction plus one obsolete-xfail removal. A proportionate Round 2 seats only the members whose mandate the rework actually touches (Legal — owns the finding; QA — owns the fixture gate + suite; CTO — regression). The remaining four members' R1 advance-sign-offs are carried forward, as the surface they reviewed is byte-for-byte unchanged.

## Context Presented

R1 returned REWORK with exactly one BLOCKING: the README "Privacy and data flow" notice and its frozen verbatim test fixture named `WIKI_EXTRACT_MODEL` as the env var that transmits ingested source content off-machine to a hosted LLM provider — false against the code, where `WIKI_EXTRACT_MODEL` only resolves a model-name string and `WIKI_EXTRACT_ENDPOINT` is the actual off-machine switch and sole consent-banner trigger. An accuracy defect in a published privacy notice on a local-first-branded tool (GDPR Art. 13/14, LGPD Art. 6 transparency), frozen into a test fixture. Legal pre-blessed the corrective wording.

Rework delivered: commit `7c6acf4` (README.md 2 bullets + `readme_privacy_notice_verbatim.md` in lockstep + removal of an obsolete `xfail(strict=False)` on `test_wiki_ingest_returns_error_on_missing_patch_decision`, council R1 Advisory 7); commit `bd43b3c` (impl-review-r3.md documenting resolution). No `src/` file modified.

## Discussion

**Independent verification, not prose-trust.** All three seated members verified against the live code contract rather than trusting the rework summary. Legal re-read `wiki/config.py:32-34` (model-name string only), `wiki/extraction.py:126` (`WIKI_EXTRACT_ENDPOINT or _ollama_url()` — the off-machine switch), and `wiki/ingest.py:421-424` (consent gate keyed on `WIKI_EXTRACT_ENDPOINT`, fires before any transmit and before the lock); confirmed all three claims in the corrected notice now match the code exactly, the R1 self-contradiction (line 46 wrong vs 159 right) is eliminated, and `.env.example:6-11` is consistent.

**The gate was proven to bite.** QA ran the full non-live suite independently → **367 passed, 20 skipped, 2 deselected (live), 2 xfailed, 0 failed** — matching the recorded envelope (chair independently reproduced the identical result). QA then *falsified* the verbatim gate: perturbing the fixture by a single token (`WIKI_EXTRACT_ENDPOINT`→`WIKI_EXTRACT_MODEL`) turned `test_readme_contains_verbatim_privacy_notice` (test_bootstrap.py:575-583, `assert fixture in readme_text`) RED, then reverted — proving a README/fixture divergence surfaces as a real failure. This directly guards the project's signature failure mode (green suite masking a broken promise): the gate protecting the corrected privacy notice demonstrably fails on divergence.

**xfail removal is safe.** The de-xfailed `test_wiki_ingest_returns_error_on_missing_patch_decision` now runs as a real passing assertion (imports real `wiki_ingest`, empty `ALDEIA_DIR`, asserts `patch_decision_missing_or_invalid`), so a future regression surfaces as a genuine fail rather than a silent xpass. QA and CTO both confirmed the 2 *surviving* xfails are genuine forward-activation pre-checks (they import the not-yet-shipped v0.4.0 `wiki.query` module), not masked v0.3.0 defects.

**Branch mergeability.** CTO confirmed `git log origin/main..HEAD` is the expected stack, `HEAD..origin/main` count = 0 (not behind, no rebase needed), tree clean. Zero `src/` files touched since R1.

**Carry-forward tag gates re-affirmed.** CTO traced the live-gate rationale to commit `5ed13e7`: the two most contract-sensitive paths — entity/concept kind routing (`ingest.py:269-276`, `_REL_KEY_BY_KIND`) and property-based bidirectional relations — were rewritten *after* the spec/test phases (`WIKI_TYPES` has no `wiki_relation` type, types_schema.py:67) and have never executed against live Anytype. Gating AC#1/AC-P2/AC-P7/V3 at TAG (not MERGE) is the correct "don't repeat v0.2.0" discipline.

## Findings

### BLOCKING
None. The single R1 BLOCKING (Legal-L1 / CA-B1) is resolved and independently code-verified by Legal, QA, and CTO. The rework introduced no regression and disturbed no production path.

### ADVISORY
1. **[All — carry-forward] Live contract gate is TAG-blocking, not merge-blocking.** AC#1 / AC-P2 / AC-P7 / V3 must run green against live Anytype + Qdrant + Ollama before the v0.3.0 PyPI tag, including a concept-producing AND a headingless source (to exercise AC#1's "≥1 Concept" half). A *skipped* live test must be treated as a failure — the runbook MUST NOT permit a `-m "not live"` shortcut. The entity/concept-routing and property-based-relation paths were rewritten after spec/test and have never run live. Recorded: spec §10.1, spec-addendum-post-test-r1 item 9, council-impl-r1 Advisory 1, impl-review-r3.md:64-66. Re-seat Infra + Legal at the pre-tag gate.
2. **[Legal — carry-forward] NOTICE / dependency-licensing gate.** New runtime deps `markdownify` + `pydantic`. Tree is not uniformly MIT: `typing-extensions` is PSF-2.0 and `pydantic-core` bundles vendored Rust crates invisible to a Python-level `pip-licenses` scan. Before tag: regenerate NOTICE via `pip-licenses --from=mixed`, diff against expected OSI-permissive tree, and manually check `pydantic-core` vendored-Rust licenses. Recorded: spec §10.1, spec-addendum-post-spec-r2 item 8, council-impl-r1 Advisory 3.
3. **[Infra — carry-forward] Qdrant backup rotation + TESTED restore** for the v0.3.0 data volume. Recorded: council-impl-r1 Advisory 2, addendum item 10. Pre-publish, not merge.
4. **[CPO/QA — carry-forward] AC#18 partial-state-idempotency disposition** recorded in release notes before tag. Recorded: council-impl-r1 Advisory 6.
5. **[QA — new, cosmetic] xfail reason-string drift.** In `TestBootstrapSchemaOutdatedV3Plus`, `test_wiki_ingest_raises_schema_outdated` imports the now-shipped `wiki.ingest` while its xfail reason still reads "module not yet implemented"; it correctly xfails on the seeded-outdated-schema path, so nothing is masked, but the reason string is misleading. Tighten in a future housekeeping pass. Non-blocking.
6. **[CTO/CPO/CA — carry-forward] v0.4.0 product item:** LLM-extraction-primary candidate derivation (current heading-primary path is coarse for headingless sources). Ensure public README/CHANGELOG "LLM-driven extraction" language does not over-promise for headingless inputs.

## Resolutions

- **BLOCKING-L1 (privacy-notice variable) — RESOLVED.** Verified against the code contract by all three seated members; the published notice is now accurate, internally consistent (README:46-47 ⇄ 159-164 ⇄ .env.example:6-11), and gate-frozen. The GDPR/LGPD transparency defect is cured.
- **Advisory 7 (stale xfail) — RESOLVED.** De-xfailed test runs as a real passing assertion; +1 real coverage, no masked xpass.
- **Full non-live suite — independently re-verified green** by QA and the chair (367 passed / 0 failed). The "green-suite-masks-broken-promise" risk is specifically guarded: the verbatim gate was falsified-and-confirmed to bite.

## Recommendation

**Recommended target:** done (approve PR)
**Confidence:** high
**Rationale:** The sole R1 BLOCKING is resolved and code-verified; the rework is a surgical, lockstep documentation/fixture correction that touched zero production logic; the full non-live suite is green and the gate protecting the correction demonstrably bites; the branch is clean and current with origin/main. Three seated members sign off and the other four members' R1 advance-sign-offs stand unchanged. All remaining items are tag-time release gates already recorded in spec §10.1 and the addenda — they are NOT merge blockers. Advance to PR; the watcher creates the PR (`Closes Aldeia-IT/aldeia-box#284`). Re-seat Legal + Infra at the post-PR/pre-PyPI-tag gate to execute the live-contract, NOTICE/licensing, Qdrant backup-restore, and AC#18-disposition gates.
**Dissent:** None.
