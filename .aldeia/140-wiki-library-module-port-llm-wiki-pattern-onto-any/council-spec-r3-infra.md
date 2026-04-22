# Council Meeting — Post-spec (Round 3, R2-rework verification) — Infrastructure Lead

**Date:** 2026-04-23
**Ticket:** #140 — Wiki Library Module: Port LLM Wiki Pattern onto Anytype
**Phase reviewed:** spec (R3 — verification of R2 fixer rework)
**Reviewer:** Infrastructure Lead (council)
**Spec under review:** `.aldeia/140-wiki-library-module-port-llm-wiki-pattern-onto-any/spec.md` @ commit `b611f41` (2123 lines after R2 rework + R3 SG1 polish).
**Review mode:** Delta-only verification. Spot-check the 8 R2 infra advisories I raised; cross-examine the new bootstrap schema-compat exception for deadlock potential; assess cumulative doctor cognitive load; re-validate the Mac Mini resource envelope under the two-defaults config.

---

## Verdict

**SIGN OFF. No BLOCKING. No new advisories. R2-infra conditions discharged.**

All 8 of my R2 advisories land in the spec with visible, verifiable text. The new bootstrap-specific schema-compat exception (§Schema Compatibility, lines 1599–1607) is operationally sound — no self-recursive loop, no deadlock potential, and the `wiki_schema_upgrade_started` log + `BootstrapResult.status` semantics are coherent for both the happy path and the mid-upgrade failure path. The doctor step-count has grown from 8 → 11 (+ steps 4b, 6b, 9, 10) but cognitive load remains manageable because each addition is a WARN-not-FAIL and the output format stays grep-friendly `[CHECK] name ... OK | WARN | FAIL`. The two-defaults extraction-model config (OQ #3 + v0.3.0 README table + doctor step 6b anchor) closes the 4.7 GB download-disappointment risk at the pre-install information layer rather than relying on post-install WARN, which was the CPO-coupled concern.

---

## Summary (R3 independent view)

I re-entered this review looking specifically for (a) whether the bootstrap exception fix is a real fix or prose-only, (b) whether the doctor sequence has become a 11-step wall of output that operators will skip, and (c) whether the 4.7 GB qwen2.5:7b download can still surprise a 16 GB operator. On all three axes the R2 fixer's work is defensible.

The bootstrap exception paragraph is worth specifically calling out as strong. The fix explicitly scopes the exception (`applies ONLY to wiki_bootstrap`); names the other three tools that keep the original fatal semantics (`wiki_ingest`, `wiki_query`, `wiki_lint`); describes the info-level upgrade-started log action; commits to `BootstrapResult.status: "ok"` + `schema_upgrade` section on success; and handles mid-upgrade failure as `status: "partial"` with WikiLog diagnostics. The self-recursive remediation loop that was the heart of my R2 A1 concern is fully eradicated — an operator running v0.4.0 bootstrap on a v0.3.0-schema space now gets an idempotent upgrade log, not a contradictory "re-run bootstrap" error.

No new advisories in R3. The three R3-SG items from `review-r3.md` (OQ #5 casing, inherited Mermaid edge-label characters, orphaned R2-SG residuals) are cosmetic and were addressed by `b611f41` where applicable. I decline to add my own cosmetic finds on top.

---

## R2 disposition table

Format: `R2 Adv # — where in spec — PASS/FAIL/PARTIAL — note`.

| R2 Adv | Spec location (R3 verified) | Status | Note |
|---|---|---|---|
| **A33** (Infra #33, bootstrap schema-compat exception) | §Schema Compatibility lines 1599–1607 | **PASS** | See Deep-dive A33 below. Exception is scoped, idempotent, and the log-action naming (`wiki_schema_upgrade_started`) is explicit. |
| **A34** (Infra #34, doctor statfs NFS/SMB/sshfs/CIFS probe) | Doctor step 9, line 1168 | **PASS** | `os.statvfs` (Linux) / `statfs` (Darwin), mount-type parsed against `{nfs, nfs4, smbfs, cifs, fuse.sshfs, afpfs}`, WARN-not-FAIL, with explicit `WIKI_LOCK_DIR=/tmp/anytype-llm-wiki-locks` remediation hint. Pre-release checklist line 764 also names "not on NFS/SMB/sshfs/CIFS" as a doctor-green gate. |
| **A35** (Infra #35, doctor Qdrant collection WARN not FAIL) | Doctor step 4b, line 1162 | **PASS** | `client.get_collection(QDRANT_COLLECTION)` → INFO if present, WARN if missing, names `reindex_anytype` (v0.1.0) or the first `wiki_ingest` (v0.3.0+) as the creation path. WARN-not-FAIL semantics correct — fresh installs should not FAIL doctor. |
| **A36** (Infra #36, sample logrotate + newsyslog configs) | v0.2.0 Scope (in) lines 713–714; §Observability lines 1524–1529 | **PASS** | Both config files are in v0.2.0 Scope (in) as deliverables (not prose-only). The §Observability rewrite enumerates the drop-in locations, sudo-vs-user-space handling on macOS (launchd wrapper OR maintainer-run setup script), and the 10 MB size trigger matching both OSes. |
| **A37** (Infra #37, 16 GB + ≥7B WARN w/ 3B fallback) | Doctor step 6b, line 1165; OQ #3 at 1946–1950; v0.3.0 pre-release checklist 863–866 | **PASS** | Doctor WARN uses `psutil.virtual_memory().total < 20 GB` guard with regex on `/:(\d+)b$/`. WARN message anchors to the README "Recommended extraction defaults" table by name, not a hardcoded model string — good decoupling. Also: the two-defaults config is a product/README commitment, not just a post-install nag. See Resource Envelope section below. |
| **A38** (Infra #38, failure-mode gaps: partial token scope + empty wiki lint) | Additional failure modes table, lines 1657–1658 | **PASS** | Row A38a: `insufficient_token_scope` named with the `create {types\|objects} but not {objects\|properties\|tags}` shape. WikiLog behavior ("only if the WikiLog type itself was creatable") is correctly conditional on the actual token scope. Row A38b: `wiki_lint` on bootstrapped-but-empty returns exactly 6 `empty_type` findings at Informational + `status: "ok"` (explicitly NOT `partial`) and cross-references AC v0.5.0 #7. |
| **A39** (Infra #39, runtime metrics deferred) | Deferred Items, line 1984 | **PASS** | Explicit paragraph "Runtime metrics surface — rolling error rate, duration percentiles, last-N-ingest aggregates" with reconsideration trigger tied to `wiki.status`. Correctly framed as acceptable for a solo operator; defers at the right granularity. |
| **A1 / CSO #3** (cross-machine TOCTOU bootstrap probe — joint CSO/Infra) | v0.2.0 pre-release checklist line 765 | **PASS** | "run `wiki_bootstrap` simultaneously from two processes on two different hosts against the same Anytype vault; assert zero duplicate Types are created. Record the result ... If duplicates appear, file a defect and add the cross-host limitation to §Concurrent Ingest Policy alongside the existing flock cross-host limitation." Has the assertion, the recording requirement, and the escalation path. |

**Summary: 8/8 PASS, 0 FAIL, 0 PARTIAL.** No R2-infra condition remains unaddressed.

---

## R3 findings

### BLOCKING

_None._

### ADVISORY

_None._

### Deep-dive: A33 bootstrap schema-compat exception (most critical R3 check)

The task prompt flagged this specifically: "if the bootstrap fix text is ambiguous or introduces new deadlock, that's a new BLOCKING." I re-read §Schema Compatibility lines 1588–1615 three times with the explicit v0.3.0 → v0.4.0 upgrade-on-existing-vault scenario in mind. Findings:

**Scenario 1: v0.4.0 client, v0.3.0 vault, operator runs `wiki_bootstrap`.**
1. Tool entry reads `wiki_schema_version = "0.3.0"` from root Collection.
2. Code compiles at `WIKI_SCHEMA_VERSION = "0.4.0"`.
3. Normal path would fire case 3 (`wiki_schema_outdated`) with `[CONFIG ERROR] ... re-run wiki_bootstrap(space_id=...)`.
4. **Exception trips.** Because `tool == wiki_bootstrap`, the outdated branch is informational, not fatal.
5. Emits `wiki_schema_upgrade_started {from: "0.3.0", to: "0.4.0"}` at info level.
6. Adds missing v0.4.0 properties idempotently; preserves all v0.3.0 properties and values.
7. Updates `wiki_schema_version = "0.4.0"` on root Collection.
8. Returns `BootstrapResult { status: "ok", schema_upgrade: {...} }`.

No loop. No deadlock. The state transition is atomic from the operator's perspective — either success with `status: "ok"`, or `status: "partial"` with a re-runnable next-attempt (idempotence guarantee preserved).

**Scenario 2: same, but bootstrap fails mid-upgrade (Anytype 500 after adding 3 of 5 new properties).**
1. Steps 1–5 as above.
2. Step 6 partially succeeds (3 properties added).
3. Failure is caught; `wiki_schema_version` is **NOT** updated (remains "0.3.0").
4. Returns `BootstrapResult { status: "partial" }` + WikiLog entry naming the failed step.
5. Operator re-runs `wiki_bootstrap`. The exception trips again (still outdated). Idempotent property creation is a no-op on the 3 already-added properties; the remaining 2 are added. `wiki_schema_version` becomes "0.4.0" on success.

No duplicate-property hazard because property creation is `type_key`-keyed and idempotent in Anytype. The partial-state recovery is naturally safe.

**Scenario 3: two operators simultaneously run v0.4.0 `wiki_bootstrap` on the same v0.3.0 vault from different hosts.**
This is outside §Concurrent Ingest Policy's flock scope (flock is per-host). The cross-machine TOCTOU probe on the v0.2.0 pre-release checklist (line 765) exists precisely to catch this — Anytype's own dedup-by-`type_key` is the only serialization. **Not a regression introduced by the exception**; this concern already existed in the R2-approved baseline and has an empirical verification gate.

**Scenario 4: v0.3.0 client, v0.4.0 vault (operator downgraded the code), operator runs `wiki_bootstrap`.**
This falls into case 4 (`wiki_schema_newer`, not case 3). The exception does NOT apply here. Bootstrap emits a `warn`-level `wiki_schema_newer` log and continues with read-forward semantics (missing-property reads return null; unknown writes skipped). Correct behavior — the operator is on an older client, not running an upgrade.

**Potential deadlock vectors I considered and ruled out:**

- **Recursive exception ("bootstrap calls bootstrap internally"):** No. The exception is a branch inside the `wiki_bootstrap` tool's own entry check, not a recursive invocation. The tool is one linear flow from check → upgrade → version update → return.
- **Flock contention with itself:** The schema-compat check runs BEFORE the flock acquisition in `wiki_ingest`, but bootstrap does not use the per-space flock at all (it is a schema operation, not an ingest operation). No flock interaction to deadlock on.
- **WikiLog write before bootstrap completes creating the WikiLog type (v0.2.0 first-run ordering):** Bootstrap's own upgrade-failure WikiLog write could fail if the WikiLog type doesn't exist yet. But that's a v0.2.0→v0.3.0 scenario, not the v0.3.0→v0.4.0 scenario the fix addresses; and the A38 row explicitly handles WikiLog writability conditional on token scope. This is a different code path with its own handling.

**Verdict on A33:** clean, unambiguous, non-deadlocking, and the fix is narrower than either of the two options the R2 council proposed (option (a) "bootstrap-specific exception inside the compat check" rather than option (b) "skip the compat check entirely for bootstrap"). Option (a) preserves a single conceptual surface — every tool runs the compat check, bootstrap has one documented special-case on the outdated branch. I consider this the correct choice; the fixer debrief explains the reasoning and it holds up.

---

### Doctor cognitive load (task prompt question 3)

**Steps in doctor now: 11 total.** Original 8 checks + 4b (Qdrant collection) + 6b (16 GB + ≥7B model) + 9 (NFS statfs) + 10 (extra ports). That's a +37% increase in doctor output length.

| Step | Severity on fail | Network call? |
|---|---|---|
| 1 API key | FAIL | No |
| 2 Anytype `/v1/spaces` | FAIL | Yes |
| 3 Anytype version match | WARN | No (header from #2) |
| 4 Qdrant `/readyz` | FAIL | Yes |
| 4b Qdrant collection | WARN | Yes |
| 5 Ollama `/api/tags` | FAIL | Yes |
| 6 Required models | FAIL (or WARN v0.2.0) | No (list from #5) |
| 6b 16 GB + ≥7B WARN | WARN | No |
| 7 Lock dir mode 0o700 | FAIL | No |
| 8 `patch-decision.md` | FAIL (skipped on v0.2.0) | No |
| 9 Lock dir filesystem type | WARN | No |
| 10 Extra ports opt-in | WARN | No |

**Cognitive-load assessment:**
- **Severity distribution is correct.** 5 FAIL-class checks (the non-negotiable reachability/auth set) and 6 WARN-class checks (the advisories). No "new WARN that should be a FAIL" or vice versa.
- **Output grep-ability preserved.** All 11 steps use the same `[CHECK] name ... OK | WARN | FAIL (reason)` format per line 1171. An operator can still `doctor 2>&1 | grep FAIL` or `grep WARN` mechanically.
- **Exit codes stay simple.** `0` all pass, `1` any FAIL, `2` WARN without FAIL. CI gate shape unchanged.
- **Sequencing is logical.** Reachability → configuration → filesystem → opt-ins. An operator reading top-to-bottom sees failures in the order they would need to diagnose them.
- **No check has an expensive side-effect.** No writes, no LLM calls, no model downloads. All checks are probes.

**One observation (not a finding):** at some point (v0.5.0+) the doctor output will cross the readability threshold where operators skim rather than read. A future `doctor --summary` one-line-per-status output could help, but this is deferred-to-future-work territory, not a v0.2.0 concern. 11 checks is under that threshold.

**Doctor verdict: manageable. No regression from R2.** The two WARN additions (step 6b, step 9) address real silent-failure modes; the two INFO/WARN additions (step 4b, step 10) surface operator-facing config state. All four are net-positive for community UX.

---

### Resource envelope: does the two-defaults config prevent the 4.7 GB download disappointment? (task prompt question 4)

**The original concern (R2 A37 + CPO #21):** a 16 GB community adopter sees "default = qwen2.5:7b", runs `ollama pull qwen2.5:7b`, waits for the 4.7 GB download, runs first `wiki_ingest`, and then — and only then — gets the doctor WARN about swap-thrashing. Sunk-cost disappointment; they've already committed the bandwidth, disk, and attention.

**Where the fix lands:**

1. **OQ #3 (spec lines 1946–1950)** publishes two defaults as a design decision: `qwen2.5:7b` at 32 GB+; `qwen2.5:3b` at 16 GB. This is a *spec-level* commitment, not a README-only nag.
2. **v0.3.0 README configuration table (CPO #21 + Infra #37 checklist line 863–866)** ships both defaults with the quality caveat ("Extraction quality is marginally lower than 7B; revisit the 7B default once you upgrade to 32 GB"). This is *pre-install* information — the adopter sees it in the README while deciding whether to try the tool at all.
3. **Doctor step 6b** emits WARN *before* the first ingest; the check runs at `doctor` time, which is the first command after install per the README prerequisites. This catches the adopter who didn't read the README (or who read it, went with the 7B default anyway, and should be reminded).
4. **WARN message anchors to the README table by anchor**, not a hardcoded model name — so if the maintainer swaps the 16 GB default in a patch release, only the README table needs editing, not the doctor code.

**Does this prevent the disappointment?** For the README-reading adopter: yes — they see the two defaults before they run `ollama pull`. For the skimming adopter who runs `doctor` first: yes — step 6b fires before they pull. For the adopter who pulls first, *then* runs `doctor` or `wiki_ingest`: the 4.7 GB is already on disk, but the doctor WARN gives them the fallback recommendation, and `ollama rm qwen2.5:7b` is a one-liner to reclaim the disk. The sunk bandwidth is unrecoverable, but the path to getting back to a working config is clear.

**Resource impact on the Mac Mini (reference hardware):** unchanged from R2 analysis. 32 GB budget:
- Anytype ~1 GB + Qdrant ~500 MB + Ollama bge-m3 (~2.2 GB) + qwen2.5:7b (~5 GB) + anytype-llm-wiki (~500 MB) = **~9.2 GB steady state during ingest**. Ample headroom.
- Plus Aldeia-IT's other co-resident services (PostgreSQL 18, Docker/Colima 2 GB, ntfy, Caddy, IronClaw, Claude Code workers): total shared-machine footprint around 14–16 GB, depending on concurrent workers. Still within the 32 GB envelope.
- **Steady-state delta vs v0.1.0: zero.** v0.2.0 is bootstrap-only; no LLM invocation. v0.3.0 adds ingest (which invokes Ollama models that already exist on disk from v0.1.0's EMBED_MODEL + any extraction model the operator pulls). No new launchd unit, no new Docker container, no Colima delta.

**Resource-envelope verdict: the two-defaults config is sufficient and the Mac Mini is not at risk.**

---

## Regressions (relative to R2-approved baseline)

I cross-checked my R2 positive endorsements against the R3 spec to ensure nothing I signed off on has regressed.

| R2 positive endorsement | R3 status | Evidence |
|---|---|---|
| fcntl.flock + closing-fd = releasing-lock design | **Preserved** | §Concurrent Ingest Policy lines 1572–1586 unchanged. Doctor step 9 hardens the non-NFS assumption with a statvfs probe rather than replacing the design. |
| Per-tool schema-compat entry check | **Preserved + improved** | §Schema Compatibility lines 1592–1598 still has the three-outcome logic. Lines 1599–1607 add the bootstrap exception — additive, not replacement. |
| Per-tool failure-modes table | **Preserved + extended** | Lines 1639–1645 original rows intact. Lines 1647–1658 extended with the partial token scope row (A38a) and the empty-wiki lint row (A38b). |
| Permissions 0o700 dir / 0o600 file | **Preserved** | Lines 1577, 1582 unchanged. |
| `WIKI_LOCK_DIR` override for NFS escape | **Preserved + surfaced** | Line 1585 unchanged. Doctor step 9 now surfaces it actively rather than passively. |
| Resource Impact table (32 GB / 16 GB / 8 GB) | **Preserved** | Lines 1617–1635 structurally identical. Two-defaults config added via OQ #3 + v0.3.0 README, not by editing this table. |
| No new launchd / Colima / Docker delta | **Preserved** | Spot-check: no new launchd/container references in R3. v0.2.0 Scope (in) adds docs/samples (filesystem only, no services). |
| Deferred Items lists `wiki.status` | **Preserved + extended** | Line 1982 unchanged. Line 1984 adds the runtime-metrics-surface paragraph for A39. |

**No regressions.** Every R2 positive finding survives into R3.

---

## Recommendation

**Spec is operationally deployable. Advance to `test` per R3 synthesis.**

All 8 of my R2 advisories are addressed. The bootstrap exception is the most consequential fix and it holds up under deliberate deadlock probing. Doctor cognitive load at 11 checks is still below the threshold where operators disengage. The Mac Mini envelope is unchanged from v0.1.0 steady state; the 4.7 GB download-disappointment risk is addressed at the README layer where it actually prevents the miss, not only at the post-install WARN layer where it just explains the miss.

No new BLOCKING. No new ADVISORY. No regressions relative to R2.

**Sign-off: SIGN OFF (unconditional for infra-scope). Concurrence with R3 chair's APPROVED recommendation.**

---

## Relevant file paths

- `/Users/Shared/development/anytype-llm-wiki-worktrees/wiki-library-module-port-llm-wiki-pattern-onto-any/.aldeia/140-wiki-library-module-port-llm-wiki-pattern-onto-any/spec.md` — spec under review (2123 lines).
- `/Users/Shared/development/anytype-llm-wiki-worktrees/wiki-library-module-port-llm-wiki-pattern-onto-any/.aldeia/140-wiki-library-module-port-llm-wiki-pattern-onto-any/council-spec-r2-infra.md` — my R2 advisories (8 items).
- `/Users/Shared/development/anytype-llm-wiki-worktrees/wiki-library-module-port-llm-wiki-pattern-onto-any/.aldeia/140-wiki-library-module-port-llm-wiki-pattern-onto-any/review-r3.md` — R3 chair's delta-verification (APPROVED).
- `/Users/Shared/development/tasks/logs/140-wiki-library-module-port-llm-wiki-pattern-onto-any/debrief-fixer-r2.md` — R2 fixer traceability matrix.
