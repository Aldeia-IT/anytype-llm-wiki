# Council Meeting — Post-spec (Round 1)

**Date:** 2026-06-18
**Ticket:** aldeia-box#325 — Contradiction Detection: Extend to Concepts
**Phase reviewed:** spec
**Client:** anytype-llm-wiki (Aldeia-IT/anytype-llm-wiki)

## Attendance

| Role | Present | Reason |
|------|---------|--------|
| Council Chair | Yes | moderator / synthesis |
| Chief Technology Officer | Yes | minimum; technical accuracy + reviewer diligence |
| Chief Security Officer | Yes | minimum; new untrusted-data path into LLM prompt |
| Chief Product Officer | Yes | minimum; central scope decision |
| QA Director | Yes | test-mirroring is literal ticket AC-3 |
| Infrastructure Lead | Yes | repo domains include infrastructure / agent-operations |
| Client Advocate | Yes | non-aldeia-box product; context files present |
| Legal Counsel | No | no new data handling, PII, trust boundary, or licensing surface (confirmed by CSO: concept text reuses the existing anti-injection-fenced prompt; no new destination/transport/data-class) |

## Context Presented

#325 extends the cross-object contradiction-detection mechanism (shipped in #287, v0.6.0)
from Entities to Concepts. Today a hard gate (`if kind == "entity":`, `ingest.py:920`)
excludes `wiki_concept` objects, so conflicting definitions between linked Concepts go
undetected — a knowledge-graph integrity gap.

The spec went through **two in-phase review rounds**:
- **R1 (NEEDS REVISION):** verified the detection change sites (CS-1..CS-6) accurate, but
  flagged a missed lint-surfacing change site (BL-1) and a wrong regression claim about
  monkeypatch stub signatures (SF-1/SF-2). R1 assumed lint surfacing was a small additive
  bootstrap change.
- **R2 (re-scope):** disproved that assumption (BL-R2-1) — re-running `wiki-bootstrap` does
  NOT attach a new property to the already-existing `wiki_concept` type (`bootstrap.py:281-285`
  `continue`s past existing types; the only inline-property-link path, `create_type`, is never
  called for them; the property loop at 330-353 never links a property onto a live type).
  Lint surfacing therefore needs a **new, idempotent bootstrap capability** of materially
  larger scope. The lead re-scoped #325 to the **confined detection core** (CS-1..CS-6 + CS-9,
  seven change sites, all in `ingest.py`) and moved lint surfacing to a **recommended
  follow-up ticket**.

**The confined core:** makes `detect_contradictions` kind-aware — candidate relation key via
`_rel_key(kind)` (`wiki_related` for concepts), peer comparable text via a new
`_facts_key_for_peer` helper keyed on each peer's own type (Option A:
`wiki_concept`→`wiki_definition`, else `wiki_facts`), gate widened to `("entity","concept")`,
plus a kind-discriminated degraded warning (CS-9). No schema change, no lint change, no
bootstrap change, no migration — rollback is a trivial `git revert`. Ten concept-path tests
(AC-C1..C10) mirror the entity suite.

## Discussion

The council converged quickly; the meeting's substance was **independent verification** of
the spec's load-bearing claims and a focused debate on the **product/stakeholder value of the
re-scope**, not on technical defects.

- **Verification (CTO, QA, Infra, CSO all read source, not just the spec):** Every cited
  anchor checked out — the detection gate, `_REL_KEY_BY_KIND` concept mapping (437), the
  signature (533-540), the call site / `except Exception` swallow / warning (922-926), the
  six monkeypatch stubs at their exact lines (1319/1388/1452/1524/1765/1899), the lint gate
  asymmetry (`lint.py:490` entity-only while neighbours 459/506 are concept-inclusive), and
  `wiki_concept` genuinely lacking `wiki_last_reviewed` (types_schema 101-114). CTO confirmed
  via grep that **no `update_type`/add-property-to-existing-type path exists anywhere** in the
  repo — so BL-R2-1 is real and the follow-up's Anytype API dependency genuinely is unverified.
  Infra confirmed via `git diff main...HEAD` that the core touches **only `ingest.py`**.

- **The crux — is "detection without surfacing" a half-feature?** CPO and Client Advocate both
  pushed on the spec's "browsable in Anytype" framing. Consensus: for this product's actual
  consumers (the agent fleet + Jan, who read contradictions through `wiki_lint`, not by
  manually browsing the Anytype graph), the confined core's standalone value is **latent /
  foundational** — it puts the graph in the correct state that the follow-up activates, plus a
  modest manual spot-check win. It is a partial-value increment, not zero value, and not a
  silent half-feature: the spec is fully transparent and frames the gap as Jan's explicit
  Decide choice with both options one step away (informed consent). The reviewers agreed this
  is textbook scope discipline (the ticket is explicitly a *confined* extension of #287), not
  scope-shaving — folding surfacing back in would be the scope creep.

- **Cross-functional flags:** Client Advocate cross-flagged value-realization + Decide-framing
  to CPO (A1/A3). CTO flagged the temporary operator-facing gap to Infra (ADV-3), managed by
  the mandated honest README/CHANGELOG edits. CSO and Infra independently endorsed the SG-2/SF-6
  observability deferrals as recoverable false-negatives that fail safe.

## Findings

### BLOCKING
None.

### ADVISORY

1. **[CPO / Client Advocate] Surfacing follow-up must be a real, linked ticket — a closure
   condition of #325, not "opened later."** The detailed "Recommended Follow-Up" spec section
   is worthless as a backlog item until it is one. In a single-developer shop the real risk is
   a forgotten follow-up leaving concept contradictions in a *false-coverage* state (recorded
   but never surfaced) — arguably worse than today's honest no-detection. If Jan chooses option
   (a), the follow-up ticket should be created and linked **before the core merges**.

2. **[QA — ADV-1] Add a clean-path "no `:concept` warning" assertion (test phase).** AC-C4
   asserts `contradiction_detection_degraded:concept` is *present* on the concept error path,
   but nothing asserts it is *absent* on a clean concept path. CS-9 introduces this new string;
   the cheap clean-path assertion closes the only CS-9 behaviour currently checked in one
   direction only. Not blocking; a one-line addition for the test worker.

3. **[Client Advocate / CPO] Keep README/CHANGELOG wording explicit that surfacing is a
   follow-up.** Neither the fleet nor the OSS community should infer a closed integrity loop.
   The spec's current caveated wording already gets this right (and fixes the `High`→`critical`
   severity error per SF-R2-1); the council endorses it and asks the impl phase to preserve it.

4. **[Infra — ADV-1] Size the fan-out follow-up against the densest real concept.** Concepts
   are plausibly hub nodes with heavier link cardinality than entities, so SG-1's worst case is
   materially worse in *latency* even though the per-object algorithm is unchanged. Not blocking
   for the core (sequential calls, non-blocking handler, no cascade), but the SG-1 follow-up
   should be sized against the densest real concept, not an average entity.

5. **[Infra — ADV-2 / CSO] The follow-up's bootstrap capability hinges on an UNVERIFIED Anytype
   `API-update-type` / property-link endpoint.** Correctly quarantined out of the core. Flagged
   so the follow-up's first research task confirms the endpoint exists and is idempotent before
   any schema-version bump — if it does not exist, surfacing needs a different mechanism and
   becomes a genuine migration concern.

6. **[CSO / QA] Detection-completeness observability (SG-2/SF-6).** Silent per-peer `get_object`
   skip and the `_facts_key_for_peer` type-key fallback (a missing `type.key` falls back to
   `wiki_facts`, a potential concept false-negative) remain silent today. Pre-existing on the
   entity path, fail safe, deferred with rationale — endorsed, captured in the SG-1 follow-up.

## Resolutions

- R1's BL-1 (lint surfacing as a missed in-scope change site) was **correctly superseded by R2's
  BL-R2-1**: the re-review falsified R1's own proposed fix mechanism rather than rubber-stamping
  it. The council reads this as evidence of genuine reviewer diligence and accepts the re-scope.
- The "no new trust boundary" security claim was contested-by-verification and **upheld** (CSO):
  concept `wiki_definition` text enters the same locked, anti-injection-fenced prompt through the
  same machinery as entity `wiki_facts`, behind the same hallucinated-id allowlist.
- The "no deployment / trivial rollback" claim was contested-by-verification and **upheld**
  (Infra, via branch diff).

## Recommendation

**Recommended target:** `decide`
**Confidence:** high
**Rationale:** The spec is technically sound, internally consistent, independently verified, and
satisfies all three literal ticket ACs with the confined core — zero BLOCKING findings across a
six-member panel. However, the spec deliberately surfaces a genuine **scope decision that belongs
to Jan**: ship the confined core + a dedicated surfacing follow-up (lead + council recommendation),
or fold surfacing back into #325 with the larger new-bootstrap-capability scope understood. The
council does not override that decision — it routes the ticket to Decide so Jan makes the a/b call
explicitly. The council's recommendation to Jan is **option (a)** (ship the confined core, file the
surfacing follow-up as a linked closure condition), with the six advisories above attached as
carry-forward conditions for whichever forward phase follows the decision.
**Dissent:** None. Unanimous sign-off (CTO, CSO, CPO, QA, Infra, Client Advocate).
