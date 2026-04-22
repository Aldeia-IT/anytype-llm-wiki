# Council Meeting — Post-spec (Round 3, Post-rework Sign-off)

**Date:** 2026-04-23
**Ticket:** #140 — Wiki Library Module: Port LLM Wiki Pattern onto Anytype
**Phase reviewed:** spec
**Client:** anytype-llm-wiki (public OSS, MIT-licensed; pipeline tickets in aldeia-box)
**Spec under review:** `.aldeia/140-wiki-library-module-port-llm-wiki-pattern-onto-any/spec.md` (2123 lines, `status: SPEC`, `review_rounds: 2`, commit `b611f41`)

---

## Why this round exists

R2 calibration council (meeting `council-spec-r2.md`, commit `7bbf9bb`) ran after the R1 subagent-routing defect was repaired and caught **1 BLOCKING (CTO-1: `anytype_client.py` "unchanged vs inherits" contradiction across 7 spec touchpoints) + 42 ADVISORY findings** the R1 impersonator council had missed. Verdict was `SIGN OFF WITH CONDITIONS, target: spec (rework)`.

Per Jan's ticket feedback — *"Since we're addressing the blocking issue in a spec re-run, fix the advisory findings as well!"* and *"make sure it's well structured and documented withstanding the scrutiny of open source communities"* and *"phases of delivery — exact scope and requirements that must be met at each point"* — the spec team fixed BLOCKING-CTO-1 **plus all 42 advisories** in a single rework pass (commits `0176cb3`, `c35215d`, `b611f41`). R3 verification review (`review-r3.md`) independently confirmed APPROVED with three non-blocking SUGGESTIONs (two applied inline, one deferred to v0.2.0 tag housekeeping).

**This R3 council is the post-rework sign-off.** Purpose: validate the rework, surface any new regressions or second-order issues, and decide advancement to `test`.

## Attendance

| Role | Present | Reason |
|------|---------|--------|
| Council Chair | Yes | moderator; synthesis only |
| Chief Security Officer | Yes | minimum roster; raised 10 R2 advisories to spot-check |
| Legal Counsel | Yes | chair decision: 11 R2 advisories + CRA Art. 14 posture (effective 2026-06-11) |
| Chief Product Officer | Yes | minimum roster; 6 R2 advisories including README:3 reconciliation |
| QA Director | Yes | chair decision: 12 R2 advisories — biggest batch, AC mechanical-assertability central |
| Infrastructure Lead | Yes | chair decision: 8 R2 advisories including quasi-BLOCKING A1 (bootstrap schema-compat loop) |
| Chief Technology Officer | Yes | minimum roster; owner of BLOCKING-CTO-1, must verify coherence across 7 touchpoints |
| Client Advocate | No | anytype-llm-wiki is Jan's OSS project, not a client engagement; CPO represents Jan's interest (consistent with R1, R2) |

All six specialist members executed **independent** R3 assessments before reading this synthesis. Each wrote a standalone `council-spec-r3-{role}.md` with mandatory Verdict / Summary / R2-advisory-disposition table / Independent R3 findings / Regressions / Recommendation sections.

## Context Presented

Post-rework validation of the R2 calibration verdict's rework directive. Inputs to the council:

- `spec.md` at `status: SPEC`, 2123 lines, commit `b611f41` (net +211 lines vs R2 baseline `f406296`)
- `review-r3.md` — delta-only R3 verification review: **APPROVED** with 3 non-blocking SUGGESTIONs (R3-SG1 applied; R3-SG2 applied; R3-SG3 deferred to v0.2.0 tag housekeeping)
- `council-spec-r2.md` + six R2 specialist files (`council-spec-r2-{role}.md`) — the rework input
- Fixer traceability matrix: `debrief-fixer-r2.md` (one row per finding → disposition)
- Actual committed files: `README.md`, `LICENSE`, `CONTRIBUTING.md`, `pyproject.toml`, `src/anytype_llm_wiki/anytype_client.py`, `src/anytype_llm_wiki/indexer.py`

**Jan's ticket feedback carried forward:** (1) fix advisories as well as BLOCKING; (2) OSS-community scrutiny bar; (3) per-version phases-of-delivery discipline.

## Discussion

### CTO Assessment — SIGN OFF (BLOCKING-CTO-1 RESOLVED)

**BLOCKING-CTO-1 fully resolved.** `grep -n "unchanged in v0\.2\.x" spec.md` → **0 matches** (was 3 pre-rework). All seven R2-identified touchpoints now tell the same story:

| Touchpoint | Line | Post-rework narrative | Coherent |
|---|---|---|---|
| Contributor's Map | 24 | Names `anytype_client.py` as refactored in v0.2.0; three module-level wrappers preserve `indexer.py:11` import | Yes |
| Architecture Overview | 224 | Explicit "addresses BLOCKING-CTO-1 from R2" callout; 45-line baseline; thin-wrapper pattern | Yes |
| v0.2.0 Scope | 707 | Bold "refactored in v0.2.0 (NOT unchanged — resolves BLOCKING-CTO-1)" | Yes |
| Module Layout tree | 997 | Tree-node comment matches refactor narrative | Yes |
| Public API signatures | 1080–1116 | `_BaseAnytypeClient` class + transport-only docstring + `AnytypeReadClient(_BaseAnytypeClient)` + module-level wrappers with v0.1.0 signatures | Yes |
| Divergent Clients §S14 | 1140–1152 | Three-step refactor enumeration; full-merge deferred to v0.4.0+ (scope-consistent with Deferred Items line 1986) | Yes |
| AC v0.2.0 #12 | 742 | New AC exercises (a) class path, (b) wrapper path, (c) `indexer.py` importer regression | Yes |

Codebase alignment verified: `wc -l src/anytype_llm_wiki/anytype_client.py` → 45 (matches spec baseline verbatim). `indexer.py:11` is literally `from .anytype_client import get_object, list_objects, list_spaces`.

**R2 advisories landed:**
- CTO #40 (`_BaseAnytypeClient` transport-only docstring): PASS — verbatim at lines 1083–1091 AND echoed in §S14 at line 1142
- CTO #41 (`_DASH_FOLDS` + U+00AD, U+2015 → 10 codepoints): PASS — table, docstring enumeration, test table, AC v0.3.0 #6 parametrization all internally consistent ("10 codepoints")
- CTO #42 (markdownify transitive deps beautifulsoup4, six): PASS — captured in v0.3.0 pre-release checklist line 873 + Deferred Items line 1986

**No regressions.** §S14 full-merge deferral consistent with Deferred Items; Module Layout matches refactor; zero `anytype-rag` residuals in `src/` or `spec.md`.

**One ADVISORY:** R3-SG3 housekeeping residuals (vestigial `O_CREAT|O_EXCL` text in SIGKILL failure-modes row; "8 checks" vs 9-enum wording mismatch; em-dash anchor slugification) remain as an R2-inherited cleanup item, appropriately deferred to v0.2.0 tag housekeeping.

### Infrastructure Lead Assessment — SIGN OFF (unconditional)

**Bootstrap schema-compat exception (A33) holds under adversarial probing.** Infra walked through four scenarios — v0.3.0→v0.4.0 upgrade, mid-upgrade failure, cross-machine concurrent bootstrap, client-downgrade (newer vault) — none exhibit deadlock, self-recursion, or duplicate-property hazard. The fixer correctly chose in-compat-check exception (option a) rather than skip-check-entirely (option b); single-surface schema-compat preserved. `wiki_schema_upgrade_started` info log + `BootstrapResult.status: "ok"|"partial"` branches coherent.

All 8 R2 advisories landed verbatim (A33 bootstrap exception; A34 doctor statfs NFS/SMB/sshfs/CIFS WARN; A35 doctor Qdrant collection WARN-not-FAIL with reindex_anytype pointer; A36 sample `logrotate`+`newsyslog.conf` under `docs/samples/`; A37 16GB + ≥7B WARN with 3B fallback anchored to README two-defaults table; A38 failure-mode gaps — partial token scope + bootstrapped-but-empty wiki lint; A39 runtime metrics enumerated in Deferred Items; joint CSO/Infra A1 cross-machine bootstrap empirical probe on v0.2.0 pre-release checklist).

**Doctor cognitive load at 11 steps manageable:** 5 FAIL-class + 6 WARN-class, grep-friendly format, exit codes unchanged. Below disengagement threshold.

**Two-defaults config genuinely prevents 4.7 GB disappointment:** README two-defaults ship pre-install (CPO A21); doctor step 6b anchors to the README table by reference, not hardcoded model name; adopter sees fallback before pulling the model.

**No regressions.** Every R2 positive (fcntl.flock design, schema-compat, failure-modes table, permissions, Resource Impact, no launchd/Colima delta, `wiki.status` deferred) survives.

**0 BLOCKING, 0 new ADVISORY.**

### QA Director Assessment — SIGN OFF (with 2 test-phase-opening SHOULD-FIX)

All **12 R2 advisories** PASS with mechanical-assertability verified:

- A24 four lint ACs (v0.5.0 #8–#11) each name seeded shape, severity, count, detail; AC #8 carries v0.6.0 re-test note for passive state
- A25 schema-compat three-tier coverage (v0.2.0 #13 `_outdated` with bootstrap exception; v0.3.0 #14 `_newer` warn-and-continue; v0.4.0 #8 both for query)
- A26 bidirectional rollback (v0.3.0 #13) names invariant + `relation_rollback` WikiLog event + specific failure injection (mock B→A PATCH to 500)
- A27 concurrent-ingest mechanism — both AC v0.3.0 #5 inline AND Test Plan line 1913 explicitly require `multiprocessing.Process`, explicitly reject threads/async/mocked lock
- A28 prompt-injection AC (v0.3.0 #12) — option (b) picked cleanly with `is_central=true` filter as final assertion; second test case covers name-policy-trip branch (stronger than a pure option-a or option-b pick)
- A29 perf-wording — all three Success Criteria lines (1852/1872/1880) carry "Jan's Mac Mini M4" qualifier matching ACs
- A30 patch-decision.md three-tier chain (v0.2.0 #14 / v0.3.0 #15 / v0.4.0 #9) with ordering assertion
- A31 Wikipedia fixture — archive.org snapshot release-gated on v0.3.0 pre-release checklist
- A32 partial-failure idempotency (v0.3.0 #18) — ships resume as default with v0.6.0 alternative documented

New AC **v0.2.0 #12** (BLOCKING-CTO-1 coverage) exercises three paths cleanly. Traceability matrix: every MoSCoW Must per version has ≥1 AC **except** v0.5.0 MoSCoW names `--json`/`--human` CLI output modes without a dedicated AC (flagged SG-4, non-blocking).

**Two SHOULD-FIX at test-phase opening** (not spec-gating):
- **QA-SF-1:** AC v0.3.0 #18 resume-vs-defer branch choice must be locked before test authoring begins.
- **QA-SF-2:** AC v0.3.0 #13 bidirectional rollback deserves a one-line Test Plan bullet for traceability polish.

Zero regressions on R1 invariants (dash-fold parametrization; 199/200/201 boundary; concurrent-ingest three-assertion).

### CSO Assessment — SIGN OFF WITH CONDITIONS (3 ADVISORY, 0 BLOCKING)

All 10 R2 CSO advisories PASS. Most were elevated from "can defer to v0.2.0 pre-release checklist" to "verbatim checklist item in spec" per Jan's OSS-scrutiny directive — stronger than the R2 recommendation. SSRF seven-invariant set, `fcntl.flock` kernel-held lock, `is_central` cross-check against source structure, three-layer prompt-injection fence all survived the rework intact. The `addr.ipv4_mapped is not None` guard at line 1756 is still correctly written (not the truthy-bug form). `source_ref` redaction at line 1579 is a new R2 hardening.

**Three new R3 ADVISORY** (all strengthenings, non-blocking):
1. **R3-CSO-1** — Bidi/control-char regex at `spec.md:1815` uses literal invisible/bidi characters instead of `\uXXXX` escapes. Maintenance-fragile under editor round-trips and invisible in diffs. One-line fix during v0.3.0 implementation.
2. **R3-CSO-2** — `pyproject.toml:4` description still carries the pre-rework broader "first open-source LLM wiki that uses a typed knowledge-graph store" claim. R2 rework reconciled `README.md:3` but did not update PyPI metadata. This ships the unverified broader claim to pypi.org at first PyPI publish. One-line fix on v0.2.0 pre-release checklist. **(Cross-thread consolidated with Legal R3-L-1 below.)**
3. **R3-CSO-3** — `source_ref` redaction logic is specified in prose but not asserted by any AC. No test enforces that the lock payload contains neither query-string nor userinfo; no guidance for file-path sources (no scheme/host). One-AC addition to v0.3.0.

### Legal Counsel Assessment — SIGN OFF (3 ADVISORY, 0 BLOCKING)

All **11 R2 Legal advisories** disposed satisfactorily. Spot-check passes end-to-end:
- **A3 LGPD phrasing** — verbatim at spec line 656
- **A5 positioning-verification.md** — named at spec line 179 (narrative) + line 768 (checklist) + `README.md:7` (inline note)
- **A7 SECURITY.md + CRA Art. 14 rationale** — landed at spec line 776 with exact regulation (EU 2024/2847), exact effective date (2026-06-11), Aldeia-IT marketing-framing monitoring note preserved. Strongest R2 ask; executed faithfully.
- **A1 NOTICE + pip-licenses CI** — spec lines 773–774, reaffirmed across v0.3.0/v0.4.0/v0.5.0 checklists (distinct from pip-audit)
- **A2 CONTRIBUTING.md inbound-license** — verbatim paragraph pre-committed in spec checklist at line 775
- **A9 Trademarks footer** — verbatim at spec lines 666–670 + checklist at 777
- **A10 Hosted-LLM ToS pass-through** — verbatim at spec line 652 + checklist at 778
- **A8 SBOM (Tier 2)** — appropriately deferred with CTO #42 transitive-deps note at spec line 1986

MIT integrity intact; no GPL/AGPL contamination in the dep matrix. `README.md:3` reconciled ("To our knowledge, the first Anytype-native LLM wiki…") with pre-committed fallback one-liner; casual community prior-art check finds no Anytype-native LLM wiki predecessor.

**Three R3 ADVISORY** (non-gating):
1. **R3-L-1** — `pyproject.toml:4` description still carries the broader claim (independent rediscovery of CSO R3-CSO-2). Gating for PyPI publish, not spec advancement. **(Consolidated cross-thread below.)**
2. **R3-L-2** — CONTRIBUTING.md inbound-license paragraph is pre-committed on the checklist; consider lifting to an immediate edit of `CONTRIBUTING.md` for belt-and-braces. Low-cost, non-blocking.
3. **R3-L-3** — Calendar reminder for 2026-05-15 (four weeks before CRA Art. 14 effective) to re-check Commission interpretation of "commercial activity."

### CPO Assessment — SIGN OFF (unconditional)

All **6 R2 CPO advisories** PASS; two exceeded the R2 request.

- **A18 v0.2.0 PyPI-publish decision** — checklist at line 769 + conditional git-tag logic at line 793. Recommended resolution (tag in git only, first PyPI publish at v0.3.0 when ingest lands) adopted.
- **A19 15-min quick-start version-stamp** — three-touchpoint update: user story scope-note at line 63 + Success Criteria rename to "Community Quick-Start (v0.4.0)" at line 1885 + v0.2.0 checklist at line 770. Exceeds R2 request.
- **A20 README:3 reconciliation** — file-level fix (actual `README.md:3` rewritten, not just spec narrative) + `README.md:7` inline note + spec §reconciliation at line 181 + pre-release checklist at line 768. Grep of broader claim on README → 0 matches. Exceeds R2 request.
- **A21 two README defaults 32/16 GB** — four-touchpoint consistency: spec lines 863–866 config table + 1946–1950 OQ #3 + 1631–1632 Resource Impact + 868 quality spot-check. Doctor WARN anchors to README table by reference.
- **A22 OQ #5 closure** — verbatim "Resolved 2026-04-22" at line 1954 + cross-ref at checklist line 781 (R3-SG1 casing nit from R3 verification already fixed in commit `b611f41`)
- **A23 Delivery Phases honesty sentence** — three-sentence paragraph at line 690 stronger than one-sentence R2 ask; names v0.2.0 as weak-link version, ties back to A18 PyPI decision. Exceeds R2 request.

Per-version "phases of delivery" story got strictly stronger with no scope-creep (checked explicitly for failure modes: new functional surface, checklist→AC elevation without coherence, spec-becomes-operator-manual — none present). Net +211 lines is proportional to six-specialist load with zero spurious additions. v0.2.0 standalone community value remains weak but is now honestly framed — weakness honestly framed is a stronger OSS product than weakness elided. README/positioning credibility passes OSS diligence.

One non-blocking SUGGESTION (R3-CPO-SG1: cross-link §Delivery Phases honesty note from v0.2.0 Scope block) for v0.2.0 tag time.

### Cross-thread resolutions

- **`pyproject.toml:4` broader-claim residual (CSO R3-CSO-2 + Legal R3-L-1)** — independent rediscovery by two specialists. The R2 rework tightened `README.md:3` but missed the parallel wording in `pyproject.toml` that ships to pypi.org. **Consolidated resolution:** add one item to the v0.2.0 pre-release checklist — "Update `pyproject.toml:4` description to match the `README.md:3` wording before first PyPI publish." Not spec-gating; gating for PyPI publish. Recommended to land inline in this spec-edit rework or be queued as the first v0.2.0 impl-phase task.
- **QA SF-1 (AC v0.3.0 #18 branch-choice lock) + QA SF-2 (bidirectional rollback Test Plan polish)** — both are test-phase-opening, not spec-gating. Test-phase lead owns them.
- **R3-SG3 housekeeping (CTO) + R3-CPO-SG1 cross-link** — both appropriately deferred to v0.2.0 tag-time cleanup pass.

### Observations on the R2 rework's shape and the R1/R2/R3 calibration arc

The rework did exactly what the R2 council directed, plus what Jan directed on top. Specifically:
- **BLOCKING-CTO-1** resolved with a +211-line architecture update across seven touchpoints; every touchpoint verified coherent by both the R3 verification review and this council's CTO independently.
- **All 42 R2 advisories** landed with either verbatim content or stronger-than-requested execution (CPO A19/A20/A23 exceeded R2 ask; CSO advisories were elevated from "checklist" to "spec verbatim").
- **No new BLOCKINGs** surfaced from real-specialist R3 scrutiny.
- **Few, small new ADVISORIES** — three from CSO (one cross-thread with Legal), three from Legal (one cross-thread with CSO, one belt-and-braces, one calendar reminder), two test-phase-opening SHOULD-FIX from QA, one housekeeping ADV from CTO, one SG from CPO. Total: ~10 items, all genuinely minor, mostly test-phase or pre-release-checklist scoped.

The **R1→R2→R3 calibration arc** is a clean learning trace. R1 impersonators signed off missing 1 BLOCKING + ~20 substantive advisories. R2 real specialists caught them. R3 real specialists verify the rework holds and surface only small, proportionate finds. The spec is stronger than R1's APPROVED version and materially stronger than the R2 baseline the rework operated on.

## Findings

### BLOCKING

_None._

### ADVISORY

**Cross-thread (pyproject.toml consistency):**

1. **[CSO + Legal]** `pyproject.toml:4` description still reads "…first open-source LLM wiki that uses a typed knowledge-graph store" — the pre-rework broader claim. R2's reconciliation of `README.md:3` did not propagate to PyPI metadata. **Resolution:** add to v0.2.0 pre-release checklist: "Update `pyproject.toml:4` description to match the `README.md:3` wording before first PyPI publish." Recommend landing inline in the spec edit or as first v0.2.0 impl task.

**Security:**

2. **[CSO]** Bidi/control-char regex at `spec.md:1815` uses literal invisible chars. Swap to `\uXXXX` escapes during v0.3.0 implementation for diff-visibility and editor round-trip safety.
3. **[CSO]** Add v0.3.0 AC asserting `source_ref` redaction in lock payload (no query-string, no userinfo; file-path case documented).

**Legal:**

4. **[Legal]** Consider lifting the CONTRIBUTING.md inbound-license paragraph from pre-release checklist to an immediate edit of `CONTRIBUTING.md` (belt-and-braces; low cost).
5. **[Legal]** Add calendar reminder for 2026-05-15 to re-check EU Commission guidance on CRA Art. 14 "commercial activity" interpretation (four weeks before effective).

**QA (test-phase-opening SHOULD-FIX):**

6. **[QA]** Lock AC v0.3.0 #18 resume-vs-defer branch choice before test authoring begins.
7. **[QA]** Add a one-line Test Plan bullet naming the bidirectional-relation rollback test for traceability polish (AC v0.3.0 #13).
8. **[QA]** v0.5.0 MoSCoW names `--json`/`--human` CLI output modes without a dedicated AC. Add before test authoring, or record as explicitly out-of-test-scope.

**Technical / Housekeeping:**

9. **[CTO]** R3-SG3 housekeeping (vestigial `O_CREAT|O_EXCL` text in SIGKILL failure-modes row; "8 checks" vs 9-enum wording mismatch; em-dash anchor slugification) remains deferred to v0.2.0 tag housekeeping.
10. **[CPO]** Cross-link §Delivery Phases honesty note from v0.2.0 Scope block for contributor visibility (v0.2.0 tag-time cleanup).

## Resolutions

- **R2 BLOCKING-CTO-1 resolved.** Unanimous sign-off from six real specialists.
- **R2 42 ADVISORY fully disposed.** Each specialist independently verified their own R2 items — 10 + 11 + 6 + 12 + 8 + 3 = 50 R2-advisory-items (with some items carrying multiple sub-items) all landed with substance preserved or exceeded.
- **R3 findings** total ~10 items across 6 specialists — none BLOCKING; most are test-phase-opening, v0.2.0 pre-release-checklist, or v0.2.0 tag-time housekeeping scope. The only cross-thread item (pyproject.toml description) is PyPI-publish-gating, not spec-gating.
- **No R3 specialist dissents from any R2 or R1 positive assessment.** SSRF architecture, fcntl.flock design, per-version phasing, schema-compat + bootstrap exception, prompt-injection three-layer defense, MIT posture, per-version AC discipline, BLOCKING-CTO-1 refactor architecture all endorsed.

## Recommendation

**Recommended target:** `test`
**Confidence:** high
**Rationale:**

The R2 council's BLOCKING + 42 ADVISORY rework directive is fully executed. All six real specialists independently verify the rework's substance with zero BLOCKING findings at R3. The R3 ADVISORY set is small, proportionate, and appropriately scoped to test-phase-opening, v0.2.0 pre-release checklist, or v0.2.0 tag-time housekeeping — none gates advancement.

The spec now withstands OSS community scrutiny per Jan's primary directive: per-version phases-of-delivery discipline is the backbone; OSS-hygiene artifacts (NOTICE, SECURITY.md, CONTRIBUTING.md inbound grant, positioning-verification.md, .bandit baseline, hosted-LLM ToS pass-through, Trademarks footer, dep-pinning disclosure) are named in the spec with required contents; LGPD/GDPR phrasing is legally precise; CRA Art. 14 preparation is on the v0.2.0 pre-release path; README:3 positioning is reconciled at the file level.

**Next-phase pickup list for the test phase lead:**

- **Inline-in-spec (optional before advancing):** consolidated cross-thread item on `pyproject.toml:4` — add one line to v0.2.0 pre-release checklist. Recommend landing as a trivial spec edit before the ticket moves.
- **Test-phase-opening (before test authoring):** lock AC v0.3.0 #18 resume-vs-defer branch; add bidirectional rollback Test Plan bullet; add/scope v0.5.0 CLI output-modes AC.
- **v0.2.0 pre-release checklist (impl phase):** all ~25 items enumerated in the spec + the new pyproject.toml line.
- **v0.2.0 tag-time housekeeping:** R3-SG3 items (vestigial text, count mismatches, em-dash anchors) + R3-CPO-SG1 cross-link.

**Dissent:** None. Six specialists, six SIGN OFFs (three unconditional, three SIGN OFF WITH CONDITIONS where the conditions are all ADVISORY-class). No specialist recommends further spec rework; no specialist recommends escalation to Decide.

---

## Sign-offs

| Role | Verdict | BLOCKING | ADVISORY | File |
|------|---------|----------|----------|------|
| Chief Technology Officer | SIGN OFF | 0 | 1 | `council-spec-r3-cto.md` |
| Infrastructure Lead | SIGN OFF (unconditional) | 0 | 0 | `council-spec-r3-infra.md` |
| QA Director | SIGN OFF | 0 | 2 SHOULD-FIX + 4 SUGGESTION | `council-spec-r3-qa.md` |
| Chief Security Officer | SIGN OFF WITH CONDITIONS | 0 | 3 | `council-spec-r3-cso.md` |
| Legal Counsel | SIGN OFF | 0 | 3 | `council-spec-r3-legal.md` |
| Chief Product Officer | SIGN OFF (unconditional) | 0 | 1 SUGGESTION | `council-spec-r3-cpo.md` |

**Council verdict:** **SIGN OFF — advance to `test`.** BLOCKING-CTO-1 resolved; all 42 R2 advisories landed; the small R3 ADVISORY set is proportionate and appropriately scoped below spec-gating. The spec is OSS-community-scrutiny ready per Jan's primary directive.
