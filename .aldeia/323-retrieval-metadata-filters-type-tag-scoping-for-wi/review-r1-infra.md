# Infra Review (R1) — Retrieval Metadata Filters / Type-Tag Scoping (#323)

**Reviewer:** Infrastructure Lead
**Date:** 2026-06-12
**Scope:** Operational readiness, migration/reindex safety, deployment/rollback, resource impact.
**Phase:** Spec-phase. No code exists yet; findings target the spec's operational design.

Platform: single-user / small-fleet anytype-llm-wiki on a 32GB Mac Mini. Qdrant (Docker v1.17.0),
Ollama (bge-m3), Anytype CLI (launchd). All localhost. Auto-reindex via launchd plist every 1800s.

---

## BLOCKING

### B1 — Incremental reindex will NOT populate the new payload fields on existing chunks; the documented migration is a no-op

**Spec ref:** §13, §15 (Deployment steps 2), §2 D2/D3, OD-1.

**Finding.** The migration story rests on "Run `reindex_anytype` to populate `source_type` and
`last_modified_date` on all existing chunks." But `reindex()` is **incremental**, not a forced full
rebuild. At `indexer.py:134-136`:

```python
last_mod = _get_last_modified(obj_summary) or "unknown"
if space_state.get(oid) == last_mod:
    continue  # unchanged
```

Every object whose `last_modified_date` is unchanged since the last index pass is **skipped** — its
chunks are never re-fetched, re-chunked, or re-upserted. After upgrading the package and running
`reindex`, the vast majority of existing objects are unchanged, so their chunks keep the old 6-field
payload **indefinitely**. The new `source_type` / `last_modified_date` fields are only written for
objects that happen to be edited after the upgrade.

This means the spec's central operational claim ("a one-time reindex populates the field for existing
objects") is **false as written**. The filters will silently under-return against the historical corpus
for an unbounded period — exactly the "footgun" the spec rejects for `domain_tags` in D4, reintroduced
through the back door for `source_type`/date.

**Operational impact.** Filtered queries (`source_type=...`, `ingested_after/before`) return partial or
zero results for old content, with no error and no signal to the operator. A user filtering "sources
since January" gets only objects modified post-upgrade. This is a correctness regression masquerading as
a working feature, and it is hard to diagnose because each individual code path looks correct.

**Recommended fix.** The spec MUST specify a forced/full repopulation path and document it as the
migration step. Concrete options (pick one, document it):
1. Add a `force: bool = False` parameter to `reindex` that bypasses the `space_state` skip check
   (re-chunks and re-upserts every object regardless of `last_modified_date`), and make the migration
   step `reindex(force=True)` (or a new `reindex_anytype --force` MCP/CLI surface). Lowest-risk;
   re-embeds the whole corpus (~7s/500 chunks per §13 — acceptable on this box).
2. Clear the index state file (`~/.local/share/anytype-llm-wiki/state.json`) before the migration
   reindex so every object is treated as new. Cheaper to specify but easy to get wrong (operator must
   know the path; also leaves a window where a crash mid-reindex loses all state — see B2).
3. A schema-version marker in the state file: if the on-disk schema version is older than the code's,
   force a full pass once, then resume incremental. Most robust; self-healing on upgrade; recommended.

Whichever is chosen, §15 deployment step 2 must name the exact command, and §13 must re-baseline the
cost as a **full** re-embed of the corpus (every chunk, not just the changed delta).

---

## SHOULD-FIX

### S1 — Stale-window query degradation between deploy and (real) full reindex is undocumented

**Spec ref:** §15 Release note, §2 D2.

**Finding.** Even once B1 is fixed with a forced reindex, there is a window between "package upgraded /
service restarted" and "full reindex complete" during which queries hit a collection with mixed-schema
chunks (some with the new fields, some without). Qdrant treats a missing field as non-matching for
equality and range conditions, so filtered queries in this window silently under-return. The spec
asserts this is "correct behavior" (D2) but never states it is a **transient operational degradation the
operator must expect**, nor how long the window lasts, nor that unfiltered queries are unaffected.

**Operational impact.** During the reindex window (seconds-to-minutes on this corpus, but unbounded if
B1 is left unfixed), filtered retrieval quality silently drops. Acceptable as a brief transient; not
acceptable as undocumented behavior.

**Recommended fix.** Expand the required release note to state explicitly: (a) filtered queries
under-return until the forced reindex completes; (b) unfiltered `semantic_search` / `wiki_query` are
unaffected; (c) the reindex should be run immediately after upgrade and before relying on the new
filters. One sentence each.

### S2 — Auto-reindex launchd job will not self-heal the payload, and may mask B1

**Spec ref:** §13, §15; `docs/samples/com.aldeia.anytype-llm-wiki-reindex.plist:34`.

**Finding.** The scheduled job runs `reindex()` (plain incremental, no force) every 1800s
(`StartInterval` 1800, `RunAtLoad` true). Because of the incremental skip (B1), the scheduled job will
**never** backfill the new fields onto unchanged objects — it only ever touches objects modified since
the last run. So an operator who upgrades and assumes "the 30-minute cron will sort it out" gets a
permanently half-populated index. If option 3 (schema-version marker) from B1 is adopted, the scheduled
job auto-heals on the first post-upgrade run, which is the desired behavior and another reason to prefer
option 3.

**Operational impact.** Silent, persistent under-population of the filter fields in the steady-state
deployment; the most likely real-world failure because the operator does nothing special.

**Recommended fix.** Tie this to B1's resolution. If the forced reindex is operator-driven (options 1/2),
§15 must state the scheduled job does NOT perform the migration and the operator must run the forced
reindex manually once. If option 3 is chosen, state that the next scheduled run auto-heals and no manual
step is needed (strongly preferred operationally).

### S3 — `reembed_object` payload extension is specified, but its consistency obligation with `reindex` should be made an explicit acceptance gate

**Spec ref:** §7.4, Step 4.

**Finding.** `reembed_object` (the V2-fail bypass / single-object update path at `indexer.py:191-231`)
duplicates the `PointStruct` payload dict verbatim from `reindex`. The spec correctly says both must gain
the new fields (§7.4 names both). The risk is purely drift: two hand-maintained copies of the same
payload dict. If only one is updated, single-object updates (the hot path for live edits) write the new
fields while bulk reindex does not, or vice versa — producing exactly the mixed-schema inconsistency
that breaks filters. There is no test in §10 asserting `reembed_object` writes the new fields.

**Operational impact.** A future edit to one path silently desyncs payload schema between bulk and
incremental updates; hard to catch without a test.

**Recommended fix.** (a) Add an AC/test asserting `reembed_object` writes `source_type` /
`last_modified_date` to the upserted `PointStruct` (mirror AC-F8). (b) Consider factoring the payload-dict
construction into one shared helper (`_chunk_to_payload(chunk)`) used by both `reindex` and
`reembed_object`, eliminating the drift class entirely. The helper is a trivial refactor and removes a
whole category of operational bug.

### S4 — In-memory Qdrant `create_payload_index` UserWarning: CI handling is hand-waved

**Spec ref:** §6.3 comment, §10.1 fake (`create_payload_index` no-op), research Q2 / Open Assumption 3.

**Finding.** The spec notes in-memory Qdrant emits a `UserWarning` that payload indexes have no effect,
and says to "suppress or monkeypatch." The unit-test fake no-ops `create_payload_index`, so the fake path
is fine. But `_ensure_collection` is also exercised by live tests (`TestEnsureCollection` per research
Q2) and any test that constructs a real in-memory client will emit the warning on every
reindex/reembed/ensure call. If CI runs with `-W error` (warnings-as-errors), this turns into spurious
test failures across the whole indexer test surface.

**Operational impact.** CI flakiness / false failures, or noisy warning spam that desensitizes reviewers
to real warnings. Not a production risk, but a release-pipeline risk.

**Recommended fix.** Specify the handling concretely: either a `pytest.ini`/`pyproject` filterwarnings
entry ignoring the specific Qdrant payload-index `UserWarning`, or wrap the index-creation loop in
`warnings.catch_warnings()` in `_ensure_collection` is NOT advised (would hide it in prod too). Prefer the
test-config filter so production still surfaces the warning. State the chosen mechanism in §10.

### S5 — DATETIME index over a field absent on most points: confirm build does not error and is genuinely cheap

**Spec ref:** §6.3, §13 ("sub-second index build").

**Finding.** `create_payload_index("last_modified_date", DATETIME)` is created unconditionally on every
`_ensure_collection`. After B1's forced reindex, `last_modified_date` is present on all chunks (it's a
universal field), so this is fine. But the index is created BEFORE/independent of the data being
populated, and in the pre-migration state (and during the stale window) the field is absent on most
points. The spec asserts "sub-second" and "no impact" but cites only the general research note, not a
benchmark against a populated collection with the field missing on a majority of points. Qdrant tolerates
indexed fields being absent on points (they're simply not in the index), so this is very likely fine, but
the claim is asserted, not verified.

**Operational impact.** Low. Worst case is a slightly slower-than-claimed first index build; no
correctness risk. Flagging because §13's "sub-second / no impact" is stated as fact without measurement.

**Recommended fix.** Downgrade the §13 wording to "expected sub-second on this corpus (hundreds of
objects); not separately benchmarked" OR add a one-line note that index build over points missing the
field is a no-op-per-missing-point in Qdrant. Either makes the claim honest. No blocker.

---

## SUGGESTION

### G1 — No rollback procedure for the payload extension

**Spec ref:** §15 Failure modes.

The spec lists forward failure modes (Qdrant down, bad date, missing collection) but has no rollback
story. Because the extension is purely additive (extra payload keys, extra indexes), rollback is in fact
trivial and safe: reverting the package leaves the extra payload fields and indexes harmlessly in place
(old code ignores them; Qdrant ignores unused indexes). Worth one sentence in §15 stating this:
"Rollback: revert the package; the extra payload fields and indexes are inert under the prior version and
require no cleanup." This converts an unstated risk into a documented non-event.

### G2 — Resource impact: re-baseline §13 for a FULL re-embed, and note Ollama contention

**Spec ref:** §13.

§13's ~7s/500-chunk figure is the projected **full** index from technical.md (2026-04-01 benchmark), so
it already corresponds to a full pass — good, that number survives the B1 fix. But §13 currently frames
it as the cost of an *incremental* reindex; once B1 forces a full re-embed, every chunk goes through
Ollama/bge-m3 again. On the shared Mac Mini, this briefly saturates Ollama (the embedding hot path) and
competes with any concurrent Claude Code worker also hitting Ollama. The corpus is small so this is
seconds, not minutes — negligible — but §13 should say the migration re-embeds the entire corpus through
Ollama once, so the operator schedules it when the box is not under other load. Memory/disk impact of two
extra short payload fields and two extra indexes is genuinely negligible (a few bytes/chunk; KEYWORD +
DATETIME indexes on hundreds of objects). No concern there.

### G3 — Watchdog/alerting: no new service, so no new watchdog needed — state it

No new long-running service, port, or daemon is introduced; the feature lives inside the existing MCP
server and the existing reindex job. So no new watchdog check or ntfy alert is warranted, and existing
log rotation (`docs/samples/anytype-llm-wiki.logrotate`, `*-newsyslog.conf.fragment`) already covers the
reindex log the migration will write to. Worth one line in §15 affirming "no new service / no new
monitoring surface" so the council and operator don't go looking for one.

---

## Cross-domain note (for CSO)

No new network exposure, port, auth surface, or egress is introduced (§1.3, §14 are consistent with this
— all filter evaluation is local in Qdrant). Nothing in my review contradicts the CSO's domain; the
input-validation boundary (§9, malformed dates rejected before reaching Qdrant) is operationally sound
and also a security positive.

---

## Verdict

**VETO (conditional) — BLOCKING on B1.** Do not sign off until the spec specifies a forced/full
repopulation path (preferably a schema-version marker that auto-heals on upgrade); as written, the
documented one-time reindex is a no-op against the existing corpus and the filters silently under-return.
S1–S5 are required clean-up before implementation; resolving B1 via the schema-version option also
resolves S2. Once B1 is fixed and S1–S5 addressed, this is a low-risk, additive, locally-scoped change I
would sign off on.
