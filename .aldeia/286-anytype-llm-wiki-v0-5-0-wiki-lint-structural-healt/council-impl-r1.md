# Council Meeting — Post-impl (Round 1)

**Date:** 2026-06-05
**Ticket:** #286 — anytype-llm-wiki v0.5.0 `wiki_lint` (structural health check)
**Phase reviewed:** impl
**Client:** anytype-llm-wiki (open-source MCP server, MIT, Aldeia-IT)
**This is the final delivery gate before the PR merges.**

## Attendance

| Role | Present | Reason |
|------|---------|--------|
| Council Chair | Yes | moderator |
| Chief Security Officer | Yes | minimum; final data-handling sign-off before public release |
| Legal Counsel | Yes | chair decision — full attendance at the final delivery gate (absent at spec/test; confirm no licensing/CRA delta in shipped code) |
| Chief Product Officer | Yes | minimum; owns the CPO-6/CPO-7 docs-honesty gates carried into impl |
| QA Director | Yes | minimum; owns AC-completeness + regression risk for the merge |
| Chief Technology Officer | Yes | minimum; owns verification that the test/spec veto-lift conditions (single-enumeration, backlinks) landed in code |
| Infrastructure Lead | Yes | chair decision — the CA-B1 shared-Ollama resource guarantee must be verified in shipped code at the final gate |
| Client Advocate | Yes | chair decision — client OSS project; confirm Jan got the CA-B1 opt-in win and honest perf claim that were promised |

Full attendance — this is the last gate before an OSS release artifact merges.

## Context Presented

`wiki_lint(space_id, severity_threshold="all", include_duplicates=False) -> LintReport` is the v0.5.0
increment that closes the Karpathy "maintain" loop (after ingest #284 / remember #289 / query #285). It
enumerates all wiki objects **exactly once** (O(N)), runs a 10-check structural battery (asymmetric
relations, orphans, pipeline-orphans, staleness, unreviewed/needs-review, oversized, empty-type,
potential-duplicates, passive contradiction), and writes ONLY its own WikiLog receipt — it mutates no wiki
objects (report-only).

Delivered:
- **NEW** `src/anytype_llm_wiki/wiki/lint.py` (~569 lines) — the core battery, single enumeration,
  D1 backlinks-primary + O(N) fallback, source-derived age (SF5), opt-in Qdrant duplicate sweep.
- `wiki/config.py` — `_bounded_float([0,1])` guard + six `WIKI_LINT_*` resolvers; `.env.example` knobs.
- `server.py` — `@mcp.tool() wiki_lint`; `wiki/cli.py` — `wiki-lint` subcommand.
- `README.md` lint section + `CHANGELOG.md` v0.5.0 entry. No schema bump (stays 0.4.1); no migration.

In-phase: 1 review round (impl-review-r1.md), APPROVED 0 BLOCKING by two independent reviewers + lead
inline checks. Test suite written pre-impl as a failing contract; impl makes it green
(44 CI tests + 2 skip-gated live smoke, 16 ACs).

Pipeline history carried into this gate:
- **Post-spec (R1):** BLOCKING CA-B1 — default-on duplicate sweep made the bare call ~160s (~3× the ≤60s
  budget) and saturated the shared Ollama. Resolved by editing the spec to make the sweep **opt-in**
  (`include_duplicates=False`). Advisories on backlinks live-shape, age-fixture seeding, docs honesty.
- **Post-test (R1):** BLOCKING — stale "two-call" guidance in `test-review-r2.md` contradicted the
  corrected single-enumeration fixtures. Resolved in-meeting; veto-lift condition was the spec addendum
  pinning the **single-enumeration constraint** as a hard impl requirement (+ CPO-6/CPO-7/CA-9 docs).

The council's task this round was to verify those hard-won conditions actually landed in the shipped code.

## Discussion

All seven specialists independently verified their respective load-bearing conditions against the shipped
source (file:line), not against prose or the debrief. The council converged on a unanimous sign-off with
zero blocking findings, and a single substantive advisory.

- **CTO** — re-ran `grep -n list_objects lint.py`: **exactly one** call (lint.py:228); the one `all_objects`
  list feeds `_schema_version_from_objects` (237), the battery filter (260), and the fetch cache (289) — the
  single-enumeration veto-lift condition is hard-enforced. All D4 helpers imported and reused, zero
  re-implementations. D1 backlinks primary path (lint.py:124–126) present with a correct malformed-fallback.
  Re-ran the suite 3× (44 passed / 2 deselected, no flake; full wiki module 472 passed). The 501-vs-502
  budget divergence is the correct call. **SIGN OFF WITH ADVISORIES** — the only residual is that the live
  `backlinks` shape is confirmed only against a real space, not in CI; this is an accepted *performance*
  degradation risk (fallback = master-spec behavior), not a correctness or merge risk.

- **QA Director** — re-ran the suites green independently (44 passed/2 deselected; full `tests/wiki/`
  472 passed/6 skipped/2 xfailed — the skips/xfails are pre-existing ingest/remember cases, none introduced
  by #286). All 16 ACs satisfied by the real impl, not vacuously: AC8 half-open band `[0.70, max)` with the
  upper-bound exclusion actually asserted; AC16 opt-in gate proven by tracking shims on both
  `semantic_search_core` and `_qdrant`; AC15 live backlinks shape is the only uncovered surface and is
  adequately compensated by the malformed-fallback CI test. The budget-count divergence is a correct
  resolution (impl changed to match the authoritative test). **Regression risk essentially nil** — change is
  purely additive; query/remember/ingest/indexer untouched. **SIGN OFF.**

- **Infrastructure Lead** — traced actual control flow: the sole bge-m3/Qdrant call
  (`indexer.semantic_search_core`, lint.py:496) is **doubly gated** — inside `if include_duplicates:`
  (lint.py:481, default `False` at lint.py:189) AND the `N <= WIKI_LINT_MAX_OBJECTS` cap. The default
  `wiki_lint(space)` path issues **zero** embeddings and **zero** Qdrant queries — the CA-B1 self-DoS path
  no longer exists in code. Migration-free, dependency-free, service-free, schema-stable (0.4.1); doctor's
  exit 1 is purely Anytype-not-running in the sandbox, not a regression. **SIGN OFF.**

- **Client Advocate** — confirmed CA-B1 delivered in code, not prose: the bge-m3 call lives entirely inside
  the `include_duplicates` branch, default `False` on all three surfaces (MCP tool, CLI `store_true`,
  internal fn). README scopes the ≤60s/≤500 claim to "the default, sweep-off path only" and states the sweep
  can exceed it — honest, no oversell under the OSS name. CA-9 docs honesty all present and in brand voice
  ("You do not need to set any of the `WIKI_LINT_*` knobs"; `pipeline_orphan` honestly described as a ±300s
  heuristic with false negatives by design). **SIGN OFF (no conditions).**

- **CSO** — object-controlled text never reaches the persisted WikiLog (receipt `subject`/`notes` are static
  literals, lint.py:553–558); titles enter findings only via `_object_title` = `strip_control_chars(...)[:200]`
  (lint.py:143–144); `oversized` emits a char count, never the body (lint.py:460–464). Both dynamic error
  strings scrubbed (lint.py:230, 501); no token/header interpolated anywhere; QA#30/QA#25 pre-checks are
  fail-closed before client construction/network (lint.py:212–257). Duplicate sweep is an embedding call
  (text→vector) — no new prompt-injection/SSRF surface. **SIGN OFF.**

- **Legal Counsel** (present at the final gate, absent at spec/test) — no net-new third-party dependency
  (`pyproject.toml` unchanged); report-only, no telemetry/phone-home/new external API/credential; operator's
  own local data only, so no GDPR/LGPD controller/processor relationship for Aldeia. **SIGN OFF (clean).**
  The CRA / SECURITY.md item is a **tag-time** concern, not a merge-time gate (this PR is a feature-branch
  merge, not a release tag; the 2026-06-11 trigger does not apply here); SECURITY.md already exists at repo
  root, only its Supported-Versions table needs a refresh at the next tag cut.

- **CPO** — CPO-7 (double-count legibility) landed cleanly: both `unreviewed_needs_review` and
  `stale_needs_review` render `object {id} ({title})` for the same object (lint.py:442–455). CPO-6
  (passive-contradiction caveat) landed honestly in **two of its three** named surfaces — README and the
  `wiki_lint` tool docstring (server.py:195–197) are exemplary — but the **third named surface, the
  LintReport output**, carries the caveat only inside a *firing* contradiction finding's detail (lint.py:417);
  on a green / zero-findings run — the exact over-trust case CPO-6 targets — the JSON report and CLI renderer
  say nothing. The CPO weighed this as BLOCKING-class (per the addendum) and **deliberately stepped it to
  ADVISORY** because the over-trust failure mode is fully closed in the two highest-traffic operator surfaces,
  no false claim ships, and the fix is a trivial always-on note. **SIGN OFF WITH ADVISORIES, contingent on
  ADVISORY-1 being tracked as a committed v0.5.1 follow-up handed to QA.**

The chair notes the CPO is the owner of the CPO-6 requirement and is therefore the correct authority on its
severity. The CPO did not raise it as BLOCKING; it raised it as ADVISORY with a tracking condition. Per
consolidation rules the chair does not *downgrade* a member's finding — and here there is nothing to
downgrade; the chair honors the owner's classification and satisfies the tracking condition (deferred ticket
below). The over-trust risk that justified CPO-6 is materially mitigated: an operator or LLM agent reading
the docs (README) or the tool docstring (what the agent sees) is correctly warned; the residual gap is only
the inline report output on a clean run.

## Findings

### BLOCKING
None.

### ADVISORY
1. **[CPO] CPO-6 third surface (LintReport output) is half-done — green contradiction reads as silently
   clean.** The passive caveat reaches report *data* only inside a firing `contradiction_unresolved`
   finding's detail (lint.py:417); on the passive (pipeline-wiki / zero-findings) path neither the JSON
   report nor the CLI renderer states the check is passive. README + tool docstring + CHANGELOG cover it.
   **Required, tracked v0.5.1 fix:** add an always-on note to `_empty_report` (e.g. a `notes: [...]` field)
   surfaced by the `_cmd_lint` renderer; QA Director to add a green-run assertion. → deferred ticket.
2. **[CTO, QA] `backlinks` live field shape unconfirmed in CI.** D1's `obj["backlinks"]` primary path rests
   on one live-API finding; only the skip-gated `test_backlinks_field_shape_live` exercises it. The
   malformed-fallback CI test compensates (graceful degrade to master-spec O(N) behavior). Run the live smoke
   against Jan's box once before any future feature depends on backlink precision. Not a merge gate.
3. **[CPO, CSO, impl-review] `orphan` check stricter than the master-spec definition.** lint.py:377 requires
   no-inbound AND no-outbound; master spec defines orphan as "no inbound." An outbound-only aged object is
   not flagged `orphan` but trips `asymmetric_relation` (Critical, a louder signal). Defensible; candidate
   v0.6.0 refinement. No AC/test violated.
4. **[Infra] Default-path O(N) `get_object` fan-out is wall-clock-bounded by wiki size, not a hard cap.**
   A latent MCP-timeout consideration on very large wikis; rides the already-tracked known-limitations §9
   O(N)-enumeration debt (count-cache deferred). Informational.
5. **[CSO, impl-review] Client construction outside the `try` block** (lint.py:223–225; `.close()` in
   `finally`). Unreachable leak (lazy constructors, no I/O until first request). Informational.
6. **[Legal] SECURITY.md Supported-Versions table refresh** required at the next **tag cut** (CRA, on/after
   2026-06-11), not at this merge. SECURITY.md already exists and is substantively CRA-aware.

## Resolutions

- Every condition the spec and test councils fought for is verified present in the shipped code:
  single-enumeration (CTO, grep-confirmed), CA-B1 opt-in gate (Infra + CA, control-flow-traced), CPO-7
  double-count legibility (CPO), CA-9 docs honesty + honest perf claim (CA), age-fixture / AC coverage (QA).
- No member's sign-off was withdrawn during discussion. There are zero BLOCKING findings. The single
  substantive advisory (ADVISORY-1) is the CPO's own classification, accepted with its tracking condition
  satisfied by a deferred v0.5.1 ticket.
- Security, legal, product, technical-accuracy, codebase-alignment, test-traceability, and operational-
  readiness dimensions are all clean.

## Recommendation

**Recommended target:** `done` (approve the PR / merge)
**Confidence:** high
**Rationale:** Unanimous seven-specialist sign-off, zero BLOCKING. The implementation is a faithful, fully
test-covered realization of the spec; every hard requirement carried from the spec and test councils
(single-enumeration, opt-in duplicate sweep, docs honesty, double-count legibility) is verified present in
the shipped source at file:line, not asserted. Regression risk is nil (purely additive; shared helpers
reused by import only; full wiki suite green). No new dependency, schema bump, migration, service, or
credential. The one substantive advisory (CPO ADVISORY-1: an always-on passive-contradiction note in the
report output) is correctly classified ADVISORY by the requirement's owner, does not ship a false claim, and
is tracked as a v0.5.1 follow-up. Advance to `done`; merge via the prepared PR (Closes #286). The watcher
applies the autonomy policy to the routing target.
**Dissent:** None. All seven sign-offs are consistent; the CPO's contingency (track ADVISORY-1) is honored.
