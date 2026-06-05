# Spec Addendum — post-spec council (R1)

**Source:** [`council-spec-r1.md`](council-spec-r1.md)
**Date:** 2026-06-05
**Target phase:** test (and impl — items 1–4 are impl-phase exit criteria; item 5 is a test-phase deliverable)
**Status:** Authoritative — the test and impl phases MUST honor these items as spec requirements,
in addition to everything in `spec.md`.

The post-spec council signed off unanimously with zero BLOCKING findings. These additional
acceptance / exit criteria capture the advisories that impose concrete next-phase obligations.
They do not change the spec's design — they harden it against the two risks multiple council
seats flagged independently: a silent-no-op platform assumption, and an operator-trust /
disclosure gap.

## Additional acceptance criteria

1. **[CTO-ADV-1] Validate the "no target GET" platform assumption against a REAL Anytype search
   response (impl-phase exit criterion).**
   The spec's §3.3 step 1, §3.4 step 1, and §4 ("NO target GET") depend on POST
   `/v1/spaces/{sid}/search` returning *hydrated* `properties[].objects` arrays for the
   objects-format relations `wiki_relations` and `wiki_contradictions`. Every existing
   objects-format reader in the codebase (`query.py` `_neighbor_ids_of`, `lint.py` backlinks)
   operates on a `get_object` result, NOT a `search` result; no code path today reads
   `prop.get("objects")` off a search response. Before relying on the no-target-GET design, impl
   MUST confirm — against a real Anytype search response, not a hand-authored fixture — that
   `_relation_ids(target, "wiki_relations")` yields the linked peer ids from the search-result
   `target` dict. **If the real search response does NOT carry populated objects-format arrays,
   impl MUST add a single target `get_object` (mirroring the peer-read pattern, +1 call) to hydrate
   the target before reading relations, and MUST correct §4's "NO target GET" claim accordingly.**
   This is the one design assumption that, if wrong, ships green-in-CI but dead-in-production
   (empty candidate set → detection silently never fires — the exact failure class R2 caught,
   relocated to a platform assumption). The AC-1 objects-shaped fixture (spec.md:498) does NOT
   validate this and must not be treated as evidence the assumption holds.

2. **[CSO-ADV-1 / CPO-A-1 / Legal-ADV-1 / Client-ADV-1] README + CHANGELOG MUST disclose the
   widened off-machine egress scope (gated docs deliverable, impl §8 step 11).**
   The existing README privacy notice (README.md:46-47) describes off-machine egress as "the source
   content you ingest" — the v0.3.0 single-source model. As of v0.6.0, enabling a remote
   `WIKI_EXTRACT_ENDPOINT` ALSO transmits the `wiki_facts` of already-linked PEER entities — i.e.,
   content distilled from *earlier* ingests — to the configured endpoint on every entity update
   with linked relations. The docs sweep MUST amend README.md:46 (and the §5 security note) to state
   this widened scope explicitly. This is a **gated** deliverable, not best-effort.

3. **[CPO-A-1 / Client-ADV-1] README + CHANGELOG MUST state the v0.6.0 detection scope limitations
   (gated docs deliverable, impl §8 step 11).**
   Because §3.7 removes the in-product "PASSIVE" caveat, the lint check now reads as fully active.
   But v0.6.0 detects contradictions ONLY between entities already linked via `wiki_relations`
   (DI-3 — unlinked-entity contradictions are not caught) and ONLY for `wiki_entity` (DI-1 — concepts
   deferred). The README lint/contradiction section and the CHANGELOG v0.6.0 entry MUST state both
   limitations in plain operator language (e.g., "v0.6.0 detects contradictions between linked
   entities only; contradictions between unlinked entities are not yet caught — planned via semantic
   pre-filter. Entity-only; concept scope deferred."). Goal: prevent operator over-trust of a green
   `contradiction_unresolved` result — the over-trust failure mode this release set out to fix.

4. **[CSO-ADV-1] Update the remote-extraction consent banner copy for the widened scope (impl).**
   The first-run remote-endpoint consent banner was written under the "source content" model. Update
   its copy to convey that enabling a remote endpoint transmits source AND previously-stored peer wiki
   content (e.g., "source and previously-stored wiki content"). A version-bumped consent ack key
   (forcing re-consent for pre-v0.6.0 remote users) is RECOMMENDED product hygiene but NOT legally
   required (operator-as-controller); impl may choose banner-copy-only and document the decision in
   the CHANGELOG. Either way, the CHANGELOG MUST note that the existing consent gate continues to
   govern all off-machine egress including the new peer-fact class.

5. **[CPO-A-1 / Client-ADV-1 / CTO-ADV-1] Test phase: add a docs-presence assertion and an
   honest-fixture note (test-phase deliverable).**
   - Add a CI test (or doc-lint assertion) that the operator-facing detection-scope limitation copy
     from item 3 (linked-peers-only / entity-only) is present in `README.md`. AC-3 already asserts the
     in-product "PASSIVE" caveat is *removed*; nothing currently asserts the *replacement* operator
     disclosure lands. Close that gap so the disclosure cannot silently regress.
   - In the AC-1 / contradiction seam tests, add a code comment noting that the hand-authored
     objects-shaped search fixture asserts the *parsing* contract only and does NOT validate that real
     Anytype search returns objects-format arrays (see item 1). This keeps the CI suite honest about
     what it does and does not prove.

## Rationale

**Items 1 and 5** address the council's strongest technical finding (CTO-ADV-1, operationally
seconded by Infrastructure): the no-target-GET optimization is elegant but rests on a platform
behavior never exercised by existing code. R2 caught a near-identical silent-no-op via the wrong-
helper bug; the residual risk is the same failure relocated to an untested search-response shape.
The fix is cheap and pre-identified (one `get_object` fallback), so this is an impl-phase
verification gate, not a redesign. Item 5 prevents the CI suite from masking the gap with a
self-fulfilling fixture.

**Items 2, 3, and 4** consolidate a finding that FOUR council seats raised independently (CSO,
CPO, Legal, Client Advocate) from security, product, legal, and stakeholder angles: activating the
lint check and broadening off-machine egress without shipping the corresponding operator disclosure
in the same release recreates the exact over-trust problem v0.6.0 exists to solve, and under-informs
operators about a widened data-egress class. Legal confirmed the existing consent gate is sufficient
control (operator-as-controller; transparency obligation, not a new gate), so the remedy is disclosure
copy treated as a gated deliverable rather than best-effort — which §8 step 11 currently leaves
implicit.
