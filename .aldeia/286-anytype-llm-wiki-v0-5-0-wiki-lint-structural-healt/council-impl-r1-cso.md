# Council Impl Review R1 — Chief Security Officer

**Ticket:** Aldeia-IT/aldeia-box #286 — v0.5.0 `wiki_lint` structural health check
**Reviewer:** Chief Security Officer (post-implementation governance gate)
**Date:** 2026-06-05
**Prior position:** SIGNED OFF at post-spec council (2 advisories: SF12 shared sanitize+truncate; confirm tokens never interpolated into output).

## Verdict

**SIGN OFF** — 0 blocking, 2 advisory. Both post-spec advisories were honored in the implementation, and the realized posture is in fact stronger than the spec required.

## Findings

### BLOCKING

None.

### ADVISORY

**ADV-1 — Static schema-gate / patch-decision errors are not routed through `scrub_credentials` (accepted, non-gating).**
`lint.py:216` (patch_decision), `lint.py:240` (wiki_schema_missing), `lint.py:248` (wiki_schema_outdated) build error strings without `scrub_credentials`. This is acceptable because each is a fully static template interpolating only version numbers (`live`, `code`) — no URL, no exception text, no header value. The two *dynamic* error paths that CAN carry a URL-shaped fragment or exception body (`anytype_unavailable` at `lint.py:230`, `lint_sweep_failed` at `lint.py:501`) ARE both scrubbed. Risk accepted: none of the unscrubbed paths can carry a secret. No action required; noted for completeness so the asymmetry is a known, reasoned choice rather than an oversight.

**ADV-2 — `pipeline_orphan` reads WikiLog `wiki_notes` text for a substring marker (new behavior vs post-spec assessment, no new risk).**
`lint.py:338-340` reads each WikiLog's `wiki_notes` and tests `_FAILURE_MARKER in str(notes)`. This is a membership test only — the notes text is never echoed into `detail`, the report, or the new WikiLog receipt. It introduces no injection or data-exfiltration vector. Noted only because it is a read path not enumerated in the post-spec wire-contract review; it does not change the attack surface.

## Rationale

I verified all five items from the review mandate against `src/anytype_llm_wiki/wiki/lint.py`:

1. **Object text into output is bounded + sanitized.** Object titles route through `_object_title` = `strip_control_chars(str(obj.get("name","")))[:200]` (`lint.py:143-144`), used uniformly by `_finding` (`lint.py:170`) and at the two `detail` sites that name a title (`lint.py:445`, `lint.py:453`). The `oversized` finding emits `len(desc)` only, never the body (`lint.py:460-464`). No object **description** text is ever placed in a `detail`/`object_title`/report string — only its length. This satisfies the SF12 / CSO-4 advisory and exceeds it.

2. **Object-controlled text never reaches the persisted WikiLog.** The receipt's `subject` is the static literal `"structural health check"` and `notes` is `f"lint: {len(filtered)} findings, status {status}"` (`lint.py:553-558`) — both static, no title/description interpolation. Both pass through `strip_control_chars`/`scrub_credentials` anyway. This is the strongest possible outcome for SF12: object-controlled text cannot bloat or poison the WikiLog because it never reaches it.

3. **Both dynamic error strings are scrubbed.** `anytype_unavailable` (`lint.py:230-231`) and `lint_sweep_failed` (`lint.py:501`) both wrap the interpolated exception in `scrub_credentials(...)`. Confirmed against `util.py:98-141` (strips userinfo + query/fragment; by-design does not redact bearer tokens, which never appear here).

4. **No header/token interpolation.** `ANYTYPE_API_KEY` / `QDRANT_API_KEY` / any header value is referenced nowhere in `lint.py`. Tokens live in client headers (`AnytypeReadClient`, `WikiClient`), never concatenated into any returned or persisted string. This closes the CSO-5 advisory.

5. **Pre-checks are fail-closed and correctly ordered.** QA#30 patch-decision gate (`lint.py:212-221`) runs as Step 0 — a pure filesystem read, BEFORE either client is constructed (`lint.py:223-224`). QA#25 schema gate (`lint.py:237-257`) runs after the single enumeration read but before any write or Qdrant call, matching the intended G9 read-between-gates design; both abort branches return `status="error"` with no WikiLog written. Fail-closed confirmed.

**No new attack surface vs the post-spec assessment.** The duplicate sweep passes object description/title text as an *embedding* query (`lint.py:494-498`) into `semantic_search_core` — text→vector, no generative prompt — confirming my load-bearing post-spec claim that the sweep introduces no prompt-injection vector. The sweep is opt-in (`include_duplicates=False` default), object-capped (`lint.py:482`), and its score band is guarded by a numeric type check (`lint.py:509`) plus the `_bounded_float` config guard (`config.py:60-75`, out-of-range → default), so a hostile env value cannot crash or widen the band. No user-supplied URLs are fetched (SSRF-clean); only configured Anytype/Qdrant hosts are contacted. The tool mutates nothing but its own receipt.

This is read-mostly OSS tooling on a single constrained box. The threat model is adequate, trust boundaries (read client vs write client, embedding vs generation) are respected, sensitive data does not leak through output or the persisted log, and credential handling is unchanged from the vetted v0.4.x baseline. I sign off.

— Chief Security Officer
