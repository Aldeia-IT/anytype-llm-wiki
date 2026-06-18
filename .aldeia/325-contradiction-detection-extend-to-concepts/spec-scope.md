# Spec Scope: 325-contradiction-detection-extend-to-concepts

**Client:** anytype-llm-wiki (Aldeia-IT/anytype-llm-wiki)
**Ticket:** aldeia-box#325
**Epic:** aldeia-box#140 · split from this ticket; semantic-pre-filter half → #328

## Problem (one line)
Cross-object contradiction detection (#287, v0.6.0) only fires for **Entities**. Conflicting
definitions/claims between already-linked **Concepts** go undetected. Extend the *existing*
linked-contradiction mechanism to `wiki_concept` Objects — reuse the detect + cross-link path,
not a new approach.

## Domains touched
- agent-operations / infrastructure (wiki ingest pipeline)

## Estimated complexity: trivial–moderate
The cross-linking machinery is already kind-agnostic. The change is confined to making the
*candidate-gathering* and *detection gate* kind-aware. No new relation/property types, no new
LLM prompt, no schema migration.

## Exact change sites (verified against `src/anytype_llm_wiki/wiki/ingest.py`)
1. **Detection gate — `ingest.py:920`** `if kind == "entity":` gates the entire
   detect+write-links block (LD1, update branch only). Must also fire for `kind == "concept"`.
2. **Candidate relation key — `detect_contradictions`, `ingest.py:555`**
   `_relation_ids(target, "wiki_relations")` is hardcoded to the **entity** relation key.
   Concepts link via `wiki_related` (`_REL_KEY_BY_KIND = {"entity": "wiki_relations",
   "concept": "wiki_related"}`, `ingest.py:437`; resolved through `_rel_key()`, `ingest.py:440`).
   Detection must select the candidate relation key by kind — reuse `_rel_key(kind)`.
3. **Peer facts key — `detect_contradictions`, `ingest.py:570`**
   `_existing_text(peer_obj, "wiki_facts")` is hardcoded to the **entity** facts key.
   Concepts store their text in `wiki_definition` (see create/update branch, `ingest.py:888–895`).
   Peer text extraction must select the facts key by the *peer's* kind.
4. **`new_facts` argument** — at the call site `facts` already carries the concept's definition
   text (concept props use `wiki_definition`, `ingest.py:891`), so the new-claim side needs no
   key change; only the variable's semantics widen ("facts or definition").

## Reuse (must NOT change behaviour)
- `_write_contradiction_links` (`ingest.py:598`) reads/writes `wiki_contradictions` regardless of
  kind — already kind-agnostic. Reuse unchanged (both positions kept, never overwritten).
- A/B rollback pattern, dedup-as-no-op, `wiki_last_reviewed` never touched.
- Detection still: update-branch-only (LD3), MUST NOT block ingest (degraded warning on error).

## Open design question for research/spec to resolve
- **Mixed-kind peers.** A Concept's `wiki_related` set and an Entity's `wiki_relations` set could
  in principle reference objects of the other kind. Decide whether detection compares only
  same-kind peers or any linked peer, and read each peer's facts key by *that peer's* kind
  (requires knowing peer kind — likely from `peer_obj` type). Spec must state the rule explicitly.

## Key prior learnings to inject (Mem0)
- **`8f597af8` (high, #287 impl):** do NOT assume Anytype *search* responses hydrate
  objects-format relation arrays; `get_object` is the proven hydration path. The existing code
  already reads peers via `read_client.get_object` (`ingest.py:563`) — the concept extension must
  keep using that path, not a search-response read.

## Tests at risk / to mirror
- `tests/wiki/test_ingest.py` → `TestContradictionDetection` (from line ~1159). Entity path tests
  (AC-1 bidirectional write, AC-2 create-branch no-op, AC-12 self-ref, AC-14 dedup) must be
  mirrored for the Concept path (`wiki_related` candidates, `wiki_definition` facts). Existing
  Entity tests must stay green (regression guard).

## Docs at risk of staleness (must update when implemented)
- `README.md:175` — "Today detection is **entity-only** … (`wiki_concept` scope deferred)".
- `README.md:237` — roadmap line "Contradiction detection beyond linked entities … and across Concepts".
- `CHANGELOG.md` — new version entry.

## Non-goals (explicit)
- Contradiction detection between **unlinked** Objects via semantic pre-filter → #328.
