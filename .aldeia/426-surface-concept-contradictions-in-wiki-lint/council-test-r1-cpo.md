# Council Test Review R1 — CPO Assessment

**Ticket:** #426 — Surface concept contradictions in wiki_lint
**Phase reviewed:** test (advancing test → impl)
**Reviewer:** Chief Product Officer
**Date:** 2026-06-25
**Verdict:** SIGN-OFF (advance to impl) — zero BLOCKING, three ADVISORY, no SPLIT

---

## Product Intent Recap (the bar I am measuring against)

#325 shipped concept-contradiction *detection* (records into `wiki_contradictions`) but
`wiki_lint` only *surfaces* entity contradictions. The fleet and Jan consume contradictions
through `wiki_lint` (the health check), not by browsing Anytype. So concept contradictions are
**recorded-but-invisible** — the graph knows about a conflict, but the one channel the consumers
actually watch stays silent. #426 is the explicit declared closure-condition of #325. The unit of
user value is: *concept-level contradictions become visible and resolvable through the same health
signal that already surfaces entity contradictions.*

---

## 1. Do the test acceptance criteria faithfully track the product intent?

Yes. The three ACs map cleanly onto the three things that must be true for the gap to be closed,
and the tests assert the user-observable behavior rather than implementation incidentals.

- **AC#1 (surfacing)** is the core user value. The test asserts the *behavioral contract a
  consumer cares about*: a concept with an unresolved contradiction fires
  `contradiction_unresolved` / `severity == "critical"`, and setting `wiki_last_reviewed` clears
  it. Crucially it pins **parity with `wiki_entity`** ("behaviour is identical"). That is exactly
  right from a product standpoint — the fleet/Jan should not have to learn a second mental model
  for concept contradictions. The phase summary confirms the fail-first test goes RED on a
  substantive value assertion (`0 == 1` finding count), not on an import/symbol error, so it is a
  genuine guard on the behavior, not a tautology.

- **AC#2 (bootstrap reconcile)** tracks the *enabling* condition for the value, not a separate
  feature. Without `wiki_last_reviewed` on `wiki_concept`, the lint gate would fire `critical`
  with no field to clear it — the precise broken UX the ticket exists to prevent. The tests pin
  the user-protective invariants (never drop existing properties; no-op on a reconciled space;
  recover cleanly on partial failure). This is correctly scoped as *making the surfacing
  resolvable*, not gold-plating.

- **AC#3 (docs) is treated as a real deliverable, and this matters.** This is the answer to the
  framing question and it is the part I scrutinized hardest. For *this* ticket the user-facing
  signal that the gap is closed lives substantially in docs: the README currently tells every
  reader "concept contradictions ... **not yet flagged by `wiki_lint`** — a planned follow-up"
  (verified live at `README.md:175`). If the behavior ships but that clause stays, the
  authoritative product surface still *advertises the gap as open* — a consumer reading the README
  would not trust the contradiction column and the closure is, from a user-trust perspective,
  invisible. The history shows the test phase initially tried to demote AC#3 to a "manual-review
  gate"; the test-reviewer (R1) **correctly escalated that to BLOCKING** and forced an automatable
  substring-absence assertion (`tests/wiki/test_docs_surfacing.py`), which now fails RED on content
  (not IO) and flips GREEN only when the README clause is removed. From a product angle this was
  the right call and I explicitly endorse it: the docs are not an afterthought here, they are
  half the deliverable's user-visible signal. The residual CHANGELOG / MIGRATIONS / README
  "surfacing is live" assertions remain a manual impl-reviewer inspection — acceptable, but see
  Advisory 1.

**Verdict on (1):** ACs faithfully track product intent. AC#3 is correctly load-bearing, not an
afterthought.

---

## 2. Scope discipline — coherent and minimal, or creeping?

The bundle (schema + 2 client methods + bootstrap reconcile + lint gate + docs) is **coherent and
minimal for the stated goal**, with one item that deserves a named justification.

- The lint-gate widening (§4) is a one-line tuple change — the actual feature.
- The schema property (§1) and the two client methods (§2) are the *minimum* required
  infrastructure to make that one-line change resolvable rather than a trap.
- **The "general reconcile for all six WIKI_TYPES" (§3) is the one place a creep accusation could
  land, and I examined it specifically.** I judge it *correct forward-design, not scope creep*, for
  three product reasons: (a) the per-type cost is bounded and self-extinguishing — every type other
  than `wiki_concept` computes an empty missing-set and is a no-op, so generalizing adds zero
  runtime behavior for this release; (b) the alternative the spec rejected (a one-off migration
  script) would *not* close the structural bootstrap gap and would re-surface as toil on the next
  schema addition — i.e., the narrow option is the higher long-run maintenance burden; (c) the
  generalization does not add a new user-facing surface, config knob, or API — it is internal
  bootstrap plumbing. The cost/value ratio favors the general loop. I would push back only if the
  reconcile had grown *format-mismatch correction* — and the spec explicitly defers that (SG-c,
  Deferred Items) as a distinct higher-risk migration. That deferral is the correct scope line and
  I endorse it.

- No feature was added beyond the ticket. The optional "lint guidance-warning when `wiki_concept`
  lacks `wiki_last_reviewed`" is correctly **deferred**, not built. Good discipline.

**Verdict on (2):** Minimal and coherent. The all-types generalization is justified forward-design;
the format-correction deferral is the correct boundary.

---

## 3. SPLIT RECOMMENDATION assessment

**No split.** I considered decomposing along the obvious seam — (A) bootstrap-reconcile
infrastructure vs. (B) lint-gate widening — and reject it.

These two are not independently shippable *from a user-value standpoint*, and shipping them apart
is actively unsafe:

- Ship (B) lint gate alone → every existing space with a concept contradiction fires `critical`
  with **no `wiki_last_reviewed` field to clear it**. That is a stranded, un-clearable critical —
  a broken user journey that degrades an existing health signal. Net-negative product increment.
- Ship (A) reconcile alone → adds a property nobody reads yet; delivers zero user-visible value
  and zero closure of the recorded-but-invisible gap.

The value only exists when both land together. The operational requirement (lint gate + reconcile
ship in the same change, per addendum item 7) is therefore not arbitrary coupling — it is the
*precondition for the user journey to be whole*. This is exactly the case my mandate names as the
one where proceeding un-split is the safe choice and splitting would "ship a half-finished user
journey that breaks existing functionality." The prior spec council (CPO + CTO) reached the same
conclusion independently; I concur on fresh reading.

Could the *docs* (§5) be a separate ticket? No — they are the user-facing closure signal for this
exact change and are gated by the same AC. Could the *audit-log durability* (addendum item 8) be a
fast-follow? Yes, and it already is correctly carved out as an operational/release item, not folded
into this PR's scope. That is a sufficient and appropriate seam; no formal split needed.

**Verdict on (3):** Single ticket is correct. No SPLIT RECOMMENDATION.

---

## 4. Product / UX risk for the fleet + Jan consumers when this lands

The dominant risk is a **product-trust / migration-sequencing risk**, and it is the right thing
for me to own as the voice of the consumer:

- **Un-clearable `critical` if sequencing is violated (primary UX risk).** If any space runs the
  new `wiki_lint` before re-bootstrapping, concept contradictions fire `critical` with no field to
  resolve them. For a consumer (Jan or a fleet agent) that manifests as a health check that is
  *permanently red with no available action* — the single worst UX outcome for a lint tool, because
  it trains consumers to ignore the signal. The spec mitigates this correctly (lint gate +
  reconcile ship together; re-bootstrap REQUIRED in MIGRATIONS.md and the deploy runbook per
  addendum item 7) and the test phase *encodes the recoverability* (partial-failure re-run test,
  marker-unstamped assertion). This is well-handled at the test gate; it becomes an
  **impl/release-owner responsibility** to actually honor the runbook step. I flag it as the
  top item the impl-reviewer and release owner must confirm.

- **Graph-corruption blast radius (replace-not-merge).** Not a UX-surface risk in the happy path,
  but if the destructive PATCH ever dropped real user properties, *every object of that type* would
  silently lose data — the consumer would experience it as wiki content quietly disappearing, with
  no error. The defense-in-depth (union-send, monotonic guard, pagination/shape guard, empty-payload
  refusal, audit log, never-drops regression test) is appropriately fail-closed, and the test phase
  even mirrors the live `get_type` shape from the real probe (BL-6.4 closed). I am satisfied the
  consumer-data-loss path is guarded. The audit-log durability (item 8) is the right *post-hoc
  diagnosability* backstop and should not be dropped.

- **No cannibalization, no positioning risk.** This strengthens the product's core promise (the
  contradiction column is trustworthy) rather than competing with anything. It removes a documented
  caveat ("don't over-trust a clean contradiction column") — a net competitive/quality improvement
  for the fleet's memory hygiene.

**Verdict on (4):** One material UX risk (un-clearable critical on mis-sequenced migration), fully
identified and mitigated at the test gate; ownership correctly handed to impl/release. Data-loss
path is fail-closed. No positioning or cannibalization concerns.

---

## Findings

### BLOCKING
None.

### ADVISORY

**ADV-1 — AC#3 docs: only the README clause is automated; CHANGELOG + MIGRATIONS + README
"surfacing is live" rest on manual impl-reviewer inspection.**
*Impact:* The user-facing closure signal lives partly in docs that have no automated guard. A
missed MIGRATIONS "re-bootstrap REQUIRED" note is the exact doc whose absence enables the
un-clearable-critical UX failure. *Recommended action:* The impl-reviewer (and QA Director) must
treat the three manual doc confirmations as hard pre-merge checklist items, not soft inspection —
specifically that MIGRATIONS.md states re-bootstrap is REQUIRED and a prerequisite for the lint
gate. Communicating to QA: please ensure the impl-phase acceptance checklist enumerates these
three doc artifacts explicitly so they cannot be silently skipped the way AC#3 was initially in the
test phase.

**ADV-2 — Migration-sequencing is the top consumer-facing risk and is an impl/release obligation,
not a test-gate artifact.**
*Impact:* If the lint gate ships without the reconcile reaching a space (or before re-bootstrap),
consumers get a permanently-red, un-actionable health check that erodes trust in the entire lint
signal. *Recommended action:* Honor addendum item 7 at release: lint gate + reconcile in the same
change, and the "re-run `wiki_bootstrap` is REQUIRED for existing spaces" step in the deploy
runbook. The release owner should confirm no existing space can observe the new gate before its
reconcile has run.

**ADV-3 — Preserve the audit-log durability commitment (addendum item 8) into impl.**
*Impact:* The SG-e union audit log is the only post-hoc reconstruction path if the destructive
PATCH ever corrupts a type. If it is not durably captured by the deployment, a consumer-visible
data-loss event becomes undiagnosable. *Recommended action:* Impl phase must ensure the INFO-level
union log is durably retained, not just emitted. Low effort, high insurance value given the blast
radius.

---

## Sign-off

From a product, scope, and user-value perspective I **sign off on advancing this ticket from test
to impl.** The acceptance criteria faithfully encode the recorded-but-invisible closure (AC#1
parity with entity behavior), the enabling reconcile is correctly scoped as a precondition rather
than a feature (AC#2), and AC#3 is properly treated as a load-bearing deliverable with the README
gap-clause removal automated. Scope is minimal and coherent; the all-types reconcile is justified
forward-design, not creep; the format-correction deferral is the correct boundary. The ticket
should **not** be split — the lint gate and reconcile must ship together to keep the user journey
whole, and shipping either alone is net-negative or unsafe. The one material consumer-facing risk
(un-clearable `critical` on mis-sequenced migration) is identified and mitigated, with ownership
correctly handed to the impl/release phase via the three advisories above.

**Decision: SIGN-OFF (advance to impl). No veto. No BLOCKING. No SPLIT.**
