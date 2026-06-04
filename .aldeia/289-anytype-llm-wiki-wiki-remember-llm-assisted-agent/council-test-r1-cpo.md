# Council Test Review (R1) — Chief Product Officer

**Ticket:** #289 anytype-llm-wiki `wiki_remember` (v0.3.1) — LLM-assisted agent memory write
**Phase reviewed:** TEST (failing-test suite, test-first TDD)
**Date:** 2026-06-04
**Reviewer:** CPO (product / user-trust lens)
**Verdict:** **SIGN-OFF — advance to impl.** 0 BLOCKING, 2 ADVISORY (impl-carried conditions).

The product's value proposition is "precise, well-maintained, TRUSTWORTHY knowledge." My job
here is to confirm the test phase locks in the trust guarantees BEFORE impl can be written, so the
contract the impl-worker must satisfy is non-negotiable on the points that protect the user's
knowledge base. It does.

---

## 1. Trust guarantees — the two destructive operations the council flagged at spec time

Both are now covered by durable-audit tests that match the addendum's intent.

- **Item 1 — non-conflict `supersede` leaves a durable, recoverable audit record.**
  `TestSupersede::test_supersede_recorded_in_wikilog_notes` (test_remember.py:2813) drives the real
  `wiki_remember` with a `fact_actions` entry `action="supersede", supersedes="TestEntity has 4 GB
  RAM."`, captures the WikiLog create payload, and asserts the removed prior text appears in the
  WikiLog note. This makes a destructive consolidation undoable from the audit log — the
  council-preferred resolution, not the documented-residual fallback. **Honored.**

- **Item 2 — conflict-path `wiki_sources` overwrite is surfaced at runtime.**
  `TestConflictSourcesOverwrite::test_conflict_path_surfaces_sources_overwrite` (test_remember.py:2881)
  asserts a `needs-review` (conflict-flagged) object yields a `sources_overwrite_on_conflict`
  warning in the result dict. The overwrite is now observable by the calling agent/operator at
  runtime, not buried in the spec. **Honored.**

**Product read:** the two weakest destructive paths now both produce a surfaced/recoverable trace.
For a tool driven repeatedly by autonomous agents, this is the proportionate guardrail against
silent, unrecoverable knowledge loss. This was my R1-spec concern and it is closed at the test
layer.

## 2. "Never guess, never silently overwrite" posture

- **Item 6b — ambiguous subject → NO write.** `test_ambiguous_subject_skips_and_warns`
  (test_remember.py:2204) is now strong after the R1 fix: the search mock is subject-aware, so the
  test proves (a) the ambiguous subject fires ZERO writes (per-id PATCH spies + `capture_post`
  asserting no create), with `action="error"` / `error="ambiguous_subject"` and `status="partial"`,
  AND (b) the co-resident UNAMBIGUOUS subject still writes exactly once (`len(clear_update_calls) ==
  1`). "Never guess" is proven, and proven not to be a blunt instrument that drops good writes.
- **Item 6a — conflict-flagging independent of the PATCH-skip gate.**
  `test_conflict_flag_when_patch_skipped` (test_remember.py:862): an already-`needs-review` entity
  whose re-asserted text normalizes equal → the text PATCH is skipped, yet `conflicts_flagged >= 1`
  AND a WikiLog conflict note is still written. The trust signal ("this entity contradicts itself")
  survives the idempotency optimization. **Honored.**

## 3. Idempotency from the user's POV

`test_remember_twice_converges_no_op` (test_remember.py:379) is genuinely twice-driven against a
stateful mock: call-1 `action="created"`, call-2 `action="consolidated"` (and explicitly NOT
`"updated"`), stable `object_id`, and ZERO PATCH calls across the run (`update_calls == []`). This
proves an agent re-asserting a fact it already wrote will not churn, duplicate, or re-touch the
user's knowledge base. This is the single most important UX property for a write path hammered by
autonomous agents, and it is end-to-end proven, not gate-fixtured. **Honored.**

## 4. Scope discipline

The test surface maps 1:1 to spec §9 ACs and §10 named tests; phase-summary confirms every AC-R1–R31,
AC-R-S1/S2, AC-R12b and all 8 addendum items trace to a named test. The genuinely deferred items in
spec §13 — `wiki_sources` GET-and-merge (§13.2), deterministic fast-path (§13.1), cross-object
contradiction detection (§13.3, that's #287), full-space relation resolution (§13.6) — are NOT
tested-in. No gold-plating; the suite tests the v0.3.1 increment and nothing the user didn't ask for.
**Scope held.**

## 5. Product-trust gaps

None that block. Two conditions the impl phase must carry (these are the only places where a
user-visible trust property is NOT yet provable in CI, by physical necessity):

---

## Findings

### ADVISORY-1 — Post-reindex retrievability has no CI proof; must be manually gated in impl.
**Description:** AC-R7 (a remembered fact is actually retrievable via `semantic_search` after
reindex) lives only in `test_live_wiki_remember_end_to_end` (`@pytest.mark.live`, AC-R24). CI cannot
exercise live Qdrant+Ollama, so the end-user-facing promise — "what the agent remembered, the user
can later find" — is not machine-enforced pre-merge.
**Impact on users:** if reindex silently no-ops, every other test still passes but the knowledge is
write-only and invisible to retrieval — a total failure of the value proposition, undetected by CI.
**Recommended action (impl-carried, already flagged in phase-summary):** the impl-worker MUST run the
live smoke gate manually before PR and record the result in the PR. Do not let "294 passed" stand in
for "the fact is retrievable." QA Director should treat the live-smoke run as a required merge gate,
not optional.

### ADVISORY-2 — Conflict / supersede audit notes are proven present, not proven human-legible.
**Description:** The item-1/item-2 tests assert the superseded text / overwrite signal is *present*
in the WikiLog note or warnings (substring / key checks). They do not assert the note is structured
for a human to actually recover from (e.g. a clearly labeled before/after, timestamp, or the
specific source-ids that were dropped on the conflict overwrite — item 2's spec offered "record the
pre-overwrite `wiki_sources` ids" as the stronger of its two options; the suite verified the weaker
warning-only option).
**Impact on users:** recoverability is only as good as the legibility of the audit record. "The old
text is somewhere in the notes blob" satisfies the letter of the guarantee; a self-hosting operator
trying to undo a bad consolidation six weeks later needs it readable.
**Recommended action (impl-carried, non-blocking):** when impl writes these notes, make them
human-parseable (label superseded vs. current text; for the conflict path, prefer recording the
dropped `wiki_sources` ids per addendum item 2's stronger option if low-cost). This is a quality
bar on the impl, not a test-phase defect — the addendum explicitly permitted the warning-only
mechanism, so the test correctly accepts it.

---

## Sign-off

**I SIGN OFF on the test phase from a product perspective. No veto.**

The test suite locks in every product-trust guarantee the council flagged at spec time: destructive
`supersede` and conflict-path source-overwrite are now recoverable/surfaced (items 1, 2); "never
guess" (ambiguous → no write, item 6b) and "never silently drop the conflict signal" (item 6a) are
proven; and true idempotency (item 5) protects the user's knowledge base from agent-driven churn.
Scope is held to the v0.3.1 increment with no creep. The suite is in correct TDD state (74 failing
on impl-absence, regression guards green). The two ADVISORY items are impl-phase conditions, not
blockers — chief among them: the impl-worker must manually run the live retrievability smoke gate
before PR, because CI cannot prove the user can actually find what was remembered.
