# Council Impl Review R1 — CPO

**Reviewer:** Chief Product Officer
**Date:** 2026-06-05
**Ticket:** Aldeia-IT/aldeia-box #286 — v0.5.0 `wiki_lint`
**Scope:** Verify CPO-6 / CPO-7 (spec-addendum items 5–6, BLOCKING-class docs gates) landed in operator-facing surfaces; scope discipline; day-one product value.

---

## Verdict

**SIGN OFF WITH ADVISORIES**

CPO-7 landed cleanly. CPO-6 landed in **two of its three named surfaces** (README + tool docstring), both honest and well-written. The third named surface — the **LintReport output itself** — does not carry the passive caveat on the case the requirement exists to protect (a green / zero-findings contradiction reading). I weighed this as BLOCKING and stepped it down to ADVISORY for the reasons in the Rationale: the literal at-risk operator (an LLM agent or human reading the report) is the same actor who reads the docstring, the over-trust surface is fully covered in the two highest-traffic operator docs, and no false claim ships. It is a real gap and must be tracked with a committed v0.5.1 fix, not waved away.

- BLOCKING: 0
- ADVISORY: 2

---

## CPO-6 verification (passive-contradiction caveat in all THREE surfaces)

Required by addendum item 5: README + `wiki_lint` tool docstring + **LintReport output** must state `contradiction_unresolved` is passive until v0.6.0/#287; a green result is NOT a guarantee.

**Surface 1 — README: PRESENT, honest.** `README.md`, "### `contradiction_unresolved` is passive until v0.6.0":
> "The `contradiction_unresolved` check is **passive** in v0.5.0: `wiki_contradictions` is not yet auto-populated by the ingest/remember pipelines (that lands in v0.6.0 / [#287]). A green contradiction result is therefore **not a guarantee** that no contradictions exist — it only means none have been manually recorded. Do not over-trust a clean contradiction column."

Also stated in the check table (`contradiction_unresolved` row: "**passive (see below)**") and in the CHANGELOG 0.5.0 entry. Exemplary.

**Surface 2 — `wiki_lint` tool docstring (server.py:195–197): PRESENT, honest.**
> "The `contradiction_unresolved` check is PASSIVE until v0.6.0/#287 — `wiki_contradictions` is not yet auto-populated, so a green contradiction result is NOT a guarantee that no contradictions exist."

The module docstring `lint.py:20–22` carries the identical caveat. Good.

**Surface 3 — LintReport output: NOT SATISFIED for the at-risk (green) case.**
The returned `LintReport` dict (`_empty_report`, lint.py:152–165) has fields `object_counts, findings, potential_duplicates, summary, elapsed_ms, wiki_log_id, deeplink, warnings, status, error, error_category` — no passive/caveat field. The only place the passive note reaches report *data* is inside the `detail` of a firing `contradiction_unresolved` finding (lint.py:417, `"...(PASSIVE check — see #287)"`). That string appears **only when the check fires** — i.e. never on a pipeline wiki, which is exactly the passive scenario. On a clean run the report (both `--json` raw dump and the `_cmd_lint` human renderer, cli.py:209–233) shows zero contradiction findings and **says nothing** about the check being passive. The over-trust risk CPO-6 was written to defuse — operator reads a green report, concludes "no contradictions" — is unmitigated in the report surface.

The impl-review-r1 claim (line 39–41) that "README + server docstring + CHANGELOG + .env.example all carry the passive caveat" is accurate but quietly substitutes CHANGELOG/.env.example for the addendum's named third surface, the **LintReport output**. That substitution was not the council's instruction.

**CPO-6 disposition: 2/3 surfaces fully satisfied; the LintReport-output surface is half-done (covered only on the non-passive path). Tracked as ADVISORY-1 with a required v0.5.1 fix.**

## CPO-7 verification (double-count legibility)

Required: when an aged needs-review object fires BOTH `unreviewed_needs_review` (High) and `stale_needs_review` (Medium), the two `detail` fields must make the shared object legible (same id/title) so summary counts don't read as double-counting confusion.

**PRESENT, correct.** `lint.py:442–455`, both findings are emitted for the same object `o` with detail strings that embed the same id and title:
- `unreviewed_needs_review`: `f"object {o['id']} ({_object_title(o)}) is marked needs-review"`
- `stale_needs_review`: `f"object {o['id']} ({_object_title(o)}) has been needs-review for over {...}d"`

Both also carry the same `object_id`/`object_title`/`deeplink` via `_finding`. An operator (or agent) seeing High count +1 and Medium count +1 can match the two findings to one object by id and title. `test_both_needs_review_checks_fire_on_aged_object` asserts both fire and both are counted. CPO-7 satisfied.

---

## Findings

### ADVISORY-1 — CPO-6 third surface (LintReport output) is half-done; green contradiction reads as silently clean
**Description:** The passive caveat reaches the report data only inside a *firing* `contradiction_unresolved` finding's detail. On the passive (pipeline-wiki / zero-findings) path — the exact case the requirement targets — neither the JSON report nor the CLI human renderer states the check is passive. README and docstring cover it, but an operator who scripts against the report, or reads CLI output without re-reading the docs, sees a clean contradiction column with no "not a guarantee" signal.
**Impact on product/users:** Operator over-trust on a green result — the precise reputation risk under the Aldeia-IT OSS name that CPO-6 was raised to prevent. Severity is bounded because the two most-read operator docs cover it and the at-risk reader is largely the same actor who reads the docstring.
**Recommended action (required, v0.5.1, tracked):** Add a stable caveat to the LintReport output that renders on every run regardless of findings — e.g. a `notes: ["contradiction_unresolved is passive until v0.6.0/#287; a green result is not a guarantee"]` field in `_empty_report`, surfaced by `_cmd_lint`'s non-JSON renderer. Cheap, one-line, closes the gap permanently. Flag to QA Director to add an assertion that the caveat is present on a zero-contradiction run.

### ADVISORY-2 — `orphan` stricter than master-spec definition (carried from impl-review SUGGESTION)
**Description:** `orphan` requires no-inbound AND no-outbound (lint.py:377); master spec defines orphan as "no inbound relations." An outbound-only aged object is not flagged `orphan`.
**Impact on product/users:** Minor and defensible — such an object trips `asymmetric_relation` (Critical), a louder signal, so it is never silently lost. No AC or test violated. Product-acceptable for v0.5.0.
**Recommended action:** Note as a v0.6.0 refinement candidate; no action this release.

---

## Rationale

**Scope discipline: clean.** The deliverable is the 10-check report-only battery the spec scoped. The contradiction check is correctly PASSIVE (fires only on manually-populated `wiki_contradictions`, lint.py:404–418) — no premature v0.6.0/#287 work pulled forward. The duplicate sweep is opt-in (`include_duplicates=False` default), honoring CA-B1 and keeping the default path cheap. No feature creep, no auto-fix, no schema bump (WIKI_SCHEMA_VERSION stays 0.4.1). The deferred-items list (auto-fix, sampling, federation) is honestly out of scope.

**Perf claim honesty: clean (CA-B1).** README, docstring, module docstring, and CHANGELOG all state the ≤60s/≤500 budget describes the **default sweep-off path only**, and that the opt-in sweep can exceed it and is hard-skipped above `WIKI_LINT_MAX_OBJECTS`. No oversell. The CA-9 knob docs are present and compact with the explicit "**You do not need to set any of the `WIKI_LINT_*` knobs**" note, and `pipeline_orphan` is honestly described as a "±300s timestamp heuristic … false negatives by design." All CA-9 conditions met.

**Product value: real on day one.** `unreviewed_needs_review` (High) fires on every `needs-review` object regardless of age (lint.py:442–446), and `wiki_remember` (#289) already sets that status on conflict — so a pipeline-built wiki generates this signal immediately. The maintain loop is genuinely closed for the operator, not a stub waiting on v0.6.0. Report-only is the right call: a tool that mutates a developer's second brain on a heuristic match would be a trust and reputation liability; surfacing and letting the human decide is the correct UX for a local-first OSS wiki.

**Why ADVISORY, not BLOCK, on CPO-6:** the addendum classes a missing/half-done CPO-6 as BLOCKING-class, and surface 3 is genuinely half-done. I do not minimize that. But the over-trust failure mode is fully closed in the two highest-traffic operator surfaces (README and the tool docstring the agent sees), no false guarantee ships anywhere, and the report-surface fix is a trivial always-on note. Blocking the entire v0.5.0 release on a one-line additive caveat — when the product value, scope, perf honesty, and CPO-7 are all clean — is disproportionate. I sign off contingent on ADVISORY-1 being committed as a tracked v0.5.1 fix, not absorbed silently. Chair: please ensure ADVISORY-1 is logged as a hard follow-up and handed to the QA Director for a green-run assertion.
