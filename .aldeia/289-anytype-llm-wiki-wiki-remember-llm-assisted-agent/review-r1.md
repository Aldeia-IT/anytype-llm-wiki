# Specification Review: `wiki_remember` — LLM-Assisted Agent Memory Write (#289)

**Reviewed:** 2026-06-04
**Spec version:** commit 9ae48c3 (status SPEC, review round 1)
**Reviewers:** Security (CSO), Architecture (CTO), Completeness/QA, Infrastructure/Ops — independent specialist lenses, consolidated by the spec lead.
**Verdict:** **NEEDS REVISION**

Three of four specialist lenses returned a conditional VETO; Infra returned a conditional sign-off. The architecture is sound and the ~80% reuse claim was **verified accurate against the actual `ingest.py`/`extraction.py`/`bootstrap.py`/`types_schema.py` code**. The blockers are completeness/correctness gaps and two code-grounded scope omissions — all correctable without redesign. Per phase policy, **every finding below (BLOCKING, SHOULD-FIX, SUGGESTION) must be addressed** in the revision; deferral is allowed only where fixing would introduce a new problem or is genuinely out of scope, with a concrete documented rationale.

Lead verification spot-checks (independent of reviewers):
- **QA-B6 confirmed** — `ingest.py:256` hardcodes `name=f"ingest {subject}"`; `_write_wikilog` has no name/action param.
- **ARCH-B1 confirmed** — `_ensure_wiki_action_tags(client, space_id, prop_map, result)` consumes `prop_map`, which carries the key-as-id fallback at `bootstrap.py:314-318`. A write-time independent `list_properties` lookup (spec D6) would return `None` for inline select properties on a fresh space → silent zero-tag seeding.
- **SEC-B1 confirmed** — `extract()` runs every LLM result through `filter_extraction_output` (`extraction.py:208-228`); a new `consolidate()` writing `consolidated_text` verbatim bypasses that gate.

---

## BLOCKING (must fix before advancing)

**B1 [Security] — Consolidation output is unsanitized and the `action` enum is unvalidated.**
`consolidated_text` is written verbatim to `wiki_facts`/`wiki_definition` (D2), but unlike `extract()` (which gates output through `filter_extraction_output`, `extraction.py:208`), the consolidation path has no output sanitization. Fix: state that `consolidated_text` is passed through `sanitize_property_value` (strip control/bidi/tag codepoints) **on write**, and that `fact_actions[].action` is validated against the closed enum `{merge,add,supersede,keep,conflict}` before any status/WikiLog decision is derived from it (drop/ignore unknown values). Add an AC asserting the `update_object` payload `wiki_facts` text == `sanitize_property_value(consolidated_text)`.

**B2 [Security/Infra] — `knowledge` is unbounded into the local LLM (DoS / OOM on the 32GB box).**
No length gate exists on `knowledge` before it reaches `extract()`/`consolidate()`; §13.4 defers OOM recovery. Fix: specify a hard input cap on `knowledge` (defined byte/char limit) enforced on the `wiki_remember` entry path **before** lock acquisition and any LLM call, returning `[DATA ERROR] knowledge_too_large`. Add an AC + test. (Coordinate with B8 — both are entry-path input validation.)

**B3 [Architecture] — Bootstrap tag-seeding helpers must consume `prop_map`, not do an independent property lookup.**
`_ensure_wiki_status_tags`/`_ensure_wiki_source_type_tags` (D5) must take and use the `prop_map` passed by `_run_bootstrap` (carrying the key-as-id fallback, `bootstrap.py:314-318`), exactly like `_ensure_wiki_action_tags` (`bootstrap.py:527`). The spec's D6 write-time pattern ("`list_properties` → get prop_id") is correct for the **runtime resolver** in `remember.py` but MUST NOT be the **bootstrap seeding** mechanism — on a fresh space inline select-property ids are unresolved via `list_properties` and seeding would silently no-op, breaking AC-R20/R21 and the entire conflict-flag/source-type story on the common path. Resolve the D5↔D6 contradiction explicitly: bootstrap seeds via `prop_map`; `remember.py` resolves at runtime via the two-step lookup.

**B4 [Architecture/Completeness] — `_create_remember_source` source_type selector is specified three contradictory ways (D7 ↔ §6.1 ↔ "Spec-writer call").**
Pick ONE rule. Recommended: non-None `source` containing case-insensitive "conversation" → `conversation` tag; otherwise → `agent`. Delete the `kind`-based and "parameter semantics" language. Specify call order: resolve the source_type tag id first, pass it into `_create_remember_source`. Ensure AC-R13 fixes both branches.

**B5 [Architecture] — D9 `subject_hint` empty-extraction fallback drops an explicit `kind="concept"`.**
The fallback hardcodes `wiki_entity`/`wiki_facts`, so a caller passing `kind="concept"` + a hint with no extractable subjects silently gets a `wiki_entity` — contradicting the §6.3 signature. Fix: the hint fallback honors `kind` (`concept` → `wiki_concept`/`wiki_definition`), defaulting to entity only when `kind` is also None. Cover the concept branch in the fallback test.

**B6 [Completeness] — `_write_wikilog` cannot produce a `remember`-named WikiLog without a signature change that is unscoped.**
Verified: `ingest.py:256` hardcodes `name=f"ingest {subject}"`, no name/action param. §11.4 requires `f"remember {subject[:50]}"`. Fix: add `action_name: str = "ingest"` to `_write_wikilog` (default preserves ingest naming) used as `name=f"{action_name} {subject}"`; add this change to §3 scope + §11.1 modified-files + an ordered impl step; add a regression note/AC that existing `wiki_ingest` WikiLog-name behavior is preserved, and an AC asserting the remember WikiLog name prefix.

**B7 [Completeness] — The core "converges to no-op" guarantee (AC-R6) is only verified on the skip-gated live path.**
The two tests mapped to AC-R6 exercise the *gate* against a fixtured `changed=False`/normalized-equal result — they don't drive `wiki_remember` twice. Fix: add a CI test that calls `wiki_remember` twice with identical `knowledge` (mocked LLM returning the same `consolidated_text` on both calls; mocked client retaining created-object state across calls) and asserts call-2 `action="consolidated"`, **no** `update_object` on call 2, and a stable `object_id`. Name it explicitly in the §10.2 AC-R6 row. This is the tool's central correctness property; it must be CI-verified, not live-only.

**B8 [Completeness] — Empty/whitespace `knowledge` has no specified behavior.**
Goes straight to lock + LLM + Source creation. Fix: validate empty/whitespace `knowledge` on entry **before** lock acquisition and any LLM/Anytype call → `[CONFIG ERROR] empty_knowledge` (or `[DATA ERROR]`). Add AC + test. (Fold into the B2 entry-validation block.)

**B9 [Completeness] — Multi-candidate resolution is undefined (silent wrong-object corruption risk).**
The ticket explicitly names "a subject that resolves to multiple candidates," but the spec covers only wrong-type exclusion (AC-R9). When `client.search` returns several same-name, same-type objects, target selection is undefined — the highest-stakes silent failure for a memory writer. Fix: pin the tie-break rule (reference `resolve_entity`'s documented exact-normalized-title-first semantics; if >1 exact same-type match, emit an `ambiguous_subject` warning and skip the update rather than guess). Add AC + test.

---

## SHOULD-FIX

**SF1 [QA-A1] — Conflict × converged precedence.** Define that conflict-flagging (set `wiki_status=needs-review` if not already set, record in WikiLog, `conflicts_flagged=N`) runs **regardless** of the normalized-equal PATCH-skip gate (the `wiki_facts` PATCH may still be skipped, but the status-flag write is attempted). Reconcile the §6.2 flowchart (move the conflict check above the normalize gate). Add a "re-assert an already-flagged conflict" test.

**SF2 [QA-A2] — `status="error"` semantics + `_error_remember_result` shape.** Define exactly when `status="error"` is set (precheck/abort failures) and the precise dict shape `_error_remember_result(message)` returns (status, `error`/`warnings` placement of the `[CONFIG ERROR]`/`[DATA ERROR]` string). Add to D3.

**SF3 [QA-A3] — `conflicts_flagged` counting unit.** State explicitly: per-object = `len(conflicts[])`; top-level = sum of per-object counts (total conflict pairs). Pin so AC-R5 and live AC-R24 agree.

**SF4 [Security S1] — Credential-scrub the `source` note.** Route `source` through `scrub_credentials` (`util.py`) in addition to `sanitize_property_value` + truncation before writing `wiki_excerpt` (the reference path scrubs URL provenance at `ingest.py:651`). Confirm the `space_ingest_lock` source_ref (which embeds `knowledge`) is scrubbed (the primitive already does this — note it, don't bypass).

**SF5 [Security S3] — Relations endpoint type safety.** Relation endpoint name→id resolution must reuse the same client-side `type.key` check so a same-name wrong-type object is never selected as a relation endpoint. Add an AC.

**SF6 [Infra R1/L1/F1/C1 + Arch S1] — Bound the consolidation-call fan-out.** Add an explicit `max_subjects` cap (e.g. 8–10) bounding the N sequential consolidation calls; surplus → `subject_cap_exceeded` warning + `status="partial"`. This bounds worst-case wall-clock latency and per-space lock-hold time (otherwise `N × WIKI_EXTRACT_TIMEOUT`, up to 600s each). Document that the lock is **shared with `wiki_ingest`** (`ingest-{space}.lock`), so a long remember blocks ingest on the same space and vice versa. Add the cap as an AC.

**SF7 [Infra R2] — Correct the §7 memory claim.** Disclose that the generation model (`WIKI_EXTRACT_MODEL`) and the `bge-m3` embedder may be co-resident during the auto-reindex phase. Steady-state is unchanged from v0.3.0 (same `_maybe_reindex` seam) — state that explicitly rather than claiming "negligible." Confirms the "no new resident generation model" constraint is met.

**SF8 [Infra D1] — Add an Upgrade/Migration subsection.** Steps: (1) deploy v0.3.1 code (schema bump + bootstrap changes ship atomically per D11); (2) run `wiki-bootstrap --space-id <id>` per existing space (idempotent, union-only — AC-R22); (3) `doctor` green (AC-R23, reframed per SF9). Note the clean additive rollback (union-only tags are harmless under reverted v0.3.0 code).

**SF9 [QA-B2] — AC-R23 (`doctor` green) is currently vacuous.** `doctor.py` has no schema/`wiki_remember` check, so the AC asserts absence of an error nothing produces. Reframe AC-R23 as a **regression guard**: "the existing `run_doctor()` returns green (no new ERROR) after a v0.3.1 bootstrap" and add `test_doctor_green_after_v031_bootstrap` to §10.6. (Do not add a new doctor schema check — that is #289 scope creep; the ticket's "doctor green" means the existing doctor still passes.)

**SF10 [QA-S3] — Orphan Source on total consolidation-degrade.** Source is created before resolve/consolidate; a total degrade leaves an orphan `wiki_source`. Specify the behavior: either accept the orphan as a documented residual, or (recommended) create the Source lazily only after at least one object is written. Reflect in D7 + AC-R17 assertions.

**SF11 [QA-S5 / Infra F2] — Partial-failure semantics across N subjects.** Specify: per-object write failures are caught and recorded in `objects[]` with an error marker (add `"error"` to the per-object action enum or an `error` key), processing continues for remaining subjects, WikiLog + reindex still run, top-level `status="partial"`. Add `test_one_subject_write_fails_others_succeed`. Note that a crash before the WikiLog step leaves objects with no audit record (recoverable via reindex) — one sentence in §13.4.

**SF12 [Arch S4] — New runtime resolvers mirror the degraded-tags-read quirk.** `_resolve_wiki_status_tag`/`_resolve_wiki_source_type_tag` should replicate `_resolve_wiki_action_tag`'s "attempt `list_tags` even with an unresolved prop_id" behavior (`ingest.py:222-223`) for degraded-path test symmetry.

**SF13 [Arch B5] — Correct the parent-spec provenance statement.** §1 describes #284 as "status SPEC"; its code is in fact merged (PRs #15/#16). Correct §1 to say the parent code is merged and the SPEC label on the parent doc is stale. Doc-only, no design change.

**SF14 [Arch S5 / QA deferred] — Note conflict-path provenance loss.** §13.2's `wiki_sources` overwrite-only write, combined with the conflict path, replaces the full source list with a single id precisely on contested entities. Acceptable to defer the GET-and-merge fix, but §13.2 must explicitly note the conflict-path interaction.

**SF15 [QA-S4] — Regression AC for the `_resolve_wiki_action_tag` generalization.** Add `test_resolve_action_tag_default_is_ingest` (call with no `action_name`, assert it resolves the `ingest` tag) to guard the shipped #284 path.

**SF16 [Arch S2 / Infra R3] — Reconcile the model name.** §7 names `qwen2.5:7b`/`qwen2.5:3b`; the ticket names `qwen3.5-mlx`; `config.py:18` defaults to `qwen2.5:7b`. State that the model is operator-configured via `WIKI_EXTRACT_MODEL` and align the example with `config.py`'s default; note the resolved model must be `ollama pull`-ed (AC-R14 covers the not-pulled abort).

---

## SUGGESTION (address or note rationale for deferral)

**G1 [Arch G2 / QA A5]** — Per-object `relations_created` (§13.5) waffles ("MAY be 0", "tests accept either"). Commit to populating it or drop the per-object field for v0.3.1; don't ship a field tests can't assert.
**G2 [Security S2]** — Document that the consent gate is a non-interactive notify-once self-ack (`extraction.py:261-265`), with the residual accepted under the single-operator model.
**G3 [QA S2]** — Reframe AC-R5's assertion to be honest about what the unit test proves: PATCH `wiki_facts` == consolidation `consolidated_text` verbatim + `wiki_status=needs-review` set; content-retention of both facts is the prompt's job (exercised by the live test, not the unit test).
**G4 [Security G1]** — Add a regression test that re-asserting a previously-conflicted entity does not spawn nested/duplicate `[CONFLICT: …]` markers.
**G5 [QA S6]** — State that relation endpoints are resolved only against this call's `name_to_id` for v0.3.1 (no extra live lookups); unresolved → warning. Note as a deferred enhancement.
**G6 [QA B5]** — The different-space non-blocking claim (§8.3) is inherited from #284; note "not re-tested here" rather than implying new coverage.
**G7 [Infra R4 / M1]** — Note that auto-reindex cost scales with total space size (not delta); document `WIKI_AUTO_REINDEX=false` + batched reindex as the high-frequency mitigation, and expected WikiLog object growth under sustained agent use.

---

## Inline lead checks (problem context / structure)
- Problem context: PASS — §2 clearly states the agent-memory gap and why LLM consolidation (not append) is the value; scope in/out is bounded; single-operator threat model named.
- Single-approach rule: PASS with exceptions — the structured fast-path is correctly Deferred (§13.1); but B4 (source_type) and B5 (kind fallback) present contradictory single-decision logic and must be collapsed to one path each.
- Diagrams: PASS — §6.1 pipeline + §6.2 consolidation-branch Mermaid present.
- AC↔test traceability: STRONG overall; gaps at B6, B7, B9, SF9, SF11, SF15.

## What's done well (preserve in revision)
- The dual-DATA anti-injection framing on `consolidate.md` (both new knowledge AND existing facts fenced as DATA) — a genuine strength; keep it.
- The never-silently-overwrite conflict invariant (AC-R5) and the two hard-gate ACs (AC-R-S1 consent-on-live-path, AC-R-S2 lock-on-entry-path) explicitly forbidding isolated-helper tests.
- The idempotency double-gate (LLM `changed` + normalized compare) — but reframe so the normalized compare is named the load-bearing guarantee and determinism merely reduces churn (Arch S3).
- The ~80% reuse design — verified accurate; no DRY objection to the `_call_ollama_prompt`/`consolidate` seam or the `_resolve_wiki_action_tag(action_name)` generalization (keep the default backward-compatible).
