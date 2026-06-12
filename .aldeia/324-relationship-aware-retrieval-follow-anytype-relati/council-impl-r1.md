# Council Meeting — Post-impl (Round 1)

**Date:** 2026-06-12
**Ticket:** Aldeia-IT/aldeia-box#324 — Relationship-aware retrieval: follow Anytype Relations to pull connected context
**Phase reviewed:** impl (final delivery gate)
**Client:** anytype-llm-wiki (epic aldeia-box#140)
**Branch tip:** 18ffba8

## Attendance

| Role | Present | Reason |
|------|---------|--------|
| Council Chair | Yes | moderator / verdict synthesis |
| Chief Security Officer | Yes | post-impl minimum |
| Legal Counsel | Yes | post-impl minimum |
| Chief Product Officer | Yes | post-impl minimum |
| QA Director | Yes | post-impl minimum |
| Chief Technology Officer | Yes | post-impl minimum |
| Infrastructure Lead | Yes | repo domains = infrastructure, agent-operations; API fan-out cost / ops readiness |
| Client Advocate | Yes | `.aldeia/context/` present; post-impl aims for full attendance (last gate before release) |

Full council convened. Post-impl is the final delivery gate — the last chance to catch issues before the PR merges — so attendance was maximized.

## Context Presented

The impl phase delivered the APPROVED D1–D6 delta over v0.4.0 `wiki_query`, implementing 1-hop relationship-aware retrieval:

- **D1** — surviving 1-hop neighbours that fed synthesis are now cited in `sources_consulted` (closes "citation dishonesty"); candidate AND neighbour titles routed through `_safe_object_name` → `[REDACTED]` (SF-B).
- **D2** — file-back stays seed-only: `_maybe_file_back` receives candidate-only `filed_sources`, preserving the #285 SF1 injection-amplifier bound; `wiki_drew_from` + min-sources gate remain candidate-scoped.
- **D3** — `_RELATION_KEYS` finalised at 5 keys (added `wiki_sources`, retained `wiki_subjects` — OQ1 resolved, Jan confirmed "keep 5 keys").
- **D4** — bounded fan-out: new `WIKI_QUERY_MAX_NEIGHBORS` knob (default 16), cap applied before the fetch loop (SF-H: bounds attempts not successes).
- **D5** — deterministic order `(seed_rank, relation_priority, object_id)` as sole carrier; `_build_context` does not re-sort (B3).
- **D6** — `logger.debug` fan-out line + conditional INFO `neighbor_fanout: fetched=N` instrument.
- Plus 3 council-mandated addendum tests (AC-T1 order-isolation, AC-T2 candidate-title sanitization, AC-T3 wiki_subjects traversal).

In-phase technical review (`impl-review-r1.md`) returned APPROVED WITH CONDITIONS (2 MINOR), both fixed in `18ffba8`. Reported suite state: 553 passed, 6 skipped, 2 xfailed, 0 failed. Code diff: `query.py` +143, `config.py` +12, `.env.example` +5, tests +1610, `README.md` −1. No new dependencies, no migration, no new MCP surface.

## Discussion

The council's central question, inherited from the post-test council, was whether the **AC-T1 order-isolation guard (B3 — "list order is the sole carrier of relation priority")** genuinely binds, given the phase summary's honest disclosure that fixture (a) does NOT isolate a no-sort impl in Tier-2 (where `seed_rank == discovery order`), and the guarantee rests entirely on fixture (b).

- **QA Director** resolved this empirically rather than on faith: mutated `query.py` to disable the D5 sort and re-ran `TestD5SortKeyIsolation` — AC-T1(a) stayed GREEN (confirming it only catches an object_id-only sort, as disclosed) while **AC-T1(b) went RED** (`zzz-rel-neighbor` not fetched; `aaa-subj-neighbor` wrongly fetched under cap=1). Restored `query.py` byte-identical and reconfirmed the full suite green. The B3 invariant IS pinned by a real binding test. QA also independently reran the suite: **553 passed, 6 skipped, 8 deselected, 2 xfailed, 0 failed** — confirms the phase-summary claim exactly.
- **CTO** spot-checked five load-bearing invariants against source (not the review narrative): all 5 `_RELATION_KEYS` are real schema properties; the three private-signature changes (`_build_context` 3→4-tuple, `_neighbor_ids_of` str→tuple, `_maybe_file_back` param) are fully propagated with zero stale callers and `warnings_sink` genuinely deleted; B3 sole-carrier holds (`_build_context` does not re-sort); AC3 seed/neighbour dedup is structurally guaranteed at discovery; M2 docstring fix and the binding AC-T1(b) guard are present and correct. Judged the "2 MINOR" outcome credible for a largely mechanical, spec-faithful refactor.
- **CSO** traced the two load-bearing security controls to real source: the SF1 injection-amplifier bound stays seed-scoped (`_maybe_file_back` reads only candidate `filed_sources`; the combined `sources_consulted` count feeds only informational WikiLog notes, never the provenance edge or the min-sources gate), and citation-title sanitization is now symmetric across candidates and neighbours, with the M1 double-warning defect fixed via a throwaway warnings list. No SSRF surface (opaque server-controlled ids, fixed loopback base URL, 30s timeout). No secrets / hardcoded paths.
- **Legal** confirmed zero new dependencies (no `pyproject.toml`/`uv.lock` change), MIT posture preserved, and that the privacy footprint broadens only along the pre-existing, off-by-default, consent-gated `WIKI_EXTRACT_ENDPOINT` path — satisfied by disclosure, not a gate.
- **Infrastructure** confirmed a clean additive delta: no new service, port, log file, data store, or launchd/Colima artifact; worst-case latency deterministically bounded by cap × 30s read timeout; graceful degradation to `partial` status on Anytype `get_object` failure mid-traversal.
- **CPO** and **Client Advocate** converged on the same framing point: the headline change is a provenance/honesty + robustness improvement (v0.4.0 already did 1-hop traversal into synthesis context — #324 makes the neighbours that fed the answer *visible and cited*), and existing callers will see `sources_consulted` return more entries without asking. This is a communication item for the PR/README, not a code defect.

## Findings

### BLOCKING
None. Unanimous — all seven members returned zero BLOCKING findings.

### ADVISORY

1. **[CPO / Client / CTO / Legal — consensus] Surface the `sources_consulted` behavior change in the PR description and README.** Post-#324 an unchanged query can return more entries in `sources_consulted` (surviving neighbours now included). No schema change (entry shape identical), and file-back/`wiki_drew_from` remains seed-only (D2) — but downstream consumers that counted/displayed `sources_consulted` will see different output. Frame the feature as "answers now cite the linked Objects they actually drew from, with bounded, deterministic graph expansion" — NOT as a brand-new "relationship-aware" capability (the wiki already traversed 1-hop). Recommended: one line in the README "Cited synthesis" bullet + a note in the PR body. Non-blocking; can ship in the same PR or a fast follow.

2. **[CSO] Record a durable single-tenant trust-model note.** Both the SG-3 accepted risk (no per-seed sub-cap → over-linked rank-0 seed can dominate the neighbour budget) AND the SF1 injection-amplifier bound rest on the local single-tenant trust assumption. Correctly documented today but scattered across spec invariants and council minutes. Recommended: one durable entry (wiki/mem0) stating that if `anytype-llm-wiki` ever gains shared-vault / multi-tenant exposure, both SG-3 and the SF1 bound must be re-derived before that change ships. (Carried forward from post-spec ADVISORY-2.)

3. **[CSO / Client — deferred-work hygiene] File the deferred items as their own tickets under epic #140.** `wiki_contradictions` traversal and neighbour-level provenance in `wiki_drew_from` are deferred with documented rationale. The `wiki_contradictions` deferral is specifically a *security* decision (adversarial context whose naive inclusion would conflate provenance against the SF1 bound) — its future ticket must re-examine the file-back/provenance path before adding it as a relevance edge. Ensure these don't get lost from the backlog.

4. **[QA / CTO — optional test hardening] Two non-binding test tightenings.** (a) AC3 dedup assertion is `count <= 1` (`test_query_fetch_paths.py:516`), which also passes if the shared object were dropped entirely; tighten to `== 1` to bind presence + uniqueness. (b) The M1 duplicate-warning suppression relies on an implicit cross-function coupling (citation suppression assumes 100% build-path coverage of survivors) with no test pinning the suppression itself; optionally add a regression assertion that a rejected name emits the warning exactly once. Both acceptable to defer.

5. **[Infra / CPO — observability & tuning] Fan-out steady-state is invisible at INFO; default cap rests on an estimate.** Normal-to-moderate fan-out (1–12 neighbours) is only visible at DEBUG; the `neighbor_fanout: fetched=N` INFO warning fires only above 12. The default cap of 16 is reasoned (capped at/below `WIKI_SYNTH_MAX_OBJECTS=24`) but not yet validated against real vault link-density. Recommended: use the shipped D6 instrument to confirm real distinct-neighbour counts post-ship and adjust the documented default only if vaults routinely saturate it. Also note: the per-query cap does not bound cross-worker concurrent fan-out (each worker fans out independently against the shared Anytype API). Operator-tunable via the env knob; no code change.

6. **[CSO / CPO] Consumer-trust contract on citation entries.** `sources_consulted` entries carry `deeplink`/`object_id` for attacker-influenceable neighbour objects now returned outside the `<context>` fence for the first time. Risk is low (deeplinks built from server-controlled opaque ids, not object content), but the consumer-facing documentation should state that titles are untrusted data and deeplinks must not be auto-followed as trusted. Documentation note only.

## Resolutions

- **AC-T1 / B3 order-isolation guard** — raised as the central concern; resolved during the meeting. QA's mutation test empirically proved fixture (b) binds the no-sort guard. The phase summary's disclosure was honest; the residual coverage is adequate. The AC is NOT left unpinned. Withdrawn as a blocker.
- **"2 MINOR for a 143-line change — credible?"** — raised by CTO as a reviewer-diligence check; resolved by CTO's own five-invariant spot-check against source. The diff is largely a mechanical, spec-faithful refactor of pre-existing v0.4.0 machinery; the outcome is credible.
- **Privacy footprint broadening** — raised by Legal; resolved as a documentation advisory (off-by-default, consent-gated remote path; local default is fully on-device).

## Recommendation

**Recommended target:** `done` (approve the PR / final delivery gate)
**Confidence:** high
**Rationale:** Unanimous APPROVE-WITH-ADVISORY, zero BLOCKING findings across all seven members. The delivered D1–D6 delta faithfully solves the stated problem (honest, bounded, deterministic citation of the linked Objects an answer drew from) while preserving the critical SF1 seed-only file-back safety invariant. Three council members verified independently against real source/suite rather than trusting the in-phase review — the B3 order-isolation guard binds (mutation-tested), the suite is green (re-run), and the load-bearing security/engineering invariants hold. All six advisory clusters are forward-looking documentation, deferred-work, observability, and optional test-hardening items; none gates this delivery. The strongest consensus advisory (#1) recommends surfacing the `sources_consulted` behavior change in the PR description / README — recommended for the PR but not blocking.
**Dissent:** None.

## Note on autonomy gating

`config/council.yaml` sets `autonomous: []` (training wheels) — the watcher will route this council's `done` recommendation to the Decide column for Jan's final sign-off rather than auto-approving the PR. The council records its honest recommendation (`done`) regardless; the watcher enforces the autonomy policy.
