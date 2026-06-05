# Council Spec Review R1 — Infrastructure Lead (#286 wiki_lint v0.5.0)

**Date:** 2026-06-05
**Reviewer:** Infrastructure Lead (operational readiness, resource impact, deployment risk)
**Phase:** spec (pre-implementation)
**Box:** Mac Mini M4 32GB shared infra; this module also runs against Jan's constrained box (Anytype:31012, Qdrant Docker:6333, Ollama/bge-m3:11434)

---

## Verdict: SIGN OFF WITH ONE ADVISORY (no BLOCKING)

The two R1 BLOCKINGs (B1 band-correctness, B2 sweep cap) are genuinely resolved at the spec level. The deployment surface is low-risk: no schema bump, no migration, no new service, no new launchd/Docker/Colima footprint, no new credential surface. The steady-state resource profile is unchanged (lint is invoked on demand, not a resident service).

I am **not** blocking, but I am raising one **ADVISORY** that R2 did not fully cost: the **default `severity_threshold="all"` run will blow the 60s budget on any wiki of a few hundred objects**, because the sweep cost is real and the default invocation triggers it. The budget is honest about the *non-sweep* battery; it is *silent* on the wall-clock of the default path that an operator actually runs. This is a latent perf trap, not a stability or data-integrity risk — hence advisory, not blocking. It must be acknowledged in the spec (a documented warning + a tightened default-path budget statement) before or during implementation.

---

## BLOCKING

None.

---

## ADVISORY

### A1 — The DEFAULT `severity_threshold="all"` run is a perf trap: ~51s battery + ~110s+ sweep ≈ 160s+ at N=500, but the budget only proves the 51s non-sweep half

**Description.** The fix for B2 gates the duplicate sweep to `severity_threshold="all"` only. But `"all"` is the **default** argument (`wiki_lint(space_id, severity_threshold="all")`, master signature, restated spec line 176 / signature note). So the out-of-the-box invocation — the one an operator types first, the one the live smoke test calls (`wiki_lint(space_id=space_id)`, spec line 320) — runs the full sweep. The Performance Budget table (spec lines 178–188) derives only the non-sweep battery (~51s) and labels the sweep "the dominant, variable cost — see below," but never gives its wall-clock number. R2 endorsed the ~51s figure (corroborated by master line 602) and treated the sweep as "gated, therefore handled." Gating to `all` does not bound the cost when `all` is the default.

**Arithmetic I checked (against `technical.md` benchmarks):**

- Benchmark: single query embed = **0.22s** (`technical.md` line 75). The sweep does `embed_query` (bge-m3, Ollama) THEN one Qdrant query, **per object, sequentially** (spec lines 98, 186, 263; confirmed `indexer.py:47-48` per R1 B2).
- Embeddings alone @ N=500: 500 × 0.22s = **110s**. Qdrant query latency is on top (small, but non-zero — say 5–20ms each → +2.5–10s). Call the sweep **~110–120s**.
- Non-sweep battery @ N=500: **~51s** (get_object fan-out 500 × ~100ms = 50s dominates; corroborated, honest).
- **Default `all` run total @ N=500 ≈ 51 + 110 ≈ 160s+** — nearly **3×** the 60s budget.
- The budget is already blown at **far fewer than 500 objects**: the sweep crosses 60s by itself at ~270 objects (270 × 0.22 ≈ 60s), and combined with the battery the default path exceeds 60s at well under 200 objects. The `WIKI_LINT_MAX_OBJECTS=2000` cap is set 4×–10× too high to protect the default path's wall-clock — it only catches the truly pathological 2000+ wiki, by which point the sweep would be ~440s of embeddings.

**So is the gating sufficient?** It is sufficient for the *narrow* claim the spec proves — "a non-default High/Critical pass (`severity_threshold="high"`) skips the sweep and fits ≤60s." That claim is true and operationally valuable. It is **not** sufficient for the headline budget "≤60s for ≤500 objects," because the default run does not meet it once the wiki has more than ~150–200 objects. The spec's own §9 reference acknowledges "hundreds of objects" is the dogfooding scale — which is exactly the scale where the default sweep overruns.

**Operational impact.**
- **Not a stability risk, not a data risk.** Lint is on-demand, single-space, read-mostly. A 160s run does not crash anything, does not mutate objects, does not cascade. The MCP stdio call just takes longer than advertised. WikiLog receipt still written; `status` still resolves correctly.
- **Real impact is two-fold:** (1) **expectation mismatch / MCP timeout risk** — a Claude Code / IronClaw caller may have a tool-call timeout shorter than 160s, in which case the default lint *appears to hang or fail* even though the work is progressing; (2) **resource pressure on the shared box** — 110s+ of continuous bge-m3 inference on Ollama, sequentially, contends with any concurrent ingest/query/reindex worker for the same Ollama instance and the M4's cores. On the 32GB Mac Mini with multiple concurrent Claude Code sessions possible, a 2-minute Ollama-saturating lint is a noticeable co-tenant. Sequential (not batched) embedding also leaves the box's batch-embed throughput (batch-20 = 0.41s ≈ 0.02s/item, ~10× faster per item — `technical.md` line 76) on the table.

**Recommended action (any one closes the advisory; (a)+(b) preferred):**
- **(a) State the default-path budget honestly in the spec.** Add one row/sentence to the Performance Budget: "default `all` run @ N=500 ≈ 51s battery + ~110s sweep ≈ 160s; the ≤60s budget holds for the *non-sweep* path (`severity_threshold` ≠ `all`) only." Honesty here is the minimum bar; R2's "budget arithmetic credible" rests on the non-sweep half only.
- **(b) Lower the sweep's effective ceiling so the DEFAULT path stays bounded.** The cleanest fix is the already-deferred `WIKI_LINT_DUPLICATE_SAMPLE` (spec line 426) — cap the sweep at, e.g., 250 embeddings (random subset) so the default `all` run's sweep is ≤~55s regardless of N. The spec defers this; given the arithmetic, I recommend pulling a *simple cap* (not full random sampling) into v0.5.0, or setting `WIKI_LINT_MAX_OBJECTS` to a sweep-specific value near the real ~250-object budget crossover rather than 2000. Degraded-coverage informational sweep is strictly better than a 160s default.
- **(c) If neither (b) variant lands, consider making the sweep opt-in rather than default-on** (e.g. default `severity_threshold` stays `all` for *findings* but the sweep requires an explicit flag). This was R1's recommended B2 option (b) "default-off flag"; the spec chose the `all`-gating variant, which is weaker because `all` is the default.

This advisory does not require a re-review cycle to clear — a spec note (a) plus an implementation-time decision on (b)/(c) is acceptable to advance.

---

## Verified-Sound (infra lens — no action)

**Deployment surface — clean.**
- **No schema bump (D2-option-B).** `WIKI_SCHEMA_VERSION` stays `"0.4.1"`; `MIGRATIONS.md` untouched (spec line 379). Confirmed: zero migration burden, no bootstrap re-run required on existing spaces. This is the right call.
- **No new service, no launchd plist, no Docker/Colima change.** Lint is a new MCP tool + CLI subcommand inside the existing `anytype-llm-wiki` process — not a resident daemon. No new port, no new container, no Colima 2GB pressure. No service restart semantics beyond the normal `uv tool install .` + MCP re-registration that any code change to this module already entails.
- **Config surface: six `WIKI_LINT_*` env knobs + `.env.example`.** All additive, all defaulted, all guarded (`_positive_int` rejects 0/negative; new `_bounded_float([0,1])` clamps the score). Unset → defaults. No operational risk; an operator who ignores them gets sane behavior. The new `_bounded_float` guard is the only new code primitive and is well-scoped.
- **No new dependency, no new credential.** `ANYTYPE_API_KEY` / optional `QDRANT_API_KEY` inherited. Doctor unchanged and stays green (G8) — correct, since lint adds no new external dep beyond Ollama/Qdrant which doctor already preflights.

**Failure modes — operationally sound.**
- **Degraded-not-aborted is the right default for the object cap (SF2).** Above `WIKI_LINT_MAX_OBJECTS` the sweep is skipped (warning emitted) but High/Critical findings still produced. Confirmed: lint never loses High/Critical findings to a large wiki — the age-independent `unreviewed_needs_review` High check still fires even when source-timestamp deref fails (spec line 143, R2 SF5 confirmation). This is the correct durability-of-signal property for a health tool.
- **`status=ok|partial|error` lifecycle is well-defined (SF6).** `partial` on a `get_object`/sweep failure (object recorded in `warnings[]`, lint continues, WikiLog still written); `error` only on enumeration/pre-check abort (no WikiLog). Warn-and-continue on per-object fetch failure is the right graceful-degradation posture — one bad object does not sink the run.
- **No cascade.** Lint mutates nothing but its own WikiLog receipt. A lint crash leaves the wiki, Qdrant, and Ollama exactly as they were. No partial-write corruption surface (the one write is a single atomic create at the end). No recovery procedure needed beyond "re-run."
- **Data durability.** Lint creates no durable data store. Its sole artifact (the WikiLog receipt) is an ordinary Anytype object covered by whatever backs up the Anytype vault — no new backup target, no new rotation concern, no new log file requiring rotation (output is the LintReport return value + one Anytype object, not a disk log).

**Monitoring.** No new watchdog needed — lint is not a resident service and exposes no health endpoint of its own. The two budget warnings (`lint_object_count_exceeded_budget` >500 advisory; `lint_sweep_skipped_object_cap` >cap action) are surfaced in `warnings[]`, which is the right place for an on-demand tool. No ntfy wiring required at the infra layer (the caller decides whether a `partial`/`error` status warrants an alert).

**Runaway protection re SF2 — adequate for stability, not for budget.** A 10k-object wiki under default `all`: enumeration + 10k get_object fetches ≈ 1000s+, sweep auto-skipped at the 2000 cap. That is slow but bounded and non-saturating-of-Qdrant (sweep skipped). The get_object fan-out is the only unbounded cost above 2000, and it is pure Anytype reads (no Ollama/Qdrant saturation). So a pathological wiki degrades to "slow read storm against local Anytype," not "Ollama meltdown" — acceptable. The honest gap is the *default-path budget* (A1), not runaway *stability*. A hard abort is NOT warranted: losing High/Critical findings to a size threshold would defeat the tool's purpose; degraded-and-slow beats aborted-and-blind for a health checker.

---

## Bottom line

R1's two infra BLOCKINGs are resolved. Deployment is low-risk and migration-free. The single remaining concern is budget *honesty* on the default path, not operational stability: the gating fixed the *uncapped-runaway* defect but left the *default* invocation overrunning the advertised 60s by ~3× on a few-hundred-object wiki, because `all` (which triggers the sweep) is the default. I sign off contingent on the spec acknowledging the default-path wall-clock (A1-a) and the implementation taking a position on a sweep sample cap or opt-in sweep (A1-b/c). None of this blocks advancing the spec.
