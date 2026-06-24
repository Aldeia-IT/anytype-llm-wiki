# Council Spec Review R1 — CTO

**Ticket:** aldeia-box#325 — Contradiction Detection: Extend to Concepts
**Reviewer:** Chief Technology Officer (council, post-spec R1)
**Date:** 2026-06-18
**Mandate:** Strategic technical readiness + audit of in-phase reviewer diligence. Not a line-by-line re-review.

## Verdict: SIGN OFF (advance to Decide)

The confined core (CS-1..CS-6, CS-9) is technically sound, internally consistent, and every load-bearing claim I spot-checked verifies exactly against source. The two in-phase review rounds did real codebase verification and caught the two findings that actually mattered (the monkeypatch `TypeError` trap and the bootstrap-provisioning gap). The re-scope decision is technically justified, not an evasion. Zero BLOCKING findings. Advisories below are for Decide's awareness, not gates.

---

## What I Verified (evidence)

Every check below was run against the worktree source, not the spec's quotation of it.

| Claim (spec) | Verification | Result |
|---|---|---|
| Gate is `if kind == "entity":` (~920) | `grep -n 'kind == "entity"' ingest.py` | **Confirmed** at `ingest.py:920`, inside the `action=="update"` branch (line 905), comment "entity-only (LD1)" at 918. CS-1 anchor exact. |
| `_REL_KEY_BY_KIND` maps concept→`wiki_related` | `ingest.py:437` | **Confirmed** `{"entity": "wiki_relations", "concept": "wiki_related"}`; `_rel_key` at 440-441. CS-4 reuse valid. |
| `detect_contradictions` signature, no `kind` today | `ingest.py:533-540` | **Confirmed** 6 positional params, no `kind`. CS-3 additive keyword-only is backward-compatible. |
| Peer facts read `_existing_text(peer_obj, "wiki_facts")` (~570) | `ingest.py:570` | **Confirmed** exact. CS-5 anchor correct. |
| Call site omits `kind` (~922) | `ingest.py:922-923` | **Confirmed**; `except Exception` swallow at 925, bare warning at 926. CS-6/CS-9 anchors exact. |
| `remember.py:_type_for_kind` encodes concept→`wiki_definition` | `remember.py:226-230` | **Confirmed**; returns 3-tuple keyed by kind. SF-5 dual-helper justification is accurate (different input key, different return shape). |
| `facts` carries concept definition text at call site | `ingest.py:891` (`wiki_definition`) / `895` (`wiki_facts`) | **Confirmed**; new-claim argument needs no change. |
| BL-R2-1: bootstrap skips existing types | `bootstrap.py:281-285` `continue` past existing; `create_type` (286-302) is sole inline-property path; property loop 330-353 only reports | **Confirmed exactly as described.** |
| No add-property-to-existing-type path anywhere | `grep update_type\|add_property` in `bootstrap.py` + `anytype_client.py` | **Confirmed empty.** The follow-up genuinely needs new capability + unverified Anytype API. |
| Lint gate excludes concept | `lint.py:490` `if tk == "wiki_entity":` while 459/506/516 use `("wiki_entity","wiki_concept")` | **Confirmed** — concept flows the loop but contradiction surfacing alone excludes it. BL-1 was real. |
| `wiki_concept` lacks `wiki_last_reviewed` | `types_schema.py:101-114`: has `wiki_contradictions` (111), no `wiki_last_reviewed` | **Confirmed** — resolution-affordance gap real. |
| README says `High`, actual severity `critical` | `README.md:175` "flags them `High`"; `lint.py:500` `"critical"` | **Confirmed** SF-R2-1 is a genuine doc bug the spec correctly flags for fix. |
| All 6 monkeypatch stubs omit `kind` | `test_ingest.py:1319,1388,1452,1524,1765,1899` | **Confirmed** all six, exact lines. SF-1 stub list complete. |
| `_make_concept` lacks contradictions/reviewed params | `test_lint.py:157` (vs `_make_entity` 117) | **Confirmed**; follow-up AC-C11 correctly notes the helper needs extension. |

Bottom line on verification: I attempted to falsify the spec's central claims and could not. The anchors are not just plausible — they are exact, including line numbers within the spec's own "approximate" tolerance.

---

## Answers to the Five Strategic Questions

**1. Are the seven change sites accurate and complete for the confined extension?**
Yes. CS-1 (gate), CS-3 (signature), CS-4 (`_rel_key(kind)`), CS-5 (`_facts_key_for_peer`), CS-6 (pass `kind`), CS-9 (kind-discriminated warning) all anchor to verified source, and CS-2 (new helper) is the only net-new symbol. Completeness check: the gate, candidate-key, peer-facts-key, and call site are the full set of kind-dependent points in the detection path — I traced `detect_contradictions` 533-582 and the update branch 905-932 and found no kind-sensitive site the spec missed. `_write_contradiction_links` is genuinely kind-agnostic (operates only on `wiki_contradictions`). Complete.

**2. Is Option A (`_facts_key_for_peer` keyed on the peer's own type) correct?**
Yes, and it is the right call over Option B. A peer's comparable text lives under the property its *own* type dictates (`wiki_concept`→`wiki_definition`, else `wiki_facts`), independent of the subject being updated. Keying off the subject `kind` would mis-read mixed-kind peers. The `kind` parameter correctly governs only the candidate *relation* key (CS-4), while peer-facts dispatch is type-driven (CS-5). The fallback-to-`wiki_facts` on missing `type.key` is a safe default (it cannot crash; worst case a silent empty read, captured as advisory SG-2). Correct.

**3. Is SF-5 (new constant + helper, cross-referenced to `_type_for_kind`) the right call vs. silent duplication?**
Yes. The two helpers key on different inputs (subject kind vs peer type-key) and return different shapes (3-tuple vs single key). Collapsing them would require inverting type-key→kind, which is more indirection than a two-entry mapping warrants. The spec's mitigation — one named constant `_TEXT_KEY_BY_TYPE_KEY` plus a bidirectional cross-reference comment — converts silent duplication into documented, discoverable duplication. This is the correct engineering trade-off and exactly what SF-5 asked for. The one residual risk: a cross-reference comment is a soft link a future editor can still miss. Advisory, not blocking (see ADV-1).

**4. Is the re-scope sound — does the confined core satisfy the three literal ACs, and is the follow-up cleanly splittable?**
Sound on both counts. The three ticket ACs are (1) concept claim detected + cross-linked, (2) entity unchanged, (3) tests mirror entity. CS-1..CS-6 deliver (1) end-to-end into `wiki_contradictions` (browsable in Anytype); CS-9's entity-bare/concept-suffixed asymmetry preserves (2) byte-for-byte; AC-C1..C10 deliver (3). None of the three literal ACs mention `wiki_lint`. The surfacing piece is cleanly splittable because it is a disjoint change set (lint.py gate + types_schema property + new bootstrap capability + AC-C11) with **zero overlap** with the core's `ingest.py`-only footprint — I confirmed the core touches no lint or schema code. The follow-up is fully specified down to the AC and the open dependency (Anytype property-link API) is explicitly flagged as the follow-up's first research item. This is not an incoherent half-state: it is a correctly-bounded unit that meets its ACs, with a known, documented, non-blocking surfacing gap. The one coherence cost is operator-facing (concept contradictions recorded but not lint-surfaced) — managed by the mandated README/CHANGELOG honesty edits (Implement step 3). Acceptable, and correctly escalated to Jan for the ship-vs-fold decision.

**5. Was reviewer diligence adequate?**
Yes — materially above document-only review. R1 caught the BL-1 lint-surfacing gap by reading `lint.py:490` and the adjacent concept-inclusive checks, AND the cascading resolution-affordance gap (`wiki_concept` missing `wiki_last_reviewed`) by reading `types_schema.py`. R1 also caught SF-1/SF-2 — the silent `TypeError` trap where stubs raise, the exception is swallowed at 925, and tests fail confusingly — which is a non-obvious failure mode a document reviewer would never find. R2 then *disproved its own R1 fix mechanism* (BL-R2-1) by reading `bootstrap.py` and discovering re-bootstrap cannot provision the property — a rare and commendable instance of a reviewer falsifying a prior round's assumption rather than rubber-stamping it. Both rounds cite specific file:line and the lead independently spot-checked. This is the diligence pattern my mandate exists to enforce, and it is present. Notably, the reviews did NOT report "no mismatches" — they found and corrected real ones across two rounds, which is the opposite of the suspicious flawless-review signature.

---

## BLOCKING findings

None.

---

## ADVISORY findings

### ADV-1 — Cross-reference comment is the only guard against the SF-5 duplication drifting
**Verified:** `remember.py:228-230` and the planned `ingest.py` `_TEXT_KEY_BY_TYPE_KEY` will both encode the concept→`wiki_definition`/else→`wiki_facts` rule. The only link between them at implementation time is a prose comment.
**Impact:** If a future kind (e.g. a third comparable-text type) is added, an editor updating one site may miss the other, producing a silent detection false-negative (peer read with the wrong key → empty text → no contradiction flagged). Low probability, low blast radius (one extra kind, not a regression of existing behaviour).
**Recommended action:** Accept as documented. The cross-reference comment is the proportional mitigation for a two-entry map; a shared constant across modules would be over-engineering. No change required for Implement; the implementer must actually write both cross-reference comments as the spec mandates (CS-2 / Implement step 1).

### ADV-2 — Silent `_facts_key_for_peer` fallback is a real (pre-existing-shaped) concept false-negative surface
**Verified:** `ingest.py:564-566` skips a failed peer GET silently; the spec's SG-2 notes a peer whose `get_object` omits `type.key` falls back to `wiki_facts` and may read empty text.
**Impact:** A concept peer with a malformed `get_object` response would silently not be compared — a false-negative, not a crash or regression. CS-9 gives the *top-level* degraded path a discriminator but these finer surfaces stay silent. The deferral rationale (equally silent for entities today; per-peer logging touches the shared loop) is concrete and correct.
**Recommended action:** Accept the deferral. Ensure the SG-1/SG-2 follow-up ticket is actually filed (the spec points to it but no ticket number is cited — confirm at Decide it gets created, not just referenced).

### ADV-3 — Operator-facing coherence gap during the core-only window
**Verified:** README.md:175 currently overclaims (`High`, entity-only) and concept contradictions will be written but not lint-surfaced until the follow-up ships.
**Impact:** Between core ship and follow-up ship, a concept contradiction is recorded in `wiki_contradictions` and browsable in Anytype but never appears in `wiki_lint`. An operator relying on lint as the single pane of glass could miss it. This is the one genuine cost of the re-scope.
**Recommended action:** The spec already mandates the honest README/CHANGELOG edits (Implement step 3, including the `High`→`critical` fix). This is sufficient *if* those edits actually land. Flagging to **Infrastructure Lead**: the core ship changes the operational contract (concept contradictions exist in-graph but not in lint output) — the known-limitations doc and any runbook referencing "lint surfaces all contradictions" should be checked.

### ADV-4 — Follow-up's foundational dependency is unverified
**Verified:** No `update_type` / add-property-to-existing-type path exists in `bootstrap.py` or `anytype_client.py` (grep returned empty). The follow-up's "ensure declared properties on existing types" capability assumes an Anytype `API-update-type`/property-link endpoint that the spec itself flags as unverified.
**Impact:** None on the core (out of scope). But if Jan folds surfacing back into #325, the entire surfacing mechanism rests on an API that may not exist, which would force a different design mid-ticket. This materially favors the lead's recommendation (separate follow-up) over folding back.
**Recommended action:** No action for the core. If Jan considers folding surfacing into #325 at Decide, the Anytype property-link API must be verified *before* commitment, not during. The spec correctly identifies this as the follow-up's first research item.

---

## Bottom Line

This spec earns sign-off. I independently re-verified thirteen load-bearing claims against the actual source — every detection change site, the bootstrap gap, the lint gate exclusion, the schema property absence, the README severity bug, and all six monkeypatch stubs — and found the spec accurate to the line. The two in-phase rounds did genuine codebase verification and caught exactly the two traps that matter (the swallowed-`TypeError` stub regression and the bootstrap-cannot-provision-on-existing-spaces gap), with R2 commendably falsifying R1's own fix mechanism rather than rubber-stamping it. The re-scope to a confined `ingest.py`-only core is technically justified: it satisfies all three literal ticket ACs in full, is a trivial git-revert rollback with no provisioned state, and cleanly disjoints from the larger surfacing work whose foundational Anytype API is correctly flagged as unverified. The only real cost is a temporary operator-facing coherence gap (concept contradictions recorded but not lint-surfaced), which the mandated honest doc edits manage. No blocking findings; four advisories for Decide's awareness. Recommend Jan approve the confined core for Implement and open the surfacing follow-up as a separate ticket.

— Chief Technology Officer
