# Council Spec Review R1 — Chief Security Officer

**Ticket:** #286 — anytype-llm-wiki v0.5.0 `wiki_lint` (structural health check)
**Phase:** spec (governance gate, strategic security posture)
**Reviewer:** Chief Security Officer
**Date:** 2026-06-05

---

## Verdict

**SIGN OFF — YES.** The security posture of this spec is sound enough to advance to implementation. No blocking concerns. Two advisory items, both low-risk and acceptable to carry into implementation.

---

## BLOCKING findings

**None.**

---

## ADVISORY findings

### A1 — Object-controlled text reaches the Anytype WikiLog; defense rests entirely on a truncation discipline the impl phase must enforce uniformly

**Risk level:** Low (accepted).
**Description:** Object titles/descriptions flow into finding `detail` and into the WikiLog `wiki_subject`/`wiki_notes` that lint itself writes back into Anytype. SF12 mandates the right controls: (a) the `oversized` finding carries a char-count summary, never the raw oversized body, and (b) any object text routed into `detail`/subject/notes passes through `strip_control_chars(...)[:N]`. I verified `strip_control_chars` (util.py:82-90) genuinely strips control/bidi/zero-width codepoints, and the `[:N]` slice on its string return is correct. This bounds both data exposure and log bloat, and — because there is no LLM in the loop — there is no classic prompt-injection vector. The residual is a "log-forging"-style concern: a crafted title containing newlines/markdown could make a WikiLog entry visually misleading. `strip_control_chars` removes control characters (including newlines/bidi), which substantially defangs this; what remains is ordinary visible text, which is the user's own wiki content displayed back to the same user. Acceptable. The advisory is that this is a *per-call-site* discipline — the protection only holds if every site that places object text into a finding or WikiLog applies the sanitize+truncate. Recommend the implementation-phase security-reviewer treat "no unsanitized object text reaches `detail`/`wiki_subject`/`wiki_notes`" as a checklist gate, ideally via a single shared helper rather than scattered inline slices.
**Recommended action:** Carry to implementation review as a verification item; no spec change required.

### A2 — `scrub_credentials` does not redact bearer tokens; correctness depends on tokens never being concatenated into output

**Risk level:** Low (accepted).
**Description:** SF11 correctly down-scoped an earlier overstatement. I verified `scrub_credentials` (util.py:98-141): it strips URL userinfo (`user:pass@`) and the query string/fragment, preserving scheme/host/port/path. It does NOT redact `ANYTYPE_API_KEY` or `QDRANT_API_KEY`. The spec's residual-risk argument is accurate: those tokens live in request *headers*, never in URLs, and lint never concatenates them into `detail`/`notes`/error strings. This is a correct and honest claim. The residual risk is that the safety property ("tokens never enter output") is an invariant the code must uphold, not something `scrub_credentials` enforces — `scrub_credentials` is a URL-hygiene function, not a token-redaction backstop. Given lint introduces no new credential surface (it inherits the existing config and the same dual-client pattern as `query.py`), the risk is low and consistent with the rest of the codebase.
**Recommended action:** No spec change. Implementation review should confirm error/exception messages that may embed a request URL pass through `scrub_credentials`, and that no header value is ever interpolated into a returned/persisted string.

---

## Security posture assessment (mandate items)

- **Attack surface / "no object mutation" claim:** Upheld by design. Lint is read-mostly; the only write is its own `wiki_action=lint` WikiLog receipt, routed through `WikiClient` (never the read client, G7). Both pre-checks (QA#30 patch-decision, QA#25 schema gate) fire before any write or Qdrant call. The enumeration read sits intentionally between the two gates (G9) — a read is not a write, so the "before any write" guarantee holds. Auto-fix/auto-merge is explicitly out of scope. No mutation surface is introduced.
- **Object-controlled text → output/log:** Bounded by SF12 (char-count summary for oversized; `strip_control_chars(...)[:N]` on object text). Verified against source. See A1.
- **Credential handling:** No new credential surface. SF11 claim verified accurate against util.py:98-141. See A2.
- **Prompt injection:** Verified genuinely N/A — including for the duplicate sweep. `semantic_search_core` → `embed_query` → Ollama `/api/embed` (embedder.py:22) is an *embedding* call (text → vector), not a generative completion. There is no prompt, no instruction-following surface. Object text enters only as embedding input. The spec's "no LLM invocation / not interpolated into any prompt" claim is correct.
- **SSRF / new credential surfaces:** None introduced. Lint fetches Anytype objects by ID against the configured host and queries the configured Qdrant host. No user-supplied URLs are dereferenced.
- **Error-path hygiene (G5):** `error_category` (`config_error`/`api_error`/`data_error`) set on every error path, mirroring `query.py:430/442`. Error strings are fixed templates that do not embed secrets; any URL-shaped fragment is scrubbed.
- **Data privacy / compliance:** Consistent with the client's local-first posture (compliance.md). Lint reads via the local API after Anytype's at-rest decryption and writes only a structural receipt back into the same local space. No telemetry, no off-machine transmission, no new PII pathway. Qdrant-layer non-encryption is a pre-existing, documented, local-only acceptance — unchanged by this increment.

---

## Rationale

This is a read-mostly structural-audit tool whose only write is a self-referential log receipt, built almost entirely on already-shipped and independently re-verified infrastructure. The strategic security story is clean: minimal attack surface, no mutation of user content, no new credential or network surface, no LLM/prompt-injection vector (the embedding call is text-to-vector, not generative), and pre-checks that correctly precede every write. The R1 security findings (SF11 credential-wording correction, SF12 object-text truncation, G5 error-category, G9 gate ordering) were genuine and are genuinely resolved in R2 — I confirmed the two load-bearing claims (`scrub_credentials` scope and `strip_control_chars` behavior) directly against source rather than trusting the prose. The two advisories are invariants the implementation must uphold per-call-site, not design defects, and both are low-risk because the data in question is the user's own local wiki content reflected back to the same user. Nothing here rises to a blocking risk to the company or its clients. Signed off to advance.
