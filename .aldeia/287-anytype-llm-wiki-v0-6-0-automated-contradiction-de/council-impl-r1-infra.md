# Council Review (impl R1) — Infrastructure Lead

**Ticket:** #287 — anytype-llm-wiki v0.6.0 Automated Cross-Object Contradiction Detection
**Phase:** POST-IMPL final delivery gate (GOVERNANCE sign-off)
**Reviewer:** Infrastructure Lead
**Date:** 2026-06-06
**Diff reviewed:** `git diff 81b54d3..HEAD` (worktree)

## Verdict

SIGN-OFF (advance to PR). No BLOCKING findings. Two ADVISORY items, both pre-mitigated and carried as documented pre-tag runbook gates rather than implementation gaps.

The operational posture is acceptable. This release adds compute (LLM + Anytype I/O) to the ingest path but introduces **no new long-lived service, no new daemon, no new port, no schema migration, and no new steady-state resource**. The entire footprint is per-ingest-event work on an existing, lock-serialized path. The non-blocking degraded design correctly protects ingest durability.

## BLOCKING findings

None.

## ADVISORY findings

### INFRA-ADV-1 — Pre-tag platform-verification gate (no-target-GET assumption) must reach the release runbook, not just the debrief

**Description.** The no-target-GET optimization (§3.3/§3.4/§4) assumes POST `/v1/spaces/{sid}/search` returns hydrated objects-format `properties[].objects` arrays. No existing code path reads `prop.get("objects")` off a *search* response (all existing readers operate on `get_object` results). If the assumption is wrong, `_relation_ids(target, "wiki_relations")` returns `[]`, the candidate set is empty, and detection silently never fires — green in CI, dead in production. I operationally seconded CTO-ADV-1 at the spec gate; this is the same gate at the delivery boundary. It cannot run headless (needs live Anytype).

**Operational impact.** This is a silent-feature-disablement risk, not a stability risk. It does NOT threaten ingest durability, the Mac Mini, or any other service — a wrong assumption degrades to "feature does nothing," not "ingest breaks." That is why it is ADVISORY rather than BLOCKING. The cost of being wrong is bounded and pre-identified: one additional `get_object` per entity update (+1 Anytype GET, negligible).

**Recommended action.** The release runbook MUST carry, as an explicit pre-tag checklist item: (1) confirm `_relation_ids(target, "wiki_relations")` yields linked peer ids from a real search-result `target` dict; (2) if not, apply the pre-identified single-`get_object` fallback and correct the §4 "NO target GET" claim. Do not tag v0.6.0 until this is checked off. The phase summary (Risks item 1) and impl-review (Outstanding pre-tag item) both record it; the action here is to ensure it lands in the actual tag/release runbook so it is not lost at the handoff to release.

### INFRA-ADV-2 — Added per-update LLM + I/O cost is acceptable but unmonitored at the SLO level; capture AC-9 wall-clock at tag

**Description.** Each entity update on a candidate with linked relations now incurs: 1 additional Ollama generate call (contradiction prompt, all peers batched into a single call — not one-per-peer), plus per-peer Anytype I/O of 1 GET + up to 2 PATCH (A-side + B-side). The contradiction Ollama call reuses `extraction._call_ollama_prompt`, which uses `WIKI_EXTRACT_TIMEOUT` — **default 600s read timeout** (`config.py:29 DEFAULT_WIKI_EXTRACT_TIMEOUT = 600.0`).

**Operational impact (resource profile on the Mac Mini M4 32GB):**
- **Memory:** negligible. One additional object dict in scope per peer during detection; the `AnytypeReadClient` is lazy (httpx.Client constructed only on first `get_object`) and closed in `finally`. No new steady-state memory. Does not move the 32GB needle.
- **CPU / Ollama contention:** the contradiction call competes with embeddings and extraction for the single local Ollama instance, but it is gated three ways — entity-only (LD1), update-branch-only (LD3), and only when the entity has linked peers. Critically, ingest is serialized per space by an existing `fcntl.flock` LOCK_EX advisory lock (`util.py:space_ingest_lock`), so contradiction LLM calls cannot stack within a space. Aldeia-IT's wiki is effectively single-space, so the realistic added load is at most a small number of sequential Ollama calls per ingest event, not a concurrent fan-out. Acceptable.
- **Worst-case latency:** the 600s extraction timeout applies to the contradiction call. A wedged/slow Ollama could stall an entity update for up to 10 minutes before the degraded path fires. Because ingest is not on a user-interactive request path and is lock-serialized, this is a tail-latency concern, not a cascade or stability risk — but the SLO budget (§E1 `<2 min p95`) is aspirational and not CI-measurable.
- **API cost:** Ollama is local — zero external-dollar cost. If a remote `WIKI_EXTRACT_ENDPOINT` is configured, the per-update contradiction call adds remote LLM cost AND ships peer `wiki_facts` off-machine (security disclosure handled by CSO/Legal; consent gate unchanged). No new external cost for the default local config.
- **Disk:** none. No new log files, no new data store, no new on-disk state. `wiki_contradictions` writes to existing Anytype objects (covered by whatever backs up the Anytype space today; no new backup target).

**Recommended action.** Capture the AC-9 live SLO wall-clock observation in the tag runbook output (it is skip-gated and cannot run headless) so the actual added latency is recorded against the `<2 min` budget at least once before tag. No watchdog or alerting change is required: there is no new service or endpoint to health-check, and the existing `contradiction_detection_degraded` warning surfaced in `result["warnings"]` plus the `contradictions_detected` counter give operators the observability they need into the detection layer's health. Log rotation: unchanged (no new log file). ntfy: no new failure mode warrants a dedicated alert.

## Rationale

**Ingest durability is correctly protected.** The hook wraps `detect_contradictions` in a bare-`except Exception` that appends `contradiction_detection_degraded` and continues (`ingest.py` hook, §3.5a) — an LLM or Anytype I/O failure (including the 600s timeout) cannot fail the ingest. The three outcomes are distinguishable (degraded warning present / empty no-warning / written), which is the right operator signal. The bidirectional write uses A/B rollback with status downgraded to `partial` only on a B-side failure, and the fact write is deliberately NOT rolled back (the fact already succeeded) — correct partial-failure semantics. The `read_client` lifecycle is sound: constructed once at the top of `_run_ingest`, all early-return paths now live inside the `try`, and `finally: read_client.close()` always runs and is safe even when the lazy client was never opened. No file-descriptor or connection leak.

**No deployment-mechanics risk.** Schema stays at 0.4.1 — no migration, no `doctor` change, no new config variable, no launchd plist change, no Docker/Colima change (Ollama and Anytype are existing services; the 2GB Colima limit is untouched since contradiction detection adds no container). Service restart to deploy is a normal `uv tool install .` re-link; safe to perform while other services run because ingest holds a per-space lock and the change is additive to an existing code path. Rollback is a plain redeploy of the prior tag — there is no irreversible data migration, and already-written `wiki_contradictions` links remain valid and idempotent under re-ingest (dedup no-op).

**No cascade surface.** A failure in the contradiction path degrades to a warning and (at worst) a `partial` status on one entity update; it does not propagate to other candidates in the same ingest, to other ingests, to the indexer/Qdrant reindex (which runs after, unchanged), or to any co-resident service on the Mac Mini. The added load is bounded by the existing ingest lock and the three-way detection gating.

**The two genuine pre-tag gates are environmental, not implementation gaps**, and are honestly documented in the impl debrief and impl-review. My sole governance condition is that both reach the **release runbook** as blocking pre-tag checklist items (INFRA-ADV-1: platform-assumption verification + fallback; INFRA-ADV-2: AC-9 SLO wall-clock capture, alongside the AC-8 live smoke). On that condition, the operational posture is acceptable to advance to PR.

**Deployment note acknowledged.** The force-push-blocked recovery (soft-reset + plain push, final rebase delegated to GitHub "Rebase and merge") is a clean, reversible Git-hygiene path with no operational consequence for the running system; branch is pushed and current.

---

Relevant files (absolute):
- `/Users/Shared/development/anytype-llm-wiki-worktrees/287-anytype-llm-wiki-v0-6-0-automated-contradiction-de/src/anytype_llm_wiki/wiki/ingest.py` (hook, `detect_contradictions`, `_write_contradiction_links`, `read_client` try/finally)
- `/Users/Shared/development/anytype-llm-wiki-worktrees/287-anytype-llm-wiki-v0-6-0-automated-contradiction-de/src/anytype_llm_wiki/wiki/extraction.py` (`_call_ollama_prompt` — 600s `WIKI_EXTRACT_TIMEOUT`)
- `/Users/Shared/development/anytype-llm-wiki-worktrees/287-anytype-llm-wiki-v0-6-0-automated-contradiction-de/src/anytype_llm_wiki/wiki/config.py:29,194` (`DEFAULT_WIKI_EXTRACT_TIMEOUT = 600.0`)
- `/Users/Shared/development/anytype-llm-wiki-worktrees/287-anytype-llm-wiki-v0-6-0-automated-contradiction-de/src/anytype_llm_wiki/wiki/util.py:213` (`space_ingest_lock` — per-space flock serialization)
- `/Users/Shared/development/anytype-llm-wiki-worktrees/287-anytype-llm-wiki-v0-6-0-automated-contradiction-de/src/anytype_llm_wiki/anytype_client.py:13` (`AnytypeReadClient`, lazy `_client()` + safe `close()`)
- `/Users/Shared/development/anytype-llm-wiki-worktrees/287-anytype-llm-wiki-v0-6-0-automated-contradiction-de/CHANGELOG.md` (v0.6.0 — egress + scope disclosure landed)
