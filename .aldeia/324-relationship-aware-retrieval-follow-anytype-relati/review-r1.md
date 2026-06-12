# Specification Review: wiki_query #324 — Relationship-Aware Retrieval (R1)

**Reviewed:** 2026-06-11
**Spec commit:** ac90b03
**Domain:** agent-operations (retrieval pipeline) + performance + security
**Specialists invoked:** Completeness/QA (qa-director), Architecture (chief-technology-officer), Security (chief-security-officer), Infra/Performance (infrastructure-lead)

## Executive Summary

A well-constructed, codebase-aligned **delta** spec (441 lines — under the ≤600 budget; #285 invariants referenced by ID, no bloat). All six task acceptance criteria are covered and the four cross-cutting decisions are made explicitly, not hand-waved. The design intent is **sound** — security (injection-amplifier bound preserved via the seed-only `filed_sources` split) and infra (bounded, gracefully-degrading fan-out) both sign off conditionally with no architectural veto.

The blocking issues are **mechanical under-specification of D5's implementation mechanics** (the return-shape changes to `_neighbor_ids_of` and `_build_context`) plus **stale/incorrect references** (British-spelled test names that don't exist; pseudocode citing non-existent variables; an inaccurate security claim). These are fixable in one revision pass; the architecture is not in question.

**Verdict:** NEEDS REVISION

BLOCKING count: 4 (below the ≥8 scope-signal threshold; no decomposition needed — proceed to fix cycle).

---

## BLOCKING

**B1 — D5's relation-priority secondary key has no data source; `_neighbor_ids_of` discards the relation key.** (CTO)
`_neighbor_ids_of` (query.py:679-687) iterates `_RELATION_KEYS` and `extend`s all ids into ONE flat list — the relation key under which each neighbour was found is lost before the caller sees it. D5's secondary sort key (relation_priority) is therefore uncomputable as specified. **Fix:** spec must state `_neighbor_ids_of` returns `(id, relation_priority)` pairs (priority = index of the matching key in `_RELATION_KEYS`), and the seed-fetch caller pairs each with the current seed's rank. Make the implementation-plan step concrete about this return-shape change.

**B2 — `_build_context` return shape unspecified for the D1/D2 split; line-404 pseudocode references non-existent variables.** (CTO, corroborated by Security #3)
`_build_context` currently returns one `contributing` list = surviving candidates (query.py:738-740). D1 needs `sources_consulted` = surviving candidates **+** surviving neighbours; D2 needs `filed_sources` = surviving candidates **only**. That requires returning BOTH sets. The spec's Implementation Plan (line 404) writes `filed_sources = [c for c in ordered if c["object_id"] in candidate_id_set_before_trim]` — but `ordered` is local to `_build_context` (not returned) and `candidate_id_set_before_trim` does not exist (nearest real name: `candidate_id_set`, query.py:525). **Fix:** specify `_build_context` returns `(context_objects, surviving_candidates, surviving_neighbours, trim_warnings)`; `sources_consulted` = candidates+neighbours, `filed_sources` = surviving_candidates. Correct the pseudocode to real variable names, and (Security #3) pin the candidate/neighbour split to the existing `candidate_id_set`/`candidate_id_order` membership, NOT the `score == -1.0` sentinel or list position (fragile).

**B3 — Neighbour D5-ordering carrier undocumented; existing budget-trim test's invariant flips silently.** (CTO, overlaps C1)
Neighbour dicts carry no `seed_rank`/`relation_priority` field (query.py:535 sets only `score=-1.0`). For D5 to hold, `neighbor_ids` must be sorted by `(seed_rank, relation_priority, object_id)` BEFORE the fetch loop and the resulting `neighbors` list order preserved into `_build_context` (nothing re-sorts it there). The spec implies this but never states that list order is the sole carrier of D5 priority. Separately, `test_synthesis_context_budget_trims_neighbors_first` (test_query.py:1678-1682) asserts `len(sources) <= 2` on the old "candidates only" meaning; under D1 the assertion's semantics flip (now counts candidates+neighbours) yet still passes at cap=2 — a real behavioural change rides under a green test. **Fix:** state the list-order-is-the-carrier contract explicitly; note in AC9 that the existing assertion's meaning changes so the implementer doesn't assume it still validates the old invariant.

**B4 — Test references name nonexistent (British-spelled) artifacts.** (QA X1, corroborated by CTO S4)
Spec lines 339, 368, 394 reference `TestNeighbourhoodCacheReplacement` / `test_shared_neighbour_fetched_once`; the actual artifacts are `TestNeighborhoodCacheReplacement` / `test_shared_neighbor_fetched_once` (American spelling — test_query_fetch_paths.py:73,75). The "already exists; verify it covers the new path" instruction is unactionable as written and risks a duplicate British-spelled class. **Fix:** correct all references to the American names; state that NEW test classes/methods use American spelling to match the file's existing convention.

---

## SHOULD-FIX

**SF-A — Default cap 32 exceeds the synthesis ceiling (24); up to ~16 get_object round-trips/query are wasted.** (Infra SHOULD-FIX 1 + CTO S3, quantified, two reviewers)
Neighbours are fetched (cap 32) then trimmed to `synth_max_objects=24` in `_build_context`. With ~8 surviving candidates, only ~16 neighbour slots can ever reach synthesis, yet 32 are fetched — up to 16 wasted serial localhost GETs (~80-320ms) per high-fan-out query, directly against the #287 HIGH latency concern the spec itself cites. The "8 slots of headroom" rationale is inverted (headroom above the synth ceiling = wasted work, not safety). **Fix:** set default ≤ `synth_max_objects` (lead recommends **16**; the dynamic ceiling `max(0, synth_max_objects - len(candidates))` is an alternative), and reframe the knob as a pure fan-out ceiling decoupled from the synthesis trim. Drop the "headroom" framing (subsumes CTO S3 / Infra SHOULD-FIX 2).

**SF-B — Citation `title` is raw `obj.get("name")`, NOT name-policy checked; the spec's security claim is inaccurate.** (Security #2)
`sources_consulted` entries use raw `obj.get("name","")` (query.py:567-572). The synthesis-context path applies `_safe_object_name` (via `_truncate_object_content`), but the citation title does not. #324 widens the blast radius: neighbour titles (attacker-influenceable) now appear in `sources_consulted` for the first time and are returned to the calling LLM outside any fence. No write-sink leak (only object_ids reach `wiki_drew_from`; filed name is `_safe_name(question)`), so not blocking — but the spec's claim (lines 291-292) that "all neighbour object names pass through `_safe_object_name`" is **false for the citation path**. **Fix:** either route citation titles through `_safe_object_name`/`sanitize_name`, or correct the spec claim and explicitly document citation titles as deliberately-raw data the consumer must treat as untrusted.

**SF-C — `wiki_contradictions` (objects-format relation on entity+concept) silently omitted from the relation-set decision.** (CTO S1)
types_schema.py:95 (entity) and :111 (concept) define `wiki_contradictions` as `format: objects` — a real graph edge, arguably high-value retrieval context (a contradicting source is exactly what a careful answer should surface). It's in neither the current nor proposed `_RELATION_KEYS`, and D3 never explains the exclusion though it sets the "explicit final set with rationale" standard for `wiki_subjects`. **Fix:** state the `wiki_contradictions` decision (include, or deliberately defer with rationale) for parity.

**SF-D — Tier-1 "enumeration order" seed rank is not guaranteed deterministic.** (CTO S2)
Tier-1 builds `candidate_entries` from `wiki_objects` (unsorted `list_objects` output, query.py:478-485). D5 (line 162) defines Tier-1 seed rank as "enumeration order," deterministic only if Anytype pagination is stable across calls — unverified. **Fix:** sort Tier-1 `candidate_entries` by `object_id` to pin seed rank, OR document the dependence on Anytype enumeration stability as an accepted risk.

**SF-E — Fan-out count observable only at DEBUG (off by default) → AC#5 "measurable" fails in steady state.** (Infra SHOULD-FIX 3)
D6's `logger.debug` line is invisible at the default `info` level; the only INFO+ signal (`neighbor_fan_out_capped`) fires only when the cap binds. In the normal un-capped case the operationally interesting number (extra round-trips this query cost) is invisible without a debug rerun. **Fix:** promote the fan-out count to INFO when `fetching` exceeds a modest threshold (e.g. > synth_max_objects/2), OR always append an informational `neighbor_fanout: fetched=N` entry to `result["warnings"]`. (Do NOT add a required result-dict field — the spec's rejection of that is endorsed.)

**SF-F — AC5 fetch-count assertion is "at most 2"; should be exactly the capped count and which ids.** (QA C2)
The cap is a deterministic slice to exactly `min(distinct, cap)`. "at most 2" passes even on a 0/1-fetch bug. **Fix:** assert exactly 2 distinct neighbour ids fetched AND that they are the D5-top 2 (binds the ordering contract).

**SF-G — Undocumented edge case: all neighbours trimmed out.** (QA E1)
When seeds alone meet/exceed `synth_max_objects`, zero neighbours survive → `sources_consulted` = seeds only. Correct but never stated. **Fix:** one sentence in AC1/AC4: "If no neighbours survive the budget trim, `sources_consulted` contains seeds only and no warning beyond `synthesis_context_trimmed`."

**SF-H — Undocumented edge case: neighbour fetch failure interaction with the cap.** (QA E2)
The cap is applied before the fetch loop, so a failed neighbour (existing `neighbor_fetch_failed`/`partial`) consumes a cap slot a survivable neighbour could have used, and is excluded from `sources_consulted` (no `obj`). Defensible but ambiguous. **Fix:** state explicitly: "the cap bounds fetch *attempts*; a failed neighbour consumes a slot and is excluded from `sources_consulted`, preserving #285 partial-status semantics."

**SF-I — `_maybe_file_back` signature delta + fate of now-unused `sources_consulted` param.** (QA X2 + CTO S4)
D2 inserts `filed_sources` after `sources_consulted`, but post-D2 only `filed_sources` feeds the gate/SF4/write — the original `sources_consulted` param becomes dead weight at the sole caller (query.py:595). **Fix:** show before/after signature; either drop the unused `sources_consulted` param or document why it stays.

**SF-J — `.env.example` entry lacks rationale + operational note.** (Infra SHOULD-FIX 4)
Every sibling knob carries a 2-3 line comment; the proposed one-liner doesn't warn that raising the knob increases per-query latency and Anytype API pressure, or that raising it above `synth_max_objects` fetches discarded objects. **Fix:** match the block style; add the operational note.

---

## SUGGESTION

- **SG-1 (QA A1):** Note the warning string uses ASCII `->` (not Unicode `→` as research wrote) — the test asserts an exact string.
- **SG-2 (CTO G1):** State plainly in AC7 that D2 is behaviour-**preserving** for the min-sources gate (a no-op-preserving refactor forced by D1), not a new safeguard.
- **SG-3 (Security advisory):** Add an explicit accepted-risk note that the global neighbour cap has no per-seed sub-cap, so an over-linked rank-0 seed can dominate the neighbour budget (D5 makes rank-0 win). Acceptable under the local trust model; surface it beyond Deferred Items.
- **SG-4 (Infra SUGGESTION 1):** One sentence that the cap also bounds per-session Anytype API pressure under concurrent Claude Code workers.
- **SG-5 (Infra SUGGESTION 2):** Add an AC asserting partial-status preservation under one-failed + one-succeeded neighbour fetch with D5 ordering active (D5 reorders the very loop that produces these failures — worth a regression test).
- **SG-6 (Infra SUGGESTION 3):** Reference the AnytypeReadClient per-call timeout as the ceiling that makes "cap × per-call" a real latency bound.

---

## Verification Audit (lead spot-checks)

- B1 confirmed: `_neighbor_ids_of` (query.py:679-687) flattens all relation keys into one id list — relation key is lost. ✔
- SF-B confirmed: citation entry uses raw `obj.get("name","")` (query.py:567-572); name policy applies only to the synthesis-context copy via `_truncate_object_content`. ✔
- SF-A confirmed: `DEFAULT_WIKI_SYNTH_MAX_OBJECTS=24` (config.py:46) < proposed cap default 32 (spec:127). ✔
- Wire-contract (get_object GET `.../objects/{id}?format=md`, single-dispatcher mock) verified accurate by CTO G2. ✔
- Reviewer diligence: research line citations spot-checked accurate by CTO; reviews are code-grounded, not document-only.

## Process note
Reviewers reported `.claude/agents/<role>.md` absent in the worktree (checklists live in `~/.claude/agents/`). Future review dispatches should point reviewers at `~/.claude/agents/<role>.md`. Did not affect review quality.
