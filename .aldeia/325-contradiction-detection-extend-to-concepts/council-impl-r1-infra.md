# Council Impl Review (Round 1) — Infrastructure Lead

**Date:** 2026-06-24
**Ticket:** aldeia-box#325 — Contradiction Detection: Extend to Concepts
**Phase reviewed:** post-impl (operational readiness)
**Client:** anytype-llm-wiki (local; 32 GB Mac Mini M4; ingest hits local Ollama + Anytype)
**Reviewer:** Infrastructure Lead

---

## Verdict

**SIGN-OFF — advance to `done`.** Zero BLOCKING findings. The implementation introduces no
new deployment, resource, or operational risk relative to the existing entity contradiction
path. The "no schema / no bootstrap / no migration" claim is verified against the diff. Five
ADVISORY items carry forward, all pre-existing or follow-up-tracked, none gating release.

---

## What I verified (diff, not spec)

`git diff origin/main...HEAD --stat` — production source changes are confined to:
- `src/anytype_llm_wiki/wiki/ingest.py` (+52/-) — the seven confined change sites (CS-1..CS-6, CS-9).
- `src/anytype_llm_wiki/wiki/remember.py` (8 lines) — **docstring-only** cross-reference comment on `_type_for_kind`; no executable change (confirmed by reading the diff: only the docstring body grew).

Non-source: `README.md` (4 lines), `CHANGELOG.md` (9 lines), `tests/wiki/*`, and `.aldeia/*`
council/spec artifacts.

`git diff origin/main...HEAD --name-only` filtered for `types_schema|bootstrap|migration|
schema_version|.plist|docker|colima|Caddyfile` returns **NONE**. The "no schema change, no
schema-version bump, no bootstrap re-run, no migration" claim is **upheld by direct inspection**.

The non-blocking guarantee is intact: the gate still sits inside the `update` branch wrapped by
`except Exception:  # noqa: BLE001 — detection MUST NOT block ingest`. CS-9 only *appends* a
`:{kind}` suffix to the warning string on the non-entity path; control flow and the entity
warning string are byte-for-byte unchanged. `peers = []` on exception so the downstream link
loop is a no-op — degraded detection cannot corrupt the ingest result.

`git revert` rollback claim is structurally true: there is no provisioned state (no type,
property, plist, container, or data) to unwind — reverting the commit restores the prior gate
and signature with no side effects.

---

## BLOCKING

None.

---

## ADVISORY

### ADV-1 (carry-forward from spec ADV-1) — SG-1 fan-out latency worst case is denser for concepts
**Description.** Per-concept-update cost is O(linked-peers) sequential `get_object` calls + one
LLM call against local Ollama — the *same shape* as the entity path, governed by the same
`wiki_related`/`wiki_relations` cardinality. The diff does not enlarge the fan-out *count*. The
residual concern is unchanged from spec phase: concepts are plausibly denser hub nodes, so the
worst-case *latency* (sequential GETs + a larger LLM prompt carrying `wiki_definition` text) can
be materially higher than the average entity even though the algorithm is identical.
**Operational impact.** A pathological hub concept could make a single ingest update noticeably
slow and drive a larger one-shot Ollama prompt. On the Mac Mini this is a transient CPU/memory
spike during one ingest, not a steady-state profile change. It runs behind the non-blocking
handler, executes sequentially (no fan-out concurrency to exhaust memory), and does not cascade
to PostgreSQL, Caddy, ntfy, or other workers.
**Recommended action.** No action for #325. The SG-1 cap (top-N peers / per-peer text truncation
in the shared `detect_contradictions` loop) belongs in follow-up #426 and should be sized against
the densest *real* concept in the live space, not an average entity. Not a release blocker.

### ADV-2 (carry-forward from spec ADV-2) — follow-up #426 bootstrap capability depends on an UNVERIFIED Anytype property-link API
**Description.** The CHANGELOG correctly names #426 as the surfacing follow-up. That follow-up
requires a *new* idempotent "link declared property onto an existing type" bootstrap capability;
no such code path exists in the repo today (chair/CTO confirmed at spec phase).
**Operational impact.** None on #325 — correctly quarantined out of this core. Becomes a genuine
deployment/migration concern for #426: if the Anytype `update-type` / property-link endpoint does
not exist or is not idempotent, surfacing needs a different mechanism *before* any
`WIKI_SCHEMA_VERSION` bump fires the `wiki_schema_outdated` re-bootstrap prompt against the live
space.
**Recommended action.** #426's first task must verify the endpoint exists and is idempotent
before stamping a schema version. Out of scope for #325 sign-off.

### ADV-3 — Per-peer silent failure surfaces remain unmonitored (pre-existing, fail-safe)
**Description.** Two finer-grained failure surfaces stay silent today and are not changed by
#325: a per-peer `get_object` skip emits no warning, and the `_facts_key_for_peer` fallback
(`type.key` absent → `wiki_facts`) can read empty text for a concept peer (silent
false-negative). Both pre-date #325 on the entity path.
**Operational impact.** Failure mode is a *missed* contradiction (recoverable on the next ingest
of the same object), never a crash, blocked ingest, or data corruption. It fails safe. No
watchdog or ntfy alert is warranted for a recoverable false-negative.
**Recommended action.** Fold a debug-level log on per-peer skip and on type-key fallback into the
#426 shared-loop work. No #325 action.

### ADV-4 — Operator-facing surfacing gap during the #426 window
**Description.** Concept contradictions are detected and recorded in `wiki_contradictions` but
NOT flagged by `wiki_lint` until #426 ships. The fleet + Jan consume contradictions through
`wiki_lint`, so concept contradictions are in a "recorded but not surfaced" state in the interim.
**Operational impact.** No infra/stability impact — this is a product-visibility gap, not an
operational one. The mandated README/CHANGELOG edits disclose it honestly (verified in the diff:
README now states concept contradictions are "detected and cross-linked yet not yet flagged by
`wiki_lint` — a planned follow-up"; CHANGELOG names #426). No false-coverage claim is shipped.
**Recommended action.** Ensure #426 stays linked and tracked so the gap is not forgotten in this
single-developer shop. No #325 action; honest disclosure is in place.

### ADV-5 — No new monitoring needed; CS-9 discriminator is the adequate in-scope win
**Description.** #325 adds no new service, daemon, port, container, plist, log file, or scheduled
job. It runs inside the existing ingest process. Therefore no new watchdog check, log-rotation
config, or ntfy alert is required — consistent with "anything that runs as a service needs
monitoring; a code-path extension inside an existing process does not."
**Operational impact.** The kind-discriminated degraded warning
(`contradiction_detection_degraded:concept`) is the correct and sufficient observability
increment: it lets an operator distinguish concept-path degradation from entity-path degradation
in `result["warnings"]` now that the degrade surface roughly doubles. Bare string ⇒ entity,
`:concept` ⇒ concept — fully diagnosable.
**Recommended action.** None. Adequate for ops to detect concept-path degradation.

---

## Rationale (answers to the four key questions)

1. **New deployment/resource/operational risk vs. entity path?** No. Production source change is
   confined to `ingest.py` (plus a docstring-only `remember.py` comment). Steady-state resource
   profile is unchanged; per-update cost is identical in shape to the entity path. The
   "no schema/bootstrap/migration" claim is verified against `--name-only` (no
   types_schema/bootstrap/migration/plist/docker/Caddy files touched). Rollback is a clean
   `git revert` with no state to unwind.

2. **Infra-ADV-1 (denser concept hubs → worse SG-1 worst case) — blocker for the core?** No —
   advisory only. The fan-out *count* is unchanged and inherited from existing
   `wiki_related`/`wiki_relations` cardinality; the worst case runs sequentially behind a
   non-blocking handler with no cascade. Latency sizing against the densest real concept is
   correctly deferred to #426.

3. **CS-9 kind-discriminated degraded warning — adequate for ops?** Yes. It is the one cheap,
   in-scope observability win, it distinguishes concept-path from entity-path degradation, and it
   preserves the entity string exactly so no existing alerting/assertion breaks. Deeper per-peer
   observability (ADV-3) is a fail-safe, pre-existing deferral to #426 — appropriate.

4. **Any operational reason NOT to advance to `done`?** None. No new service to monitor, no
   migration to run, no restart sequencing, no backup-script change (no new data store — concept
   contradictions land in existing `wiki_contradictions` relations already covered by whatever
   backs up the Anytype space), no startup-order or health-check dependency introduced. Failure
   is non-blocking and fails safe.

---

## Sign-off

**SIGN-OFF.** No operational blocker. The change is code-only inside an existing process, adds no
service/daemon/container/plist/port/log/cron, requires no migration or restart sequencing, and
rolls back via `git revert`. Failure mode is non-blocking and fails safe with adequate
(CS-9) observability. The five advisories are pre-existing or #426-tracked and do not gate
release. **I approve advancing aldeia-box#325 to `done`.**
