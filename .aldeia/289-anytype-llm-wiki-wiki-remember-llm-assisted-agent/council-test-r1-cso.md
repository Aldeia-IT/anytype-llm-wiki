# Council Review — TEST phase (R1) — Chief Security Officer

**Ticket:** #289 anytype-llm-wiki `wiki_remember` (v0.3.1 LLM-assisted agent memory write)
**Phase reviewed:** test
**Reviewer:** Chief Security Officer (governance council)
**Date:** 2026-06-04
**Verdict:** SIGN-OFF (advance to impl). 0 BLOCKING, 4 ADVISORY.

---

## Scope and posture statement

This is the first write path in the product driven *repeatedly and autonomously* by
agents, writing LLM-extracted content into a user's Anytype space. My mandate is whether
the security-critical properties of this write path are *proven by substantive tests*
before impl begins. I evaluated the four security-load-bearing test families against
their ACs and the addendum, and traced the assertions to the real sanitizer / consent /
lock primitives. I did not re-do the per-phase tactical review (R2 APPROVED).

Verified state (chair): 74 failed / 294 passed / 1 skipped on `-m 'not live'`; all 74
failures are impl-absence (`ModuleNotFoundError`). Correct TDD red state.

---

## Evaluation findings

### Q1 — Hard gates drive the REAL entry boundary (addendum item 3): SATISFIED

All four gate tests import and invoke the real `wiki_remember` entry point — none
shortcut through an isolated helper.

- `test_empty_knowledge_rejected_before_lock` (test_remember.py:2637) — iterates
  `("", "   ", "\n\t\r")`, asserts `status=="error"` + `empty_knowledge`/`[CONFIG ERROR]`,
  and the three negative spies: `mock_lock.assert_not_called()` (2673),
  `mock_extract.assert_not_called()` (2674), `assert not create_calls` (2675). This is
  exactly the "lock / extract / create_object NEVER called before the gate" requirement.
- `test_oversize_knowledge_rejected_before_lock` (2679) — `"x"*32_001`, asserts
  `knowledge_too_large`/`[DATA ERROR]`, `status=="error"`, and `assert_not_called()` on
  both lock and extract (2700-2701).
- `test_space_lock_held_returns_ingest_in_progress` (2703) — mocks at the
  `space_ingest_lock` boundary (raises `[DATA ERROR] ingest_in_progress`), drives the real
  entry, asserts the error surfaces and `extract` is never reached (2734).
- `test_consent_banner_fires_on_live_path` (2736) — real entry, non-local
  `WIKI_EXTRACT_ENDPOINT`, spies `check_remote_endpoint_consent` and `extract`.

Verdict: the highest-stakes "fail closed before doing work" properties are bound to the
real surface, not to fixtured helpers. This is the single most important security
property of an autonomous write path and it is correctly tested.

### Q2 — Consent ordering before non-local transmit: SATISFIED (with two precision gaps → ADVISORY)

`test_consent_banner_fires_on_live_path` asserts (a) consent IS called on a non-local
endpoint (2792), and (b) consent fires BEFORE `extract` — the first non-local transmit —
via `consent_idx < extract_idx` (2799-2802). Ordering intent is met. Two precision gaps,
both ADVISORY (see A-1, A-2), prevent me from calling this airtight.

### Q3 — Exact sanitized value reaches `update_object` byte-for-byte (addendum item 4): FULLY SATISFIED

`test_consolidated_text_sanitized_on_write` (2634→ at 1034) is the strongest test in the
suite from a security standpoint:

- Feeds `consolidated_text` containing U+200C (zero-width non-joiner — a bidi/zero-width
  control codepoint).
- Setup guard `assert sanitized != raw_text` (1044) — proves the codepoint is actually
  stripped, so the equality assertion can't pass trivially.
- Final assertion is `val == sanitized` (1091) i.e. byte-for-byte equality to
  `sanitize_property_value(consolidated_text)` — NOT "contains", NOT "non-empty", NOT
  "sanitize was called".

I traced the sanitizer: `sanitize_property_value` (extraction.py:201) → `strip_control_chars`
(util.py:82) whose `_CONTROL_CHAR_RE` (util.py:67-79) covers C0 controls, `​-‏`
(includes the tested U+200C), bidi embeds/overrides `‪-‮`, isolates `⁦-⁩`,
BOM, line/para separators, and the Unicode tag block `\U000e0020-\U000e007f`. So the test's
codepoint is genuinely in scope and the property-injection / direction-spoofing vector on
write is provably closed. The claim "raw LLM output never reaches Anytype unsanitized" is
proven for the entity/concept text path.

### Q4 — Prompt-injection / untrusted-content posture: ADEQUATE for stored-text; residuals noted

The `knowledge` input is agent/LLM-sourced and untrusted. The test suite proves the
load-bearing containment properties:

- **Property-value injection / trojan-source:** closed and byte-proven (Q3).
- **Closed-enum on `fact_actions[].action`:** `test_unknown_fact_action_dropped`
  (1096) — an unknown action (`"frobnicate"`) is dropped, does not raise
  `conflicts_flagged`, does not abort. This is the right defense: a malicious/hallucinated
  action verb cannot escalate into a status mutation or control-flow change.
- **Conflict-marker injection:** `test_reassert_conflict_no_nested_markers` (960) asserts
  `[CONFLICT` count ≤ 1 per pair in the written text — input content cannot fabricate
  nested conflict annotations.
- **Never-silent-overwrite:** `test_conflict_never_silently_overwrites` (813) proves both
  the existing and the new/conflicting fact survive into the written `consolidated_text`.
- **Ambiguity = no write:** the ambiguous-subject path asserts NO `create_object`/`update_object`
  (per addendum item 6 / R2 fix).

Residuals the impl phase carries (documented, acceptable under the stated single-operator
threat model — see R-1/R-2 below), not blockers.

---

## ADVISORY findings

### A-1 (ADVISORY) — Consent test proxies "non-local transmit" via the `extract` spy, not a transmit-level spy
**Risk:** Low. AC-R-S1 wording is "BEFORE any off-machine HTTP transmission." The test
spies `extract`/`consolidate` (both mocked) as the stand-in for off-machine transmit and
asserts consent precedes `extract`. Because `extract`/`consolidate` are the *only*
non-local transmits and both are monkeypatched out, no real off-machine HTTP can occur in
the test regardless — so the ordering assertion proves "consent before the function that
would transmit," not "consent before bytes leave the host." In practice these coincide,
but a future refactor that adds a second off-machine call path (or transmits inside a
different helper) would not be caught by this test.
**Recommended action (impl phase):** keep the consent check structurally co-located on the
`wiki_remember` entry path *above* the extract/consolidate calls (spec §8.2 already
mandates this); the impl-time live smoke (AC-R24) exercises the real transmit. No test
change required to advance.

### A-2 (ADVISORY) — Consent test does not assert AC-R-S1 item 2 (ack file written), and ordering is `if extract_calls:`-gated
**Risk:** Low. AC-R-S1 (spec:1145) explicitly requires asserting an ack file keyed by
`sha256(endpoint)[:8]` is written after the banner. The test's `mock_consent` *writes* an
ack file (2750-2755) but the test never asserts it exists — the notify-once self-ack
behavior (the actual guardrail that prevents banner spam from desensitizing the operator)
is therefore unproven at the entry-path level. Additionally the ordering assertion is
guarded by `if extract_calls:` (2798), so if `extract` were never reached the ordering
check silently passes vacuously (the `consent_calls` assertion at 2792 still fires, so
this is not a full escape, but the ordering branch is skippable).
**Recommended action (impl phase):** add an assertion that the ack file exists after the
call, or rely on the existing `extraction.py` consent unit tests for the self-ack mechanics
and treat this entry-path test as ordering-only. Note the accepted residual: G2 (spec
§8.2) is a non-interactive notify-once self-ack — an agent CAN transmit off-machine after a
single self-acknowledged warning. Accepted under the single-operator threat model. The CSO
concurs with that acceptance for v0.3.1 but flags it as the weakest control in the chain.

### A-3 (ADVISORY) — Sanitize byte-for-byte proof covers entity/concept text, not the Source `wiki_excerpt` or WikiLog `notes` paths
**Risk:** Low-medium. The strong byte-for-byte assertion (Q3) is on the `wiki_facts`/
`wiki_definition` PATCH. The Source-note path (spec §8.5: `scrub_credentials` →
`sanitize_property_value` → truncate-500) and the WikiLog `notes` channel (which now carries
superseded prior text per addendum item 1, and conflict text) also write
LLM/agent-influenced strings into Anytype. The supersede/WikiLog tests
(`test_supersede_recorded_in_wikilog_notes` 2813; `test_conflict_recorded_in_wikilog_notes`
629) assert *content presence* (`superseded_text in wikilog_str`) but not that those
strings are sanitized/scrubbed byte-for-byte the way the main text path is.
**Recommended action (impl phase):** ensure `_create_remember_source` applies the
scrub→sanitize→truncate order (spec §8.5) and that WikiLog `notes` text is passed through
`sanitize_property_value`. Consider one impl-phase test asserting the Source `wiki_excerpt`
equals `sanitize_property_value(scrub_credentials(note))[:500]`. Not a blocker — the
primary, highest-volume write path is proven; these are lower-volume audit/provenance fields.

### A-4 (ADVISORY) — Credential-scrub on the lock `source_ref`/Source note is asserted only at the spec level, not by a dedicated test
**Risk:** Low. SF4 routes `knowledge[:50]` (lock ref) and the source note through
`scrub_credentials` so URL creds embedded in agent narration don't land in the lock ref or
provenance. I did not find a test asserting a `user:pass@host` string in `knowledge` is
scrubbed out of the lock `source_ref` or the Source excerpt. The addendum item 9(e)
explicitly documents that ONLY URL credentials are scrubbed (arbitrary secrets in narrated
knowledge are stored as-is) — that is an accepted, documented residual, correct for the
threat model.
**Recommended action (impl phase):** add a focused scrub assertion on the Source path, and
ensure the 9(e) docs ship (operator must know narrated secrets are stored verbatim). Docs
obligation already lives in addendum item 9 → impl/docs phase.

---

## Why none of these BLOCK

The two destructive, autonomous, off-device-touching properties that would expose the
company or a client — (1) raw LLM output reaching Anytype unsanitized, and (2) work/transmit
happening before the fail-closed gates — are both proven against the real entry point with
substantive, non-tautological, byte-level assertions. The four advisories are precision and
coverage refinements on lower-volume paths (consent ack mechanics, provenance/audit-field
sanitization, cred-scrub on the source note), each with a documented residual that is
reasonable under the explicitly-stated single-operator threat model. No advisory describes a
path by which agent-controlled input escalates beyond stored, sanitized text into property
injection, status mutation, control-flow change, or silent destruction — those are each
closed by a named test. There is no pattern of minor issues indicating a systemic gap; the
opposite — the security-critical surface is the best-tested part of the suite.

---

## SIGN-OFF

**I sign off on the TEST phase from a security perspective. Advance to impl.**
0 BLOCKING, 4 ADVISORY. The four advisories are impl-phase carry items, not test-phase
exit blockers. Top residual to watch into impl/PR: the consent gate is a notify-once
self-ack (G2) — the weakest control in the chain — and its entry-path ack-write is not
asserted (A-2); ensure the AC-R24 live smoke exercises the real off-machine transmit before
PR. Sanitization-on-write is proven byte-for-byte and is the correct, strong containment for
the autonomous-agent property-injection threat.
