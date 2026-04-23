# Council Meeting — Post-test (Round 1)

**Date:** 2026-04-23
**Ticket:** Aldeia-IT/aldeia-box#140 — Wiki Library Module: Port LLM Wiki Pattern onto Anytype
**Phase reviewed:** test (v0.2.0 failing-test scaffolding)
**Client:** anytype-llm-wiki (public OSS, MIT-licensed; pipeline tickets in aldeia-box)
**Branch:** `test/wiki-library-module-port-llm-wiki-pattern-onto-any`
**Commit under review:** `8f94d09` (R2 APPROVED head; includes r1-fixer `ab25890` that resolved 2 BLOCKING + 4 SHOULD-FIX)
**Test-review cycle:** R1 NEEDS CHANGES (commit `dfc8ae8`) → r1-fixer (`ab25890`) → R2 APPROVED (`8f94d09`)
**Final test-run shape:** 193 failed / 6 passed / 6 skipped / 3 xfailed

---

## Attendance

| Role | Present | Reason |
|------|---------|--------|
| Council Chair | Yes | moderator; synthesis only |
| QA Director | Yes | minimum roster — AC coverage central to test phase |
| Chief Technology Officer | Yes | chair decision — BLOCKING-CTO-1 test-gate coverage (AC #12, refactor regression) |
| Chief Security Officer | Yes | chair decision — AC #15 credential scrubbing was R1 BLOCKING-B1 (CSO domain); scrubbing is security-relevant |
| Infrastructure Lead | Yes | chair decision — real `multiprocessing.Process` + `fcntl.flock` concurrency test, doctor 12-check enumeration, CI readiness |
| Chief Product Officer | Yes | chair decision — scope discipline (v0.2.0-only), verbatim privacy-notice contract, test-as-contract over-specification risk |
| Legal Counsel | No | chair decision — test phase introduces no new data-handling or regulatory surface; R3 Legal advisories already landed in spec |
| Client Advocate | No | anytype-llm-wiki is Jan's OSS project, not a client engagement; CPO represents Jan's interest (consistent with R1/R2/R3 spec councils) |

All five specialists executed **independent** R1 post-test assessments before this synthesis. Each wrote a standalone file (`council-test-r1-{role}.md`) with Verdict / Summary / spot-checks / Findings / Recommendation sections.

---

## Context Presented

Post-test governance review of a phase that itself completed a R1 → R1-fixer → R2 APPROVED cycle. Inputs to the council:

- `tests/wiki/` (8 new files) + `tests/test_anytype_client.py` extensions + `tests/test_server.py` docstring update + `pyproject.toml` 4 new dev deps at commit `8f94d09`
- `test-review-r1.md` (NEEDS CHANGES — 2 BLOCKING + 4 SHOULD-FIX)
- `test-review-r2.md` (APPROVED — all 6 R1 findings verified fixed)
- `phase-summary-test.md` — lead's honest assessment including "Problems Discovered" (watcher test-branch-from-main gap; sandbox `uv run pytest` block; two real BLOCKING defects caught by R1)
- `council-spec-r3.md` + six R3 spec-council specialist files — prior post-spec sign-off with deferred test-phase-opening SHOULD-FIX items (QA-SF-1/2/3) and carry-forward advisories (R3-CSO-1/2/3)
- `spec.md` at `status: SPEC`, commit `b611f41` — authoritative 15-AC contract for v0.2.0

**Jan's ticket feedback carried forward:** *"Since we're addressing the blocking issue in a spec re-run, fix the advisory findings as well!"* — applied in spirit to this post-test round: specialists were asked to identify advisories that could be cheaply landed before impl begins rather than reflexively deferring.

---

## Discussion

### QA Director — SIGN OFF (0 BLOCKING, 3 ADVISORY)

All 15 v0.2.0 ACs are covered by substantive tests. Three spot-checks at file level (AC #5 union-only re-bootstrap, AC #13 `schema_upgrade` section, AC #15 scrubbing) all substantive and spec-anchored. `check_anytype` fixture refactor (module-level → class-level autouse) is clean — three v0.1.0 live test classes (lines 53, 71, 91 of `test_anytype_client.py`) explicitly opt in; five v0.2.0 mock classes do not. Concurrency test uses `multiprocessing.Process` per spec line 1913 (confirmed at `test_util.py:261`). Pre-impl failure signal (193/6/6/3) is credible — 189 raw `def test_` × parametrization expansion matches 208 collected items. Three prior-spec-council QA SHOULD-FIX items (QA-SF-1/2/3) correctly deferred to v0.3.0+/v0.5.0 scope phases. Surfaces three ADVISORIES: A1 (tighten spec `schema_upgrade` key contract), A2 (xfail audit discipline for v0.3.0), A3 (impl lead must understand pre-release checklist co-gating).

### Chief Technology Officer — SIGN OFF (0 BLOCKING, 2 ADVISORY)

**BLOCKING-CTO-1 test-gate is fully covered.** Spot-checked four test classes spanning two files; each of the three AC #12 paths (class / module-wrapper / `indexer.py` import regression) is gated by substantive assertions that fail pre-impl, not skip:

- `tests/test_anytype_client.py::TestAnytypeReadClientClassPath` (lines 125–195) — 4 respx-mocked methods
- `tests/test_anytype_client.py::TestModuleWrapperPath` (lines 198–250)
- `tests/test_anytype_client.py::TestImportRegressionIndexer` (lines 253–270) — reproduces `indexer.py:11`'s exact import
- `tests/wiki/test_base_client.py::TestInheritanceHierarchy` (lines 105–129) + `TestBaseClientHasNoReadOrWriteMethods` (74–102, parametrized across 9 method names)

Refactor-coherence clean. R3-CSO-1 `\uXXXX` escape form: byte-level verified — all 10 dash-fold rows are pure ASCII. R2 reviewer diligence is rigorous (grep-verified removal, named each new method by line number, byte-scanned for non-ASCII, specifically checked FAIL-not-SKIP for AC #11). Two ADVISORIES, both inherited from earlier rounds and non-blocking: `test_missing_space_returns_config_error` silent-skip on raise (inherited pattern, R2-flagged not-a-regression); duplicate inheritance-hierarchy assertion across two files (belt-and-suspenders, defensible).

### Chief Security Officer — SIGN OFF WITH ADVISORIES (0 BLOCKING, 6 ADVISORY: 4 actionable pre-impl + 2 v0.3.0 carry-forward)

**R1 BLOCKING-B1 (tautological QDRANT_URL test — CSO domain) genuinely resolved.** New `TestCredentialScrubbing` at `tests/wiki/test_util.py:310` calls `scrub_credentials` directly. Grep of `wiki_bootstrap` in the test file → zero matches (tautology re-introduction path closed). Six invariants span value-scrubbed, query-form-scrubbed, and host-preserved across both QDRANT_URL api_key and userinfo password shapes. **R3-CSO-1 escape form** verified at byte level: every non-ASCII byte in `test_util.py` lives in docstrings, prose comments, or `\uXXXX` escape sequences — never in DATA strings. **R3-CSO-2 resolved** (`pyproject.toml:4` carries reconciled narrower claim). **R3-CSO-3** partially pre-empted by `TestSpaceIngestLockSourceRefRedaction` at `test_util.py:196–227`.

Surfaces **four actionable-pre-impl** advisories (three of them the same defect class as R1 SF-1 that the test reviewer caught and fixed — weak OR-disjunctions in spec-verbatim assertions, plus one packaging defect with safety-signal implications):

- **R1-CSO-A1** — `test_bootstrap.py:609` AC #9 `test_403_on_create_type_returns_config_error` uses `or`; spec line 739 requires both `[CONFIG ERROR]` AND `insufficient_token_scope`.
- **R1-CSO-A2** — `test_bootstrap.py:630` AC #9 `test_insufficient_scope_error_mentions_settings_api` splits "Settings" + "API" into independent `in` checks; spec requires the load-bearing "Settings → API" operator breadcrumb.
- **R1-CSO-A3** — `test_bootstrap.py:583` AC #8 `test_readme_contains_gdpr_controller_statement` uses `or`; spec AC #8 requires verbatim privacy notice containing BOTH GDPR and controller (+more — see CPO A-CPO-T2).
- **R1-CSO-A4** (cross-thread CTO/Infra) — `psutil>=5.9` in dev deps only; doctor command calls `psutil.virtual_memory()` at **runtime** (spec lines 1165, 1633). Packaging defect; consumers installing via `pip install anytype-llm-wiki` (no `[dev]` extra) will see `ModuleNotFoundError` when running `anytype-llm-wiki doctor`. Safety-signal continuity concern (check 6b is OOM-kill prevention).

Two carry-forward to v0.3.0 test phase: R1-CSO-A5 (end-to-end `[API ERROR]` scrubbing via `wiki_ingest` + forced Qdrant 500), R1-CSO-A6 (file-path source_ref redaction — R3-CSO-3 unresolved half).

### Infrastructure Lead — SIGN OFF (0 BLOCKING, 2 ADVISORY)

Doctor 12-check `EXPECTED_CHECK_NAMES` enumeration verified line-by-line against spec 1158–1169: all 12 names match including check 4b (`qdrant_collection`), check 6b (`ollama_extraction_model_ram_fit`), check 7 (`wiki_lock_dir`), and check 9 (`wiki_lock_dir_fs_type`). Concurrency test at `test_util.py:243–281` uses real `multiprocessing.Process` + real `fcntl.flock` — no threads, no asyncio, no mocked lock (per spec line 1913). Verification script tests (AC #7) exercise trap-before-probe ordering, conditional guards, stderr routing, `ANYTYPE_OBJECT_ID` absence. Cross-host bootstrap probe correctly stays a pre-release checklist item (spec line 765), not pre-authored. Zero launchd / Colima / Docker / ntfy / Caddy impact. Two advisories:

- **Infra-A1** — `time.sleep(0.3)` handoff in concurrency test at `test_util.py:268` is a CI flake vector on loaded runners. Replace with `result_queue.get(timeout=5)` sentinel read (child already puts `"acquired"`). Two-line edit.
- **Infra-A2** — `uv.lock` drift: 4 new dev deps added to `pyproject.toml` (`respx>=0.21`, `pytest-timeout>=2.2`, `freezegun>=1.5`, `psutil>=5.9`) but lock not regenerated. Impl-phase opening must run `uv sync --extra dev` and commit refreshed lock before any src-code edits.

### Chief Product Officer — SIGN OFF (0 BLOCKING, 2 ADVISORY)

Scope discipline PASS: v0.3.0+ surfaces touched only through three `strict=False` xfail scaffolds (AC #13/#14 activation paths); QA SF-1/2/3 carry-overs correctly deferred; v0.2.0 helpers (`normalize_title`, `space_ingest_lock`, `scrub_credentials`) tested in isolation with no integration over-reach. R3 CPO advisories A18–A23 verified still landed (spec.md:690, :768, :769, :770, :1954; README.md:3, :7). AC #9 "Settings → API" adequately gated (pragmatic, ASCII-safe — though CSO R1-CSO-A2 strengthens it). AC #10 exit-code contract correctly enforced. Delivery-phase honesty note (line 690) intact — v0.2.0 as "structurally shippable" with honest user value framed as "schema scaffolding + preflight diagnostics". Two advisories:

- **A-CPO-T1** — Test hardcodes `schema_upgrade` keys (`from`/`to`/`properties_added`) and 12 doctor check-names that are test-invented, not spec-mandated. Impl kickoff brief should name the test as the contract (or amend spec line 1604 with one-sentence clarification). **(Cross-thread with QA A1.)**
- **A-CPO-T2** — AC #8 verbatim-privacy-notice test is too loose (4 substring checks) to catch good-faith truncation. Spec requires full 10-bullet block plus hosted-LLM ToS paragraph, Qdrant/Ollama off-localhost warning, content-rights-and-PII paragraph, and GDPR Art. 4(7) + LGPD Art. 5(VI) controller disclaimer. Recommended fix: `tests/wiki/fixtures/readme_privacy_notice_verbatim.md` fixture file + single `assert FIXTURE_CONTENT in README_TEXT` assertion (~30 min). **(Cross-thread with CSO R1-CSO-A3.)**

### Cross-thread resolutions

1. **`psutil` packaging defect** (CSO R1-CSO-A4 ↔ Infra ADVISORY cross-thread-to-CTO ↔ implicit-product-risk). Three specialists converge: runtime dep, not dev-only. One-line pyproject.toml edit. **Consolidated as addendum item #1.**
2. **Weak OR-disjunction assertions on AC #8 / AC #9** (CSO R1-CSO-A1 + R1-CSO-A2 + R1-CSO-A3). Same defect class as the R1 SF-1 that the test reviewer caught (AC #3). Three one-line test edits. **Consolidated as addendum items #2, #3, #4.**
3. **Verbatim-privacy-notice gating strength** (CPO A-CPO-T2 ↔ CSO R1-CSO-A3). Two specialists recommend replacing the loose substring checks with a fixture-file verbatim-match. Legal-compliance contract (GDPR Art. 4(7) + LGPD Art. 5(VI) disclaimer is spec-required). **Consolidated as addendum item #5.** Subsumes CSO R1-CSO-A3 when addressed via fixture-file.
4. **Test-as-contract documentation** (CPO A-CPO-T1 ↔ QA A1). Impl kickoff brief names the test as contract for `schema_upgrade` keys and doctor check-names. No spec edit required if brief is captured. **Consolidated as addendum item #6.**
5. **CI flake + uv.lock drift** (Infra-A1 + Infra-A2). Two small impl-opening hygiene items. **Consolidated as addendum items #7 and #8.**

### Observations on R1 test-reviewer diligence

The R1→R2 test-review cycle caught two genuinely meaningful BLOCKING defects (B1 tautology, B2 autouse-skip) and four SHOULD-FIX items, all correctly resolved by the r1-fixer. The council's R1-CSO-A1/A2/A3 findings are of the same defect class (weak OR-disjunction on spec-verbatim assertions) but were missed by R1 because R1's assertion-correctness pass focused on AC #3 and stopped there. This is a **convention gap** rather than a reviewer defect: the R1 review had no standing rule against OR-disjunctions, so catching them was opportunistic. Test-writer convention for v0.3.0+: "no `or` between spec-verbatim substrings unless the spec explicitly names an either-or contract."

Test-writer pre-emptively applied R3-CSO-1 escape-form discipline (dash-fold table is pure ASCII `\uXXXX`) and R3-CSO-3 URL-redaction (source_ref URL redaction tested) without being formally directed — a sign of attentive reading of the R3 spec-council output.

### Observations on R1/R2/R3 (spec) → R1/R2 (test) calibration arc

Spec R1 impersonators missed 1 BLOCKING + ~20 advisories. Spec R2 real-specialist calibration caught them. Spec R3 real-specialist post-rework sign-off verified the rework held. Test R1 real-reviewer caught 2 BLOCKING + 4 SHOULD-FIX. Test R2 verified the r1-fixer rework. Post-test R1 council surfaces 8 consolidated advisories (6 of them actionable pre-impl, 2 process/carry-forward). The pipeline's calibration continues to improve: the real-specialist signal survives the handoff between phases, and the cross-phase carry-forwards (R3-CSO-1 → test-writer pre-emption; R3-CSO-3 → partial pre-emption) demonstrate that spec-phase advisories land in the next phase's artifacts when they're specific enough.

---

## Findings

### BLOCKING

_None._

### ADVISORY

**Cross-thread / packaging (highest impact):**

1. **[CSO + Infra + CTO]** `psutil>=5.9` is in `[project.optional-dependencies].dev` only; used at runtime by doctor command (spec 1165, 1633). Move to `[project].dependencies`. Packaging defect; doctor safety-signal (OOM-kill prevention) continuity depends on it. `pyproject.toml` two-line edit. **Pre-impl actionable.**

**Test assertion strengthenings (same class as R1 SF-1 that was caught):**

2. **[CSO]** `tests/wiki/test_bootstrap.py:609` — change `or` → `and` (AC #9 `test_403_on_create_type_returns_config_error`). **Pre-impl actionable.**
3. **[CSO]** `tests/wiki/test_bootstrap.py:630` — replace `"Settings" in result_str and "API" in result_str` with `"Settings → API" in result_str` (the spec's operator breadcrumb). **Pre-impl actionable.**
4. **[CSO]** `tests/wiki/test_bootstrap.py:583` — change `or` → `and` (AC #8 `test_readme_contains_gdpr_controller_statement`). **Pre-impl actionable** (or subsumed by item #5 below).

**Verbatim privacy-notice contract:**

5. **[CPO + CSO]** Replace loose 4-substring AC #8 coverage with a `tests/wiki/fixtures/readme_privacy_notice_verbatim.md` fixture-file containing the full 10-bullet block from spec lines 645–656 (plus hosted-LLM ToS paragraph, content-rights-and-PII paragraph, GDPR Art. 4(7) + LGPD Art. 5(VI) disclaimer). Single `assert FIXTURE_CONTENT in README_TEXT` assertion. Legal-compliance-gate strengthening. **Pre-impl actionable (~30 min).**

**Test-as-contract documentation:**

6. **[CPO + QA]** Impl kickoff brief explicitly names the test as contract for `schema_upgrade` keys (`from`/`to`/`properties_added`) and doctor check-name strings (`EXPECTED_CHECK_NAMES` list in `test_doctor.py:105–118`). No spec edit required. **Pre-impl actionable (one-paragraph brief).**

**CI/operational hygiene:**

7. **[Infra]** Replace `time.sleep(0.3)` with `result_queue.get(timeout=5)` sentinel read at `tests/wiki/test_util.py:268` for deterministic concurrency-test handoff. **Pre-impl actionable.**
8. **[Infra]** Run `uv sync --extra dev` at impl-phase opening; commit refreshed `uv.lock` before any src-code edits. **Impl-opening actionable.**

**Carry-forward to v0.3.0 test phase (not v0.2.0 scope):**

9. **[CSO]** R1-CSO-A5 — End-to-end `[API ERROR]` integration-tier scrubbing assertion once `wiki_ingest` lands.
10. **[CSO]** R1-CSO-A6 — File-path source_ref redaction AC (basename-only or hashed) — R3-CSO-3 unresolved half.
11. **[QA]** A2 — `strict=False` xfail audit discipline: v0.3.0 test-phase lead must audit the 3 xfail markers (AC #13/#14) and flip to `strict=True` during authoring, or remove when the underlying feature lands.

**Process / impl-phase awareness:**

12. **[QA]** A3 — Impl opening must explicitly surface that `pytest -xvs` green ≠ ship. Spec lines 762–794 pre-release checklist (esp. AC #6 p95 timing, AC #7 live verification script) is co-gating and maintainer-measured.

**Inherited / observational (no action required):**

13. **[CTO]** `test_missing_space_returns_config_error` silent-skip on raise (inherited from R1 pre-fix pattern; R2-flagged not-a-regression).
14. **[CTO]** Duplicate inheritance-hierarchy assertion between `test_anytype_client.py::TestBaseClientInheritance` and `test_base_client.py::TestInheritanceHierarchy` — belt-and-suspenders, defensible.
15. **[CPO]** `test_exit_code_0_when_all_checks_pass` accepts `0 OR 2` — mild weakening of AC #10 "exits 0 on fresh install" contract, not a product-blocker.

---

## Resolutions

- **R1 test-review BLOCKING-B1 (tautological QDRANT_URL scrubbing) and BLOCKING-B2 (autouse-skip gating AC #11)** fully resolved in the r1-fixer commit `ab25890`. Independently re-verified by CSO (B1, CSO's own domain) and QA (B2) at the council.
- **R1 test-review SHOULD-FIX-1 through SHOULD-FIX-4** all resolved; R2 review and this council both verify.
- **R3 spec-council carry-forwards:**
  - R3-CSO-1 (escape form) pre-emptively applied; byte-level verified.
  - R3-CSO-2 (pyproject.toml broader-claim) resolved.
  - R3-CSO-3 (source_ref redaction) URL-half pre-emptively covered; file-path-half correctly deferred to v0.3.0.
  - QA-SF-1/2/3 correctly deferred to v0.3.0+/v0.5.0 scope phases.
- **No R1 post-test specialist dissents** from any R2 spec-council or R3 spec-council positive assessment. Refactor-architecture, SSRF architecture, fcntl.flock design, per-version phasing, schema-compat, prompt-injection defense, MIT posture all survive this round's scrutiny.

---

## Spec Addendum

This council's advisory set includes items that act as additional acceptance criteria for the impl phase (items #1–8 above) and items to carry forward to the v0.3.0 test-phase lead (items #9–12). Per the lead process, these are captured as a **spec addendum** at `.aldeia/140-.../spec-addendum-post-test-r1.md` — the impl-phase lead is required to honor them as spec requirements during Task Intake.

Items #13–15 are observations only and are **not** carried into the addendum.

---

## Recommendation

**Recommended target:** `impl`
**Confidence:** high
**Rationale:**

The test phase produced a genuinely gating v0.2.0 scaffold. R1 test-review caught two meaningful BLOCKING defects (both of the "looks right but doesn't actually assert" class); r1-fixer resolved them in substance; R2 test-review and this council's independent specialist spot-checks both verify the resolution held. No BLOCKING findings surface from this post-test council. The 8 actionable advisories (items #1–8) are small, contained, and fall naturally into the impl phase's opening commits (`psutil` runtime-dep relocation, three one-line assertion strengthenings, privacy-notice fixture file, CI flake fix, `uv.lock` regen, and one impl-kickoff brief paragraph).

Per Jan's ticket feedback — *"Since we're addressing the blocking issue in a spec re-run, fix the advisory findings as well!"* — the council consolidates the actionable items into a **spec addendum** that the impl phase's Task Intake MUST read and honor. This is the same pattern the R3 spec-council used to carry test-phase-opening items forward (QA-SF-1/2/3), and it keeps the fix latency low without triggering another test-phase rework round for items that are genuinely impl-opening hygiene.

The impl-phase exit criteria MUST include: (a) the `psutil` runtime-dep move merged, (b) the four test-assertion strengthenings landed, (c) the privacy-notice fixture file in place with the verbatim 10-bullet block, (d) the CI flake fix in the concurrency test, (e) a refreshed `uv.lock` on the branch head, and (f) the impl-opening brief referencing the test-as-contract pattern and the co-gating pre-release checklist explicitly.

**Next-phase pickup list for the impl lead:**

- **First-commits on impl branch (before any src-code edit):** Items #1–5 of the addendum — all are test-file or pyproject-file edits that leave the failing-test suite cleaner and correctly-gating. Item #7 is also on this set (one-line concurrency-test fix). This is the "fix the test gates" pass.
- **Impl opening task file or CLAUDE.md note:** Items #6, #8, #12 — documentation of test-as-contract, `uv sync --extra dev` command, pre-release-checklist co-gating awareness.
- **v0.3.0 test-phase lead handoff:** Items #9, #10, #11 — surface in `phase-summary-review.md` and the ticket handoff comment so the next test-phase kickoff sees them.
- **Observations (no action):** Items #13–15 recorded here for audit only.

**Dissent:** None. Five specialists, five SIGN OFFs (two unconditional — CTO and Infra; three SIGN OFF WITH ADVISORIES — CSO, QA, CPO). No specialist recommends another test-phase rework. No specialist recommends escalation to Decide.

---

## Sign-offs

| Role | Verdict | BLOCKING | ADVISORY | File |
|------|---------|----------|----------|------|
| QA Director | SIGN OFF | 0 | 3 | `council-test-r1-qa.md` |
| Chief Technology Officer | SIGN OFF | 0 | 2 (inherited / observational) | `council-test-r1-cto.md` |
| Chief Security Officer | SIGN OFF WITH ADVISORIES | 0 | 6 (4 pre-impl + 2 carry-forward) | `council-test-r1-cso.md` |
| Infrastructure Lead | SIGN OFF | 0 | 2 | `council-test-r1-infra.md` |
| Chief Product Officer | SIGN OFF | 0 | 2 | `council-test-r1-cpo.md` |

**Council verdict:** **SIGN OFF — advance to `impl`, with addendum honoring Jan's "fix the advisories too" directive.**
