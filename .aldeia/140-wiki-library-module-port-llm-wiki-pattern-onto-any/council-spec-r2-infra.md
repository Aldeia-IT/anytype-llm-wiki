# Council Meeting — Post-spec (Round 2, Calibration) — Infrastructure Lead

**Date:** 2026-04-22
**Ticket:** #140 — Wiki Library Module: Port LLM Wiki Pattern onto Anytype
**Phase reviewed:** spec
**Reviewer:** Infrastructure Lead (council)
**Review mode:** Independent re-review after R1 architectural-defect calibration run on #172

---

## Verdict

**SIGN OFF WITH CONDITIONS.**

Spec is operationally deployable for the v0.2.0 shippable slice. The concurrent-ingest redesign (kernel-held `fcntl.flock`), the per-tool schema-compat entry check, and the per-tool failure-modes table are all materially stronger than what I would expect from a pre-impl artifact. None of the issues I found rise to BLOCKING on an infrastructure basis. Conditions are documentation / small-behaviour gaps — the spec should carry most of them inline before impl phase begins.

Three conditions I consider non-waivable before impl begins (see A1, A2, A5 below).

---

## Summary (Independent view, formed before reading R1 Infra)

Operational posture is good. The fcntl.flock design is textbook — closing-the-fd = releasing-the-lock removes an entire class of stale-detection hazards and the LOCK_NB path is semantically correct on both APFS and ext4/xfs/btrfs. Permissions (0o700 dir / 0o600 file) are correctly restrictive. `WIKI_LOCK_DIR` override documents the NFS escape hatch honestly.

The Resource Impact table is the most significant change vs the naive version of this spec — it concedes that 8 GB is not supported, it names the bge-m3 + qwen2.5:7b co-residence cost, and it offers the qwen2.5:3b fallback for 16 GB. The per-tool failure-modes table covers every realistic local-dep outage plus reindex-failure as a warning (not error), SIGKILL mid-ingest, disk-full, `patch-decision.md` corrupted, Anytype version drift, and empty-source.

The schema-compat entry check with missing/older/newer outcomes and MIGRATIONS.md is textbook — newer-client downgrade-to-warn is the right call for a single-operator OSS tool where older clients pinging a newer-schema space should not hard-fail.

Deployment risk on the Mac Mini: none beyond what v0.1.0 already paid for. No new launchd unit, no new Docker container, no Colima impact. The 500 MB RSS budget per tool is rounding error at 32 GB.

What I found on probing that the spec either skips or gets slightly wrong:

1. **Schema-upgrade path for `wiki_bootstrap` itself is ambiguous.** §Schema Compatibility says every tool entry runs a compat check; but `wiki_bootstrap` is also one of those tools, AND the thing that records the schema version. When v0.4.0's bootstrap runs against a space already carrying `wiki_schema_version = "0.3.0"`, the entry-compat check reads v0.3.0, code is v0.4.0, the outdated branch fires — but that branch's error tells the operator to "re-run wiki_bootstrap," which is exactly what they ARE running. This is a loop. Bootstrap specifically should either (a) skip the compat-check entry gate and handle the upgrade inline, or (b) the "outdated" branch needs to distinguish `tool == wiki_bootstrap` and proceed through idempotent upgrade rather than short-circuiting with an error. Spec does not address this.
2. **macOS path convention.** Defaults are Linux-XDG (`~/.local/share/anytype-llm-wiki/`) on both platforms. The spec even notes that Anytype itself uses `~/Library/Application Support/Anytype2` on macOS. This is a contributor friction point but is also consistent with what `uv tool install` lands on macOS today. Not worth changing.
3. **Doctor coverage.** 8 checks is fine for a preflight. Not worth adding Python-version (pip metadata enforces `requires-python >= 3.11` already), but `statfs(WIKI_LOCK_DIR)` NFS-type probe and a disk-free check on `INDEX_STATE_DIR` would close two realistic community issues. R1 already called the NFS one.
4. **Dependency footprint.** No optional-extras split; `pip install anytype-llm-wiki` on v0.3.0 gets everyone markdownify and pydantic v2. Manageable (both are small, both already widely installed in Python environments) but the spec does not justify the monolithic install vs a `[wiki]` extra. Acceptable because the pipeline already rests on fastmcp/httpx/qdrant-client — splitting wiki into an extra creates more release-discipline burden than it solves.
5. **Doctor is not CI-runnable.** No `--ci-mode` flag. This is actually the right call because most of doctor's value is in the Anytype/Qdrant/Ollama reachability checks — a CI invocation that skips all of those is not worth having. Worth one line in the CLI help text.
6. **Resource impact at 8 GB.** Spec correctly marks 8 GB as "not supported" and emits a WARN (not FAIL) at doctor time. Honest. Would not recommend tightening to a FAIL; the warn-and-continue semantic respects operator autonomy.
7. **Log rotation recipe is one-line prose, not a shipped config.** `logrotate -p 10M` is a Linux convention; macOS needs `newsyslog.conf` (system-wide, typically root-only) or a per-user `launchd` script. The spec's single sentence lumps both together. A community macOS operator who follows that line literally cannot edit `/etc/newsyslog.conf` without sudo and will file an issue. Low-cost fix: ship `docs/samples/anytype-llm-wiki.logrotate` and `docs/samples/anytype-llm-wiki-newsyslog.conf` as reference configs, referenced from the README.
8. **Observability: events only, no runtime metrics.** No aggregated last-N-ingest-durations or rolling-error-rate surface. For a solo operator this is fine; `wiki_status` is deferred and `wiki_lint` with severity_threshold acts as the daily-health surrogate. Acceptable for v0.2.0–v0.5.0; worth naming in Deferred Items if not already there.

---

## Independent Findings

### BLOCKING

None.

### ADVISORY (infra-scope)

**A1. Bootstrap-specific schema-compat path is ambiguous and can deadlock the upgrade UX.** §1429-1434: the entry-time compat check fires on *every* `wiki_*` tool. `wiki_bootstrap` is in that set. When a v0.4.0 client runs bootstrap against a v0.3.0-schema space, the check sees `found=0.3.0 expected=0.4.0`, fires the "outdated" error, and tells the operator to "re-run wiki_bootstrap" — which is literally what they are doing. The spec needs one of:
- Add a sentence under §Schema Compatibility that reads: "For `wiki_bootstrap`, the outdated branch is informational — bootstrap proceeds with idempotent upgrade (add missing properties, update `wiki_schema_version` on the root Collection on success) rather than raising `[CONFIG ERROR]`."
- Or: call out that the entry-time compat check is skipped for `wiki_bootstrap`, with the version-update logic encapsulated in the bootstrap tool itself.

Either is fine; picking one is not. This is a spec-polish fix, not an impl-phase decision. **Recommend land inline before impl begins.**

**Operational impact:** medium. Without this fix, the first operator who runs v0.4.0's bootstrap on a live v0.3.0 wiki gets an error telling them to do exactly what they just did. README troubleshooting would have to paper over it.

**A2. Doctor should STATFS-probe `WIKI_LOCK_DIR` and WARN on NFS/SMB/sshfs/CIFS.** `fcntl.flock` on network filesystems silently non-serializes. A community operator whose `$HOME` is on Synology / TrueNAS / WSL mount gets no lock collision and no observable failure — until two simultaneous ingests corrupt each other. The fix is ~10 lines of `os.statvfs` + `f_fstypename` (Darwin) / `/proc/self/mounts` (Linux) parsing. Elevate to a 9th doctor check, WARN (exit 2), not FAIL. R1 Infra also flagged this (their Adv #1) — I concur independently.

**Operational impact:** high for affected operators (silent lock loss); zero for the default-install case.

**A3. 16 GB model-swap warning at doctor time.** §1459: spec concedes 16 GB is marginal and recommends qwen2.5:3b. Nothing enforces or surfaces this at doctor time — an operator on 16 GB who set the default `WIKI_EXTRACT_MODEL=qwen2.5:7b` gets no warning until ingest #1 thrashes swap. Doctor should detect `psutil.virtual_memory().total < 20 GB AND WIKI_EXTRACT_MODEL.name matches /:(\\d+)b/ AND \\1 >= 7` → WARN with the 3b fallback suggestion. R1 Infra Adv #2 identified this; I concur and add that the WARN is cheap — don't wait until v0.4.0 to land it.

**Operational impact:** medium. Users on 16 GB hit swap and blame the tool; the warning short-circuits the support load.

**A4. Shipped sample log-rotation configs, not a prose one-liner.** §1367: "friendly to `logrotate` / `newsyslog` (`-p 10M`)." This conflates two OS-specific formats. Ship two small samples under `docs/samples/`:
- `docs/samples/anytype-llm-wiki.logrotate` (Linux, drop into `/etc/logrotate.d/` or user-space rotation).
- `docs/samples/anytype-llm-wiki-newsyslog.conf.fragment` (macOS, typically appended by maintainer-local launchd wrapper, since `/etc/newsyslog.conf` is root-only).

README "Logging" section points at both. Low effort; eliminates the "how do I rotate this log" GitHub issue.

**Operational impact:** low. Community UX polish.

**A5. Qdrant collection existence vs readyz.** Doctor step 4 checks Qdrant `/readyz`. That verifies the daemon is up, not that `$QDRANT_COLLECTION` exists. First `wiki_ingest` on a fresh install hits the collection-missing branch — `reindex_anytype` in v0.1.0 presumably creates the collection on demand (worth verifying against v0.1.0 code during impl), but if there is any path where `wiki_ingest` runs before the collection is created, the error surface is Qdrant's "collection not found" rather than a friendly doctor check. Add step 4b: `client.get_collection(QDRANT_COLLECTION)` → INFO if exists, WARN (not FAIL) if not, naming `reindex_anytype` or the equivalent collection-creation path.

**Operational impact:** medium. Likely covered by v0.1.0 behaviour but not verified in the spec.

**A6. Failure modes table — two gaps.**
- **Partial token scope:** §709 + §1641 handle the "token cannot create Types at all" case. Not covered: the "token can create Types but not Objects" or "can create Objects but not Properties" case — if Anytype's API permits granular scopes at all (spec does not say). Worth one row in the failure table: `Partial Anytype token scope (can create types but not objects, or vice versa)` → `[CONFIG ERROR] insufficient_token_scope` with a pointer to Settings → API, WikiLog written iff the WikiLog type itself is writable.
- **Bootstrapped wiki with zero objects, `wiki_lint` invocation:** §Empty types reported at Informational in AC v0.5.0 #7, but the composite case (bootstrap ran, no ingest yet, operator runs lint) is not called out. Most likely works fine (8 empty-type findings at Informational + zero others). Add one line to the failure table or in AC v0.5.0 clarifying: "lint on a bootstrapped-but-empty wiki returns 6 empty-type findings (one per bootstrap type) and exits `status: ok`."

**Operational impact:** low. Both are edge cases; the spec does not visibly handle them but neither is likely to produce bad behaviour.

**A7. Observability — no aggregate or rolling metrics surface.** Events only. For v0.2.0–v0.5.0 this is correct; aggregated metrics (last-N ingest durations, rolling error rate) are `wiki_status` / watchdog territory and correctly deferred. I am flagging this only so the spec's Deferred Items explicitly lists "runtime metrics surface (rolling error rate, duration percentiles)" as deferred. Currently Deferred Items mentions `wiki.status` but not the metrics subset. One sentence addition.

**Operational impact:** nil. Pure documentation.

**A8. `uv tool install` vs `pip install` path conventions.** Spec uses `~/.local/share/anytype-llm-wiki/` across both platforms. `uv tool install` on macOS also uses `~/.local/share/` by default (since `uv` is XDG-compliant), so this is actually consistent with where the tool's *other* data lands on macOS. Overriding to `~/Library/Application Support/` would create a conflict with uv's conventions. **Keep as-is.** I flag it only because R1 and R2 both will likely ask.

---

## R1 Delta (after reading the R1 Infra assessment at council-spec-r1.md lines 93-106)

**Agreements with R1 Infra:**
- fcntl.flock adoption eliminates PID-reuse race / TOCTOU-on-stale-replace / SIGKILL-mid-write in one primitive. I concur.
- Schema migrations are properly designed — entry-time compat check, three outcomes, MIGRATIONS.md policy, newer-schema-downgrades-to-warn. I concur.
- Failure-modes table covers every realistic operational edge. I concur, except I identified two small gaps (A6).
- Mac Mini deployment risk is low. Additive code; no launchd/container/Colima delta. I concur.
- Cascading-failure blast radius is zero. Individual tool errors don't spill. I concur.

**R1 Infra's Advisories 1 and 2 (NFS doctor check; 16 GB model-swap warning):** both are real concerns. I restated both independently (as my A2 and A3) before reading R1 — which is a good calibration signal. Both should land before impl begins; neither is BLOCKING.

**R1 Infra's Advisory 3 (Qdrant growth re-validation at v0.3.0 pre-release):** reasonable but I would not flag it; the 50 MB / 100 sources estimate is obviously rough in the spec (§1372: "rough estimate"). Calling for empirical validation at v0.3.0 is procedural, not a substantive gap.

**R1 Infra's Advisory 4 (lint 60s benchmarks implicit in AC):** agree but not strongly — the AC v0.5.0 #6 literally cites "Jan's Mac Mini M4 (p95 over 3 runs)." It's as explicit as a single-maintainer OSS project gets.

**R1 Infra's Advisory 5 (README prerequisites block):** reasonable CPO/UX territory; not operational.

**R1 Infra's Advisory 6 (verification-script-not-CI):** already in spec §1295. R1 Infra recorded it as endorsement rather than a gap. Fine.

**R1 Infra's Advisory 7 (all-perf-gates-on-Jan's-hardware is honest):** agree. Already covered by QA's Advisory #8 which consolidates the reference-hardware point.

**R1 Infra's Advisory 8 (dependency chain realistic for solo maintainer):** endorsement, not a gap.

**R1 Infra items I consider MISSED:**
1. **Bootstrap-specific schema-compat ambiguity (A1 above).** R1 Infra accepted the schema-compat design at face value. The entry-check-applies-to-every-tool-including-bootstrap loop is a real gap and I do not see it addressed anywhere in R1. This is the only substantive item a real specialist should have caught that R1 missed.
2. **Qdrant collection-existence check in doctor (A5 above).** R1 Infra noted readyz coverage but did not probe whether the collection itself is verified. Likely benign but worth catching at spec time.
3. **Sample log-rotation configs (A4 above).** R1 Infra flagged `logrotate` vs `newsyslog` at §1367 by accepting the one-liner. Shipping the actual sample configs is more actionable.
4. **Partial Anytype token scope (A6 first bullet).** R1 Infra did not probe this edge. Spec only handles the binary "can/cannot create Types" case.

**R1 Infra items I considered but agreed with R1's disposition:**
- macOS vs Linux path divergence: R1 did not flag (consistent with my A8 disposition).
- CI runnability of doctor: R1 correctly did not flag; doctor's value is in local checks.
- Dependency footprint / optional extras: R1 correctly did not flag; a single-package install is correct for a solo-maintainer OSS project.

---

## Calibration Verdict on R1

**R1 Infra assessment quality: STRONG.**

The R1 Infra assessment (council-spec-r1.md §93-106) reads as if it came from a real operational reviewer, not a general-purpose impersonator. Evidence:
- Accurately names the three failure classes collapsed by fcntl.flock (PID-reuse race, TOCTOU-on-stale-replace, SIGKILL-mid-write). An impersonator would list generic categories.
- Correctly situates the schema-compat design ("newer-schema client correctly downgrades to warn-and-continue rather than hard-fail — right call for a single-operator tool"). This is a judgement call with operational context.
- Advisory #1 (statfs NFS check) and Advisory #2 (16 GB model-swap warning) are concrete, low-cost, high-value fixes. Both are the right findings.
- Honest about perf-gate reproducibility (Advisory #7).

**R1 Infra shortfall: minor.**

The bootstrap-specific schema-compat loop (my A1) is the one real operational gap R1 missed. It is a subtle spec-reading issue: one needs to notice that `wiki_bootstrap` is both in the enumerated set of "every wiki_* tool" AND is the recommended remediation for the outdated branch. I caught it by reading §1429-1434 with specific attention to the tool enumeration. An R1 impersonator would not have caught it — a real specialist should, and R1's did not, but this is a one-item miss in an otherwise strong review.

**Net: R1 Infra's verdict (SIGN OFF WITH CONDITIONS) stands.** My R2 verdict is the same. The conditions set expands by three substantive items (my A1, A5, A6) and two minor polish items (A4, A7).

---

## Conditions (for spec promotion / impl start)

Recommended land-before-impl:
- **A1 (bootstrap schema-compat clarification).** Add one sentence or refactor the compat-check applicability to avoid the `wiki_bootstrap` self-recursive-remediation loop.
- **A2 (statfs NFS probe in doctor).** Elevate to doctor step 9.
- **A5 (Qdrant collection existence check in doctor).** Elevate to doctor step 4b.

Recommended land-before-v0.3.0-release:
- **A3 (16 GB + 7B-model warning in doctor).** Ship with the doctor update that lands alongside WIKI_EXTRACT_MODEL variable.
- **A4 (sample log-rotation configs).** Ship under `docs/samples/`, referenced from README.

Optional/documentary:
- **A6 (failure-mode gaps: partial token scope, empty-wiki lint).** One row each in the failure table.
- **A7 (Deferred Items list metrics surface).** One sentence addition.
- **A8 (state-dir path convention).** No change; flagged for record.

---

## Sign-off

**SIGN OFF WITH CONDITIONS.** No dissent. Conditions are documentation / small-behaviour items; none are BLOCKING. The spec is operationally deployable; the Mac Mini will not notice this work vs v0.1.0 steady state. R1 Infra's verdict was earned; my R2 verdict matches, with three additional substantive conditions (A1, A2, A5) and two polish items (A3, A4). Impl phase can start in parallel with landing the conditions inline.
