# Council Meeting — Post-spec (Round 1)

**Date:** 2026-06-05
**Ticket:** Aldeia-IT/aldeia-box#287 — anytype-llm-wiki v0.6.0 Automated Cross-Object Contradiction Detection
**Phase reviewed:** spec
**Client:** anytype-llm-wiki (open-source, infrastructure + agent-operations)

## Attendance

| Role | Present | Reason |
|------|---------|--------|
| Council Chair | Yes | moderator |
| Chief Security Officer | Yes | minimum; remote-LLM egress of peer-object data |
| Chief Product Officer | Yes | minimum; scope/value/boundary alignment |
| Chief Technology Officer | Yes | minimum; technical accuracy + reviewer diligence |
| Infrastructure Lead | Yes | infrastructure/agent-operations domain; resource + deployment risk |
| Legal Counsel | Yes | widened off-machine data egress; OSS licensing |
| Client Advocate | Yes | non-aldeia-box OSS project; Jan's pre-queue direction fidelity |
| QA Director | No | chair decision — QA concerns (AC↔test adequacy, docs-assertion gap) folded into CPO/CTO mandates; test-phase council will cover quality gates directly |

## Context Presented

v0.6.0 closes master-spec OQ#8: the `wiki_contradictions` property and the v0.5.0
`contradiction_unresolved` lint check shipped schema-only / passive. This release adds
**cross-object** contradiction detection at ingest time — when an entity is updated, the
pipeline asks an LLM whether the new facts contradict the facts of already-linked peer
entities (bounded by `wiki_relations`), and if so writes a **bidirectional**
`wiki_contradictions` link on both objects (Hermes policy: document both, flag, never
overwrite, human resolves; `wiki_last_reviewed` left null), then activates the lint check.

The spec passed three internal technical review rounds (R1 with 3 specialist sub-reviews →
R2 → R3), converging to APPROVED. R1 caught 7 real implementability blockers (missing
read-plane client, `.format()`-on-JSON crash, incoherent target-read source, wrong test
name, nonexistent `test_live.py`, unhandled tuple-return call site, undefined `ollama_base`);
R2 caught a silent-detection bug *introduced by the R1 fix* (`_existing_text` reads
text-format props only, returns `""` for objects-format relations → empty candidate set →
detection never fires), fixed via a new `_relation_ids` helper placed circular-import-safe in
`util.py`; R3 verified the fix at every call site. Jan's pre-queue feedback (cross-object
framing, #289 boundary, distinct signals, POST-search wire contract, schema v0.4.1 by-key
logic) was provided and assessed for fidelity.

## Discussion

The council reviewed in parallel with cross-functional flagging. The discussion converged on
two themes that recurred across multiple seats:

1. **The "no target GET" platform assumption (raised by CTO, ADV-1; operationally seconded by
   Infrastructure).** CTO independently verified against source that *every* existing reader of
   objects-format `objects` arrays in the codebase operates on a `get_object` result
   (`query.py:720`, `query.py:924`, `lint.py:420`) — **zero** code paths read `prop.get("objects")`
   off a `search()` result, and the existing update-path search fixture returns text-format props
   only. The spec's §3.3/§3.4/§4 "NO target GET" design depends on POST `/search` returning
   *hydrated* `properties[].objects` for `wiki_relations`/`wiki_contradictions`. If Anytype's
   search returns lean objects (common for search endpoints), detection silently no-ops in
   production — green-in-CI, dead-in-prod, the exact failure class R2 caught, relocated to an
   untested platform assumption. CTO noted R3 "closed" R2's SF-B by requiring the *test fixture*
   to be objects-shaped, which validates nothing about real Anytype behavior and risks a
   self-fulfilling test. Infrastructure concurred this is the one operational gotcha that could
   ship green and fail silently. **Consensus: not a spec blocker (cheap pre-identified fallback —
   one target `get_object`, +1 call; live smoke AC-8 would expose it), but a mandatory
   validate-against-real-Anytype impl-phase exit criterion.**

2. **Widened off-machine disclosure scope — docs disclosure (raised independently by CSO ADV-1,
   CPO A-1, Legal ADV-1, Client ADV-1).** Four seats independently flagged the same gap from
   different angles: contradiction detection ships peer objects' `wiki_facts` (distilled from
   *other, previously-ingested* sources) to a possibly-remote LLM, broader than #284's
   single-source egress. The README privacy notice (README.md:46-47) still describes egress as
   "the source content you ingest" — the v0.3.0 model. Separately, the lint check now returns
   *active* (passive caveat removed by design), but v0.6.0 only detects contradictions among
   **already-linked** peers (DI-3) — an operator could over-trust a green result as "no
   contradictions in my wiki," the very over-trust failure mode the release set out to fix.
   - **Legal:** for an MIT, local-first, no-telemetry, operator-as-controller tool, reliance on
     the *existing* consent gate (no new gate, no forced re-consent) is **legally sufficient** —
     consent specificity attaches to the controller↔data-subject relationship, not a publisher↔
     self-hosting-operator one. The obligation is **transparency/duty-to-warn**, satisfied by a
     specific README disclosure. Not a blocker.
   - **CSO:** concurred the existing gate is the correct/sufficient *control* (defense-in-depth:
     anti-injection preamble in file + OSError fallback, plus the hallucinated-ID candidate-set
     filter that bounds any injection's blast radius to already-linked peers). Flagged stale
     consent (pre-v0.6.0 ackers get the broader scope silently) and recommended banner re-wording.
   - **CPO/Client:** the operator-facing scope limitation (linked-peers-only) and entity-only
     scope (DI-1) must ship *in the same release as the activation* — docs sweep (§8 step 11) must
     be treated as **gated, not best-effort**.

3. **Reviewer diligence verdict (CTO).** The review process did its job — R1 blockers were all
   substantive (spot-checked BL-1/BL-3/BL-6/BL-7 against source), R2 caught a real
   reviewer-introduced regression by reading the code not the document, R3 was correctly scoped.
   The one weakness: R2's SF-B (does search return objects-format arrays?) was resolved with a CI
   fixture rather than flagged as a must-validate-against-real-platform gate — surfaced here as
   ADV-1 and carried into the addendum.

4. **Resource fan-out (Infrastructure ADV-1).** Candidate set is bounded (O(relations), single
   batch Ollama call), but not *capped* — a hub entity with many `wiki_relations` produces a large
   single prompt + N peer GETs + up to 2N PATCHes, which can transiently spike local-Ollama latency
   on the shared machine. Degrade-not-block absorbs timeouts (no stability threat); a defensive
   candidate cap is a reasonable v0.6.x defensive bound. Monitoring gap (ADV-2): the degraded
   warning is passive — nothing watches it, so chronic Ollama unavailability would silently render
   detection dead. Ops follow-up, not a spec defect.

## Findings

### BLOCKING
None.

### ADVISORY

1. **[CTO-ADV-1 — elevated]** "No target GET" rests on an unvalidated platform assumption that
   POST `/search` returns hydrated `properties[].objects` for `wiki_relations`/`wiki_contradictions`.
   Every existing objects-format read in the codebase is off `get_object`, not `search`. Risk:
   detection silently no-ops in production (green-in-CI, dead-in-prod). Action: impl MUST validate
   against a *real* Anytype search response before relying on no-target-GET; if arrays are absent,
   add a single target `get_object` and correct §4's "NO target GET" claim. The AC-1 objects-shaped
   fixture does NOT validate this. → addendum item 1.
2. **[CSO-ADV-1 / CPO-A-1 / Legal-ADV-1 / Client-ADV-1 — converged]** README + CHANGELOG must
   disclose, before release: (a) the *widened peer-fact egress scope* when a remote
   `WIKI_EXTRACT_ENDPOINT` is enabled (peer `wiki_facts` from earlier ingests now leave the machine,
   not just the current source); (b) the *linked-peers-only detection limitation* (DI-3) so a green
   check is not over-trusted; (c) *entity-only scope* (DI-1). Docs sweep (§8 step 11) must be treated
   as a gated deliverable. → addendum items 2, 3.
3. **[CSO-ADV-1]** Stale consent: pre-v0.6.0 remote-endpoint ackers receive the widened scope with
   no re-prompt. Update consent banner copy to "source and previously-stored wiki content"; consider
   a version-bumped ack key for re-consent (product hygiene, not legally required). → addendum item 4.
4. **[CPO-A-1 / Client-ADV-1 / CTO]** Test honesty: nothing asserts the operator-facing
   linked-peers-only caveat actually lands in the README, and the objects-shaped search fixture
   entrenches the unvalidated platform assumption. The test phase should add a docs-presence
   assertion and a comment noting the fixture does not validate real platform behavior. → addendum item 5.
5. **[Infra-ADV-1]** Fan-out bounded but not capped — a hub entity yields a large single prompt +
   N peer GETs + 2N PATCHes. Defensive candidate cap (~K=20) deferrable to v0.6.x. → noted, not gated.
6. **[Infra-ADV-2]** Silent-degradation monitoring gap: `contradiction_detection_degraded` is passive.
   The scheduled ingest caller should surface a degraded-count to ntfy above a threshold. Ops
   follow-up, post-merge. → noted, not gated.
7. **[CTO-ADV-2]** `except Exception` in the hook (§3.5a) will swallow logic errors as transient
   degradation. Acceptable for a degrade-safe seam; document the breadth intentionally. → noted.
8. **[CTO-ADV-3]** Double-fault rollback (A written, B failed, A-revert failed) leaves a one-sided
   link; self-healing via the High lint finding. Add a one-line note in §6. → noted.
9. **[Legal-ADV process]** A feature that broadens an off-machine data class should trip a
   "privacy-disclosure review" in the *product* checklist before spec sign-off. The spec author
   self-reported SF-6 correctly (commendable), but recommend the pipeline add this flag upstream.
   → chair pipeline-improvement note.

## Resolutions

- The egress-gate question was resolved cross-functionally: Legal (sufficiency under
  operator-as-controller), CSO (correct control + defense-in-depth), and Infrastructure (no new
  network surface; default-local Ollama keeps it on-box) all concurred **no new gate is required** —
  the obligation is a specific README/CHANGELOG disclosure, captured as addendum items 2–4. No member
  pressed for a hard re-consent gate as a blocker.
- CTO's reviewer-diligence audit cleared the review chain as genuine (not rubber-stamping), with the
  single SF-B "closed-by-fixture" weakness elevated to ADV-1 rather than treated as a process failure.

## Recommendation

**Recommended target:** test
**Confidence:** high
**Rationale:** Unanimous sign-off, zero BLOCKING findings. The spec is implementable, internally
coherent, faithful to Jan's pre-queue direction, and its core contract is CI-verifiable. The next
phase per the SDLC order is `test`. The advisories impose concrete next-phase acceptance/exit
criteria (search-response validation, gated docs disclosure, consent-banner copy, a docs-presence
test) — captured authoritatively in `spec-addendum-post-spec-r1.md`. None rises to a spec blocker;
all are addressable within test/impl.
**Dissent:** None.
