# Council Impl Review R1 — CTO

**Ticket:** aldeia-box#325 — Contradiction Detection: Extend to Concepts
**Reviewer:** Chief Technology Officer (post-impl governance review)
**Date:** 2026-06-24
**Scope:** Engineering accuracy, codebase alignment, in-phase review diligence, split assessment.

---

## Verdict

**SIGN-OFF: YES.** Advance to `done` (PR open + merge).

Zero BLOCKING findings. The production diff matches the approved spec
(CS-1..CS-6, CS-9) verbatim, entity behaviour is preserved, the in-phase impl
review was genuinely codebase-grounded, and the spec-addendum merge-gate items
are satisfied. Findings below are ADVISORY only.

---

## What I verified (evidence)

- **Production diff is confined and accurate.** `git diff origin/main...HEAD --
  src/.../ingest.py src/.../remember.py` shows exactly the seven change sites
  plus the remember.py comment-only cross-reference. No schema/lint/bootstrap
  code touched. Diff is ~52 lines in ingest.py + a docstring on
  `_type_for_kind`.
- **CS-1 gate is in the update branch only.** Read `ingest.py:928-978`: the
  `if kind in ("entity", "concept")` detection block sits inside
  `if resolution["action"] == "update":`. The `else` create branch
  (968-978) calls only `create_object` — no detection call. LD3 holds; create
  path is untouched.
- **`kind` is a live local at the call site.** `ingest.py:909`
  `kind = cand.get("kind", "entity")` defines it before the call at 944-949;
  `facts` (910) already carries concept definition text. `kind=kind` wiring is
  correct, not guessed.
- **CS-9 entity preservation is byte-for-byte.** `ingest.py:953-956`: the
  warning is the bare `contradiction_detection_degraded` unless `kind !=
  "entity"`. Entity path emits the identical legacy string; only the concept
  path gains `:concept`. AC-2 regression assertions need no change. Confirmed.
- **CS-4 relation-key dispatch is real.** `_rel_key`/`_REL_KEY_BY_KIND`
  (`ingest.py:437,446`) maps `concept → wiki_related`, reused unchanged;
  candidate line (578) now keys on `_rel_key(kind)`.
- **Option A peer dispatch is type-driven, not kind-driven.**
  `_facts_key_for_peer` (`ingest.py` new helper) reads `peer_obj.get("type",
  {}).get("key", "")` and looks up `_TEXT_KEY_BY_TYPE_KEY` with a
  `wiki_facts` default. Peer text still read via `read_client.get_object`
  (586) — the #287 wire contract (search responses don't hydrate relation
  arrays) is honoured.
- **Single-source-of-truth duplication is documented, not silent.** Both
  `_TEXT_KEY_BY_TYPE_KEY` (ingest.py) and `_type_for_kind` (remember.py) carry
  symmetric "MUST stay in sync" cross-reference comments. Acceptable SF-5
  resolution.
- **Tests pass and exercise the real path.** Ran the concept contradiction
  subset: 10 passed, 0 failed. AC-C7 (`test_concept_peer_uses_wiki_definition`)
  and AC-C8 (`test_concept_mixed_kind_peer_uses_peer_facts_key`) exercise the
  real `detect_contradictions` with concept and entity peers respectively;
  AC-C10 (`test_concept_empty_definition_peer`) covers the empty-definition
  case; QA-ADV-1 clean-path negative present at line 2286.
- **README disclosure is correct.** `README.md:175` states detection fires for
  Entity **or** Concept, discloses the surfacing gap (concept contradictions
  recorded + browsable but **not yet flagged by `wiki_lint`** — a follow-up),
  and uses severity `critical`. Satisfies spec-addendum items CA/CPO-ADV-1 and
  CA/CPO-ADV-3.
- **Follow-up tracked.** `CHANGELOG.md:16` references the lint-surfacing
  follow-up as **#426**. (The local `gh` CLI is scoped to the client repo
  `anytype-llm-wiki` and cannot resolve aldeia-box org issues; I rely on the
  chair-verified fact that #426 is OPEN, corroborated by the CHANGELOG ref I
  read directly.)
- **Rebase noise is not #325.** Confirmed the pyproject/server.py/test_query/
  uv.lock churn lives outside the two production files I diffed against
  origin/main; consistent with the chair note that it arrived via rebase from
  merged PRs.

## In-phase review diligence — credible

The impl-review-r1 finding distribution (production clean; all FIX items in
test code + one docstring nit) is **credible, not shallow**. I independently
confirmed the production diff is a near-mechanical application of an
already-council-reviewed spec, so the absence of production findings is the
expected outcome of a tight spec, not a missed review. The review shows real
verification: it cites specific line numbers for the DRY MAJOR-1 inline-build
sites, distinguishes the deliberate two-helper split from a defect, and
correctly defers the file-wide JSON-parse boilerplate as pre-existing
convention. The DRY MAJOR-1 condition (route AC-C6/AC-C9 through the shared
fixture) was subsequently committed (`1a7dc30`). This is a review that checked
the code.

---

## BLOCKING findings

**None.**

---

## ADVISORY findings

### ADV-1 — Silent false-negative on a concept peer missing `type.key` (accepted risk)
**Verified:** `_facts_key_for_peer` falls back to `wiki_facts` when a peer's
`get_object` response omits `type.key`; a concept peer hitting that fallback
reads empty text and is silently not flagged. **Found:** this is documented in
the spec (SG-2) and deferred with the per-peer-skip observability follow-up.
**Impact:** low — `peer_obj.get("type",{}).get("key")` is reliably present on
`get_object` responses (verified pattern at the existing `anytype_client`
read path), so the fallback is a defense-in-depth default, not a live gap.
**Action:** none required for merge; ensure the deferred debug-logging
follow-up (SG-2) eventually covers the type-key fallback so a real occurrence
is observable.

### ADV-2 — Surfacing gap is a real (disclosed) coverage asymmetry
**Verified:** concept contradictions are written to `wiki_contradictions` but
`lint.py`'s `contradiction_unresolved` gate remains `wiki_entity`-only, so they
are recorded-but-not-surfaced until #426 ships. **Found:** correctly and
prominently disclosed in README and CHANGELOG; #426 filed as the merge gate.
**Impact:** acceptable as a deliberate scope decision; the risk is purely that
#426 slips and the asymmetry becomes load-bearing. **Action:** none for #325
merge; track #426 to avoid an indefinite "detected but invisible" state.

### ADV-3 — `_TEXT_KEY_BY_TYPE_KEY` cross-reference is comment-enforced only
**Verified:** the sync between `_TEXT_KEY_BY_TYPE_KEY` and
`_type_for_kind` is guaranteed by paired comments, not by code. **Impact:**
low — both encode a tiny 2-entry rule and any drift would be caught by the
real-function AC-C7/AC-C8 tests. **Action:** none; noted so a future editor
adding a third kind knows to touch both sites (and add a test).

---

## Split Recommendation

**None.** #325 is appropriately confined and should NOT be decomposed further.
The larger, genuinely separable concern (lint surfacing, which requires a new
idempotent bootstrap "ensure-properties-on-existing-types" capability + schema
property + lint gate + schema-version bump + migration note) has **already**
been split out as #426 — the correct module boundary. From the
engineering/module-boundary angle: the confined core touches a single function
cluster in one file (`detect_contradictions` + its call site), has a single
coherent test surface (`TestContradictionDetection` in test_ingest.py), and
fits comfortably in one reviewer's context. The surfacing follow-up touches a
different subsystem (bootstrap + lint + schema) with its own test surface
(test_lint.py) and its own open API-verification risk. The existing split is
exactly where the module boundary lies.

---

## Rationale

This is a textbook confined extension: a mature, #287-shipped detection path is
widened from entity-only to entity+concept by parameterizing the relation key
and peer-text key, with the entity path preserved byte-for-byte (default
`kind="entity"`, bare degraded warning unchanged). I spot-checked five
load-bearing claims — the update-branch-only gate, the live `kind`/`facts`
locals at the call site, the `_rel_key` concept mapping, the type-driven
Option A peer dispatch reading via `get_object`, and the README/CHANGELOG
surfacing disclosure with `critical` severity — and every one held against the
actual code. The Option A mixed-kind rule is sound: keying peer text on the
peer's own type-key (not the caller's kind) is the correct choice and is
exercised end-to-end by real-function tests AC-C7/AC-C8. The in-phase impl
review was diligent and codebase-grounded, not document-only, and its one
substantive condition was committed. The only residual risks (type-key
fallback silence, surfacing asymmetry) are pre-existing, disclosed, and tracked
(#426 + SG-2 follow-up). No technical inaccuracy, no unverified assumption, and
no safety concern reaches the threshold to block. Sign-off granted.
