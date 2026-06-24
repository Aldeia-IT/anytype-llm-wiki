# Council Impl Review R1 — QA Director — #325 Contradiction Detection: Extend to Concepts

**Ticket:** aldeia-box#325 — Contradiction Detection: Extend to Concepts
**Phase:** POST-IMPL governance review (final delivery gate)
**Reviewer:** QA Director (council)
**Date:** 2026-06-24
**Mandate:** quality-gate review only (acceptance-criteria coverage, test adequacy, regression risk). Mem0 not read/written (reviewer independence).

---

## Verdict: SIGN-OFF (no QA veto)

The deliverable is fit for purpose from a quality standpoint. All three literal
ticket ACs and the mandatory addendum item (QA-ADV-1) are covered by meaningful,
correctly-failing-before-impl tests. Entity regression is genuinely guarded. The
full suite is green (independently re-run: **709 passed / 37 skipped / 2 xfailed**;
the 37 skips are `@pytest.mark.live`, services unreachable — expected). Production
diff matches the approved spec (CS-1..CS-6, CS-9) verbatim.

Zero BLOCKING findings. Three ADVISORY findings, all acceptable with documentation
— two of which are **not QA-owned** (follow-up-ticket existence is a CA/CPO merge
gate) and are flagged to the chair for routing.

---

## Acceptance-criteria → test traceability (verified)

| Ticket AC | Spec AC-Cn | Test | Verified |
|-----------|-----------|------|----------|
| AC-1 (concept conflict detected + cross-linked) | AC-C1 | `test_concept_contradiction_bidirectional_write` — asserts `kind='concept'` passed, candidates from `wiki_related`, bidirectional `wiki_contradictions` PATCH (>=2), no target GET, `contradictions_detected>=1` | PASS |
| AC-1 (real-fn concept dispatch) | AC-C7 | `test_concept_peer_uses_wiki_definition` — real `detect_contradictions`, asserts candidate facts drawn from `wiki_definition` AND `wiki_facts` sentinel absent | PASS |
| AC-2 (entity behaviour unchanged) | AC-C2 | full `TestContradictionDetection` entity suite green; real-call tests (`test_hallucinated_id_filtered`, `test_self_reference_skipped`) byte-unchanged; monkeypatched stubs get only `**kwargs`; degraded warning stays bare on entity path | PASS |
| AC-3 (create no-op) | AC-C3 | `test_concept_no_detection_on_create` | PASS |
| AC-3 (degraded on error) | AC-C4 | `test_concept_detection_degraded` — asserts `contradiction_detection_degraded:concept` present AND bare string absent; no PATCH | PASS |
| AC-3 (self-ref skipped) | AC-C5 | `test_concept_self_reference_skipped` (real fn) | PASS |
| AC-3 (dedup no-op) | AC-C6 | `test_concept_dedup_no_op` (refactored to use shared fixture per impl-review MAJOR-1) | PASS |
| AC-3 (mixed-kind peer, Option A) | AC-C8 | `test_concept_mixed_kind_peer_uses_peer_facts_key` (real fn; entity peer → `wiki_facts`) | PASS |
| AC-3 (multiple peers) | AC-C9 | `test_concept_multiple_peers_contradict` — 2 detected, >=4 PATCHes; guards wrong-relation-key reads | PASS |
| AC-3 (empty/absent definition) | AC-C10 | `test_concept_empty_definition_peer` (real fn; no crash, not flagged) | PASS |
| **Addendum item 1 (QA-ADV-1, mandatory)** | clean-path negative | `test_concept_detection_degraded_warning_absent_on_clean_path` — asserts both `:concept` and bare warnings ABSENT on clean path | PASS |

All 10 concept tests + QA-ADV-1 present and green. Concept/contradiction subset:
19 passed, 1 skipped (matches chair). Test descriptions carry `#325 AC-Cn` tags and
clearly state intent. Tests are meaningful (positive + negative assertions, not
trivial), follow file conventions (respx mocks mirror `TestContradictionDetection`,
`/tmp` not relevant here, SG-7 unwrapped-dict rule honoured in AC-C7/C8/C10).

**Fail-before-impl (test-first):** confirmed by impl-worker — 7 of 10 concept tests
failed against unmodified code; the 3 that passed (create no-op, dedup no-op,
clean-path-absent) are trivially satisfied by the old `kind=="entity"` gate and are
**forward-regression** guards by design (they pin that the new path does NOT regress
those no-op behaviours). This is a sound test-first posture, not a gap.

---

## Entity regression — genuinely guarded (verified)

- `detect_contradictions` default `kind="entity"` (keyword-only) → real-call entity
  unit tests need no change and were not changed.
- Gate widened to `in ("entity", "concept")`; the create branch is untouched.
- CS-9 appends `:concept` **only** for non-entity; the entity path emits the bare
  `contradiction_detection_degraded` string unchanged → `test_detection_degraded`
  assertion unchanged. AC-C4 additionally asserts the bare string does NOT leak onto
  the concept path (good two-sided check).
- Monkeypatch stubs received only the SF-1 one-line `**kwargs` touch-up (6 stubs) —
  no behaviour change. Without it the `kind=kind` call would have raised `TypeError`
  swallowed by the non-blocking handler, silently failing assertions; correctly
  pre-empted.
- I re-ran the entity real-call + integration subset: 15 passed.

Regression risk is **low**. The change is additive and kind-gated; the shared
write path (`_write_contradiction_links`) is untouched and kind-agnostic.

---

## ADVISORY findings

### ADV-1 — Sibling docs test asserts on loose, non-proximate substrings (pre-existing weakness, not a #325 regression)
**Finding.** `test_readme_discloses_linked_entities_only_scope`
(`tests/wiki/test_docs_disclosure.py:56`) gates only on
`"linked entities" in readme and "contradiction" in readme` — two independent
substring checks that do not pin the two phrases to the same section. It would pass
even if the disclosure were split across unrelated parts of the README. The
impl-worker debrief correctly flagged this latent fragility.
**Impact.** Quality of the *docs-disclosure guard*, not of the shipped behaviour.
The actual README copy (line 175) IS correct and complete — it discloses
entity+concept detection, the linked-peers-only bound, the `wiki_lint` surfacing
gap (concept contradictions detected but not yet flagged, follow-up), and the
`critical` severity. I verified the disclosure content directly.
**Assessment.** This is a **#287-era pre-existing weakness** in a sibling test the
worker only re-pointed its neighbour, not this one. The companion test
`test_readme_discloses_concept_lint_surfacing_gap` (re-pointed from the stale
`test_readme_discloses_entity_only_scope`) adds a stronger 4-substring gate
(`concept` + `wiki_lint` + `follow-up` + `contradiction`) plus a negative
`"entity-only" not in readme` assertion, which materially compensates. Not a
blocking coverage gap.
**Recommended action.** Tighten `test_readme_discloses_linked_entities_only_scope`
to pin the phrase to the contradiction section (single-window/regex match) — fold
into the SG-1 follow-up or a docs-test cleanup. Advisory; do not hold `done`.

### ADV-2 — Stale-test re-point is sound; rationale is documented in-test
**Finding.** `test_readme_discloses_entity_only_scope` was **re-pointed** (renamed to
`test_readme_discloses_concept_lint_surfacing_gap`), not deleted, because its premise
("detection is entity-only") became false once #325 shipped concept detection. The new
test asserts the stale claim is GONE and the surfacing gap IS disclosed.
**Impact.** None negative. This is the correct way to handle a test whose premise a
feature invalidates — the coverage intent (an operator-facing scope disclosure exists)
is preserved and strengthened, not dropped. The in-test docstring documents the
supersession rationale clearly.
**Assessment.** Acceptable. Noted only so the council record reflects a deliberate,
justified modification of an existing test during impl (per post-impl review lens:
"any tests modified during implementation, with rationale" — yes, documented).

### ADV-3 — Follow-up ticket existence is a CA/CPO merge gate I cannot independently confirm
**Finding.** Addendum item 2 (CA/CPO-ADV-1) makes "a dedicated lint-surfacing
follow-up ticket created and linked before the core merges" a closure condition of
#325. The CHANGELOG now cites this follow-up by number (**#426**) — which is the
written closure artifact the addendum demanded (a filed ticket number, not prose).
However, GitHub issue lookup from this environment does not resolve **any** issue
for `Aldeia-IT/anytype-llm-wiki` (not #426, not even #325 itself), so the project's
issue tracking is evidently external to this GitHub repo and I cannot verify #426
exists/links from here.
**Impact.** If #426 is a real, filed, linked ticket, the closure condition is met
and the README/CHANGELOG honesty framing (ADV-2 / CA/CPO-ADV-3) is intact — concept
contradictions are explicitly disclosed as "detected but not yet lint-flagged
(follow-up #426)." If #426 is a placeholder number with no backing ticket, the
addendum's central re-scope condition is unmet and concept contradictions risk the
"false-coverage" state the CA warned about.
**Assessment.** This is a **process/merge-gate** owned by the Council Chair / CA /
CPO, **not a QA code-quality gate**. From a pure QA lens (AC coverage, test adequacy,
regression risk) the deliverable passes. I flag #426 verification to the chair as
the one external condition to confirm before `done`.
**Recommended action.** Chair to confirm follow-up #426 is a filed, linked ticket
carrying the verbatim "Recommended Follow-Up" spec section + the unverified
Anytype property-link API as its first research task. QA does not block on this.

---

## Known deferred coverage gaps — acceptable

- **SG-4 (B-side rollback test on a concept).** Acceptable. `_write_contradiction_links`
  is kind-agnostic and locked (untouched by #325); the entity suite has no B-side
  rollback test either — this is pre-existing debt, not a #325 requirement. AC-C1/AC-C9
  do assert bidirectional PATCH *success* (A-side + B-side land), so the happy-path
  bidirectional write is covered; only the rollback-on-B-side-failure branch is
  unguarded, equally for both kinds. Folded into the SG-1 follow-up. No new risk
  introduced by #325.
- **SG-1 / SG-2 (fan-out cap, per-peer observability).** Out of confined scope;
  pre-existing for entities, not enlarged in kind by #325. Deferred with concrete
  rationale. The one cheap in-scope win (CS-9 kind-discriminated warning) IS done and
  IS tested two-sided (AC-C4 presence, QA-ADV-1 absence).

---

## Quality gates

- Code review completed within phase (impl-review-r1.md, APPROVED WITH CONDITIONS;
  4 specialist reviewers + lead). Production code CLEAN; all findings were test-code
  polish + one docstring nit.
- SHOULD-FIX findings addressed: DRY MAJOR-1 (AC-C6/AC-C9 now route through the shared
  fixture — confirmed in diff via `peer_ids=` and `existing_contradictions=` params),
  the `_kind_attrs` shared helper collapses the fixture ternaries (DRY/Simplifier
  MINOR-1), the `_TEXT_KEY_BY_TYPE_KEY` comment trimmed, the docstring reflowed (all
  visible in the commit log: efd861f, 1a7dc30, 0212e3d).
- No deferred BLOCKING items.
- Behaviour-change docs updated: README line 175 (entity+concept, linked-peers bound,
  surfacing gap, `critical` severity) and CHANGELOG entry — both present and honest.
- No CLAUDE.md behavioural change required (additive, kind-gated extension).

---

## Sign-off

**I sign off on aldeia-box#325 from a QA perspective. No veto.**

Acceptance criteria (all three ticket ACs + addendum QA-ADV-1) are fully and
meaningfully tested; tests correctly failed before impl; entity regression is
genuinely guarded; the full suite is green (709 passed / 37 skipped-live / 2 xfailed,
independently re-run); regression risk is low. The three ADVISORY items are
acceptable with documentation. The single external condition before advancing to
`done` — confirming follow-up ticket #426 is actually filed and linked — is a
CA/CPO/Chair merge gate, not a QA code-quality gate, and I defer it to the chair.
