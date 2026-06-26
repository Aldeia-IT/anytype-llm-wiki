# Council Meeting — Post-impl (Round 1)

**Date:** 2026-06-26
**Ticket:** #327 — Retrieval: lexical / hybrid dense+sparse fusion
**Phase reviewed:** impl
**Client:** anytype-llm-wiki

## Attendance

| Role | Present | Reason |
|------|---------|--------|
| Council Chair | Yes | moderator |
| Chief Security Officer | Yes | minimum |
| Legal Counsel | Yes | minimum |
| Chief Product Officer | Yes | minimum |
| QA Director | Yes | minimum |
| Chief Technology Officer | Yes | minimum |
| Infrastructure Lead | Yes | chair decision — repo domains are infrastructure / agent-operations |
| Client Advocate | Yes | chair decision — post-impl is the final delivery gate; full roster convened |

Full council convened: post-impl is the last governance checkpoint before release.

## Context Presented

#327 adds **hybrid dense+sparse retrieval** to anytype-llm-wiki: an app-level Reciprocal
Rank Fusion (RRF, k=60) over the existing dense (Qdrant) leg and a new lazy in-memory BM25
(`rank-bm25`) leg, invalidated cross-process via a `bm25_corpus_version` integer stamp in
`state.json`. The `semantic_search` MCP tool and `wiki_query` Tier-2 are switched to the new
`hybrid_search_core`; `wiki_lint` deliberately stays on `semantic_search_core` (out of scope).
v1 is app-level fusion; native Qdrant sparse vectors are deferred to v2 (OD-327-A).

The motivation is a documented, reproduced user-facing failure (the ticket's 2026-06-25
reproduction): dense-only retrieval silently dropped exact-keyword / rare-token / identifier
hits that BM25 recovers.

Delivered: 6 atomic commits (~390 lines in `indexer.py` + tests + docs + one dependency).
The chair **independently re-ran** the full non-live suite: **757 passed, 29 skipped, 2
xfailed** (green). The internal impl review (`impl-review-r1.md`) was APPROVED with 0
CRITICAL/MAJOR; all four MINOR cleanups handled. Both prior spec addenda (post-spec: 7 items;
post-test: 2 carries) were verified honored.

The one known open gate: **AC-EVAL** — the live retrieval-quality eval (`tests/eval/ -m live`)
that is the *single* proof hybrid beats dense — cannot run in the headless sandbox (no live
credentials, Anytype down, the 294-object production wiki unreachable). The impl correctly
shipped a schema-correct fixture *template* + `AC-EVAL-CURATION.md` runbook rather than
fabricating IDs; the live eval must be curated, run green, and recorded on the PR before merge.

## Discussion

The council converged strongly and independently on a single theme: **the code is complete,
correct, and reviewed; the feature's proof-of-value is the only thing outstanding, and it is
an owner-only gate.**

- **CTO** independently verified the RRF math (`1/(k+rank+1)`, k=60, dedup by `_point_id`,
  matches the pinned `pytest.approx(2/61)` in AC-H2b), the cross-process staleness
  invalidation, and — critically — that the **addendum item-1 lock-race fix genuinely
  eliminates** (not merely narrows) the `reembed_object` lost-update hazard: both the cron
  `_run_reindex` bump and the `reembed_object` bump now run under the same `_reindex_lock`
  flock, and a skipped bump is self-healing because the server's rebuild always scrolls *live*
  Qdrant. CTO also endorsed the module-qualified call decision as the codebase's established
  monkeypatch-seam convention, not a test-driven smell, and judged the internal review
  substantively diligent (cleanups verified in-tree).
- **Infra-lead** confirmed the operational picture is conservative — no new service/port/
  container, ~1–3 MB in-RAM index at current scale, O(1) `reembed_object`, atomic
  `state.json` writes — and concurred with CTO on the lock-race self-healing analysis. Raised
  the one operational gap: the dense-only degradation path is **silent** (one WARN line, no
  ntfy/health signal), so the feature could disable itself in production unnoticed.
- **CSO** confirmed CSO-1 (cross-space BM25 isolation) is enforced at candidate-generation by a
  real, engineered-to-win exclusion test that cannot silently drift, and CSO-2 (state.json
  trust channel) is bounded to a redundant rebuild / dense-only fallback (int-coerced, equality
  compare only, no code-exec/data-exposure/leakage). Legal concurred there is no
  breach-notification implication.
- **QA** independently re-ran the #327 + Tier-2 subset (151 passed, 10 skipped) and verified
  the live eval *errors* until curated (`FileNotFoundError`, not skip-pass) — a genuinely
  enforced gate, not a "pytest exits 0" formality. Confirmed QA-3 (filter-equality under
  populated filters), QA-4 (≥1 filter-gate AC through the *real* build path, defeating the
  zero-score shortcut), and the #336 OD-B retarget as a faithful adaptation with byte-identical
  assertions.
- **Legal** verified `rank-bm25` is Apache-2.0 (PyPI), MIT-compatible, numpy-only (no net-new
  package), LEGAL-1 recorded in §8, lockfile hashes intact, no new data flow / PII / regulatory
  surface.
- **CPO** and **Client Advocate** converged on the load-bearing risk: shipping changes the
  *default* retrieval path for every fleet agent and Jan, and the value claim is **unproven in
  any executable sense** until the live eval runs. Both stressed (a) the eval must prove
  **strict lift**, not a no-op tie, and (b) `repro-327`'s `expected_ids` must be derived
  independently from the 2026-06-25 reproduction, never reverse-engineered from BM25 wins. Both
  judged deferring *proof* to a human-reviewed PR gate acceptable **only because** graceful
  degradation guarantees no regression below today's dense-only behavior in the interim.

## Findings

### BLOCKING
The following are blocking **for merge**. None requires impl-phase rework — the phase output is
complete and correct. Each is satisfiable only by the repo owner (Jan) at the PR / Decide gate,
which is why the council routes this ticket to **decide** rather than recommending merge.

1. **[Client Advocate, CPO, QA, CSO, CTO, Infra — convergent] AC-EVAL live eval must be
   curated, run green on the live stack, and recorded on the PR before merge.** This is the
   feature's only executable evidence that hybrid actually improves recall over dense. The 757
   green tests prove the *machinery* (fusion, keying, gating, fallback, no `semantic_search_core`
   regression) — not that retrieval *helps*. Required at PR: strict per-case
   `dense_recall < hybrid_recall` on `repro-327`, ≥1 strict `hybrid > dense` lift case, and the
   per-query diagnostic table pasted into the PR. CI-unverifiable by design; routes to Jan.
2. **[Client Advocate] `repro-327` `expected_ids` must be derived independently** from the
   2026-06-25 reproduction comment and justified by manual inspection in Anytype — never
   reverse-engineered from what BM25 surfaces (which would be a self-fulfilling green proving
   nothing for the user who hit the bug). The curation runbook already mandates this; the PR
   reviewer must confirm it, not just that the test exits 0.

### ADVISORY
1. **[Infra ADV-1] Silent dense-only degradation has no alert.** Any BM25-path failure
   fails open to dense-only with a single WARN line and no ntfy/health signal — the feature can
   disable itself in production unnoticed. Recommend a lightweight log-grep watchdog (existing
   log-watch mechanism suffices) firing on repeated `bm25_fallback` outside the cold-start
   window. Post-deploy follow-up, not a deploy blocker.
2. **[CPO A1 / Client Advocate A2] `score` semantics change.** Hybrid path returns RRF scores
   (~0.01–0.05) instead of cosine (~0.7–0.9). Internally safe (`wiki_query` treats score as
   opaque), but recommend a CHANGELOG line warning external/OSS consumers that
   `semantic_search`'s `score` is now an opaque RRF rank-fusion score, not cosine.
3. **[CPO A2 / Client Advocate A1] Eventual-consistency / cold-start window.** Newly
   cron-indexed objects become BM25-visible only on the server's next hybrid query after the
   version bump; a cold restart serves dense-only until the first query builds the index
   (<100 ms warm-up). Accepted trade; worth a one-line user-doc/troubleshooting note.
4. **[QA ADV-2 / CPO A3 / Client Advocate A4] SF-B short results under aggressive filtering.**
   Documented/accepted (§6.7); no committed test distinguishes the acceptable case (gated
   BM25-only chunks dropped) from a real dense-drop regression. Consider a small guard test
   asserting all dense filter-passing chunks survive the gate. Not required for ship.
5. **[Client Advocate A3 / CPO A4] `wiki_lint` stays dense-only.** Deliberate scope boundary,
   but note the originating complaint was about contradiction-detection retrieval, which lint
   serves — a plausible future user surprise. Confirm intended; fast-follow if needed.
6. **[Infra ADV-2/3/4] Accepted scaling trades:** per-query `state.json` read on the hot path
   (grows with object count, not chunk count; §19 sidecar split is the future mitigation),
   cold-start build cost O(corpus) (fold an `ms` threshold into the ADV-1 watchdog), and the
   in-RAM index correctly needs no backup (confirm `state.json` is in the existing backup set —
   it predates this change). All accept-and-track.
7. **[CTO ADV-1] Empty-corpus rebuild retry** issues a Qdrant scroll per query until the corpus
   is non-empty (bootstrap-only, cheap, recall never wrong). Worth a one-line code comment so a
   future maintainer does not "optimize" it into stamping the version on an empty build.

## Decomposition

None. Both the CPO and the CTO explicitly considered and **recommended against** a split. The
ticket is one internally cohesive retrieval-fusion concern landing almost entirely in
`indexer.py` with two inseparable one-line call-site switches (the new path is dead until the
callers switch). The pieces are not independently shippable user value. The genuine independent
unit of work — native Qdrant sparse vectors — is already correctly carved out as v2 (OD-327-A).
The PR is large but reviewable (one concern, clean seam: `semantic_search_core` left
byte-identical as an invariant).

## Resolutions

No findings were withdrawn during discussion; the council converged rather than conflicting.
The members independently triangulated the same two-part conclusion — code complete/correct,
proof-of-value an owner-only pre-merge gate — and the CTO/Infra cross-checked each other's
lock-race self-healing analysis to the same conclusion. No dissent.

## Recommendation

**Recommended target:** decide
**Confidence:** high
**Rationale:** The implementation is complete, faithful to the approved spec, internally
reviewed (0 critical/major), independently CI-verified green (757 passed), and every spec-
addendum exit criterion is honored. There are **zero BLOCKING findings requiring impl rework**.
The remaining gates are structurally the repo owner's and cannot be discharged headless: (1) the
AC-EVAL live eval — the feature's sole proof-of-value — must be curated and run green against
the live 294-object production wiki and recorded on the PR; (2) `repro-327` IDs must be
independently verified; and (3) the open decisions **OD-327-A** (accept app-level BM25 for v1)
and **OD-327-B** (lazy-build + version-stamp design) await Jan's ratification under
training-wheels autonomy. The council therefore does **not** recommend `done`/merge; it routes
to **decide** so Jan can ratify OD-327-A/B, run and record the live eval, and then merge the
already-prepared PR ("Rebase and merge"). Graceful degradation guarantees no regression below
today's dense-only behavior in the interim, which is what makes deferring proof to the PR gate
safe.
**Dissent:** None.
