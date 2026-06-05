# Council Impl Review R1 — Infrastructure Lead (#286 wiki_lint v0.5.0)

**Date:** 2026-06-05
**Reviewer:** Infrastructure Lead (operational readiness, resource impact, deployment risk)
**Phase:** post-implementation governance — final delivery gate before PR merge
**Box:** Mac Mini M4 32GB shared infra; module also runs against Jan's constrained box (Anytype:31012, Qdrant Docker:6333, shared Ollama/bge-m3:11434)

---

## Verdict: SIGN OFF

The CA-B1 operational guarantee I corroborated at spec (A1) holds in the shipped code, verified by tracing the actual control flow — not just the mock. The default `wiki_lint(space)` path issues ZERO bge-m3 embeddings and ZERO Qdrant queries. The deployment surface is migration-free, service-free, dependency-free, and credential-free. The steady-state resource profile of Jan's box is unchanged: lint is an on-demand MCP tool, not a resident daemon. 0 BLOCKING. 2 ADVISORY (both informational; neither gates merge).

---

## Default-path resource verification (the CA-B1 guarantee)

**The guarantee holds in code.** Traced control flow in `src/anytype_llm_wiki/wiki/lint.py`:

- The duplicate sweep is the entire Step-7 block, `lint.py:479-527`, wrapped in `if include_duplicates:` at `lint.py:481`.
- The signature default is `include_duplicates: bool = False` (`lint.py:189`) — so the bare call never enters the block.
- The ONLY bge-m3 / Qdrant invocation in the whole file is `indexer.semantic_search_core(...)` at `lint.py:496` (grep-confirmed: single hit; no `_qdrant`, no `embed_query` anywhere else in lint.py). That call sits in the `else` branch (`lint.py:488`) of the object-cap check `if len(wiki_objects) > config.lint_max_objects():` (`lint.py:482`). So the embed/query path is doubly gated: behind `include_duplicates=True` AND behind `N <= WIKI_LINT_MAX_OBJECTS`.
- Consequence for the default path: `report["potential_duplicates"]` is assigned the empty list (`lint.py:480`, `lint.py:527`); zero Ollama load; zero Qdrant load. The ~110s bge-m3 saturation risk I flagged at spec (A1) is genuinely off by default.

**Test integrity confirmed (not just mock-deep).** `tests/wiki/test_lint.py::test_duplicate_sweep_off_by_default` (test_lint.py:1225) patches BOTH `semantic_search_core` and `_qdrant` on the real `anytype_llm_wiki.indexer` module (test_lint.py:1250-1252) and asserts both call-count lists stay empty (test_lint.py:1261-1266) for the bare call AND for `severity_threshold="all"`. Because lint.py calls these through the `indexer` module object (`lint.py:496`), the patch is on the true call boundary — a leak in the impl would fail the assertion, not pass it silently. Ran it live: `3 passed` (off_by_default + runs_regardless + skipped_over_object_cap). Full lint suite: `44 passed, 2 deselected`.

**Default-path resource ceiling is honest.** The default path is the O(N) get_object battery only (~51s @ 500 on the shared box per the spec's per-phase arithmetic, dominated by N x ~100ms Anytype reads). These are pure local-Anytype reads — no Ollama, no Qdrant — so even the default path imposes no inference contention on the shared Ollama that ingest/query/IronClaw depend on. The ≤60s/≤500 claim now truthfully describes the default sweep-off path, and the README/docstring/CHANGELOG say exactly that (`lint.py:16-18`, README "The duplicate sweep is opt-in"). A soft `lint_object_count_exceeded_budget` warning fires above 500 objects (`lint.py:276-280`); it is advisory, lint still runs.

---

## Findings

### BLOCKING

None.

### ADVISORY

#### A1 — MCP caller timeout risk on the default path is bounded but not infinite (informational)

**Description.** The default path wall-clock is dominated by the sequential O(N) get_object fan-out (`lint.py:295-302`). At ~100ms/object this is ~51s @ 500 and scales linearly: a 1000-object wiki is ~100s, 2000 is ~200s — all pure Anytype reads, no hard internal timeout, no per-call deadline on the fan-out loop. An MCP client (Claude Code / IronClaw) with a tool-call timeout shorter than the run could see the default lint "appear to hang" on a large wiki even though work is progressing.

**Operational impact.** Not a stability or data risk — lint mutates nothing but its final WikiLog receipt (a single atomic create, `lint.py:550-561`), a crash/timeout leaves wiki + Qdrant + Ollama untouched, recovery is "re-run." The worst case is bounded by wiki size, not unbounded. But the bound is N-proportional, not a wall-clock cap. This is the residual of the original O(N) concern, not a sweep concern — the sweep (the part that hit the shared Ollama) is now gated off.

**Recommended action.** No code change required for merge. The `lint_object_count_exceeded_budget` warning above 500 (`lint.py:276`) is the right operator signal. If a caller routinely lints wikis well past 500 objects, document a higher MCP tool-call timeout for `wiki_lint` (or run it via the CLI rather than over MCP). Track the wall-clock cap with the deferred count-cache in known-limitations §9.

#### A2 — O(N) enumeration debt grows acceptably; §9 count-cache remains deferred (informational)

**Description.** `docs/known-limitations.md §9` documents `wiki_query`'s O(N) full-enumeration as a deferred concern and names a write-invalidated count-cache as a *v0.5.0 candidate*. wiki_lint adds a second O(N) consumer of `list_objects` + an O(N) get_object fan-out. The count-cache did NOT land in v0.5.0 (explicitly deferred — spec Deferred Items, spec.md:458). So lint adds to the §9 debt.

**Operational impact.** Acceptable at the current dogfooding scale (hundreds of objects). Crucially, lint mitigates rather than compounds the worst of it: D1 makes native `backlinks` the primary inbound source (`lint.py:117-127`), removing the second O(N) reciprocal-traversal pass the master spec's primary path would have required, and `list_objects` is called EXACTLY ONCE (`lint.py:228`) feeding both the schema gate and the battery via the shared per-run cache. So lint's enumeration cost is one O(N) read storm against local Anytype per invocation, on demand — not a resident or per-write cost. It does not change the steady-state profile.

**Recommended action.** None for merge. When the §9 count-cache is eventually built for `wiki_query`, wiki_lint should consume it too. No new debt ticket needed — it is the same §9 concern, already tracked.

---

## Rationale

**Deployment surface — clean, re-verified against the shipped diff.**
- **No schema bump.** `WIKI_SCHEMA_VERSION` stays `"0.4.1"` (types_schema.py:27, grep-confirmed). D2-option-B held: zero migration, no bootstrap re-run on existing spaces, `MIGRATIONS.md` untouched.
- **No new service / launchd plist / Docker / Colima change.** `git diff --stat main...HEAD` touches only `lint.py` (new), `config.py`, `cli.py`, `server.py`, `.env.example`, `README.md`, `CHANGELOG.md`, tests, and council docs. Zero `pyproject.toml` change → **no new dependency**. All "launchd/docker/colima" grep hits are documentation prose, not deployment artifacts. Lint is a new MCP tool + CLI subcommand inside the existing `anytype-llm-wiki` process — not a resident daemon, no new port, no new container, no Colima 2GB pressure. Deployment is the normal `uv tool install .` + MCP re-registration that any code change already entails.
- **No new credential.** `ANYTYPE_API_KEY` / optional `QDRANT_API_KEY` inherited. Six additive `WIKI_LINT_*` knobs, all defaulted, all guarded (`_positive_int` rejects 0/negative; new `_bounded_float([0,1])` clamps the score — config.py:60-75). Unset → sane defaults; README states "you do not need to set any of these."
- **Doctor stays green.** Ran `uv run python -m anytype_llm_wiki.wiki.cli doctor`: exit 1, but ONLY because Anytype isn't running in the sandbox (`anytype_api_key` FAIL, `anytype_reachable` FAIL — app not started). That is NOT a lint regression: lint added zero doctor checks (G8). The lint-relevant infra is green — Qdrant reachable, Ollama reachable, bge-m3 pulled, lock dir mode 0o700, patch-decision parseable.

**Failure modes — operationally sound.**
- **No cascade.** Lint mutates nothing but its own WikiLog receipt (one atomic create at the end, `lint.py:550`). A lint crash leaves wiki/Qdrant/Ollama exactly as they were. No partial-write corruption surface. Recovery is "re-run."
- **Graceful degradation.** Per-object `get_object` failure → `warnings[]` + `status="partial"`, lint continues (`lint.py:298-301`); enumeration failure → `status="error"`, no WikiLog (`lint.py:229-234`); `try/finally` closes both clients (`lint.py:567-569`). Above `WIKI_LINT_MAX_OBJECTS` the sweep is skipped with a warning (`lint.py:482-487`) while High/Critical findings still fire — the correct durability-of-signal property for a health tool.
- **Data durability / backup.** Lint creates no durable data store. Its sole artifact (the WikiLog receipt) is an ordinary Anytype object covered by whatever backs up the Anytype vault — no new backup target, no new rotation concern, no new disk log file requiring rotation (output is the LintReport return value + one Anytype object).

**Monitoring — no new watchdog needed.** Lint is on-demand, not a resident service, and exposes no health endpoint of its own. The two budget warnings live in `warnings[]`, the right place for an on-demand tool. No ntfy wiring at the infra layer — the caller decides whether a `partial`/`error` status warrants an alert.

**My spec-phase A1 advisory is resolved exactly as recommended (option c).** The sweep — the ~110s of continuous bge-m3 inference that would have self-DoS'd the shared Ollama against ingest/query — is now opt-in (`include_duplicates=False`), decoupled from `severity_threshold`. The default invocation imposes zero inference load on Jan's single Ollama. The advertised budget now honestly describes the default path. This was the central operational issue for this project, and the shipped code closes it. I sign off.
