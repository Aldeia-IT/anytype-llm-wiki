# Council Meeting — Post-impl (Round 1)

**Date:** 2026-06-24
**Ticket:** aldeia-box#325 — Contradiction Detection: Extend to Concepts
**Phase reviewed:** impl
**Client:** anytype-llm-wiki (Aldeia-IT/anytype-llm-wiki)

## Attendance

| Role | Present | Reason |
|------|---------|--------|
| Council Chair | Yes | moderator / synthesis |
| Chief Technology Officer | Yes | minimum; production-diff accuracy + reviewer diligence |
| Chief Security Officer | Yes | minimum; concept text into the LLM prompt path |
| Chief Product Officer | Yes | minimum; detection-vs-surfacing value call |
| QA Director | Yes | minimum; AC coverage + entity regression |
| Legal Counsel | Yes | minimum (post-impl final gate); data/licensing surface check |
| Infrastructure Lead | Yes | repo domains infrastructure / agent-operations; operational readiness |
| Client Advocate | Yes | non-aldeia-box client project; value-realization / false-coverage |

Full council convened — this is the post-impl final pre-release gate.

## Context Presented

#325 extends cross-object contradiction detection (shipped #287, v0.6.0) from Entities to
Concepts. The impl delivered the **confined detection core** (spec CS-1..CS-6, CS-9): a
production change confined to `ingest.py` (~52 lines) plus a comment-only cross-reference on
`remember.py:_type_for_kind`, with README/CHANGELOG disclosures and a mirrored concept test
suite (AC-C1, AC-C3..C10 + the QA-ADV-1 clean-path negative) in `test_ingest.py`. The
user-visible surfacing affordance (concept contradictions flagged by `wiki_lint`) was
deliberately deferred at spec phase to a dedicated follow-up, **aldeia-box#426**.

Chair-verified facts presented to the council:
- Production diff vs `origin/main` matches the approved spec verbatim (CS-1..CS-6, CS-9);
  entity path byte-for-byte preserved (default `kind="entity"`, gate widened to
  `("entity","concept")`, degraded warning stays bare on the entity path).
- Full test suite re-run by chair: **709 passed / 37 skipped / 2 xfailed** (37 skips are
  `@pytest.mark.live`, services unreachable — expected). Concept/contradiction subset: 19 passed.
- The `pyproject.toml`/`server.py`/`test_query.py`/`uv.lock` entries in `git diff main...HEAD`
  are from already-merged PRs (#346, pytest 9.1.0) pulled in via rebase — NOT part of #325
  (confirmed against `origin/main`).
- All three literal ticket ACs satisfied by the confined core.
- Spec-addendum closure conditions satisfied: follow-up **#426 filed and OPEN**; README/CHANGELOG
  honestly disclose that concept contradictions are detected/cross-linked but **not yet flagged
  by `wiki_lint`**; severity worded `critical`; QA-ADV-1 clean-path test present.

## Discussion

The council converged on unanimous sign-off. As at spec phase, the substance was **independent
verification against source**, not defect-hunting.

- **Verification (CTO, CSO, QA, Infra all read the diff, not just the spec):** CTO confirmed the
  gate sits in the `update` branch only (LD3 holds), `kind`/`facts` are live locals at the call
  site, and the in-phase impl review was diligent (cited line numbers, deliberate-vs-defect
  distinction). CSO upheld the anti-injection claim against the diff — concept `wiki_definition`
  text traverses the identical JSON-escaped, anti-injection-fenced channel as entity `wiki_facts`;
  `kind` selects only the read/relation key, never prompt shape; `_facts_key_for_peer` reads from
  a closed 2-key allowlist with a safe default (no arbitrary-property read). QA independently
  re-ran the suites and mapped every AC to a test. Infra confirmed via name-filtered diff that
  no schema/bootstrap/migration/plist/container path is touched — rollback is a clean `git revert`.

- **The detection-vs-surfacing call (CPO, Client Advocate):** Both reaffirmed their spec-phase
  position. Shipping detection-without-surfacing is **latent/foundational value, not a
  false-coverage trap**, *because* #426 is filed as a tracked closure condition and the gap is
  honestly disclosed (now regression-guarded by `test_docs_disclosure.py`). Folding surfacing
  back in would have been the scope creep. Textbook scope discipline.

- **Cross-functional flags:** CSO, CPO, Infra, and Client Advocate independently noted they could
  not re-confirm #426's OPEN status from the worktree (the repo's `gh` is scoped to the client
  repo, not the aldeia-box org). **The chair independently verified #426 is OPEN** (labeled
  `deferred`, titled "Surface concept contradictions in wiki_lint") — the closure condition is
  met. CSO/Infra/CPO/CA all endorsed the SG-2/SF-6 silent-fallback deferrals as recoverable,
  fail-safe false-negatives (can only miss a finding, never fabricate one or leak data).

## Findings

### BLOCKING
None.

### ADVISORY
1. **[CPO / Client Advocate / CTO / Infra] Keep #426 linked and prioritized.** The user-visible
   payoff is latent until the surfacing follow-up ships; the fleet reads contradictions via
   `wiki_lint`, so concept contradictions stay effectively invisible to automated consumers
   until then. No longer an open risk (#426 is filed/OPEN and the gap is disclosed) — a tracked
   deferral to keep on the radar.
2. **[CSO / CTO / QA / CPO / Infra] SG-2 silent false-negative fallback (deferred, fail-safe).**
   A concept peer whose `get_object` omits `type.key` falls back to `wiki_facts` and may read
   empty text — a silent missed finding. Pre-existing and equally silent on the entity path;
   can only under-detect, never mis-write or expose data. Correctly folded into the SG-1/#426
   follow-up scope.
3. **[Infra / Client Advocate] SG-1 fan-out latency worst case is denser for concepts.** Concepts
   are plausibly heavier hub nodes; the per-object algorithm is unchanged and runs sequentially
   behind the non-blocking handler (no cascade), but the SG-1 cap follow-up should be sized
   against the densest real concept, not an average entity.
4. **[Infra / CPO / Client Advocate] #426 bootstrap capability hinges on an unverified Anytype
   property-link API.** Correctly quarantined out of #325; flagged as #426's first research task
   (confirm the endpoint exists and is idempotent before any schema-version bump).
5. **[QA] Latent test fragility in a sibling docs-disclosure test.**
   `test_readme_discloses_linked_entities_only_scope` passes incidentally on a loose,
   non-proximate substring match and is not pinning the contradiction section. Pre-existing
   #287-era weakness, not introduced here and compensated by the re-pointed companion test;
   fold a tightening into a follow-up.
6. **[Legal] Pipeline-hygiene note.** The legal-counsel mandate references
   `.aldeia/context/engagement.md`, which does not exist (the equivalent is `business.md`).
   Substantively moot (no external client engagement), flagged for pipeline hygiene.

## Decomposition

None required. The one genuinely separable concern — lint surfacing plus its new bootstrap
"ensure-properties-on-existing-types" capability — is **already correctly split out as
aldeia-box#426**. CTO and CPO affirmed the #325/#426 decomposition is the right one: distinct
review surfaces, independently shippable, #325 trivially revertible (code-only in `ingest.py`)
while #426 is a larger schema+bootstrap+lint+migration unit gated on the unverified property-link
API. No SPLIT RECOMMENDATION was emitted.

## Resolutions

- The "no new trust boundary" security claim, contested-by-verification, was **upheld** (CSO):
  concept definition text enters the same locked, anti-injection-fenced prompt through the same
  machinery as entity facts, behind the same hallucinated-id allowlist.
- The "no schema / no bootstrap / no migration / trivial rollback" claim, contested-by-verification,
  was **upheld** (Infra, via name-filtered branch diff).
- The spec-phase central condition (surfacing follow-up must be a real, linked ticket before the
  core merges) was **closed**: chair confirmed #426 OPEN; CPO/CA false-coverage concern resolved.
- The in-phase impl review's "production clean, all FIX items in test code" distribution was
  judged **credible, not shallow** (CTO) — the expected outcome of a tight, already-council-reviewed
  spec applied near-mechanically, with the one substantive condition (DRY MAJOR-1) committed.

## Recommendation

**Recommended target:** `done`
**Confidence:** high
**Rationale:** The confined detection core satisfies all three literal ticket ACs in full, the
production diff matches the approved spec verbatim with the entity path byte-for-byte preserved,
the full suite is green (709 passed), and every spec-addendum closure condition is met (#426
filed/OPEN, honest docs, QA-ADV-1 test present). Zero BLOCKING findings across a seven-member
panel; all six advisories are either pre-existing fail-safe deferrals correctly folded into #426
or tracking reminders. Advance to `done` — open the PR (watcher) and route to Jan for review and
merge. The watcher enforces autonomy policy and may override to `decide` if `done` is not yet
autonomous for this project.
**Dissent:** None. Unanimous sign-off (CTO, CSO, CPO, QA, Legal, Infra, Client Advocate).
