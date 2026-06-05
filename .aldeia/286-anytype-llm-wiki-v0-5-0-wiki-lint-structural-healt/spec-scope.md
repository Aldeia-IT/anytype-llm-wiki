# Spec Scope: 286 — anytype-llm-wiki v0.5.0 (`wiki_lint`)

**Date:** 2026-06-05
**Repo:** anytype-llm-wiki
**Ticket:** #286 (Aldeia-IT/aldeia-box)
**Master spec:** `.aldeia/140-wiki-library-module-port-llm-wiki-pattern-onto-any/spec.md` (status SPEC, council-approved) — §"Lint Suite (wiki.lint — v0.5.0)" lines 519–607; canonical `type_key` values lines 230–284; relation property semantics lines 254–281; MCP conventions lines 609–618.
**Shipped dependencies (all merged):** v0.2.0 (schema/bootstrap), v0.3.0 `wiki_ingest` (#284 — objects + WikiLog failure cross-ref), v0.3.1 `wiki_remember` (#289), v0.4.0 `wiki_query` (#285 — per-run cache, `_qdrant()`, `semantic_search_core`), v0.4.1 schema rename (#303 — `Wiki …` display-name prefix).

## Nature of this spec

**INCREMENT spec**, not from-scratch. The master spec (#140) is the authoritative design baseline and already specifies `wiki.lint` (signature, LintReport schema, the 9-check table with severities, the data-flow diagram, the perf budget, OQ#7). **This spec does NOT re-derive that design.** It:

1. **References** the master spec for the bulk of the lint design (data-flow, signature, LintReport schema, check semantics, MCP conventions, deeplink format).
2. **Locks five deltas** discovered/shipped since the master spec was written (verified against the post-#303 codebase) — see "Deltas to LOCK" below.
3. **Grounds every helper and wire contract** against real function names in the post-#303 `wiki/` surface (no invented helpers).
4. **Firms** the v0.5.0 acceptance criteria into a single authoritative, testable list.

## Deltas to LOCK (the entire reason this increment spec exists)

### D1 — OQ#7 resolved in v0.5.0's favor: native `backlinks` is the PRIMARY orphan/asymmetric primitive
Master spec lines 595–606 treat native `Backlinks` as a deferred v0.6.x optimization and ship the O(N) reciprocal-traversal as the primary path. **This is now reversed.** Session findings (verified live 2026-06-03, `llm-wiki-test`): `get-object` returns a `backlinks` property auto-populated by inbound `wiki_relations`/`wiki_related`/`wiki_subjects`/`wiki_sources`. The spec MUST make `backlinks` the **primary** inbound-relation method (≈O(1) per object via the already-fetched object), and keep the O(N) reciprocal traversal only as an explicit **fallback** when `backlinks` is absent/empty in the API response. Do NOT leave both as co-equal paths — name backlinks primary, traversal fallback.

### D2 — "Stale stub" check is broken as written; replace the signal
Master spec line 599 keys the "Stale stub" check on `wiki_status == "stub"`. **There is no `stub` tag**: `bootstrap.py` `_WIKI_STATUS_TAGS` seeds only `needs-review` / `reviewed` / `archived` (verify in research). The check can never fire. **Resolution (spec must pick and justify, default = option B):**
- (A) seed a `stub` tag in bootstrap — schema change, MIGRATIONS/`WIKI_SCHEMA_VERSION` impact, heavier; OR
- (B) **re-target the check to a real signal**: `wiki_status == "needs-review"` aged `> N` days (the stale-needs-review check). Default to B (no schema bump). Rename the check `stale_needs_review` (Medium) and update the `check` enum accordingly, or keep `stale_stub` as the enum string with the new detection — research/spec to decide and pin one.

### D3 — New live HIGH signal: `needs-review` conflicts from `wiki_remember` (#289)
`wiki_remember` (shipped) already sets `wiki_status = needs-review` and returns `conflicts_flagged` when it detects an intra-entity conflict. Lint can surface this as a **real, populated High finding now** (distinct from D2's *staleness* angle — this is the *unreviewed-conflict* angle). The spec should add/define this check so v0.5.0 produces a genuine High finding on pipeline-produced wikis (not only passive). Confirm via research whether one `needs-review` check covers both D2 and D3 or whether they are two checks (age-based Medium vs conflict-flagged High).

### D4 — Reuse v0.4.0 (#285) infra; do not re-derive
Pin in the reuse map (verbatim names from `wiki/query.py` — confirm in research):
- per-run object-fetch **cache** (shared across all lint checks — orphan/asymmetric/stale/oversized read the same fetched objects);
- `_qdrant()` factory (Qdrant client);
- `semantic_search_core` (nested space-AND-(type-OR) filter) — directly reusable for the **potential-duplicates** sweep in the 0.70–upsert-threshold band.

### D5 — Schema is v0.4.1 (#303); read by KEY, pin wire contracts
Property **display names** are now prefixed `Wiki …`, but lint reads by **key** (`wiki_*`, unchanged) so logic is unaffected — state this explicitly so the spec targets the current schema. **Pin wire contracts** (the #285 C1 / #289 lesson — verb + path + the existing test mock to mirror, for every endpoint lint calls):
- tag resolution = the **property-scoped `list_tags` two-step** (NO space-level `/tags` — it 404s);
- `search` is **POST** (`POST /v1/spaces/{id}/search`);
- `list_objects` batching = `GET /v1/spaces/{id}/objects?limit=100&offset=…`;
- `get_object` (carries `backlinks` + relation props) = verb/path + mock to mirror;
- WikiLog create (lint emits its own `wiki_action=lint` WikiLog receipt) = verb/path + the `test_ingest.py` create mock to mirror.
- respx note: use no-arg `respx.post()/get()` for match-any (Mem0: `respx.patterns.M` raises at registration in installed respx 0.23.x).

## Checks carried verbatim from master (no change, just reference)
Asymmetric relation (Critical); Pipeline orphan (High, no grace, WikiLog failure cross-ref from #284); Orphan entity/concept (High, 7-day grace); Unresolved contradiction (High, **PASSIVE** until v0.6.0/#287 — zero findings on pipeline wikis, fires only on manual `wiki_contradictions`); Stale (Medium, `last_modified` vs linked-source `wiki_ingested_at` −90d); Oversized description (Low, >~2000 chars); Empty type (Informational); Potential duplicates (Informational, Qdrant 0.70–upsert band). LintReport schema + `wiki_lint(space_id, severity_threshold="all")` signature exactly per master lines 541–586.

## Performance / O(N) reference
Lint's ≤60s/≤500-object budget (warn + may exceed above 500) is the same O(N)-enumeration concern documented in `docs/known-limitations.md §9` (every query enumerates the whole wiki, both tiers; count-cache deferred). Spec must **reference §9**, not restate it. D1 (backlinks primary) is the main mitigation: it removes the second O(N) reciprocal traversal that the master spec's primary path required. Note the count-cache *could* land here but is not a v0.5.0 deliverable unless the budget proof needs it.

## Domains touched
- agent-operations (the `wiki_lint` MCP tool surface, severity-graded report, deeplinks)
- infrastructure (Qdrant duplicate sweep reuse, Anytype read clients, per-run cache, batching)
- security (read-mostly tool; lint only WRITES its own WikiLog receipt — no object mutation; prompt-injection N/A for a structural report; pre-checks fire before the WikiLog write)
- product (the operator payoff: fix structural problems without manually scanning objects)

## Estimated complexity: moderate
Design is already specified in the master spec; ~80% reuse of #284/#285 (read clients, WikiLog, per-run cache, `_qdrant()`, `semantic_search_core`, schema-compat + patch-decision pre-checks). Genuinely new work is bounded: a new `wiki/lint.py` (object enumeration + the check battery + duplicate sweep + LintReport assembly + WikiLog receipt), a `wiki-lint` CLI subcommand, and `server.py` registration. Careful spec treatment needed only for D1 (backlinks-primary vs traversal-fallback), D2/D3 (the needs-review check re-target), and the perf-budget proof.

## Anti-bloat directive (Mem0, #289 lesson — HARD)
#289 reached ~1,700 lines / 34 ACs for a "moderate, ~80% reuse" feature; the review→fix loop ratchets size UP by appending, which lowered downstream review fidelity (the GET/POST wire defect slipped two rounds). This spec MUST stay lean: **reference** the master spec by line range rather than restating it; resolve findings by **tightening**, not appending; keep any large payload samples as references to the master LintReport block; target a tight AC set (**aim ≤ ~15 firmed ACs**). Inherited constraints (QA#25 schema-outdated, QA#30 patch-decision pre-check) are **referenced by ID**, not recopied as guard ACs. A large BLOCKING count in review R1 (≥8) is a scope/altitude signal to tighten — not just a fix list.

## Pre-checks to activate at v0.5.0 (reference, firm as ACs by ID — do not recopy text)
- **QA#25 — `wiki_schema_outdated`**: `wiki_lint` against a space whose `wiki_schema_version` < code `WIKI_SCHEMA_VERSION` → `[CONFIG ERROR] wiki_schema_outdated` naming found+expected; `_newer` → warn-and-continue. (master lines 743, 1590–1607)
- **QA#30 — `patch_decision_missing_or_invalid`**: missing/malformed `patch-decision.md` → `[CONFIG ERROR] patch_decision_missing_or_invalid` **before any Anytype write** (the WikiLog receipt) or Qdrant call. (master line 905)

## Core-contract test backstop (Mem0, #284 lesson — do NOT repeat)
The core promise (a seeded fixture of EACH check yields the right finding; `severity_threshold` filters correctly; backlinks-primary orphan/asymmetric verified against a known asymmetric fixture; duplicate sweep in the 0.70–threshold band) MUST have **CI-runnable mocked backstops**. The live-API lint smoke test is **additive, skip-gated** (`@pytest.mark.live`), not the sole verification.

## Reviewer dispatch note (Mem0, carried from #285)
The reviewer subagent types named in phase-spec.md (`completeness-reviewer`, `spec-architecture-reviewer`, `security-reviewer`, `infra-reviewer`) are **not registered Agent tool types** in this sandbox. Dispatch the review team as **general-purpose agents** with the full role persona, the checklist reading list, and the anti-injection line embedded in each prompt.

## Files at risk of staleness if implemented
- `README.md` (add a lint section/diagram; "How it works" completes the maintain loop) — grep README marketing claims for consistency (Mem0 #140 R2 lesson).
- `CHANGELOG.md` (v0.5.0 entry); `MIGRATIONS.md` only if D2-option-A seeds a `stub` tag (default D2-B avoids it); `.env.example` (`WIKI_LINT_*` knobs if any: oversized-char threshold, orphan/stub grace days, duplicate floor — prefer reusing existing `WIKI_INDEX_THRESHOLD` for the upper duplicate bound).
- `docs/known-limitations.md` (reference §9; add a lint-budget note if >500-object behavior needs documenting).

## Out of scope (per master spec roadmap)
Automated `wiki_contradictions` population (v0.6.0 / #287 — keeps the contradiction check passive); retroactive WikiLog-edit detection (explicitly NOT checked, master line 286); multi-space federation (deferred); count-cache as a shipped deliverable (referenced as future); auto-fix/auto-merge of any finding (lint is report-only — it mutates nothing but its own WikiLog receipt).
