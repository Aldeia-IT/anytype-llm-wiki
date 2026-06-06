# Implementation Review — R1 (consolidated)

**Spec:** anytype-llm-wiki v0.6.0 — Automated Cross-Object Contradiction Detection (#287)
**Branch:** aldeia/287-anytype-llm-wiki-v0-6-0-automated-contradiction-de
**Diff reviewed:** `git diff 81b54d3..HEAD` (6 commits)
**Reviewers:** security, code-quality (DRY/simplify), completeness (spec/AC + addenda) — dispatched as parallel agents; lead inline checks added.
**Date:** 2026-06-06

## Verdict: APPROVED

Full non-live suite green: **572 passed, 25 skipped, 8 deselected, 2 xfailed**. All 15 target (previously-red) tests pass. Live tests (AC-8/AC-9) collect cleanly; not run (headless, no ANYTYPE_SPACE_ID). Zero CRITICAL/MAJOR/BLOCKING findings across all three reviews.

## Security review — CLEAN (no findings)
- Prompt injection: anti-injection preamble present in BOTH `prompts/contradiction.md` and the `_load_contradiction_prompt()` OSError fallback (SF-5). Rendering via `str.replace` + `json.dumps` (not `.format`). Peer facts JSON-escaped; natural-language injection handled by preamble.
- Hallucinated-ID filter (SG-2): only candidate-set ids (target wiki_relations minus self) may be written; non-candidate / None ids dropped.
- Credential scrubbing (SG-1): both rollback-note sites use `{type(exc).__name__}: {scrub_credentials(str(exc))[:120]}`; no raw httpx body written.
- Disclosure (SF-6): README + CHANGELOG + consent banner disclose widened peer-fact egress; consent gate unchanged and fires before any off-machine transmit (`check_remote_endpoint_consent` in entry path).
- No path traversal / unsafe interpolation; prompt path is a fixed constant.

## Code-quality review — no CRITICAL/MAJOR; MINOR informational only
- Reader move to `util.py` (`_existing_text`, `_parse_relation_elements`, `_relation_ids`) verified clean: no stale duplicate in `remember.py`; `query.py` re-exports `_parse_relation_elements`; `lint.py` resolves transitively. Circular-import-safe.
- MINOR (closed inline by lead): `detect_contradictions` `client` param unused — spec §3.3-mandated by signature and required by locked test call sites. **Cannot remove** (would break spec/tests). Closed by adding a docstring note clarifying it is a reserved write-plane handle.
- MINOR (no action — explicitly acceptable): `_write_contradiction_links` vs `_write_bidirectional_relations` share an A/B-rollback skeleton but differ in real ways (key resolution, A-list source, dedup, counting). Spec §3.4 contrasts them; a shared abstraction would obscure. Reviewer: "no change recommended."
- MINOR (out of scope): pre-existing `query._relation_objects_for_key` is a near-duplicate of the new `util._relation_ids`. Outside the diff (present in base), not a regression. Future cleanup, not this PR.
- MINOR (optional, not taken): the contradiction hook in `_run_ingest` could be extracted to a helper to flatten nesting. Current inline form is readable, consistent with how the function keeps other step logic inline, no correctness concern.

## Completeness review — COMPLETE (no gaps)
- AC-1..AC-14 present and matching intent (not merely test-passing).
- Lint check ACTIVE (§3.7): `_PASSIVE_CONTRADICTION_NOTE` removed, `_empty_report` notes `[]`, finding detail carries no "PASSIVE", docstrings cleaned.
- Addendum-post-spec items 2,3,4 delivered and operator-legible (README widened-egress + scope limitations; CHANGELOG; consent banner copy in extraction.py).
- Addendum-post-test item 1 (verbatim fixture lockstep): README privacy block byte-consistent with `tests/wiki/fixtures/readme_privacy_notice_verbatim.md` (new peer-fact wording, not stale v0.3.0).
- Addendum-post-test item 5: scope disclosure in operator-facing lint section; AC-2/AC-5-contrast/AC-12 negative assertions confirmed non-vacuous.
- `_create_source` tuple unpacked at both call sites (BL-6); `_call_ollama_prompt` imported bare into ingest namespace (post-test item 3).

## Outstanding pre-tag item (NOT a review finding — environmental)
- **Platform-assumption gate (post-spec item 1 / post-test item 2):** the no-target-GET design depends on POST `/search` returning hydrated objects-format `properties[].objects` arrays. Requires LIVE Anytype; CANNOT run headless. Honestly documented in the impl debrief as an outstanding pre-tag verification item with the pre-identified single-`get_object` fallback. The AC-1 fixture proves the parsing contract only (carries the addendum-5b honesty comment). Must be confirmed before tag/release alongside the AC-8/AC-9 live smoke runbook.

## Lead inline checks
- Verified branch is the feature branch (not main). 6 atomic commits, pushed.
- Re-ran full non-live suite myself: green. Target tests: 15 passed. Live collection: 8 collected, deselected.
- Read the new functions (`detect_contradictions`, `_write_contradiction_links`, hook, read_client try/finally lifecycle): spec-conformant; entity-only + update-branch-only gating correct; `wiki_last_reviewed` never touched; rollback flows to both warnings and WikiLog notes; `status` downgraded to partial only on rollback.
