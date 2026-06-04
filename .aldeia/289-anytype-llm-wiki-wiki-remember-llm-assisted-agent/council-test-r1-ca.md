# Council Review — TEST phase, Ticket #289 (`wiki_remember` v0.3.1)

**Reviewer:** Client Advocate
**Phase:** TEST (governance gate before impl)
**Date:** 2026-06-04
**Verdict:** SIGN-OFF (no blocking findings)

---

## Who the client is here

This is an open-source, self-hosted product (anytype-llm-wiki). The "client" I represent is the
self-hosting community operator and the autonomous agents/users who rely on the wiki being a
**trustworthy, recoverable** knowledge base. The product's entire stated value (business.md,
spec §2.2) is "precise, deduplicated, well-maintained knowledge." For a write path driven
*repeatedly and unattended by agents*, the operator's core interest is: **when the machine writes
something wrong or destructive, can I find out and undo it?** That is the lens I applied.

Two of the spec-time addendum items originated from this role: item 1 (supersede audit) and item 2
(conflict-path provenance overwrite surfaced). My first job is to confirm the test phase did not
quietly drop them.

---

## Evaluation against the brief

### Q1 + Q2 — Did the test phase honor the two CA-originated requirements, substantively?

**YES — both are honored by real, TDD-failing tests, not token gestures.**

**Item 1 — supersede leaves a durable, recoverable WikiLog audit record.**
`test_supersede_recorded_in_wikilog_notes` (tests/wiki/test_remember.py:2813) feeds a
`fact_actions` entry with `action="supersede"` and `supersedes="TestEntity has 4 GB RAM."`, then
captures the WikiLog `create_object` payload and asserts the **removed prior text** appears in the
WikiLog properties. This is the exact undo-from-audit-log mechanism the council preferred over
documenting silent deletion as a residual. The test is genuinely gating: it fails today with
`ImportError ... No module named 'anytype_llm_wiki.wiki.remember'` (verified), i.e. it is in the
correct TDD-failing state and will hold the impl to producing the note. This is the highest-value
test for operator trust in the whole suite, because supersede is the one **non-conflict**
destructive path — the LLM silently drops the old fact, and without this note there is no record
that "4 GB" ever existed. The test makes that recoverable.

*Minor note (ADVISORY, below):* the assertion's `or "4 GB RAM"` fallback arm is a substring of the
full superseded text, so it is slightly weaker than asserting the whole string — but "4 GB RAM" is
the load-bearing, distinguishing token (the actual lost value), so the test still proves the
recoverable fact reaches the audit channel. Acceptable.

**Item 2 — conflict-path `wiki_sources` overwrite is surfaced at runtime.**
`test_conflict_path_surfaces_sources_overwrite` (tests/wiki/test_remember.py:2881) drives a
conflict-flagged write and asserts `"sources_overwrite_on_conflict"` appears in
`result["warnings"]`. The addendum permitted EITHER recording pre-overwrite source ids in the
WikiLog note OR emitting this warning; the test picks the warning mechanism, which is a valid
council-sanctioned choice. Also TDD-failing (verified). This closes the SF14 gap — on exactly the
entities a reviewer will inspect (the conflicted ones), the loss of prior source-link history is
now surfaced in the result the agent/operator sees, not buried only in spec §13.2.

Both requirements survived the handoff into enforceable, falsifiable, currently-failing tests.
That is what I needed to see.

### Q2 (deeper) — Is operator recoverability actually *proven* by tests?

Largely yes, with one honest boundary the operator should understand:

- Conflict path: never silently overwrites (AC-R5 + `test_conflict_never_silently_overwrites`),
  flags `needs-review`, records both facts + the conflict in WikiLog. Strong.
- Supersede path: now audited (item 1 above). Strong.
- Ambiguity: `test_ambiguous_subject_skips_and_warns` (verified subject-aware after R1 fix) proves
  the writer **refuses to guess** among same-name same-type objects — `action=error`,
  `error="ambiguous_subject"`, NO `update_object` on the ambiguous subject, AND a co-resident
  unambiguous subject still writes exactly once. This is the single highest-stakes silent-failure
  mode for a memory writer, and the test is genuinely discriminating.
- Convergence: `test_remember_twice_converges_no_op` is twice-driven against a stateful mock and
  asserts ZERO PATCH on call 2 + stable `object_id`. This protects the operator from the
  accumulating-garbage failure mode that §2.2 calls out as unacceptable.

**Honest boundary (already disclosed, not a new gap):** §13.4/SF11 accepts that a process-level
crash *after* object writes but *before* the WikiLog `create_object` leaves those objects with no
audit record (recoverable only via reindex, not via WikiLog). This is an accepted v0.3.1 residual
and is correctly out of scope for the test phase. I flag it only so it is not later mistaken for a
regression — it is a known, documented limit of the audit guarantee.

### Q3 — Operational burden deferred to impl/docs (addendum item 9): correctly deferred, or silently dropped?

**Correctly deferred — and the handoff risk is real but currently mitigated.** Addendum item 9 is
explicitly scoped `impl/docs phase` in the addendum header and itemizes all five operator-facing
concerns: (a) per-space re-bootstrap runbook, (b) auto-reindex cost model + `WIKI_AUTO_REINDEX=false`
mitigation, (c) monotonic WikiLog growth / pruning, (d) `ingest_in_progress` fail-fast back-pressure
+ ≤ 8×timeout lock-hold bound, (e) narrated `knowledge` stored as-is (only URL creds scrubbed) +
notify-once consent banner. Each also has a spec anchor (§11.5, §13.7, §8.2/G2, §8.3/D12, §8.5),
so it is not floating only in the addendum.

These are documentation deliverables, not test-phase deliverables — the test phase cannot and
should not encode README prose. So deferral is correct. **The risk is the handoff:** the
phase-summary-test.md "Risks and Open Items" section carries N-R1 (the 5→6 action-tag count update)
and the AC-R7 live-smoke manual run, but it does **not** re-list item 9's five docs requirements.
That is the one place this could get lost — if the impl worker reads only the phase summary and not
the addendum. I am raising this as ADVISORY (CA-1) so the council chair ensures item 9 is carried
forward into the impl/docs phase brief explicitly. The operator-facing docs are not optional polish
for a self-hosted product whose users *are* the operators; (e) in particular — "narrated knowledge
is stored as-is, arbitrary secrets are NOT scrubbed" — is a trust/safety disclosure the community
operator must see before pointing agents at this tool.

### Q4 — Any unaddressed client-interest concern that should BLOCK?

**No.** I reviewed §13 residuals for anything that materially harms operator trust:

- §13.2/SF14 (sources overwrite) — now *surfaced at runtime* by item 2's test. The residual is the
  v0.4.x GET-and-merge fix, which is acceptable to defer **because** the loss is now visible.
- §13.7 (reindex cost / WikiLog growth) — disclosed, operator-controllable via
  `WIKI_AUTO_REINDEX=false`. Documentation, not a blocker.
- §13.4/SF11 (crash-before-WikiLog) — accepted residual, single-operator threat model.
- §8.2/G2 (consent is notify-once self-ack, non-interactive) — accepted under the single-operator
  threat model and must be documented (item 9e). Not a test-phase blocker.

None of these rise to misalignment with the engagement or the product's trust posture. The two
destructive operations the council flagged at spec time (supersede, conflict-path provenance) are
the ones with proven test coverage. The trust posture is intact.

---

## Findings

### ADVISORY CA-1 — Item 9 (operator docs) is not echoed in the impl handoff summary
**Description:** Addendum item 9's five operator-facing documentation requirements are correctly
deferred to impl/docs and are anchored in both the addendum and spec sections, but
`phase-summary-test.md`'s "Risks and Open Items" handoff list does not re-state them. Only N-R1
(tag-count update) and the AC-R7 live-smoke run are carried forward there.
**Client impact:** For a self-hosted product, the operator IS the client; missing the re-bootstrap
runbook (9a), the reindex cost model (9b), or the "knowledge stored as-is / secrets not scrubbed"
disclosure (9e) would ship a deliverable that demos fine but burns operator trust on first
production use.
**Recommended action:** Council chair to ensure item 9 (all five sub-items + the backup-coverage
confirmation) is carried into the impl/docs phase brief as explicit exit criteria, not left to be
rediscovered from the addendum. No test-phase rework required.

### ADVISORY CA-2 — Supersede-audit requirement lives only in the addendum + test, not in spec §9 ACs
**Description:** The supersede WikiLog-note requirement (item 1) is enforced by
`test_supersede_recorded_in_wikilog_notes` and stated in the addendum, but spec §9 AC-R3 still only
asserts `fact_actions[].supersedes` is captured in the *result dict* — it was not updated to
reference the durable WikiLog note. The addendum is authoritative (its header says so), so the
requirement is binding, but the canonical AC list reads as if supersede has weaker auditing than it
actually now requires.
**Client impact:** Low/cosmetic now (the test gates correctly). Risk is future drift — a later
reader trusting §9 alone might "simplify away" the WikiLog note as untested.
**Recommended action:** During impl, fold the WikiLog-note assertion into AC-R3's text (or add a
short AC-R3b) so the spec body and the test agree. Documentation hygiene, not a gate.

### ADVISORY CA-3 — Supersede test's `or "4 GB RAM"` arm is weaker than the full-string assertion
**Description:** The assertion accepts either the full superseded text or the substring "4 GB RAM".
The substring is the distinguishing/load-bearing token, so recoverability is still proven, but the
weaker arm could in principle pass on a note that mangles surrounding context.
**Client impact:** Negligible — the lost *value* (the old RAM figure) is what an operator needs to
recover, and that is asserted.
**Recommended action:** Optional: tighten to assert the full superseded string once impl confirms
the note format. Not required for sign-off.

---

## Sign-off

**The Client Advocate SIGNS OFF on advancing ticket #289 from TEST to impl.**

The two CA-originated trust guardrails — supersede audit (item 1) and conflict-path provenance
overwrite surfacing (item 2) — are protected by substantive, currently-failing, falsifiable tests
that will genuinely gate the implementation. The refuse-to-guess (ambiguity) and refuse-to-overwrite
(conflict) postures that make this memory-writer safe for autonomous agents are well covered. No
§13 residual rises to a blocker; each destructive path is either recoverable from the audit log or
explicitly surfaced at runtime.

**BLOCKING findings: 0.** Three ADVISORY items, none of which require test-phase rework. The one I
care most about is CA-1: do not let the operator-facing docs (item 9) fall through the impl handoff
— for a self-hosted product, those docs are part of the deliverable, not an afterthought.
