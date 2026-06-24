# Council Spec Review R1 — Infrastructure Lead — #325 Contradiction Detection: Extend to Concepts

**Date:** 2026-06-18
**Reviewer:** Infrastructure Lead (operational readiness, resource impact, deployment risk)
**Scope:** spec-phase governance review of the confined detection core (CS-1..CS-6, CS-9). Lint surfacing is explicitly OUT of scope (moved to follow-up).
**Spec:** `.aldeia/325-contradiction-detection-extend-to-concepts/spec.md`

## Verdict: SIGN OFF (low operational risk)

The confined core is code-only in `ingest.py`, introduces no schema/type/property/bootstrap/migration change, and inherits the exact resource shape of the already-shipped #287 entity detection path. Rollback is a trivial `git revert`. I verified the central claims directly against source rather than relying on the spec narrative. No BLOCKING findings. Two ADVISORY items, both already correctly deferred with sound rationale by the spec author — I am endorsing the deferrals, not contesting them.

---

## Verification performed (not taken on faith)

- **Core touches no schema/bootstrap/lint.** `git diff --name-only main...HEAD` shows the only source files changed on this branch are `ingest.py`, plus pre-existing unrelated `server.py`/`test_query.py` edits. No `bootstrap.py`, `types_schema.py`, or `lint.py` in the diff. The "no deployment, no migration" claim is structurally true, not just asserted.
- **Detection gate confirmed** at `ingest.py:920` (`if kind == "entity":`), signature at `ingest.py:533`, degraded warning at `ingest.py:926` — matches the CS-1/CS-3/CS-9 anchors.
- **`_REL_KEY_BY_KIND` / `_rel_key` already map `concept → wiki_related`** (`ingest.py:437,441`) — the candidate-key change (CS-4) reuses existing infrastructure; no new relation provisioning.

Conclusion: question (1) answered — the "no deployment, no migration, trivial rollback" claim is **accurate for the confined core**, and it does hinge correctly on lint surfacing being out of scope. The spec's gate keeping that boundary clean is the "What Must NOT Change" table (`spec.md:191-203`) locking `lint.py` and `types_schema.py`.

---

## BLOCKING

None.

---

## ADVISORY

### ADV-1 — Unbounded peer fan-out: concept density may make this materially worse than the entity baseline (SG-1). [deferral endorsed, with a sharper risk note]
**Description.** Each gated concept update adds O(linked-peers) sequential `get_object` calls plus one local-Ollama LLM call per peer-batch prompt (`spec.md:212-214`, Resource Impact). The spec defers a top-N cap on the grounds that the fan-out *count* is governed by the same `wiki_related`/`wiki_relations` cardinality an entity already has, and that capping is a cross-cutting change to the shared loop that would alter entity behaviour — out of confined scope.

**Assessment of the deferral.** The deferral is operationally sound for *this ticket's scope boundary*: capping the shared loop genuinely would change entity behaviour and belongs in a cross-cutting follow-up. However, the spec's premise that the risk is "not enlarged in count by #325" deserves a sharper operational caveat. Concepts in a knowledge graph are frequently **hub nodes** — a concept like "authentication" or "deployment" can accumulate far more `wiki_related` links than a typical entity accumulates `wiki_relations`. So while #325 does not change the *per-object* algorithm, it extends that algorithm to a class of objects whose link cardinality distribution is plausibly heavier-tailed. The realistic worst case is a hub concept update triggering dozens of sequential `get_object` round-trips to the Anytype CLI (port 31012) followed by a large local LLM prompt to Ollama.

**Operational impact.** On the 32GB Mac Mini this is latency, not a stability threat: the calls are sequential (no thundering-herd memory spike), Ollama is already resident, and the existing non-blocking exception handler (`ingest.py:925`) means a slow or failed detection degrades rather than blocks ingest. Worst realistic outcome is a single ingest call taking seconds-to-tens-of-seconds and one concept's detection timing out into a `contradiction_detection_degraded:concept` warning. No cascade to PostgreSQL, Qdrant, Caddy, ntfy, or other services. No steady-state memory increase — the resource profile change is transient per-update, not a new resident footprint.

**Recommended action.** Endorse the deferral. Strengthen the follow-up ticket's framing so it does not under-scope: it should note that concept hubs may exhibit higher peer cardinality than the entity baseline assumed, and that the cap/truncation work should be sized against the densest concept in the real aldeia-box graph (a quick max-`wiki_related`-count query against the live space would right-size it). This is a follow-up note, not a #325 blocker.

### ADV-2 — Silent per-peer skip and type-key fallback remain unobservable (SG-2 / SF-6). [deferral endorsed]
**Description.** Two finer failure surfaces stay silent (`spec.md:228-233`): (a) a peer whose `get_object` fails is skipped with no log (`ingest.py:564-566`); (b) a peer whose `get_object` response omits `type.key` falls back to `wiki_facts` via `_facts_key_for_peer` and may read empty text — a silent false-negative for a concept peer. CS-9's kind-discriminated top-level warning (`contradiction_detection_degraded:concept`) is the one in-scope visibility win and is correctly included.

**Assessment.** Acceptable to defer. Both surfaces are pre-existing and equally silent on the already-shipped entity path; #325 does not introduce them, it inherits them. Adding per-peer debug logging means editing the shared loop — a broader observability change than this confined extension warrants, and one that would touch the entity path too. CS-9 is the right minimum: an operator monitoring `result["warnings"]` can now distinguish entity-path from concept-path degradation, which is the one new diagnostic dimension #325 actually adds.

**Operational impact of leaving it.** Low. The failure mode is a missed contradiction (false negative), not a crash, not data corruption, not a cascade. The contradiction graph is browsable in Anytype, so a missed link is recoverable on re-ingest. No alerting gap that risks system stability — only detection completeness.

**Recommended action.** Endorse the deferral as documented in the Deferred Items table (`spec.md:418`). When the SG-1 follow-up touches the shared loop, fold in debug-level logs on per-peer skip and on type-key fallback at the same time (one PR, one review of the shared loop) rather than as a separate change.

---

## Items assessed and cleared

- **(2) Concept fan-out deferral** — sound; sharpened in ADV-1. Not blocking.
- **(3) Observability deferral** — acceptable; ADV-2. Not blocking.
- **(4) Mac Mini resource profile** — **no realistic load concern for the core.** No new resident service, no new daemon, no launchd plist, no Docker/Colima container, no new port, no new dependency that runs continuously. The only added load is transient per-concept-update API + LLM calls against already-running local services (Anytype CLI, Ollama), identical in shape to the entity path running in production since v0.6.0. No watchdog check, no log-rotation config, no ntfy alert, no backup-script change required — nothing new runs as a service, and `wiki_contradictions` links are stored in Anytype (already backed up as part of the existing space). Steady-state memory/CPU/disk profile is unchanged.
- **(5) Follow-up's unverified Anytype property-link endpoint** — correctly fenced OUT of the core. The new bootstrap capability ("ensure declared properties on existing types") depends on an Anytype `API-update-type`/property-link endpoint that **no current repo code path exercises and that the spec explicitly flags as unverified** (`spec.md:384,409`; phase-summary `risks` section). **Operational flag for whoever picks up the follow-up, recorded here so it is not lost:** if that endpoint does not exist or is not idempotent, the entire surfacing follow-up's deployment story changes — provisioning `wiki_concept.wiki_last_reviewed` onto the already-bootstrapped live aldeia-box space would require a new mechanism (or a destructive type recreate, which would be a genuine BLOCKING-class migration). The follow-up's *first* research task must be to confirm this endpoint against the running Anytype CLI before any schema-version bump or MIGRATIONS.md entry is written. This does not affect #325 core sign-off — the core deliberately provisions nothing.

---

## Bottom line

**SIGN OFF on the confined #325 core (CS-1..CS-6, CS-9).** It is code-only in `ingest.py`, adds no service, no schema, no migration, and no new resident resource footprint on the Mac Mini; rollback is a clean `git revert`; failure is non-blocking and non-cascading. Verified directly: the branch diff touches no bootstrap/schema/lint files. The two ADVISORY items (peer fan-out, deeper observability) are pre-existing, correctly deferred, and do not threaten system stability — they affect detection completeness and latency, not durability or other services. The follow-up's dependency on an unverified Anytype property-link endpoint is a real operational risk **for the follow-up** and is correctly kept out of the core; flagged here so the follow-up team verifies the endpoint before committing to a schema/migration plan.

No deployment, monitoring, backup, or dependency-ordering changes are required for the core. Cleared for Implement from an infrastructure standpoint.
