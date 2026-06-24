---
status: RESEARCH
ticket: 426
title: Surface concept contradictions in wiki_lint
parent: 325
---

# Surface concept contradictions in wiki_lint (#426)

> **Phase status: RESEARCH complete.** This is a status stub. The decision-ready
> research deliverable is [`research.md`](./research.md); the scope brief is
> [`spec-scope.md`](./spec-scope.md). The spec body is authored in the Spec phase.

## Gating question — RESOLVED

Does an Anytype property-link endpoint exist and behave idempotently?
**YES.** `API-update-type` (`PATCH /v1/spaces/{space_id}/types/{type_id}`) links a
property onto an already-existing type, verified live. Critical caveat: it **replaces**
the user-defined property set, so the new bootstrap capability must be **read-modify-write**
(send the union of live user properties + declared-but-missing ones). Full probe transcript
and contract in `research.md` §1. **The ticket is NOT blocked.**

## Scope (verified against post-#325 main)

Four coordinated change sites (detailed in `research.md` §2 and `spec-scope.md`):
1. **Schema** (`types_schema.py`): add `wiki_last_reviewed` (date) to `wiki_concept`; bump `WIKI_SCHEMA_VERSION` (0.4.1 → next).
2. **New bootstrap capability** (`bootstrap.py` + `wiki_client.py`): idempotent read-modify-write `update_type` to reconcile declared-but-missing properties onto existing types.
3. **Lint gate** (`lint.py:490`): `tk == "wiki_entity"` → `tk in ("wiki_entity", "wiki_concept")`; fix the stale "(SF9)" comment at `:487`.
4. **Docs**: README surfacing-gap clause, CHANGELOG, MIGRATIONS.md re-bootstrap note.
