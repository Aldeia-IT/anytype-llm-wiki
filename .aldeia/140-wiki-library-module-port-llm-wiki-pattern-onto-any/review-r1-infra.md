# Infra / Ops Review — Wiki Library Module (r1)

**Reviewer:** infra-reviewer
**Domain:** agent-operations + infrastructure
**Date:** 2026-04-22

## Summary

**Verdict: Approve with SHOULD-FIX items before v0.3.0; one BLOCKING item for v0.2.0 pre-release.**

The spec shows strong operational awareness in several areas: single-writer per-space filesystem locking with PID-based staleness, structured JSON-to-stderr logging, an explicit three-category error taxonomy, SSRF guards with a sound blocklist, a pre-release verification script that collapses dual code paths into a single canonical one, and explicit failure-mode tables per tool. The WikiLog-as-durable-receipt pattern is well-designed and is the right abstraction for an offline-tolerant CLI.

What is missing is largely the boring operator plumbing: no concrete per-operation memory budget, no disk-growth model (Qdrant collection, state directory, or lock directory), no first-run / `doctor` health-check command, no CHANGELOG/migration-between-versions story, no concrete schema-migration or downgrade narrative, and several lock edge cases that flock-vs-O_EXCL on macOS will expose in practice. None of these block v0.2.0 (which is schema-only), but they must be resolved before v0.3.0 ships or the OSS community will file bug reports the maintainer cannot triage from logs alone.

## Resource Impact Assessment

Per-operation estimates derived from the spec. **Where the spec is silent, the cell is marked (not stated).**

| Operation | Memory peak | CPU profile | Disk delta | Network |
|---|---|---|---|---|
| `wiki_bootstrap` | Small: ~6 type defs + ~40 property defs + ~7 tag options held in-process. O(100 KB). | Negligible; ~50 sequential Anytype POSTs. | Lock dir created (`~/.local/share/anytype-llm-wiki/locks/`). No Qdrant writes. | `localhost:31012` only. |
| `wiki_ingest` (per source) | **(not stated)** — must hold: source markdown (up to ~1 MB HTML → 100–300 KB markdown), embedding model (bge-m3 ~2.2 GB resident in Ollama), extraction model `qwen2.5:7b` (~5 GB resident in Ollama), per-run object cache. Peak realistic on-machine: Ollama bge-m3 + qwen2.5:7b co-resident ≈ 7–8 GB on the Ollama process alone. | Ollama extraction is the long blocking call (tens of seconds for 7B model on M4). No explicit token budget stated for extraction input; extraction prompt truncation is referenced ("truncated to N tokens") but **N is undefined**. | Qdrant grows by (entities + concepts + source embedding) × 1024 dims × 4 bytes + payload. 1 source ≈ 5–20 new vectors ≈ ~100 KB Qdrant. Source body in Anytype: up to source size. Lock file: <200 bytes. No tmp files documented. | URL fetch (source host), httpx follow-redirect loop, Anytype localhost, Qdrant localhost, Ollama localhost. Hosted-LLM extraction egress if `WIKI_EXTRACT_ENDPOINT` off-machine. |
| `wiki_query` | Per-run object cache (≤ 20 neighborhood objects capped, but object size itself not bounded). Synthesis LLM context: all fetched bodies + question. **(context cap not stated)** | Tier 1: N type queries + 20 object fetches + 1 LLM synthesis call. Tier 2: adds 1 vector search. Bounded by neighborhood cap. | Query object + drew_from relations written if file-back triggers. ~one new Anytype object per query. | Anytype + Ollama localhost. |
| `wiki_lint` | Whole-wiki object list held in the per-run cache (500 objects × ~5 KB each ≈ 2.5 MB). Plus Qdrant similarity sweep results. Tractable. | O(N) API calls; 500 objects ≈ 50s wall-time at p50 100ms latency. Entirely I/O-bound. | No writes (read-only). | Anytype + Qdrant localhost. No egress. |

**Mac Mini M4 compatibility:**
- **16 GB config:** marginal for v0.3.0+. With Ollama hosting bge-m3 (~2.2 GB) + qwen2.5:7b (~5 GB) co-resident, plus Anytype desktop (~500 MB–1 GB), plus Qdrant (~500 MB baseline), plus the Python server, the 16 GB ceiling is reachable under concurrent query+ingest. Spec does not acknowledge this and does not propose a smaller extraction model fallback for 16 GB users.
- **32 GB config:** comfortable. Reference hardware claim holds.
- **Spec lacks a stated minimum RAM requirement.** This is an OSS-community friction point — users will install, attempt first ingest, and OOM-kill Ollama without understanding why.

## Failure Modes

Each documented mode and the spec's treatment:

| Mode | Spec coverage | Gap |
|---|---|---|
| Anytype API 500/down mid-ingest | **Covered** — failure table specifies `[API ERROR]` + `status: "partial"` + WikiLog written if possible. Bidirectional relation writes are transactional (rollback both sides on failure). | WikiLog may itself fail to write if Anytype is down — the spec notes "except when Anytype is unreachable, in that case only the JSON log exists." JSON log contents for this case are not specified to contain the partial object IDs needed to hand-recover. |
| Ollama unreachable | **Covered** — failure table shows `[API ERROR]`, no Source created, lock released. | Extraction model-pull-on-demand pattern common to Ollama is not addressed: if the operator has Ollama running but has not `ollama pull qwen2.5:7b`, the error message is Ollama's generic "model not found" — no spec-level remediation guidance ("run `ollama pull qwen2.5:7b`"). |
| Qdrant unreachable | **Partially covered** — table says "Tier-2 fallback cannot proceed; `[API ERROR]` logged; Source still created with `embedded=false` note" for ingest. But the embedding-similarity resolution (Step 2 of `resolve_entity`) also needs Qdrant. If Qdrant is down, resolve_entity cannot detect duplicates above auto-upsert threshold and may create duplicate objects. | The degraded-Qdrant path during ingest is under-specified. Spec should say: "if Qdrant unreachable during ingest resolution, skip embedding similarity step and emit a warning; downgrade to title-only matching." |
| Disk full during ingest | **Not addressed.** Lock file write is `O_CREAT\|O_EXCL` which may fail with ENOSPC; not handled. WikiLog write to Anytype does not hit local disk, but JSON log to stderr does via the terminal; unlikely to be the failure point. | The `contextmanager` releases lock on exception, so ENOSPC mid-ingest should still release the lock. Worth an explicit test. |
| Process killed (SIGKILL) mid-ingest | **Partially covered** — spec's stale-lock detection via `os.kill(pid, 0)` covers the case where the PID is reused before next ingest. | **PID reuse race:** on Linux/macOS, PIDs are reused aggressively. If the original PID (e.g. 12345) is now a different process, the stale-lock check returns "alive" and refuses to clear. Spec does not handle this; `started_at` field is recorded but not used in staleness logic. Recommend: "considered stale if PID alive AND started_at > lock `started_at` field" via `ps -o lstart` comparison, or a lock TTL (e.g. reject locks older than 30 minutes). |
| Corrupted `state.json` / `patch-decision.md` | **Not addressed.** `patch-decision.md` is described as the source of truth for PATCH path; what happens if it is missing or malformed? | No recovery path stated. Recommend: v0.3.0 refuses to start if `patch-decision.md` is missing or cannot parse, with a remediation message. |
| SIGKILL during lock acquisition (file created, process dies before writing payload) | **Not addressed.** O_EXCL succeeds; process dies; lock file is empty. Next ingest reads empty lock, cannot parse PID, and the spec does not say what happens. | Recommend: empty or unparseable lock payload → treated as stale. |
| Anytype version bump between `patch-decision.md` timestamp and ingest | Spec states "Rerun verification on any version bump" but does not describe the detection mechanism. | Recommend: `wiki_client` reads current `Anytype-Version` from a health call at startup, compares to `patch-decision.md` recorded version; mismatch emits a loud warning. |

## Findings

### BLOCKING

**B1. `scripts/verify-anytype-writes.sh` hard dependency on a live user-owned object is not safe for CI.**
Appendix A requires `$ANYTYPE_OBJECT_ID` and *mutates its body and name*. Any operator running this against their main space will have one of their objects renamed to `"PATCH Property Test - <timestamp>"` and its body overwritten. The spec does not create a throwaway object, does not restore the original name/body on cleanup, and does not warn operators. This is a foot-gun for any contributor who runs the script against their real space without reading every line of it first. **Fix:** the script must (a) create its own test object at start, (b) perform all probes on that object, and (c) delete it on exit (including trap on error). The pre-release checklist says "`scripts/verify-anytype-writes.sh` run" but never names which space/object — implicitly the operator's real one.

### SHOULD-FIX

**S1. First-run doctor / health-check command is absent.**
Spec mentions `anytype-llm-wiki wiki-bootstrap` and three other subcommands but no `anytype-llm-wiki doctor`. This is a community-friendly convention — check Anytype reachable, Qdrant reachable, Ollama reachable, `qwen2.5:7b` pulled, `bge-m3` pulled, `ANYTYPE_API_KEY` set, lock dir writable, `patch-decision.md` present and parseable. Without it, the default user experience for a broken setup is a crashed MCP tool call with a stack trace. **Recommend:** add `anytype-llm-wiki doctor` to v0.2.0 scope; it is ~50 lines of Python and eliminates most first-run support burden.

**S2. PID-reuse race in stale-lock detection.**
`os.kill(pid, 0)` returning success means "some process with this PID exists," not "the original ingest is still running." After a crash + reboot + another long-running process happens to grab the same PID, the spec's logic treats the lock as held forever. Add a secondary check: compare `started_at` in the lock payload to the living process's start time (via `psutil.Process(pid).create_time()` or a shell-out), or add a 30-minute TTL as a belt-and-suspenders stale cue.

**S3. Lock strategy is `O_CREAT | O_EXCL` — on macOS this is atomic on local APFS but not reliably atomic on NFS or SMB-mounted home directories.**
Community operators on Synology / NAS-mounted home directories will see spurious lock collisions or races. Not a showstopper; spec correctly notes this is a "single-host lock." Recommend adding a one-line README note: "lock dir must be on a local filesystem; override `WIKI_LOCK_DIR` if your home is network-mounted."

**S4. No concrete memory/CPU budgets per operation.**
The only stated budget is wall-time (30s bootstrap, 5s query, 60s lint). Nothing for memory. An OSS user whose ingest gets OOM-killed has no spec reference for "should this have worked on my machine." Recommend: table of "reference-hardware budgets" stating "Mac Mini M4, 16 GB, with Ollama + Anytype + Qdrant running: peak RSS of `anytype-llm-wiki` process ≤ 500 MB during ingest; Ollama RSS will be dominated by the loaded models."

**S5. Extraction prompt token budget is unspecified.**
Prompt says "truncated to N tokens" but N is undefined, and the model default (`qwen2.5:7b`) has a specific context window (typically 32K for qwen2.5). Truncation boundary matters: too small loses context, too large silently exceeds context on long arxiv papers. Recommend: `WIKI_EXTRACT_MAX_INPUT_TOKENS` env var, default 8K, documented.

**S6. Schema migration / upgrade-downgrade story is absent.**
Spec says "Won't: schema migration tooling (not yet needed)." But v0.3.0+ adds properties that v0.2.0 bootstrap did not create. What happens when a user who ran v0.2.0 bootstrap then upgrades to v0.3.0 and the code expects a property that was not created? Spec acknowledges bootstrap is idempotent ("creates any missing elements") — good. But: (a) there is no spec-level statement that `wiki_ingest` calls a "verify/upgrade schema" step on startup, and (b) there is no downgrade policy. If a user runs v0.5.0 lint against a space whose schema was bootstrapped by v0.2.0 (no v0.5.0-only properties added, if any), what happens? Recommend: every `wiki_*` tool runs a schema-compatibility check on entry and emits a `[CONFIG ERROR]` with "re-run `wiki_bootstrap` to add missing v{X}.{Y} properties" if the schema is older than the code.

**S7. Qdrant collection growth and pruning is not modeled.**
v0.1.0 ships Qdrant. The wiki module indexes new types. Nothing in the spec says "Qdrant collection grows unboundedly; user may need to occasionally drop and rebuild." For a user ingesting weekly over a year, Qdrant collection size should be estimable. Recommend: one README paragraph on expected Qdrant disk growth (e.g. "per 100 sources, expect ~50 MB Qdrant growth") and how to rebuild from Anytype if needed.

**S8. Observability: spec defines log keys but not log levels or rotation.**
Stderr-JSON is fine for MCP runtime, but for long-running operators (cron-launched reindex, overnight ingest batches) there is no guidance on piping to a file or rotation. Recommend: one README paragraph on "Logging" with a recipe (`anytype-llm-wiki serve 2>> ~/.local/share/anytype-llm-wiki/run.log`) and a note on log-rotate-friendly format.

**S9. CHANGELOG / migration guide is implied but not spec'd.**
Every version's pre-release checklist has "CHANGELOG.md entry" as a one-liner. No spec says what the CHANGELOG schema is (user-visible changes vs internal). No migration-between-versions doc (what does a v0.2.0 → v0.3.0 user need to do besides `pip install -U`?). Given the schema-additive evolution, this is a real concern. Recommend: a `MIGRATIONS.md` or a README "Upgrading" section covering per-version operator steps.

**S10. `scripts/verify-anytype-writes.sh` CI invocation is impossible without a live Anytype desktop.**
Spec says the script is a pre-release checklist item. It requires Anytype desktop running and an API key. GitHub Actions cannot run it. This is fine — but it should be said explicitly: "this script runs on the maintainer's machine during pre-release, not in CI." Otherwise a contributor will waste time trying to wire it into a GH Actions workflow.

**S11. No CLI command to inspect wiki state cheaply.**
Spec ships `wiki-lint` which is comprehensive but slow (60s for 500 objects). For daily "is my wiki healthy?" the `Deferred Items` section explicitly punts a `wiki.status` tool. Given how cheap "count objects by type + last ingest timestamp" is, this seems like a 10-line feature that would materially improve the operator experience. Reconsidering this punt would be worth a discussion.

### SUGGESTION

**G1. Add `wiki_lint --json` vs `wiki_lint --human` output modes.**
The current `LintReport` is JSON-native. Operators tailing logs or running lint interactively will want a human-readable severity-grouped text output. Trivial to add.

**G2. Consider `flock`-based locks instead of O_EXCL-file locks.**
On macOS, `fcntl.flock` (advisory lock) integrates with OS-level lock tracking — if the holding process dies, the lock is automatically released by the kernel. This eliminates the whole stale-lock-detection code path. Trade-off: flock semantics differ slightly between Linux (BSD flock) and macOS, and don't work on NFS. For a single-host lock, both approaches work; flock removes the PID-reuse footgun at the cost of a small platform-abstraction layer.

**G3. Persist extraction endpoint to log, not just once at startup.**
Spec says startup log prints `extraction_endpoint`. For long-running MCP processes where a config reload happens, subsequent ingests could use a different endpoint without re-logging. Recommend logging `extraction_endpoint` on every ingest start, not just server boot.

**G4. Document Anytype's local data-directory location so backup guidance can point to it.**
Spec is silent on "where does Anytype store its data, and does my wiki live inside that backup set?" A one-line note in the README ("Anytype stores its data at `~/Library/Application Support/Anytype2` on macOS; backing that up backs up your wiki; the pip-installed module's state is ephemeral except for `~/.local/share/anytype-llm-wiki`") eliminates a common support question.

**G5. Consider exposing `wiki_bootstrap --dry-run`.**
For community developers evaluating the module before committing, a dry-run that prints "would create 6 types, 40 properties, 7 tags" without touching Anytype is low-risk and high-confidence-boosting.

**G6. Add a `WIKI_MIN_EXTRACT_RAM_GB` advisory check.**
At `wiki_ingest` start, query `psutil.virtual_memory().available`; if less than a threshold (e.g. 4 GB on top of Ollama's resident models), warn. This is belt-and-suspenders but helps 16 GB Mac Mini operators self-diagnose.

**G7. Documentation: troubleshooting section per failure mode.**
The failure-mode table in the spec is a perfect seed for a README troubleshooting section. Each row → one H3 + remediation. Spec lists the failures but does not commit to turning them into operator docs.

## What's done well

- **Single canonical path via pre-release verification (PATCH body, FilterExpression).** This is the right engineering decision for an OSS project. Committing the decision to `patch-decision.md` and having code reviewers enforce the chosen path at PR time is cleaner than dual code paths with runtime dispatch.

- **Per-space locking with explicit cross-space concurrency allowed.** The right granularity. Spec acknowledges the distributed (multi-machine) case honestly rather than pretending to solve it.

- **Structured JSON logs to stderr with a defined key schema.** OSS-friendly, grep/jq-friendly, and aligned with MCP stdout/stderr conventions.

- **WikiLog-as-durable-receipt.** The append-only log inside Anytype itself is an excellent design — the operator's existing backup of Anytype doubles as wiki-operation audit.

- **Explicit three-category error taxonomy (`api_error` / `data_error` / `config_error`)** with message patterns. Users reading errors know immediately which of the three remediation paths to take.

- **SSRF blocklist is complete** (RFC1918 + loopback + link-local + IPv6 equivalents). The follow-redirect-manually-and-revalidate pattern is the correct approach; accepting DNS rebinding as out-of-scope is honest.

- **Failure modes table per tool.** Few specs commit this concretely to what each tool does when each dependency is unreachable.

- **Tiered retrieval with an explicit boundary test (199/200/201).** Prevents off-by-one regressions and is trivial to test.

- **Write-token scope verification as a first-class pre-release step.** Token scope is a common OSS-MCP gotcha; the spec handles it upfront.

- **Per-run object cache documented as a cross-check optimization.** Good instinct; will likely become important when the wiki grows.

- **Explicit "won't" list per version** prevents scope creep and gives reviewers a concrete veto target.
