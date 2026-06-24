# Council — Post-Impl Review (R1) — Chief Product Officer

**Date:** 2026-06-24
**Ticket:** aldeia-box#325 — Contradiction Detection: Extend to Concepts
**Phase reviewed:** impl (post-implementation governance)
**Reviewer:** Chief Product Officer
**Client:** anytype-llm-wiki (local-first typed knowledge-graph wiki over MCP; consumers = agent fleet + Jan)

---

## Verdict

**SIGN-OFF (no veto).** The confined core faithfully implements the spec's intent,
satisfies all three literal ticket ACs, and the central spec-council condition
(ship confined core + filed/linked surfacing follow-up #426 + honest doc
disclosure) is satisfied. Zero BLOCKING findings. Advance to `done` (open PR,
merge) is supported from a product perspective.

---

## What I verified (product-relevant facts)

- **Production scope is genuinely confined.** `git diff origin/main...HEAD --stat`
  shows production code touched only in `ingest.py` (+52/-? lines, all CS-1..CS-6,
  CS-9 as specified) and a single docstring cross-reference comment in
  `remember.py`. No schema, lint, bootstrap, or migration code touched. This is
  exactly the seven-change-site core the spec promised — no scope creep into the
  follow-up's territory.
- **The doc disclosure is honest AND test-enforced.** README now states entity
  contradictions are flagged by `wiki_lint` (severity `critical`) but concept
  contradictions are "detected and cross-linked yet **not yet flagged by
  `wiki_lint`** — a planned follow-up," still recorded/browsable in Anytype.
  CHANGELOG mirrors this and names #426. Critically,
  `tests/wiki/test_docs_disclosure.py` was rewritten to (a) assert "entity-only"
  is **gone** from the README, and (b) assert the surfacing gap
  (concept + wiki_lint + follow-up) **is** disclosed. The false-coverage trap the
  spec-council worried about is now guarded by a regression test, not just prose.
- **Roadmap hygiene.** The roadmap bullet correctly dropped "and across Concepts"
  (detection shipped) while keeping the still-open "beyond linked peers (semantic
  pre-filter)" item (#328). No stale promise left dangling.
- **Severity wording corrected** to `critical` (SF-R2-1), per addendum item 3.

I relied on the chair-verified fact that #426 is filed and OPEN (gh CLI has no
network access from this worktree; I could not independently confirm, see ADVISORY-1).

---

## BLOCKING

None.

---

## ADVISORY

### ADVISORY-1 — #426 existence is the load-bearing closure condition; confirm before merge
The entire product justification for shipping detection-without-surfacing rests on
#426 being a real, open, linked ticket (spec-council central condition CA/CPO-ADV-1).
The chair has verified this; I could not independently re-confirm from this worktree
(no gh network access). **Recommended action:** the chair/Jan should eyeball that
#426 is OPEN and cross-links back to #325 at the moment of merge. If #426 were ever
closed-without-shipping or silently dropped, the product would sit in a
false-coverage state (contradictions detected but never surfaced to the consumers
who read via `wiki_lint`) — worse than today's honest no-detection. This is the one
condition I would not let drift.

### ADVISORY-2 — Latent value is real but unrealized until #426; manage the gap window
For this product's actual consumers (the agent fleet + Jan, who read contradictions
through `wiki_lint`, not by manually browsing the Anytype graph), the confined
core's standalone user-visible payoff is **near-zero today** — its value is
foundational (it puts the graph in the correct state #426 activates) plus a modest
manual spot-check win. This is an acceptable partial-value increment given the
honest disclosure and the textbook scope discipline (folding surfacing in would be
the scope creep, not shipping confined). But the value-realization clock starts at
merge: the longer #426 sits unshipped, the longer the agent fleet operates with a
known integrity blind spot it may not feel because detection "looks done." Track
#426 with intent, not as indefinite backlog.

### ADVISORY-3 — Silent false-negative on concept peers missing `type.key` (carry-forward)
`_facts_key_for_peer` falls back to `wiki_facts` when a peer's `get_object` omits
`type.key`, which for a concept peer reads empty text → a silent missed
contradiction. This is pre-existing in kind (entity path is equally silent), fails
safe, and is correctly deferred to the SG-1/SF-6 observability follow-up. Noted only
so it stays visible to QA as a known completeness gap, not a defect to fix here.

---

## Split Recommendation

**The #325 / #426 split is the correct decomposition — affirmed, no further split
needed.** From the product/user-value angle:

- **#325 (detection + cross-linking)** and **#426 (lint surfacing + bootstrap
  property-link capability)** are genuinely separable concerns with distinct review
  surfaces. #325 is code-only in `ingest.py`, trivially revertible, no provisioned
  state. #426 requires a new idempotent bootstrap capability (link declared
  properties onto already-existing types), a schema property + version bump, a lint
  gate change, and a migration note — a materially larger, riskier unit gated on an
  **unverified** Anytype property-link API.
- Bundling them would have produced an unreviewable mixed PR (ingest logic +
  schema + bootstrap + lint + migration) and forced shipping a half-finished user
  journey contingent on an API that may not exist. The split de-risks both.
- The split is **advisory-as-already-done**, not BLOCKING: the work is already
  decomposed and #426 is filed. I am affirming the decomposition was right, not
  asking for new action.

No additional decomposition is warranted within #325 itself — the confined core is a
single coherent concern (make `detect_contradictions` kind-aware).

**Flag for Jan at the #426 Decide:** #426's first research task MUST verify the
Anytype `API-update-type` / property-link endpoint exists and is idempotent BEFORE
any schema-version bump (Infra-ADV-2/CSO). If that endpoint does not exist,
surfacing needs a different mechanism and becomes a genuine migration concern — that
is the moment to re-scope #426, not after a version bump locks in a half-provisioned
schema.

---

## Rationale (sign-off)

This is exemplary scope discipline against a dual-purpose product (internal agent
infrastructure + OSS reputation funnel). The implementation does exactly what the
ticket asked and nothing more; the one genuine product hazard of a partial feature
— consumers inferring a closed integrity loop — is mitigated three ways: honest
README/CHANGELOG copy, a regression test that fails if the "entity-only" claim
returns or the gap disclosure disappears, and a filed/linked follow-up (#426) as a
tracked closure condition. The dual-purpose stakes actually make the honest
disclosure *more* valuable here: an overclaimed "closed loop" would erode both
agent-fleet trust and OSS credibility. All three literal ACs met, no scope creep, no
unnecessary abstraction (the one new helper + constant is justified and
cross-referenced), trivial rollback, negligible resource impact.

No product reason to withhold advance to `done`. **SIGN-OFF.**
