# Impl Review R3 — Council BLOCKING-L1 Rework Resolution

**Date:** 2026-06-04
**Ticket:** #284 — anytype-llm-wiki v0.3.0 wiki_ingest compile pipeline
**Round:** 3 (narrow council-directed rework)
**Verdict:** APPROVED — single BLOCKING resolved, ready for PR

## Scope

Council post-impl R1 (`council-impl-r1.md`, commit `7282e94`) returned REWORK
with exactly **one BLOCKING** finding and a recommended target of `impl` for a
surgical, Legal-pre-blessed documentation/fixture correction. Six of seven
council members had already signed off to advance to PR; the implementation was
not reopened.

## BLOCKING-L1 — RESOLVED (commit `7c6acf4`)

**Finding:** README.md "Privacy and data flow" and its frozen verbatim test
fixture named `WIKI_EXTRACT_MODEL` as the environment variable that causes
ingested source content to be transmitted to a hosted provider. An accuracy
defect in a published privacy notice (GDPR Art. 13/14, LGPD Art. 6 transparency)
on a local-first-branded tool.

**Code verification (not prose-trust):**
- `WIKI_EXTRACT_MODEL` — `wiki/config.py:33-34` resolves only a model-name
  string (`DEFAULT_WIKI_EXTRACT_MODEL = "qwen2.5:7b"`). It performs no network
  routing.
- `WIKI_EXTRACT_ENDPOINT` — `wiki/extraction.py:126` (`base = os.environ.get(
  "WIKI_EXTRACT_ENDPOINT") or _ollama_url()`) is the actual off-machine switch;
  `extraction.py:215-241` scrubs and logs it; `ingest.py:422` reads it as the
  consent-banner trigger.

**Fix applied (two locations, in lockstep — Legal pre-blessed):**
1. `README.md` "Privacy and data flow" bullets — `WIKI_EXTRACT_ENDPOINT` is now
   named as the off-machine switch; `WIKI_EXTRACT_MODEL` is described only as the
   model-name selector that does not by itself cause transmission; the one-time
   consent banner on first off-machine endpoint is noted.
2. `tests/wiki/fixtures/readme_privacy_notice_verbatim.md` — updated identically
   so the verbatim-substring gate (`test_readme_contains_verbatim_privacy_notice`)
   stays green.
3. Confirmed consistency with the already-correct `README.md:159-164`
   (Local-first callout) and `.env.example:7-11`.

**Verification:** `TestBootstrapReadmePrivacyNotice` → 2 passed.

## Advisory 7 — RESOLVED (same commit)

Removed the obsolete `@pytest.mark.xfail(strict=False)` on
`test_wiki_ingest_returns_error_on_missing_patch_decision` (test_bootstrap.py).
The test xpassed now that v0.3.0 is implemented; confirmed it passes as a normal
test (`--runxfail` → 1 passed) before removing the marker, so a future
regression now surfaces as a real failure.

## Suite result

`pytest -m "not live"` → **367 passed, 20 skipped, 2 deselected (live), 2 xfailed
(genuine v0.4.0 pre-checks), 0 failed.** (+1 pass vs council R1's 366 = the
un-xfailed test now counted as a real pass.)

## Carry-forward (tag-time, NOT merge blockers)

Recorded in `council-impl-r1.md` Advisories 1-6 and spec §10.1 / addendum
items 9-10. Re-seat Legal + Infra at the post-PR/pre-tag gate:
- Live AC#1 / AC-P2 / AC-P7 / V3 green against live Anytype + Qdrant + Ollama
  (no `-m "not live"` shortcut; a *skipped* live test = failure; include a
  concept-producing AND a headingless source).
- NOTICE regen via `pip-licenses --from=mixed` + vendored-Rust check.
- Qdrant backup rotation + TESTED restore for the v0.3.0 volume.
- AC#18 partial-state-idempotency disposition recorded in release notes.
- README data-flow prominence eyeball.
- v0.4.0 product item: LLM-extraction-primary candidate derivation.
