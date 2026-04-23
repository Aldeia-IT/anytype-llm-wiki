# Council Meeting — Post-spec (Round 2, Calibration Re-review)

**Date:** 2026-04-22
**Ticket:** #140 — Wiki Library Module: Port LLM Wiki Pattern onto Anytype
**Phase reviewed:** spec
**Client:** anytype-llm-wiki (open-source, MIT-licensed; pipeline tickets in aldeia-box)
**Spec under review:** `.aldeia/140-wiki-library-module-port-llm-wiki-pattern-onto-any/spec.md` (1912 lines, `status: SPEC`, commit `da44848` / `f406296`).

---

## Why this re-review exists

Round 1 of this council (commit `da44848`, meeting file `council-spec-r1.md`) ran under an architectural defect. The `anytype-llm-wiki` repo has no `.claude/agents/` directory, and at the time of R1 the `agent` user's `~/.claude/agents/` was empty. When the chair dispatched `subagent_type: chief-security-officer`, `legal-counsel`, `qa-director`, `infrastructure-lead`, `chief-technology-officer`, and `chief-product-officer`, none of those names resolved in Claude Code's catalog — every specialist "present" at R1 was served by `general-purpose` with the role definition injected as a prompt. The narrative in `council-spec-r1.md` reads polished because the chair is competent, but the review depth was synthesis-level role-play, not specialist execution.

A parallel calibration re-run on ticket #172 (commit `e3e3ba6`) revealed the quality cost was severe: real specialists caught **3 BLOCKING correctness defects** that R1 impersonators had signed off on.

As of 2026-04-22 the architectural fix is in (aldeia-box PRs #187, #188): `~/.claude/` on `jan`, `agent`, and `ironclaw` is wired to aldeia-box's specialist catalogue via symlinks. Real specialists now resolve natively in every worktree — including this one.

**This Round 2 meeting is the calibration verdict for #140.** Purpose: validate whether #140's R1 APPROVED verdict holds under real-specialist scrutiny, or whether (like #172) the general-purpose impersonators missed BLOCKING items.

## Attendance

| Role | Present | Reason |
|------|---------|--------|
| Council Chair | Yes | moderator; synthesis only |
| Chief Security Officer | Yes | minimum roster; SSRF/prompt-injection/token/extraction-exfiltration are prominent |
| Legal Counsel | Yes | chair decision: MIT OSS distribution, hosted-LLM consent, CRA preparation, trademark nominative use |
| Chief Product Officer | Yes | minimum roster |
| QA Director | Yes | chair decision: AC determinism, traceability, mock strategy — the phase where R1 impersonation gaps are most likely to show |
| Infrastructure Lead | Yes | chair decision: `fcntl.flock`, schema migrations, doctor, resource impact, community deployment burden |
| Chief Technology Officer | Yes | minimum roster; codebase alignment audit specifically targeting the spec-vs-code coherence class R1 impersonators plausibly miss |
| Client Advocate | No | anytype-llm-wiki is Jan's own open-source project, not a client engagement; CPO represents Jan's interest. Consistent with product-phase council decision and R1. |

All six specialist members executed **independent** assessments before reading the R1 meeting summary. Each wrote a standalone `council-spec-r2-{role}.md` with mandatory Verdict / Summary / Independent findings / R1 Delta / Calibration verdict on R1 sections. This meeting summary synthesizes their findings.

## Context Presented

Calibration re-review of ticket #140's post-spec council verdict after the R1 architectural defect was repaired. Inputs to the council:

- `spec.md` at `status: SPEC`, 1912 lines — unchanged since R1
- `council-spec-r1.md` (R1 meeting summary) — read by each specialist AFTER forming an independent view
- Individual R1 specialist reviews (`review-r1-{completeness,architecture,security,infra}.md`, `review-r1.md` consolidated, `review-r2.md` verification) — these were real, independent from the R1 council impersonators
- R1 council's recommended target: `test`
- R1 council's finding counts: 0 BLOCKING, 26 ADVISORY

**Jan's ticket feedback carried forward:** "make sure it's well structured and documented withstanding the scrutiny of open source communities"; "delivery has many layers — think about the phases of delivery to spec out exact scope and requirements that must be met at each point."

## Discussion

### CSO Assessment — SIGN OFF WITH CONDITIONS

SSRF architecture, `fcntl.flock` semantics, and the three-layer prompt-injection defense (fence + pydantic + `is_central` cross-check) all hold under real-specialist scrutiny. All seven SSRF invariants verified by inspection; `ipaddress.ipv4_mapped is not None` guard is correct; 169.254.169.254 (AWS/GCP IMDS) is caught by both the explicit `/16` and `is_link_local`; fcntl.flock removes TOCTOU between open-and-lock because the kernel attaches the lock to the open fd. `is_central` cross-check is correctly treating extractor output as untrusted.

**10 new advisory-level items surfaced that R1 CSO did not.** The most concrete:
- **Bidi/control-char regex coverage gap** at spec line 1615: `U+FEFF` (BOM/ZWNBSP), `U+2028` (LINE SEPARATOR), `U+2029` (PARAGRAPH SEPARATOR), and Unicode tag characters (`U+E0020-U+E007F`) are not in the character class. R1 CSO endorsed the regex without enumerating its coverage.
- **Verification-script trap-window race.** Script creates the probe object (line 1249) before installing `trap cleanup EXIT INT TERM` (line 1266). A SIGINT in that window leaves an orphaned probe. Plus `|| true` on the DELETE swallows all failure signals — the script can "succeed" while leaving a zombie object with no diagnostic.
- **Cross-machine TOCTOU on bootstrap.** R1 Infra documented the two-machine-shared-vault limitation for flock; same shape applies to `wiki_bootstrap`'s check-then-create for Types. Needs an empirical probe on the v0.2.0 pre-release checklist.
- **Persistent prompt-injection via v0.4.0 Query objects.** Three-layer extraction defense is correct, but entity names that ride through extraction become interpolation material in v0.4.0 query synthesis prompts — a persistence channel. R1 Advisory #16 partially flagged this at the CLI render layer only.
- **`WIKI_EXTRACT_ENDPOINT` userinfo credential leakage** in error strings: parallel to the `QDRANT_API_KEY` query-string concern R1 raised; same fix shape.

Cross-thread: CSO flagged A3 (cross-machine TOCTOU on bootstrap) to Infra for doctor coverage; flagged A6 (v0.4.0 persistent injection) to CPO for README trust note.

### Legal Counsel Assessment — SIGN OFF WITH CONDITIONS

MIT license integrity verified independently (LICENSE clean with 2026 Aldeia IT); full runtime dep license matrix confirmed MIT-compatible (httpx BSD-3, fastmcp Apache-2.0, qdrant-client Apache-2.0, markdownify MIT, pydantic MIT, bge-m3 MIT). "First Anytype-native LLM wiki" claim with qualifier + verification gate + committed fallback meets reasonable-diligence bar under Lanham §43(a) and CDC Art. 37. Hosted-LLM consent via endpoint-hash ack is proportionate under GDPR Art. 7 / LGPD Art. 8.

**Two items R1 Legal missed:**
- **CONTRIBUTING.md lacks an inbound-license clause** (confirmed by reading the file — 55 lines, no CLA/DCO/inbound=outbound statement). Project currently relies on GitHub ToS §D.6 default; mature OSS practice adds an explicit one-paragraph grant. Low-cost fix.
- **CRA free-software exemption conditionality.** EU Regulation 2024/2847 Recital 18 exempts OSS "outside the course of a commercial activity." Per `.aldeia/context/business.md` line 21, this repo is explicitly framed as reputation/marketing for Aldeia-IT. Under a strict Commission interpretation of "commercial activity," this could complicate the exemption. Not a current obligation (Art. 14 effective 2026-06-11; full conformity 2027-12-11), but posture work (SECURITY.md, private disclosure, Art. 14 awareness) should start at v0.2.0 — a stronger rationale than R1's community-norms framing.

**Precision refinements to R1-endorsed text:**
- "This module is a tool, not a data controller under GDPR/LGPD" is technically imprecise — software is never a controller; Art. 4(7) and Art. 5(VI) attach controllership to persons. Tightened replacement wording provided.
- Positioning-verification should produce a **committed** `positioning-verification.md` artifact (analog to `patch-decision.md`), not just PR-description prose.
- NOTICE file + license-scan CI step (separate from pip-audit) close the Apache-2.0 attribution-propagation and license-compatibility gaps.

Cross-thread: Legal upgraded SECURITY.md priority to v0.2.0 checklist (aligned with CSO + R1 Legal), with CRA-preparation as the stronger rationale than community norms.

### CPO Assessment — SIGN OFF WITH CONDITIONS

Per-version Scope/MoSCoW/AC/Deliverables/Dependencies/Risks backbone is the strongest structural response in the spec — it directly answers Jan's "phases of delivery" feedback. Personas clearly articulated; market positioning credible with fallback; additive architecture preserves v0.1.0.

**Three items R1 CPO missed that matter:**
- **Committed `README.md:3` makes a broader claim than the spec supports.** Current committed README line 3 says *"The first open-source LLM wiki that uses a typed knowledge-graph store"* — broader than the spec's "to our knowledge, the first Anytype-native" positioning. This line exists **today, in the repo**, without the prior-art verification having been run. R1 CPO did not audit the committed README against the spec positioning.
- **The 15-minute quick-start promise appears in two separate places** (user story line 63, Success Criteria line 1684), both presuming ingest+query. Ingest is v0.3.0, query is v0.4.0 — the 15-minute promise is a v0.4.0 promise. The v0.2.0 README must version-stamp this explicitly, or first adopters hit unambiguous promise-vs-reality drift.
- **OQ #3 (qwen2.5:7b default) is a product decision not just a doctor labeling issue.** 16 GB community adopters hitting Ollama's back-to-back model swap (bge-m3 + qwen2.5:7b) will experience a first-ingest disappointment that the doctor WARN fires too late to prevent (after they've downloaded the 4.7 GB model). The README needs two recommended defaults (32 GB / 16 GB), not just a post-install warning.

**v0.2.0 PyPI-publish strategy remains the biggest single product risk** (confirms R1 ADV #6): pre-release checklist line 735 says `Git tag v0.2.0` without addressing PyPI publish. Recommendation: tag v0.2.0 in git only; first PyPI publish is v0.3.0 after ingest lands. **Must be an explicit checklist item before tag day.**

**OQ #5 (community branding) must close before v0.2.0 implementation begins** — currently "Jan's call" open, but "must resolve by v0.2.0 README update" and the README update IS part of the v0.2.0 deliverable. Sequencing gap.

### QA Director Assessment — SIGN OFF WITH CONDITIONS

AC determinism is unusually disciplined (dash-fold parametrized over 8 codepoints; 199/200/201 boundary nailed; concurrent-ingest AC makes three independent assertions; mock-strategy tiers correct). Dash-fold-before-casefold ordering empirically verified: casefold does NOT touch any of U+2010–U+2014, U+2212, U+FE63, U+FF0D — ordering is correct but not load-bearing today (only if a future codepoint is both dash-like and case-sensitive).

**Four items R1 QA missed (and one counting error):**
- **R1 QA's lint check-count gap miscounted.** R1 said "5 of 9 lint checks missing a test"; actual count is **4 of 9**. AC v0.5.0 #7 covers `empty_type`; R1 miss-listed it. Real missing: `contradiction_unresolved`, `oversized`, `stale_stub`, `potential_duplicate`. Still the single largest coverage hole, just miscounted.
- **Bidirectional-relation rollback has no AC.** Implementation Plan commits to atomicity ("if either write fails, roll back both") and Deliverables names a rollback test, but no AC enforces the invariant. Test author could satisfy existing ACs without ever exercising the rollback path.
- **Schema-compatibility three-outcome coverage gap.** Three documented outcomes (missing / outdated / newer). Only `missing` has any AC (v0.4.0 #6, query-only). `_outdated` and `_newer` untraced. Cross-cutting regression risk — the check runs on every tool entry.
- **Concurrent-ingest test mechanism under-specified.** AC v0.3.0 #5 assumes `respx` suffices; it does not. `respx` mocks httpx synchronously; `fcntl.flock` is OS-level and requires `multiprocessing.Process` or equivalent. Test author taking R1 endorsement at face value could write a test that never exercises the real race.
- **Prompt-injection AC v0.3.0 #12 is internally contradictory.** The OR branch says `is_central=false` demotion is acceptable; the final assertion says "no object with that name appears in Anytype." If the policy doesn't reject the name (it's ordinary English like "AcmeCorp Is A Scam"), the object IS created with `is_central=false`. AC must pick one.
- **Performance-gate Success Criteria wording drops the "Jan's Mac Mini M4" qualifier** on lines 1652 / 1672 / 1680, while the matching ACs carry it. Spec internally inconsistent.

QA's full traceability matrix (35 traceable items; 5 documented but implicit; 7 AC-missing) is attached in `council-spec-r2-qa.md`.

### Infrastructure Lead Assessment — SIGN OFF WITH CONDITIONS

fcntl.flock design is textbook; Resource Impact table honestly concedes 8 GB is not supported; schema-compat entry check with three outcomes + MIGRATIONS.md is textbook; failure-modes table covers every realistic local-dep outage. Mac Mini deployment risk nil beyond v0.1.0.

**One substantive miss from R1 Infra:**
- **Bootstrap-specific schema-compat path is ambiguous and can deadlock the upgrade UX.** §Schema Compatibility says every `wiki_*` tool entry runs a compat check. `wiki_bootstrap` is in that set. When a v0.4.0 client runs bootstrap against a v0.3.0-schema space, the outdated branch fires and tells the operator to "re-run wiki_bootstrap" — which is literally what they are doing. Self-recursive remediation loop. Needs either (a) bootstrap-specific exception or (b) outdated branch that distinguishes `tool == wiki_bootstrap` and proceeds with idempotent upgrade. Subtle but real; one of the closest things to a BLOCKING find outside of CTO's.

**Additional infra items:**
- Doctor should add `statfs` probe on `WIKI_LOCK_DIR` for NFS/SMB/sshfs/CIFS (reaffirms R1 Infra Adv #1; independent rediscovery).
- Doctor should WARN on 16 GB + ≥7B extraction model combination (reaffirms R1 Infra Adv #2).
- Doctor should check `$QDRANT_COLLECTION` existence, not just `/readyz` — first `wiki_ingest` on a fresh install hits collection-missing branch.
- Ship sample `logrotate` + `newsyslog.conf` configs under `docs/samples/` — current spec conflates Linux and macOS conventions in one sentence.
- Failure-modes table has two small gaps: partial Anytype token scope (can create Types but not Objects), and bootstrapped-but-empty wiki under `wiki_lint` invocation.

### CTO Assessment — SIGN OFF WITH CONDITIONS (one BLOCKING — the single blocking find of this council)

Every codebase-verification claim R1 CTO made holds under independent spot-check: zero `anytype-rag|anytype_rag` matches under `src/` or in `spec.md`; `server.py` tool registrations at lines 12 & 67 match; `anytype_client.py` is per-call `httpx.Client` at line 17; `pyproject.toml` has `fastmcp>=2.0.0` at line 10 and `packages = ["src/anytype_llm_wiki"]` at line 26; `wiki/prompts/extraction.md` will ship with wheel via hatchling's default packaging; R1 architecture reviewer's empirical normalize_title check was genuinely executed (reviewer file quotes specific Python output, not paraphrase); FastMCP tool-name-from-function-name matches; `fec0::/10` deprecated site-local IPv6 is caught by `addr.is_reserved` even without explicit blocklist entry.

**One BLOCKING spec-internal contradiction, missed by R1 reviewers and R1 CTO alike:**

**BLOCKING-CTO-1 — Spec contradicts itself on `anytype_client.py` v0.2.0 refactor.**

- Spec line 24: "v0.1.0's `...` files ... are not modified in substance during v0.2.x"
- Spec line 220: "The existing `anytype_client.py` (read-only) is **unchanged in v0.2.x**"
- Spec line 908: "anytype_client.py — existing read-only client; unchanged in v0.2.x"
- vs.
- Spec line 916: "`_base_client.py` — `_BaseAnytypeClient`: ... anytype_client and WikiClient **both inherit**"
- Spec lines 993–994: "Both anytype_client (read-only, v0.1.0) and wiki_client (write, v0.2.0+) inherit from this in v0.2.0."
- Spec lines 1024–1026: "v0.2.0 introduces `_BaseAnytypeClient` ... Both `anytype_client.py` (read-only, existing) and `wiki_client.py` (write, new) **inherit from it**."

Actual codebase: `src/anytype_llm_wiki/anytype_client.py` is 45 lines of **free functions** (`def list_spaces()`, `def list_objects()`, `def get_object()`) — no class to inherit from. `indexer.py:11` imports them as free functions. Making a free-function module "inherit from" a class is not a no-op — it requires a refactor that touches importers. "Unchanged" and "inherits" are incompatible.

Impact: impl agent hits this on day one. Worst case ships a wrapper that technically inherits but doesn't actually share a session (because the free functions still construct fresh clients via `_client()`), defeating S14's intent. Fix is a ≤5-line spec edit (recommend Option A in CTO assessment: state explicitly that v0.2.0 **refactors** `anytype_client.py` to an `AnytypeReadClient` class inheriting from `_BaseAnytypeClient`, with module-level free-function wrappers preserving the existing import surface).

This is exactly the class of defect the R1 subagent-routing defect was expected to produce: a prompt-injected generalist could grep-verify line citations (which R1 CTO did, successfully) but miss the coherence check between two paragraphs in different sections that assert incompatible things about the same file.

**Three other CTO advisories:**
- `_BaseAnytypeClient` transport-only scope reminder that R1 CTO accepted as Adv #3 did not land in the `f406296` SUGGESTION fix commit. Still missing from the spec.
- `_DASH_FOLDS` table misses U+00AD (SOFT HYPHEN — classic PDF-paste vector) and U+2015 (HORIZONTAL BAR). Two-codepoint extension.
- `markdownify` transitive closure pulls `beautifulsoup4` (MIT) and `six` (MIT) — not enumerated in R1 Legal's dep list. Licenses fine; Legal's v0.2.0 SBOM will naturally capture this.

### Cross-thread resolutions

- **BLOCKING-CTO-1 intersects Infra's bootstrap self-recursive-remediation loop (A1).** Both are spec-coherence issues in the same v0.2.0 architecture section. CTO's fix (explicit `AnytypeReadClient` refactor) and Infra's fix (bootstrap-specific schema-compat exception) are independent — both edits should land in the rework.
- **CSO A3 (cross-machine TOCTOU on bootstrap) is orthogonal to but adjacent to Infra's A2 (NFS statfs probe).** CSO raised the API-level check-then-create concern; Infra raised the lock-serialization concern. Both belong on the v0.2.0 pre-release checklist.
- **CPO's ADV-CPO-R2-3 (committed `README.md:3` broader claim) intersects Legal's A5 (verification-record artifact).** CPO raised a product consistency issue; Legal raised a reproducibility / false-advertising diligence issue. Consolidated: the `README.md:3` line must be reconciled against the spec's narrower claim, AND the verification record must be a committed `positioning-verification.md` artifact delivered before the v0.2.0 README prose is finalized.
- **CPO's ADV-CPO-R2-4 (16 GB extraction default) extends and up-weights R1 Infra Adv #19 + R2 Infra A3.** Infra scopes it as a doctor WARN; CPO frames it as a README-level two-defaults product decision. Resolution: both land — README shows two defaults; doctor WARN anchors to the README table by reference.
- **QA's A5 (concurrent-ingest test mechanism) intersects Infra's A2 (NFS probe).** QA concern is test authorship; Infra concern is production correctness on network FS. Same underlying primitive (fcntl.flock semantics), different angle. Test Plan needs a one-sentence note naming `multiprocessing.Process` or equivalent.
- **Legal's A7 (CRA commercial-activity conditionality) and CSO's Advisory #2-reaffirming SECURITY.md converge** on "SECURITY.md belongs on v0.2.0 pre-release checklist." Legal adds stronger rationale (CRA Art. 14 preparation, effective 2026-06-11) than R1's community-norms framing.

### Observations on the R1 impersonation hypothesis

The R1 calibration defect manifested across this council as a consistent pattern but at LESSER magnitude than #172:

- **R1 CTO: one BLOCKING miss** (BLOCKING-CTO-1). Exactly the "spec-coherence audit across multiple paragraphs" class of find a prompt-injected generalist plausibly misses while still successfully reproducing line-citation claims.
- **R1 Infra: one substantive spec-reading miss** (bootstrap-specific schema-compat loop). Subtle cross-reference between tool-enumeration and remediation-instructions.
- **R1 QA: four traceability misses** (bidirectional rollback AC, schema-compat outcomes, concurrent-ingest test mechanism, prompt-injection AC contradiction) + one counting error (5-of-9 vs 4-of-9). All are Implementation-Plan-vs-AC-list gaps.
- **R1 CSO: depth shallowness** — correct verdict and correct positive assessments (seven SSRF invariants, fcntl.flock, is_central cross-check) but did not enumerate the bidi regex coverage, did not notice the verification-script trap-window race, did not extend cross-machine concurrency to bootstrap.
- **R1 CPO: three artifact-inspection misses** — did not audit the committed `README.md:3` against the spec; did not trace the 15-minute promise across two spec locations; framed 16 GB model default as labeling rather than product decision.
- **R1 Legal: substantially sound.** No BLOCKING missed; two genuinely new advisories (CONTRIBUTING.md inbound-license, CRA exemption conditionality) + precision refinements. Legal assessment does NOT exhibit the failure mode.

**Aggregate: 1 BLOCKING + ~20 substantive advisory misses across the council relative to the #172 baseline of 3 BLOCKINGs.** The calibration hypothesis is confirmed at a lesser magnitude — consistent with the shape of the defect (impersonators reproduce plausible line citations easily but miss coherence audits that require independent mental modeling of the artifact under review).

## Findings

### BLOCKING

1. **[CTO]** Spec internally contradicts itself on `anytype_client.py` v0.2.0 refactor. Lines 24/220/908 say "unchanged in v0.2.x"; lines 680/916/993–994/1024 say it "inherits from `_BaseAnytypeClient` in v0.2.0." Actual codebase is a 45-line module of free functions; "inherits" requires a refactor. **Fix:** ≤5-line spec edit. Recommended: state explicitly that v0.2.0 refactors `anytype_client.py` to an `AnytypeReadClient` class inheriting from `_BaseAnytypeClient`, with module-level free-function wrappers (`list_spaces`/`list_objects`/`get_object`) preserving the existing import surface; update `tests/test_anytype_client.py` to exercise both the class-level and wrapper-level paths.

### ADVISORY

(Consolidated across six specialists; R1-derived items reaffirmed but not re-enumerated.)

**Security**

1. **[CSO]** Extend bidi/control-char regex at spec line 1615 to include U+FEFF (BOM/ZWNBSP), U+2028 (LINE SEPARATOR), U+2029 (PARAGRAPH SEPARATOR), and Unicode tag characters (U+E0020–U+E007F). Add test cases per codepoint.
2. **[CSO]** Reorder verification script so `trap cleanup EXIT INT TERM` is installed BEFORE probe object creation, with conditional-execution guards in the cleanup function. Also: replace `|| true` on the DELETE call with a "log response body on non-2xx" diagnostic so zombie objects produce a signal.
3. **[CSO + Infra]** v0.2.0 pre-release checklist adds an empirical cross-machine bootstrap probe: run `wiki_bootstrap` simultaneously from two processes on two hosts against the same Anytype vault; assert zero duplicate Types. Document the result in the pre-release notes.
4. **[CSO]** For v0.4.0 (query), pre-commit the synthesis-prompt defense now: entity/concept names interpolated into the synthesis prompt pass the same name-policy regex AND are fenced in `<context>...</context>` parallel to the extraction `<source>` fence. Document as a v0.4.0 pre-release item.
5. **[CSO]** Add regression test: `[API ERROR]` triggered by Qdrant failure with `QDRANT_URL=https://xyz.cloud.qdrant.io/collections/x?api_key=abc...` returns an error string containing neither the API key value nor the raw query string. Extend to `WIKI_EXTRACT_ENDPOINT` userinfo (`user:password@`) credential shape.
6. **[CSO]** Commit a `.bandit` or `[tool.bandit]` baseline at v0.2.0 tag time with rationale-annotated expected findings for the SSRF fetch layer. Prevents drive-by PR weakening of actual defense.
7. **[CSO]** Document the two-layer dependency-pinning story in README: (a) `pyproject.toml` minor-range bounds, (b) `uv.lock` for reproducible dev installs, (c) downstream pip-install consumers without `--require-hashes` inherit only the minor-range guarantee.
8. **[CSO]** Tighten default port allowlist to `{None, 80, 443}`; add `WIKI_FETCH_EXTRA_PORTS` env var for operators who need 8080/8443. (Reaffirms R1 CSO Adv #13; did not land.)
9. **[CSO]** DNS-rebinding accepted-residual should carry a mechanical tripwire, not just a note. Add integration test asserting `wiki_ingest` fails closed if the post-connect peer IP does not match one of the check-time resolutions.

**Legal / Compliance**

10. **[Legal]** Add a NOTICE file at v0.2.0 tag enumerating direct deps with SPDX identifiers and URLs, Apache-2.0 upstream NOTICE contents concatenated, and model attribution. Add license-scan CI step (`pip-licenses` / `license-check`) that fails on any GPL/AGPL/SSPL/EUPL in the transitive closure — this is separate from `pip-audit`.
11. **[Legal]** Add one paragraph to `CONTRIBUTING.md` establishing inbound=outbound MIT licensing for contributions. "By submitting a pull request, you agree that your contribution is licensed under the MIT License..." Minimum defensible inbound-license posture for an MIT project without a full CLA.
12. **[Legal]** Replace the imprecise "This module is a tool, not a data controller under GDPR/LGPD" sentence (README Privacy section, spec line 651) with: "Aldeia IT, as the publisher of this open-source module, does not determine the purposes or means of data processing that you perform with it, and is therefore not a controller of your data under GDPR Art. 4(7) or LGPD Art. 5(VI). You are the controller..."
13. **[Legal]** Commit the prior-art verification as a `positioning-verification.md` artifact (analog to `patch-decision.md`) with verbatim search queries, dates, zero/nonzero finding count, and URLs of any near-matches reviewed. Land at v0.2.0 tag.
14. **[CSO + Legal]** Ship `SECURITY.md` on the v0.2.0 pre-release checklist with supported-version statement, private disclosure channel (GitHub Security Advisories + email), response-time expectation, and public advisory format. Rationale: CRA Art. 14 preparation (effective 2026-06-11) given Aldeia-IT's marketing framing of this repo per `.aldeia/context/business.md`. Monitor CRA "commercial activity" interpretation through 2026–2027.
15. **[Legal]** Add to README Privacy section: "When you configure `WIKI_EXTRACT_MODEL` to point at a hosted LLM API, your ingested source content is processed under that provider's Terms of Service and data-handling policies — including training-on-input, data-retention, and data-residency terms. Review those terms before configuring a hosted endpoint..."
16. **[Legal]** Trademark footer adopting nominative-use disclaimer, with a pre-v0.2.0 check of Anytype's public community-integration / brand-use policy recorded in the pre-release checklist.
17. **[Legal]** CycloneDX SBOM at tag time via `uv export --format cyclonedx` (or `cyclonedx-py`) attached to each GitHub Release. Tier-2 — can land v0.2.x if not v0.2.0.

**Product**

18. **[CPO]** v0.2.0 pre-release checklist must explicitly resolve the PyPI-publish decision. Recommended: tag v0.2.0 in git only; first PyPI publish is v0.3.0 after ingest lands. If PyPI publish of v0.2.0 is chosen, the README headline and CHANGELOG entry must prefix the release as "**Preview — schema and preflight only; ingest in v0.3.0.**"
19. **[CPO]** v0.2.0 README version-stamps the quick-start: "In v0.2.0, the quick-start is: install → bootstrap → inspect schema in Anytype (about 5 minutes). The full workflow (ingest → query) lands in v0.3.0 and v0.4.0 respectively." Remove or defer the 15-minute promise prose from the v0.2.0 README. Rename the Success Criteria line 1684 sentence "Community Quick-Start (v0.4.0)".
20. **[CPO + Legal]** Currently-committed `README.md:3` line ("The first open-source LLM wiki that uses a typed knowledge-graph store") is broader than the spec's "first Anytype-native" positioning. Reconcile before v0.2.0 implementation begins: either tighten the README line to match the spec, or widen the spec's positioning and have Legal re-sign on the wider claim. Prior-art verification (Advisory #13) is v0.2.0 implementation task #1.
21. **[CPO + Infra]** v0.3.0 README configuration table shows **two recommended extraction defaults**: 32 GB+ = `qwen2.5:7b`; 16 GB = `qwen2.5:3b` with "extraction quality is marginally lower; revisit at 32 GB." Doctor WARN anchors to the README table by reference. Re-evaluate at v0.3.0 pre-release once the Wikipedia fixture AC runs against both model sizes.
22. **[CPO]** Close OQ #5 (community branding) in the spec before v0.2.0 implementation begins. Recommended resolution: "**Resolved 2026-04-22.** Module name is 'Anytype LLM Wiki' in documentation; repo name is `anytype-llm-wiki`; PyPI package is `anytype-llm-wiki`. Legal's Trademarks footer advisory is adopted."
23. **[CPO]** Amend §Delivery Phases intro: "Each phase is internally coherent; end-user value accrues cumulatively across phases, not within each single phase." This is a one-sentence honesty adjustment. Preserves the per-version discipline; removes the slight overstatement.

**QA / Traceability**

24. **[QA]** Add ACs for the four missing lint check enum values (`contradiction_unresolved`, `oversized`, `stale_stub`, `potential_duplicate`) before test authoring of `test_lint.py` begins. R1 counted 5-of-9; real count is 4-of-9 (AC v0.5.0 #7 covers `empty_type`).
25. **[QA]** Add ACs for the two untraced schema-compatibility outcomes (`_outdated`, `_newer`). The check runs on every `wiki_*` tool entry (line 1429–1434); only `missing` has an AC (v0.4.0 #6, query-only).
26. **[QA]** Add a v0.3.0 AC for bidirectional-relation rollback: "If either direction of a bidirectional relation write fails, both directions are rolled back and the relation does not appear in Anytype. The WikiLog records `relation_rollback` with the attempted A/B object IDs."
27. **[QA]** Add Test Plan sentence to line 1709: "The concurrent-ingest test uses `multiprocessing.Process` (or equivalent) to acquire the flock in a second process; a pytest-level threading.Thread or async gather against a mocked lock does not exercise the kernel-held flock and is insufficient."
28. **[QA]** Resolve the prompt-injection AC (v0.3.0 #12) internal contradiction. Pick one: (a) policy rejects injected-looking names outright and the object is never created, OR (b) `is_central=false` demotion is acceptable and the final assertion becomes "no object with that name appears with `is_central=true`."
29. **[QA]** Align Success Criteria performance wording with AC performance wording on "Jan's Mac Mini M4" qualifier. Lines 1652, 1672, 1680 drop the qualifier while the matching ACs carry it. Mark performance ACs as maintainer-measured-at-release-time: "This AC is maintainer-measured-at-release-time. CI runs a sanity timing check (must complete within 5× the target) but does not enforce the p95 budget."
30. **[QA]** Add v0.3.0 and v0.4.0 ACs covering missing/malformed `patch-decision.md`: "Missing or malformed `patch-decision.md` → `[CONFIG ERROR] patch_decision_missing_or_invalid` before any Anytype write or URL fetch."
31. **[QA]** Pin the Wikipedia fixture: capture an `archive.org` snapshot at spec-sign-off time; use the archive URL as the release-gate AC; live URL is aspirational. Alternative: bundle a local markdown fixture.
32. **[QA]** Add v0.3.0 AC covering idempotency after a partial-failure ingest (Source created, extraction failed, operator reruns). Either document as intended behavior or explicitly scope to v0.6.0+.

**Infrastructure**

33. **[Infra]** Resolve the bootstrap-specific schema-compat self-recursive-remediation loop. Add one sentence under §Schema Compatibility: "For `wiki_bootstrap`, the outdated branch is informational — bootstrap proceeds with idempotent upgrade (add missing properties, update `wiki_schema_version` on the root Collection on success) rather than raising `[CONFIG ERROR]`." OR call out that the entry-time compat check is skipped for `wiki_bootstrap` entirely, with upgrade logic inside bootstrap itself.
34. **[Infra]** Elevate doctor to step 9: `statfs`-probe `WIKI_LOCK_DIR` and WARN on NFS/SMB/sshfs/CIFS filesystem types. `fcntl.flock` silently non-serializes on network filesystems. (Reaffirms R1 Infra Adv #1.)
35. **[Infra]** Add doctor step 4b: `client.get_collection(QDRANT_COLLECTION)` → INFO if exists, WARN (not FAIL) if not, naming `reindex_anytype` or equivalent collection-creation path.
36. **[Infra]** Ship sample configs under `docs/samples/`: `anytype-llm-wiki.logrotate` (Linux) and `anytype-llm-wiki-newsyslog.conf.fragment` (macOS). README "Logging" section references both. Replaces the one-sentence prose at §1367 that conflates the two OS conventions.
37. **[Infra]** Doctor 16 GB + ≥7B-extraction-model WARN with 3B fallback suggestion. Ship with the doctor update that lands alongside `WIKI_EXTRACT_MODEL` env var. (Reaffirms R1 Infra Adv #2; also CPO Advisory #21.)
38. **[Infra]** Two failure-mode table gaps: (a) partial Anytype token scope (can create Types but not Objects, or vice versa) → `[CONFIG ERROR] insufficient_token_scope`; (b) lint on bootstrapped-but-empty wiki → returns empty-type findings at Informational + `status: ok`.
39. **[Infra]** Add "runtime metrics surface (rolling error rate, duration percentiles)" to Deferred Items explicitly. Currently only `wiki.status` is listed.

**Technical / Engineering Craft**

40. **[CTO]** Add the `_BaseAnytypeClient` transport-only scope docstring that R1 CTO Advisory #3 named but that did not land in commit `f406296`. One-line addition to spec line 992: "Scope is transport-only: session + headers + timeout + close(). Do NOT lift read-plane methods (`list_spaces`, `list_objects`, `get_object`) or write-plane methods (`create_type`, `create_property`, etc.) into this base class — they belong on their respective subclasses."
41. **[CTO]** Extend `_DASH_FOLDS` with U+00AD SOFT HYPHEN and U+2015 HORIZONTAL BAR. U+00AD in particular is a classic PDF-copy-paste vector — important for future PDF ingest flows. Update the AC v0.3.0 #6 parametrization accordingly.
42. **[CTO]** Legal's NOTICE file (Advisory #10) naturally captures `markdownify`'s transitive deps (`beautifulsoup4` MIT, `six` MIT). No separate spec change; noting for dependency-chain completeness.

## Resolutions

- **CTO's BLOCKING-CTO-1** is the single BLOCKING find and the sole reason this council does not re-endorse R1's sign-off at the same level. Fix is a spec-only edit (≤5 lines), not an impl-phase decision; it should land inline in the spec before the ticket advances to test.
- **Infra's A1 (bootstrap schema-compat loop)** and **CTO's BLOCKING-CTO-1** are independent spec-coherence issues in the same architectural section (v0.2.0 type refactor + schema compat). Both must land in the same rework.
- **CPO's ADV-CPO-R2-3 (committed `README.md:3` broader claim)** and **Legal's A5 (verification-record artifact)** are consolidated: the `README.md:3` line must be reconciled against the spec's narrower claim AND the verification record must ship as a committed `positioning-verification.md` artifact at v0.2.0.
- **R1's 26 advisories** remain in force; no R2 specialist dissents from them. R2 adds ~35 substantive new advisory items (after consolidation of duplicates), concentrated on test traceability (QA), supply-chain posture (Legal), and operational polish (Infra). The council's rough total across R1 + R2 is ~40 advisories, weighted toward v0.2.0 pre-release checklist items.
- **Calibration finding:** the R1 architectural defect manifested on #140 as ONE BLOCKING spec-coherence miss (BLOCKING-CTO-1) plus ~20 substantive advisory depth-shortfalls spread across CSO / CPO / QA / Infra / CTO. Legal's R1 assessment was substantially sound. The magnitude is LESSER than #172 (which had 3 BLOCKINGs), consistent with the shape of the defect — impersonators reproduce line citations easily but miss coherence audits that require independent mental modeling of the artifact under review.
- **No R2 specialist dissents from any R1 positive assessment.** The SSRF architecture, fcntl.flock design, per-version phasing, schema-compat approach, extraction-injection three-layer defense, MIT license posture, and per-version AC discipline are all endorsed. The deltas are additions, not reversals.

## Recommendation

**Recommended target:** `spec` (rework)
**Confidence:** high
**Rationale:**

The council has one BLOCKING finding (CTO-1) that must land before the ticket can advance. The fix is a spec edit of ≤5 lines resolving the `anytype_client.py` "unchanged vs. inherits" contradiction. This is not a design flaw — the architectural direction is correct — but the spec as committed is internally inconsistent in a way that will directly harm the impl phase.

A focused spec-rework pass should fold in BLOCKING-CTO-1 plus the highest-leverage of the R2 advisories that can be cheaply addressed at spec-edit time rather than pre-release-checklist time. Specifically:

**Must land in the spec-rework (BLOCKING + spec-coherence):**
- BLOCKING-CTO-1: `anytype_client.py` refactor clarification (≤5 lines).
- Infra A1: bootstrap-specific schema-compat path (1 sentence).
- CTO Advisory #40: `_BaseAnytypeClient` transport-only scope docstring (1 line).
- CPO Advisory #22: OQ #5 close (1 line).
- CPO Advisory #23: Delivery Phases honesty-tuning sentence (1 line).
- QA Advisories #24, #25, #26, #28, #29, #30: the six AC gaps (#24 four lint ACs; #25 two schema-compat ACs; #26 rollback AC; #28 prompt-injection AC resolution; #29 perf-wording alignment; #30 `patch-decision.md` ACs).
- Legal Advisory #12: LGPD phrasing precision in README additions (minor wording edit).
- CSO Advisory #1: extend bidi/control-char regex with U+FEFF, U+2028, U+2029, tag characters (1-line edit).
- CTO Advisory #41: extend `_DASH_FOLDS` with U+00AD, U+2015 (2-line edit + AC #6 parametrization).

**Can defer to v0.2.0 pre-release checklist (does not block advance):**
- All remaining security advisories (CSO #2–9): verification-script trap reorder, bandit baseline, port allowlist tightening, DNS tripwire, etc.
- All remaining legal advisories (Legal #10, #11, #13–17): NOTICE file, CONTRIBUTING inbound-license, positioning-verification.md, SECURITY.md, ToS pass-through, trademark footer, SBOM.
- All remaining product advisories (CPO #18, #19, #20, #21): v0.2.0 publish framing, README quick-start version stamping, README:3 reconciliation, 16 GB README defaults.
- All remaining infra advisories (Infra #34–39): doctor enhancements, sample configs, failure-mode gaps.

**After the spec rework lands and is re-verified, the ticket advances to `test` as R1 recommended.** The R1 verdict direction was correct; this R2 calibration tightens the conditions attached to that advance and surfaces the BLOCKING that R1 missed.

**Dissent:** None. All six council members agree on SIGN OFF WITH CONDITIONS subject to BLOCKING-CTO-1 being resolved. No specialist recommends escalation to Decide.

---

## Sign-offs

| Role | Verdict | File |
|------|---------|------|
| Chief Security Officer | SIGN OFF WITH CONDITIONS (0 BLOCKING, 10 ADVISORY) | `council-spec-r2-cso.md` |
| Legal Counsel | SIGN OFF WITH CONDITIONS (0 BLOCKING, 11 ADVISORY) | `council-spec-r2-legal.md` |
| Chief Product Officer | SIGN OFF WITH CONDITIONS (0 BLOCKING, 5 ADVISORY) | `council-spec-r2-cpo.md` |
| QA Director | SIGN OFF WITH CONDITIONS (0 BLOCKING, 12 ADVISORY) | `council-spec-r2-qa.md` |
| Infrastructure Lead | SIGN OFF WITH CONDITIONS (0 BLOCKING, 8 ADVISORY) | `council-spec-r2-infra.md` |
| Chief Technology Officer | SIGN OFF WITH CONDITIONS (**1 BLOCKING**, 4 ADVISORY) | `council-spec-r2-cto.md` |

**Council verdict:** SIGN OFF WITH CONDITIONS — subject to one BLOCKING spec-coherence fix. Recommended target: `spec` (rework). After rework, advance to `test` per R1 recommendation.
