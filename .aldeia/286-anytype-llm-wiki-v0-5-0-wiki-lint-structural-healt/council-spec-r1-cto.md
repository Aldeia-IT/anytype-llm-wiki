# Council Spec Review R1 — CTO

**Ticket:** #286 — wiki_lint v0.5.0 (structural health check)
**Reviewer:** CTO (Aldeia-IT review council)
**Date:** 2026-06-05
**Phase reviewed:** Spec (post R1/R2, commits d4a2606 + 7ab44e7)

## Verdict: SIGN OFF (no veto)

The spec is technically sound and well-grounded against the real post-#303
codebase. Every load-bearing helper, line reference, wire contract, and
schema-placement claim I spot-checked is accurate. The B1 duplicate-band fix
is correct and necessary. The phase reviewers (R1/R2) demonstrably verified
against source rather than reviewing prose. One integration risk (D1
backlinks) is honestly disclosed and defensively designed; it is ADVISORY,
not BLOCKING.

---

## BLOCKING

**None.**

---

## What I Verified Against Source

| Claim | Source checked | Result |
|-------|----------------|--------|
| D2: no `stub` tag | bootstrap.py:57 | CONFIRMED `_WIKI_STATUS_TAGS = ["needs-review","reviewed","archived"]`. `stale_stub` could never fire. |
| `lint` action tag seeded | bootstrap.py:54 | CONFIRMED `_WIKI_ACTION_TAGS = [...,"lint",...]` index 2. No bootstrap change needed. |
| B1: `index_threshold()` is a COUNT not a score | config.py:67-69 | CONFIRMED returns `WIKI_INDEX_THRESHOLD` default 200, "object-count flip". R1's B1 defect was a genuine catch. |
| `_positive_int` is int-only (justifies new `_bounded_float`) | config.py:45-58 | CONFIRMED `int(raw)`. Cannot express 0.85. New guard is necessary, not gold-plating. |
| `semantic_search_core` signature + score | indexer.py:20, :79 | CONFIRMED `(query, space_id, types, limit)`; `"score": round(r.score,4)` cosine 0-1. Band `[0.70,0.85)` is dimensionally correct. |
| `_qdrant`, `embed_query` | indexer.py:16, embedder import :13 | CONFIRMED. |
| Reused helpers | query.py:72/474/684/709, ingest.py:212/241/447, util.py:82/98/229, remember.py:124/659 | ALL CONFIRMED at exact lines with compatible signatures. |
| QA#25 three branches | query.py:424-448 | CONFIRMED exact: None→`wiki_schema_missing` abort; `<0`→`wiki_schema_outdated` abort; `>0`→`wiki_schema_newer` warn-continue. error_category set on aborts. SF4 fix is faithful. |
| D5 wire contracts | wiki_client.py:113/127/133/136, anytype_client.py:44-52 | CONFIRMED: search POST `/search`; tag resolution two-step `/properties/{id}/tags`; no space-level `/tags`; get_object GET `?format=md` returning `resp.json()["object"]`. |
| SF5 age-derivation (highest-value catch) | types_schema.py:79/93/96/109 | CONFIRMED `wiki_ingested_at` on `wiki_source` ONLY; entity/concept carry `wiki_sources` (objects) and NO top-level ingest timestamp. Cross-source dereference is mandatory and correct. |
| SF9 contradiction scope | types_schema.py:97 vs 101-112 | CONFIRMED `wiki_last_reviewed` on `wiki_entity` only, absent from `wiki_concept`. Entity-only scoping correct. |
| Schema version | types_schema.py:27 | CONFIRMED `WIKI_SCHEMA_VERSION = "0.4.1"`. QA#25 `code="0.4.1"` correct. |
| D3 conflict signal | remember.py:659-673 | CONFIRMED `_flag_conflict_status` sets `wiki_status=needs-review`, no separate conflict marker. Both needs-review checks keying on the status are justified. |
| #303 is recent, not greenfield | git log | CONFIRMED commit 56249a3 (schema rename) immediately precedes this ticket. Spec correctly treats system as mature; reads by KEY. |
| Truncation precedent (SF12) | query.py:347 | CONFIRMED `strip_control_chars(question)[:50]`. |
| Dual-client (G7) | query.py:405-406 | CONFIRMED `AnytypeReadClient()` + `WikiClient()`. |
| cli SUBCOMMANDS | cli.py:21 | CONFIRMED tuple exists; "wiki-lint" addition is coherent. |

No invented helpers found. No alternative-stack introductions (band fix
reuses existing config idiom; bge-m3/Qdrant/respx all established).

---

## ADVISORY

### A1 — D1 `backlinks` field name rests on a live-API session finding, not source
**Verified:** grepped `backlinks` across all of `src/` and `tests/` — the only
hit is a comment in `test_ingest.py:391`. No production code reads
`obj["backlinks"]`; no fixture or schema confirms the API emits a top-level
`backlinks` array. technical-research.md §B is explicit: the field name comes
from a "session finding (verified 2026-06-03)," and `get_object` returns
`resp.json()["object"]` verbatim so *whatever* the API includes is passed
through.
**Impact:** D1's "primary path is O(1) backlinks" is an assumption about API
behavior that cannot be validated from the repository. If the field is named
differently or absent on the target Anytype version, the primary path silently
yields empty and every object falls to the O(N) fallback — degrading the perf
win, not correctness.
**Why not BLOCKING:** the spec designs for exactly this — explicit
absent/empty/malformed → fallback (D1 §55, SF10, `test_backlinks_malformed_falls_back`).
The system is safe either way. This is the one place where "verified against
code" was not possible, and the spec is honest about it.
**Recommended action:** during impl, the live smoke test (AC15) MUST assert the
shape of `backlinks` on a real space, and the impl review must confirm the
fallback is actually exercised when the key is absent (not just present-empty).
Flag to infra-lead: the perf budget (~51s @ 500) assumes the O(1) path; if
backlinks is absent in production, every run pays the fallback traversal on top
of the get_object fan-out.

### A2 — Citation path imprecision for the indexer module
**Verified:** the indexer lives at `src/anytype_llm_wiki/indexer.py` (package
root, imported `from .. import indexer` at query.py:36), NOT
`src/anytype_llm_wiki/wiki/indexer.py`. The spec's Reuse table cites bare
"indexer.py:16/20/79" without a path. Line numbers and signatures are all
correct.
**Impact:** cosmetic; an implementer following `from .. import indexer` (the
existing pattern) will land correctly. No functional risk.
**Recommended action:** none required; optionally note the `..` import in the
impl.

---

## Reviewer Diligence Assessment

R1 and R2 are credible and source-grounded, not document-only reviews:

- **R1 caught the real B1 defect** (object-count used as a cosine bound) with
  exact evidence (config.py:67, indexer.py:79) — independently reproduced here.
  This is precisely the #285/#289 value-semantics failure mode the council
  worries about, and R1 caught it before impl.
- **R1's "Verified-correct" block** claims all helpers exist at cited lines
  "off by ≤1 in two cases." I independently confirmed ~14 of them at exact
  lines — the claim holds; this was not a rubber-stamp.
- **R2's APPROVED is credible.** It re-verified the high-risk fixes (SF5/SF4/SF9)
  against specific line numbers that I confirmed are accurate. R2 did not hedge
  with "should work"; its claims are checkable and checked out.
- **The one gap both rounds share:** neither R1 nor R2 flagged that D1's
  `backlinks` field name is unverifiable from source (A1). Both accepted the
  research's session-finding. This is a minor diligence gap, mitigated by the
  spec's own defensive fallback — but the impl-phase review must close it with
  a live-shape assertion.

## Jan's 5 Deltas — Coverage Confirmed

1. Broken `stub` check → D2 re-targets to `stale_needs_review` (no schema bump). CONFIRMED against bootstrap.py:57.
2. New `needs-review` live signal (#289) → D3 `unreviewed_needs_review` High. CONFIRMED against remember.py:659.
3. Reuse v0.4.0 infra → D4 reuses `_qdrant`/`semantic_search_core`/per-run cache. CONFIRMED importable.
4. O(N) enumeration / §9 budget → Performance Budget section with per-phase arithmetic + `WIKI_LINT_MAX_OBJECTS` cap. Honest.
5. Schema v0.4.1, read by KEY, pin wire contracts → D5. CONFIRMED two-step tag resolution, search POST, key-based reads.

All five deltas map to a locked decision and each is validated against source.

---

## Sign-Off

I **sign off** on the spec phase for #286. It is technically accurate, aligned
with the real codebase, follows established patterns (config guards, dual-client,
WikiLog receipt, respx mocking), and the prior reviews did their job. The single
unverifiable claim (D1 backlinks field) is honestly disclosed and defensively
designed, so it carries no correctness risk — only a perf-degradation risk that
the live smoke test and impl review must close.

Carry A1 forward as an explicit impl-phase verification gate.
