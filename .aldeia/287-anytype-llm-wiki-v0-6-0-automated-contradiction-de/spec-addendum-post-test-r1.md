# Spec Addendum — post-test council (R1)

**Source:** [`council-test-r1.md`](council-test-r1.md)
**Date:** 2026-06-06
**Target phase:** impl
**Status:** Authoritative — the impl phase MUST honor these items as spec requirements, in
addition to everything in `spec.md` AND the prior `spec-addendum-post-spec-r1.md` (items 1–4 of
which remain binding impl obligations).

The post-test council signed off unanimously with zero BLOCKING findings and recommended advancing
to impl. These additional exit criteria capture the advisories that impose concrete impl-phase
obligations. They do not change the spec's design — they (a) reaffirm the post-spec addendum's
impl-phase gates so they are not lost in the handoff, and (b) add one genuinely new gate the test
phase surfaced: an existing verbatim-fixture test that will mask the widened-egress disclosure if
impl does not update it in lockstep.

## Additional acceptance / exit criteria for the impl phase

1. **[CSO-ADV-1 / Client-A1 — NEW] Update the verbatim privacy-notice fixture in lockstep, and gate
   the widened-egress disclosure.**
   `tests/wiki/test_bootstrap.py:575` (`test_readme_contains_verbatim_privacy_notice`) pins the README
   privacy notice to `tests/wiki/fixtures/readme_privacy_notice_verbatim.md`, which currently discloses
   only the v0.3.0 "source content you ingest" egress model. Because that test asserts substring
   presence, impl can satisfy it while silently leaving the incomplete v0.3.0 wording in place —
   dropping the peer-fact egress disclosure required by post-spec addendum items 2 and 4. Impl MUST:
   - Amend `README.md:46` (and the §5 security note) to disclose the widened egress scope: enabling a
     remote `WIKI_EXTRACT_ENDPOINT` now transmits the `wiki_facts` of already-linked PEER entities
     (content distilled from *earlier* ingests), not only the current source content.
   - Update `tests/wiki/fixtures/readme_privacy_notice_verbatim.md` in lockstep so the verbatim test
     and the README stay in sync at the NEW wording (not the stale v0.3.0 text).
   - SHOULD add a presence assertion (mirroring `tests/wiki/test_docs_disclosure.py::TestReadmeDetectionScopeDisclosure`)
     for a peer-fact / "previously-stored wiki content" phrase, so addendum items 2/4 cannot regress
     silently behind the green verbatim test.
   The test-phase `phase-summary-test.md` "Risks and Open Items" omitted items 2 and 4; this criterion
   reinstates them as gated deliverables.

2. **[CTO-ADV-1 / QA-A2 / CPO-ADV-1 / Client-A1 — reaffirmed from post-spec addendum item 1]
   Validate the "no target GET" platform assumption against a REAL Anytype search response.**
   This is the single highest residual risk in the ticket (green-in-CI, dead-in-prod). Before relying
   on the no-target-GET design (§3.3/§3.4/§4), impl MUST confirm — against a real Anytype POST
   `/v1/spaces/{sid}/search` response, NOT the hand-authored AC-1 fixture — that
   `_relation_ids(target, "wiki_relations")` yields the linked peer ids from the search-result target
   dict. **If the real search response does NOT carry populated objects-format arrays, impl MUST add a
   single target `get_object` (mirroring the peer-read pattern, +1 call) to hydrate the target before
   reading relations, and MUST correct §4's "NO target GET" claim accordingly.** The AC-1 objects-shaped
   fixture proves the parsing contract only (the addendum-5b honesty comment in
   `_make_objects_shaped_search_response` is present and confirms this); it must NOT be treated as
   evidence the assumption holds.

3. **[QA-A3 / CTO-ADV-1] Import the reused helpers into the `ingest` namespace and call them
   module-locally.**
   AC-11 and AC-12 monkeypatch/import `anytype_llm_wiki.wiki.ingest._call_ollama_prompt`, which
   `ingest.py` does not currently import. Impl MUST `from .extraction import _call_ollama_prompt` (and
   define/surface `detect_contradictions`, `_CONTRADICTION_PROMPT_PATH`, `_load_contradiction_prompt` in
   the `ingest` namespace) and call `_call_ollama_prompt` bare/module-locally, consistent with spec
   §3.3 step 4. If impl instead calls it qualified (`extraction._call_ollama_prompt(...)`), the SG-2
   hallucinated-id security test (AC-11) stays red against a functionally correct impl. Do not weaken
   the test to compensate — fix the import.

4. **[QA-A4] Unpack the `_create_source` tuple at BOTH call sites (spec §3.6 BL-6).**
   `_create_source` changes to return `tuple[str | None, bool]`. Impl MUST unpack at both call sites in
   `ingest.py` (`source_id, _ = _create_source(...)`; assign `source_id`, not the raw tuple, to
   `result["source_object_id"]`). Storing the tuple breaks the pre-existing green
   `tests/wiki/test_ingest.py::TestReingestIdempotency::test_reingest_same_source_creates_zero_and_reuses_source`.
   Run `grep -n "_create_source(" src/` and confirm both sites are unpacked.

5. **[CTO-ADV-2 / CSO-ADV-2 / CPO-ADV-3 / Client-A2 / QA-A1] Impl-reviewer verification points (not new
   code, but must be confirmed):**
   - The detection-scope disclosure copy (post-spec addendum item 3, gated by `test_docs_disclosure.py`)
     lands in the operator-facing contradiction/lint README section and reads legibly — not merely
     present as a document-wide substring.
   - The three negative/absence assertions (AC-2 not-called, AC-5 contrast warning-absent, AC-12
     compound `not called or all(...)` at `test_ingest.py:1769`) pass for the RIGHT reason post-impl —
     confirm a deliberate fault injection flips each red, so none is vacuously satisfied.

## Rationale

**Item 1** is the council's one new finding: the widened-egress disclosure (a convergence of four
spec-council seats) has no CI regression gate and is actively masked by the existing verbatim-fixture
test, which currently encodes only the v0.3.0 egress model. Without this criterion, impl could ship a
green suite that silently under-discloses a broadened off-machine data class — the exact transparency
gap the spec council flagged.

**Items 2–4** reaffirm the post-spec addendum's impl-phase gates (item 1 platform assumption; the
helper-namespace coupling implied by spec §3.3; the BL-6 tuple unpack) because the test phase locked
test seams that will fail against a correct-but-non-conforming impl, and because the test-phase risk
handoff did not re-enumerate all of them. **Item 5** records the two impl-reviewer verification points
(disclosure placement; negative-assertion non-vacuity) that are inherent limits of the test gates
rather than test defects.

None of these is a test-phase blocker; all are addressable within impl.
