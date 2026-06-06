# Council Impl R1 — CTO Review (#287 v0.6.0 Automated Cross-Object Contradiction Detection)

**Seat:** Chief Technology Officer (deepest technical scrutiny + reviewer-diligence audit)
**Gate:** POST-IMPL final delivery gate
**Date:** 2026-06-06
**Diff audited:** `git diff 81b54d3..HEAD` (7 commits) + independent suite run

## Verdict

**SIGN-OFF (APPROVED to open PR).** Zero BLOCKING findings. The implementation is
technically sound, matches the codebase, conforms to Jan's wire-contract guidance,
and the in-phase review was genuinely diligent (verified against code, not document-only).
The single highest residual risk — the no-target-GET platform assumption (my own
CTO-ADV-1) — is correctly handled as a **documented PRE-TAG verification gate, not a
PR blocker.** My explicit engineering position on that call is in the Rationale.

## BLOCKING findings

**None.**

I attempted to break the central claim and could not. Every spot-check held:
- The no-target-GET design is implemented exactly as specced and the risk is honestly
  disclosed in code, tests, the impl debrief, and a stored memory — it is not a hidden
  or hand-waved assumption (see ADV-1).
- The #289/#287 signal boundary is technically correct (see "Verified" below).
- Wire contract matches Jan's guidance; no fabricated endpoints (the #285 C1 lesson).
- The suite I ran independently is green at the exact count claimed.

### What I verified (evidence)

1. **No-target-GET data path is real and load-bearing.**
   `resolve_entity` (ingest.py:192) returns `target = obj` straight from
   `client.search(...)`. `WikiClient.search` (wiki_client.py:113-115) returns
   `resp.json()["data"]` — the raw search objects, whatever shape the platform emits.
   `detect_contradictions` (ingest.py:411) and `_write_contradiction_links`
   (ingest.py:473) call `_relation_ids(target, "wiki_relations" / "wiki_contradictions")`,
   which reads `prop.get("objects")` (util.py:152) directly off that search-result dict.
   There is NO target `get_object` and NO fallback. Confirmed: if live POST `/search`
   does not hydrate objects-format arrays, `candidates` is `[]` → early return
   (ingest.py:412-413) → detection silently never fires. This is exactly the
   green-in-CI / dead-in-prod class. It is an ADVISORY (not BLOCKING) because it is
   environmental, honestly gated, and has a cheap pre-identified fix — see ADV-1.

2. **#289/#287 signal boundary — technically correct.**
   `grep wiki_status src/anytype_llm_wiki/wiki/ingest.py` → **zero matches.** #287 never
   writes `wiki_status` (that is #289's intra-entity signal). `wiki_last_reviewed`
   appears in ingest.py only once, in a docstring ("Never touches wiki_last_reviewed",
   ingest.py:469) — never assigned. `_write_contradiction_links` writes only
   `wiki_contradictions` bidirectionally (A-side ingest.py:486, B-side ingest.py:500-502).
   The boundary in spec §3.9 holds in code: #287 = cross-object `wiki_contradictions`
   link + `wiki_last_reviewed` left null; it does NOT write `wiki_status`.

3. **Wire contract matches Jan's authoritative guidance — no fabricated endpoints.**
   - `search` is **POST** `/v1/spaces/{sid}/search` (wiki_client.py:113). ✓ (the #289
     POST-landmine.)
   - `list_tags` is the property-scoped **two-step** GET `/properties/{property_id}/tags`
     (wiki_client.py:127-133), NOT `/options`. ✓
   - `AnytypeReadClient.get_object` is **GET** `/v1/spaces/{sid}/objects/{oid}?format=md`
     (anytype_client.py:47-52) and is used for PEER reads only (ingest.py:419, :497) —
     never the target. ✓ Matches WIRE LANDMINE 2.
   - Schema stays at v0.4.1 (no type/property change); logic keyed by `wiki_*` keys with
     display names unchanged. ✓ Consistent with Jan's "display names prefixed, keys
     unchanged." No invented endpoint anywhere in the diff.

4. **LD5 reader move is circular-import-safe and correct.**
   `util.py` now carries `_existing_text` (text-format, util.py:98), `_parse_relation_elements`
   (util.py:119), and the new `_relation_ids` (util.py:141). `query.py` re-exports
   `_parse_relation_elements`; no stale duplicate left in `remember.py`. The text-vs-objects
   reader distinction (the bug class R2 caught) is honored: `wiki_facts` uses `_existing_text`,
   `wiki_relations`/`wiki_contradictions` use `_relation_ids`.

5. **Hook + lifecycle + degraded-warning semantics correct.**
   `read_client` constructed once (ingest.py:636), closed in `finally` (ingest.py:791).
   Detection is entity-only + update-branch-only (ingest.py:726), wrapped in try/except
   that appends `contradiction_detection_degraded` (ingest.py:731-732). Three outcomes are
   distinguishable exactly as specced: degraded (warning present), no-contradiction (empty,
   no warning), written (counter incremented). Hallucinated-ID filter (SG-2) enforced
   against `candidate_set` (ingest.py:448). A/B rollback with `scrub_credentials` (SG-1)
   present (ingest.py:488-516).

6. **Suite reproduced independently.** `.venv/bin/python -m pytest -m "not live"` →
   **572 passed, 25 skipped, 8 deselected, 2 xfailed** — byte-matches the review and
   phase-summary claims. Contradiction+reingest subset: 11 passed, 2 skipped. The review's
   headline number is verified, not taken on trust.

### Reviewer-diligence audit — the in-phase review DID its job

`impl-review-r1.md` is NOT a document-only review. It cites specific file:line evidence
(reader move verified in util.py/query.py/remember.py; rollback-note sites; consent gate
in entry path), re-ran the suite, read the new functions, and — critically — did NOT claim
the platform assumption away. It carried CTO-ADV-1 forward as an explicit "Outstanding
pre-tag item (NOT a review finding — environmental)" rather than burying it. The review
does surface real mismatches/limits (the unused `client` param, the
`query._relation_objects_for_key` near-duplicate), so it is not the suspicious
"zero mismatches found" pattern. This passes my diligence bar.

## ADVISORY findings

### ADV-1 — No-target-GET platform assumption: PRE-TAG gate is the correct call (do NOT block PR)

- **What I verified:** ingest.py:411/473 read `prop.get("objects")` off the
  `client.search` result with no fallback `get_object`; util.py:152; the honest-fixture
  comment at test_ingest.py:1213-1221 ("PARSING CONTRACT ONLY … Do NOT treat this fixture
  passing as evidence the no-target-GET assumption holds").
- **What I found:** No existing codebase reader consumes objects-format `prop.get("objects")`
  off a *search* response — every prior reader operates on a `get_object` result. The CI
  fixture is hand-authored and proves only the parsing contract. If the live platform does
  not hydrate the arrays, detection silently no-ops (empty candidate set).
- **Impact:** Feature could ship green and be dead in production. This is the same
  silent-no-op failure class R2 already caught once, relocated to a platform behavior.
- **Recommended action:** Keep as a **gated pre-tag verification** in the release runbook
  (alongside AC-8/AC-9 live smoke): against a real Anytype POST `/search` response, confirm
  `_relation_ids(target, "wiki_relations")` yields the linked peer ids. If not, add a single
  target `get_object` (+1 call, mirrors the peer-read pattern) and correct §4's "NO target GET"
  claim. **Engineering judgment: this is correctly a pre-tag gate, not a PR blocker**, because
  (a) it is environmental — it cannot run headless, so blocking the PR cannot resolve it;
  (b) the fix is cheap and pre-identified; (c) it is honestly documented in the debrief, the
  fixture, the PR body, and a stored impl-worker memory — it is disclosed, not concealed.
  Blocking the PR would gain nothing verifiable and lose the merged CI-complete baseline.
  **The condition I do attach:** this gate MUST be a release-blocking line item in the runbook,
  not a "nice to have" — tag/release MUST NOT proceed until it is checked. Flagging to
  infra-lead as the owner of the pre-tag/live-smoke runbook.

### ADV-2 — `pyproject.toml` still at 0.5.0 while CHANGELOG declares [0.6.0]

- **What I verified:** `pyproject.toml:3` → `version = "0.5.0"`; `CHANGELOG.md:10` →
  `## [0.6.0] - 2026-06-06`. Git history (`git log -S 'version = "0.5.0"'`) shows prior
  releases bumped the package version in a dedicated `chore(release):` commit (v0.4.0 #21,
  v0.5.0 #23), separate from the feature PR.
- **What I found:** Leaving pyproject at 0.5.0 on the feature branch is **consistent with
  established project cadence** — the version bump is a downstream release step. Not a defect.
- **Impact:** Low. Only a problem if the tag step is skipped.
- **Recommended action:** No code change in this PR. Add "bump pyproject to 0.6.0" to the
  same pre-tag runbook as ADV-1 so it is not forgotten. Documentation-only.

### ADV-3 — Unused `client` param in `detect_contradictions` (informational, already dispositioned)

- **What I verified:** ingest.py:394 `client: WikiClient` is unused in the body; the review
  closed this inline by adding the reserved-handle docstring note (ingest.py:405-406).
- **What I found:** Spec §3.3 mandates the signature and the test call sites pin it; removal
  would break the contract. The docstring disposition is correct.
- **Impact:** None. Cosmetic.
- **Recommended action:** Accept as-is. Reconsider the signature only if DI-3 (Qdrant
  pre-filter) never materializes a write-plane need.

## Rationale

I treated the central technical question adversarially and could not break it. The
no-target-GET design is implemented exactly as specified, the data path is real (search
result → `_relation_ids` → `prop.get("objects")` with no fallback), and the risk that it
no-ops in production is genuine — but it is **environmental, honestly disclosed in four
places (debrief, fixture comment, PR body, stored memory), and carries a cheap pre-identified
fallback.** Blocking the PR cannot resolve an assumption that by definition requires live
Anytype to verify; it would only forfeit a complete, green, CI-verified baseline. The correct
engineering control is a **release-blocking pre-tag gate**, which is precisely what the phase
proposes. That is sound.

Everything else checked out under spot-checking: the #289/#287 signal boundary is correct in
code (`wiki_status` never written, `wiki_last_reviewed` never touched), the wire contract
matches Jan's authoritative guidance with no fabricated endpoints (the #285 C1 lesson held),
the LD5 reader move is circular-import-safe, the security invariants (SG-1/SG-2/SF-5/SF-6) are
present in code, the operator-disclosure deliverables landed with the verbatim fixture updated
in lockstep, and the suite reproduces at the claimed 572-pass count. The in-phase review
demonstrated real codebase verification and, decisively, did not paper over CTO-ADV-1 — it
escalated it. That is the diligence I require.

My only firm conditions are documentation, not code: ADV-1 and ADV-2 must be
**release-blocking line items in the pre-tag runbook** (owner: infra-lead), so the
green-in-CI baseline is not mistaken for green-in-prod.

---

**VERDICT: SIGN-OFF (APPROVED to open PR). BLOCKING: 0 · ADVISORY: 3.** The implementation
is technically sound, codebase-aligned, and wire-correct, and the in-phase review was
genuinely diligent; the no-target-GET platform assumption correctly **defers to a
release-blocking PRE-TAG gate rather than blocking the PR**, because it is environmental,
honestly disclosed, and has a cheap pre-identified fallback.
