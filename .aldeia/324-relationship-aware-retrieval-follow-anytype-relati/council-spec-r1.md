# Council Meeting — Post-Spec (Round 1)

**Date:** 2026-06-12
**Ticket:** #324 — Relationship-Aware Retrieval (follow Anytype relations)
**Phase reviewed:** spec
**Client:** anytype-llm-wiki
**Spec commit:** a18b10c

## Attendance

| Role | Present | Reason |
|------|---------|--------|
| Council Chair | Yes | moderator (lead acting as chair — watcher council short-circuited on prior run; convened manually per Jan's instruction, root cause aldeia-box#333) |
| Chief Security Officer | Yes | post-spec minimum; data-handling + attack-surface sign-off |
| Chief Product Officer | Yes | post-spec minimum; product alignment + OQ1 decision |
| Chief Technology Officer | Yes | post-spec minimum; technical accuracy + reviewer-diligence audit |
| Legal Counsel | No | local single-tenant tool, no PII/third-party/regulatory surface introduced by this delta |
| QA Director | No | test coverage already validated in internal R1/R2; no acceptance-criteria gap surfaced |
| Infrastructure Lead | No | no deployment/service-config change; fan-out latency bound already covered by spec Resource Impact + SG-6 |
| Client Advocate | No | no external-audience artifact; internal product feature |

## Context Presented

#324 is a tightly-scoped **delta over v0.4.0 (#285)**. `wiki_query` already does 1-hop
neighbour traversal; this spec changes four things: (D1) cite surviving neighbours in
`sources_consulted` — closing a citation-honesty gap where answers drew on neighbour content
the caller never saw; (D2) keep file-back (`wiki_drew_from`) seed-only via a `filed_sources`
split, preserving the #285 SF1 injection-amplifier bound; (D3–D5) finalize the relation set to
5 keys, add a bounded fan-out cap (`WIKI_QUERY_MAX_NEIGHBORS=16`), and a single deterministic
total order `(seed_rank, relation_priority, object_id)`; (D6) measurability via DEBUG log + a
conditional INFO `warnings` entry.

The spec passed two internal review rounds: R1 returned NEEDS REVISION (4 BLOCKING + 10
SHOULD-FIX, all mechanical); the spec-fixer addressed every finding in a18b10c; R2 confirming
review returned APPROVED with code-grounded verification. This post-spec council is the
**governance gate** — it had not actually convened on the prior run.

## Discussion

The three officers converged independently. The central security claim — that the SF1
injection-amplifier bound stays seed-scoped — was verified by the **CSO against real source**:
`_maybe_file_back` drives both the min-sources gate and the `wiki_drew_from` write loop from the
parameter D2 replaces with `filed_sources` (surviving candidates only), so neighbours never
reach the write sink by construction. The CSO also confirmed the "no SSRF / no new attacker
surface" claim by tracing neighbour ids to `_parse_relation_elements` (opaque Anytype object
ids, consumed only against the fixed loopback base URL with a 30s timeout and the fan-out cap).

The **CTO audited reviewer diligence** by spot-checking nine load-bearing code claims against the
worktree source (`_neighbor_ids_of` flat-list current shape, `DEFAULT_WIKI_SYNTH_MAX_OBJECTS=24`,
current 4-key `_RELATION_KEYS` missing `wiki_sources`, American test-class names, `_safe_object_name`
behaviour, raw pre-#324 citation title, the `score=-1.0`/`candidate_id_set` structures, `_TIMEOUT=30`,
types_schema relation formats). **All nine held.** The CTO rated the internal review DILIGENT, not a
rubber-stamp: R1 caught four real mechanical defects (a discarded relation key that made D5's
secondary sort uncomputable, a phantom `candidate_id_set_before_trim`, a silently-flipping test
invariant, British-spelled nonexistent test artifacts), independently confirmed as real draft bugs.

The **CPO** judged scope discipline exemplary (depth-1 only; no re-embedding; no new MCP surface;
N-hop, contradiction-surfacing, and full neighbour provenance each explicitly deferred with
rationale) and took a firm position on the one open product question.

## Findings

### BLOCKING

None. All three officers signed off with zero blocking findings.

### ADVISORY

1. **[CSO] Consumer-trust boundary on `sources_consulted`.** Citation *titles* are sanitized via
   `_safe_object_name`, but entries also carry `deeplink`/`object_id` for attacker-influenceable
   neighbour objects now returned outside the `<context>` fence for the first time. Low risk
   (deeplinks built from server-controlled ids), but the contract should state that the consumer
   must treat titles as data and not auto-follow deeplinks as trusted. Documentation note, not a code gap.
2. **[CSO] Accepted-risk (SG-3, no per-seed sub-cap) is sound but rests entirely on the
   single-tenant local trust model.** If `anytype-llm-wiki` ever gains multi-user / shared-vault
   exposure, both this accepted-risk and the SF1 bound need re-derivation. Worth a one-line note in
   the durable threat-model record so a future maintainer doesn't inherit the assumption silently.
3. **[CSO] `wiki_contradictions` deferral is correct** — the deferred ticket must not re-introduce
   it as a naive relevance edge without re-examining the file-back/provenance path.
4. **[CPO] No seed-vs-neighbour provenance marker in `sources_consulted`.** Seeds and neighbours
   merge into one flat list with no origin flag. Acceptable for v1 (full neighbour provenance is an
   explicit, disciplined deferral); track "neighbour provenance distinction in citations" as a
   fast-follow once real query transcripts show whether the undifferentiated list confuses
   downstream agents. AC1/AC3 correctly verify presence+dedup and need not assert labeling.
5. **[CPO] Default cap of 16 rests on an estimate ("research Q6"), not measured production data.**
   Low-stakes and fully reversible via env var. Confirm real-world distinct-neighbour counts against
   the default once shipped; adjust the documented default if vaults routinely exceed it. No spec change.
6. **[CTO] D5 Tier-1 determinism** is pinned by sorting `candidate_entries` by `object_id` (SF-D) —
   implementer must apply the sort to the Tier-1 branch only (Tier-2 already arrives score-ranked).
7. **[CTO/CPO] Resource numbers (~5–20ms/call) are asserted, not benchmarked in this delta.** The
   D6 `neighbor_fanout: fetched=N` INFO instrument is the right way to validate the assumption
   post-ship; steady-state observation recommended once the cap × 30s-timeout bound is exercised.

## Resolutions

**OQ1 — `wiki_subjects` retention.** The spec retained `wiki_subjects` as a 5th relation key — a
deliberate deviation from the strict four-key #324 brief — and flagged it for confirm/veto.
**Council position: CONFIRM RETENTION (CPO, concurred by CTO).** Dropping it to satisfy a literal
four-key count would silently regress comparison→subject traversal that v0.4.0 already ships — a
user-visible correctness loss to honour a count, not an intent. The deviation is cheap, documented,
and confined to one AC2 test case. Recorded here as a traceable council decision so the "five keys,
not four" choice is not re-questioned as unexplained scope creep. Jan retains final veto at the
Decide gate; absent veto, retention stands.

No findings were withdrawn during discussion; all three officers' positions were independently
consistent.

## Recommendation

**Recommended target:** decide
**Verdict:** APPROVED — advance.
**Confidence:** high
**Rationale:** Unanimous officer sign-off, zero BLOCKING findings, and a genuinely code-grounded
internal review confirmed by independent CTO spot-checks (9/9 claims held). The spec is technically
accurate, implementable as written, scope-disciplined, and risk-reducing on every security-relevant
axis (file-back narrowed to seeds, citation titles sanitized, fan-out bounded). The natural next SDLC
phase is **test**; routing to **Decide** per the autonomy policy (post-spec is not autonomous) and
Jan's dispatch instruction, so Jan confirms the OQ1 retention decision and selects the next move. The
seven advisory items are documentation notes, forward-looking threat-model hygiene, and post-ship
observations — none gate phase exit.
**Dissent:** None.
