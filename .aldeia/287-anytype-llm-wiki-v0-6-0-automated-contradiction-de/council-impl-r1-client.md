# Council Impl Review R1 — Client Advocate

**Ticket:** #287 — anytype-llm-wiki v0.6.0 Automated Cross-Object Contradiction Detection
**Phase:** POST-IMPL final delivery gate
**Reviewer:** Client Advocate (aldeia-box review council)
**Date:** 2026-06-06

For aldeia-box internal work the "client" is Aldeia-IT itself plus the operators/users of
the self-hosted, privacy-first anytype-llm-wiki. I evaluate against the product principles
(local-first by default; one gated remote-egress exception), the brand (honest, technical,
no over-claiming), and the operator-trust concerns I co-raised as Client-ADV-1.

## Verdict

**SIGN-OFF (no veto).** This delivery honestly serves the client's stated goals and respects
the privacy-first positioning. The two trust-critical risks I flagged — honest egress
disclosure and prevention of operator over-trust of an active-but-scoped lint check — are
both addressed in-release, in plain operator language, and protected by CI regression gates.
The two outstanding pre-tag verification gates are honestly deferred as documented runbook
items, not silently claimed done, which is the acceptable posture from the client's side.

## BLOCKING findings

None.

## ADVISORY findings

### ADV-1 — Platform-assumption gate must actually be run before tag, or the feature ships dead-in-prod

**Description.** The no-target-GET design assumes Anytype POST `/search` returns hydrated
objects-format `properties[].objects` arrays. If that assumption is wrong, the candidate set
is empty, detection silently never fires, and `contradictions_detected` is always 0 while CI
stays green. Impl correctly did NOT claim this verified (it cannot run headless) and carries
it as a pre-tag runbook item with a pre-identified one-line `get_object` fallback.

**Client impact.** From the operator's perspective this is the difference between a feature
that works and a feature that is decorative. The honest-deferral is the right call — better a
documented gate than a false "done." But the deferral is only acceptable IF the gate is
genuinely executed before the v0.6.0 tag. If #287 is tagged/released without running it, the
client receives a green-in-CI feature that may do nothing in production — directly undermining
the wiki-integrity value proposition this release exists to deliver.

**Recommended action.** Treat the platform-assumption verification (post-spec addendum item 1 /
post-test item 2) and the AC-8/AC-9 live smoke as hard tag-blocking gates in the release
runbook. The PR body must surface them as "must run before tag," not bury them. Do not tag on
green CI alone. (Flag to CTO/release owner; this is the council's strongest residual technical
risk and it converts to a client-facing failure if skipped.)

### ADV-2 — Activating the lint check while detection is scoped is a real over-trust hazard; mitigated, keep it that way

**Description.** v0.6.0 removes the in-product "PASSIVE" caveat and activates
`contradiction_unresolved`, but detection only covers linked-entity, entity-only
contradictions (DI-1, DI-3). A green contradiction column does not mean "no contradictions."

**Client impact.** Operators relying on a clean result for wiki integrity could be misled.
This is the exact over-trust failure mode the release set out to fix, so shipping it
unaddressed would have been self-defeating.

**Assessment — adequately mitigated.** Verified in the delivered diff:
- README lint table entry changed from "passive" to "active in v0.6.0; scoped (see below)."
- README section rewritten to "active in v0.6.0 — but scoped," stating both limits plainly
  ("Linked entities only," "Entity-only; concept scope deferred") with the explicit warning
  "do not over-trust a clean contradiction column."
- CHANGELOG v0.6.0 carries a "Detection scope limitations (read before trusting a clean
  result)" bullet.
- `tests/wiki/test_docs_disclosure.py::TestReadmeDetectionScopeDisclosure` gates the
  linked-entities-only and entity-only phrases so the disclosure cannot silently regress.

No action required beyond keeping the disclosure tests in place. Advisory only because the
client should be aware the column is intentionally non-exhaustive in v0.6.0.

### ADV-3 — Widened off-machine egress: disclosure is honest and legible; trust preserved

**Description.** v0.6.0 widens egress — peer `wiki_facts` (distilled from earlier ingests)
now transmit to a configured remote `WIKI_EXTRACT_ENDPOINT`, a broader data class than the
v0.3.0 single-source model. This is the core of my original Client-ADV-1 concern: the
privacy-first positioning is the trust foundation, and a dishonest or buried disclosure would
damage it.

**Client impact.** Operators who trust "local-first by default" must understand exactly what
the one opt-in remote exception now sends. Verified in the delivered diff:
- README "Privacy and data flow": hosted-LLM bullet amended to state the endpoint "**also
  receives the `wiki_facts` of already-linked peer entities** — content distilled from
  *earlier* ingests, not just the current source."
- README ingest/security narrative amended ("any source or previously-stored wiki content").
- CHANGELOG carries an explicit "Widened off-machine egress disclosure" bullet.
- Consent banner copy (extraction.py) updated to name "source and previously-stored wiki
  content ... the wiki_facts of already-linked peer entities."
- Verbatim privacy fixture updated in lockstep so the disclosure is regression-gated, not
  maskable behind a stale-wording substring test.

The egress remains gated by the existing consent mechanism (no new gate, no forced
re-consent — Legal confirmed operator-as-controller makes this a transparency obligation,
not a new control). The disclosure is honest, in plain language, and consistent across
README + CHANGELOG + banner. Trust is preserved. Advisory only — the client should be aware
the privacy surface broadened, but the handling is correct.

### ADV-4 — #289/#287 signal boundary is documented; minor operator-legibility note

**Description.** Jan clarified #289 handles intra-entity conflicts (`wiki_status`) and #287
handles cross-object contradictions (`wiki_contradictions`). Spec §3.9 captures the boundary
cleanly and the CHANGELOG describes the #287 signal (`wiki_contradictions`, bidirectional,
`wiki_last_reviewed` null) without conflating it with the #289 `needs-review` signal.

**Client impact.** Low. Operators reading the CHANGELOG will not confuse the two signals. The
distinction is well-drawn in the spec/code. No cross-reference to #289 appears in the
operator-facing README contradiction section, but none is required for v0.6.0 correctness.

**Recommended action.** None blocking. Optional: a one-line README note distinguishing
"contradiction" (cross-object) from "needs-review" (intra-entity) would aid operators who use
both signals, if/when #289 ships operator docs. Defer to CPO.

## Rationale

The client's goals for v0.6.0 are: close the long-deferred contradiction-detection gap
(OQ#8), make the previously-passive lint check trustworthy, and do so without compromising
the privacy-first brand or over-claiming. The delivery meets all three.

The two genuinely trust-load-bearing risks — honest egress disclosure and over-trust of an
active-but-scoped check — were the substance of my Client-ADV-1 flag. I verified in the actual
README/CHANGELOG/extraction diff (not just the phase summary) that both are landed in plain
operator language and protected by `test_docs_disclosure.py` plus the lockstep verbatim
fixture, so neither can silently regress. The consent gate is unchanged and continues to fire
before any off-machine transmit. This is exactly the disclosure-as-gated-deliverable posture
the council mandated.

Scope discipline is good: no gold-plating (Qdrant pre-filter and concept scope correctly
deferred to v0.6.x), no silent shortcuts (the lint check is honestly described as scoped, not
oversold). Schema stays at 0.4.1 — no migration burden imposed on operators. The work is
demo-ready for a sprint demo modulo the live gates.

The only thing standing between this and a fully shippable feature is execution of the
pre-tag platform-assumption verification (ADV-1). I am comfortable signing off because impl
did not claim that gate done — it deferred it honestly with a pre-identified fallback. My
sign-off is therefore conditional in spirit on that gate being run before tag, which I have
recorded as ADV-1 for the release owner. It is not a BLOCKING finding for THIS delivery gate
(the CI-runnable scope is complete and the deferral is honest), but it is a hard precondition
for the eventual tag.

**Relevant files:**
- `/Users/Shared/development/anytype-llm-wiki-worktrees/287-anytype-llm-wiki-v0-6-0-automated-contradiction-de/README.md` (egress + scope disclosure)
- `/Users/Shared/development/anytype-llm-wiki-worktrees/287-anytype-llm-wiki-v0-6-0-automated-contradiction-de/CHANGELOG.md` (v0.6.0 entry)
- `/Users/Shared/development/anytype-llm-wiki-worktrees/287-anytype-llm-wiki-v0-6-0-automated-contradiction-de/src/anytype_llm_wiki/wiki/extraction.py` (consent banner copy)
- `/Users/Shared/development/anytype-llm-wiki-worktrees/287-anytype-llm-wiki-v0-6-0-automated-contradiction-de/tests/wiki/test_docs_disclosure.py` (disclosure regression gate)
