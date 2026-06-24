# Council Impl Review R1 — Chief Security Officer

**Ticket:** aldeia-box#325 — Contradiction Detection: Extend to Concepts
**Phase:** POST-IMPL governance (strategic security-posture review)
**Reviewer:** Chief Security Officer
**Date:** 2026-06-24
**Diff reviewed:** `git diff origin/main...HEAD` — production = `ingest.py` (52 lines) + `remember.py` (docstring-only)

## Verdict: SIGN-OFF (no veto)

Zero BLOCKING findings. The deliverable does not change the security posture of the
contradiction-detection subsystem. It is a kind-dispatch widening over an already-fenced,
already-allowlisted machinery shipped and reviewed in #287. I independently verified every
load-bearing security claim against source rather than accepting the spec/impl-review
assertions.

## Independent verification (source-confirmed, not spec-trusted)

1. **No new untrusted-data path / no new trust boundary.** Concept `wiki_definition` text
   enters `detect_contradictions` through the *identical* channel as entity `wiki_facts`:
   - Peer text is read via `read_client.get_object` (never off the search-response relation
     array) — `ingest.py:586`.
   - It is placed into the candidate channel through `json.dumps(candidates_json)` and
     interpolated into `{{CANDIDATES}}`, which sits inside the `<candidates>…</candidates>`
     fence of the shared contradiction prompt (`ingest.py:534-535`, `601-602`). The new claim
     goes into `{{NEW_CLAIM}}` inside `<new_claim>` identically. The prompt template and its
     anti-injection preamble are unchanged by this diff. `kind` selects only the relation key
     and the read key — never the prompt shape. **Anti-injection claim UPHELD against the diff.**
   - LLM output is constrained by the hallucinated-ID allowlist (`if peer_id not in
     candidate_set: continue`, `ingest.py:614-617`) — unchanged. The model cannot cause a
     write to an object that was not already a linked candidate.

2. **No arbitrary-property read (`_facts_key_for_peer`).** Confirmed: it reads
   `peer_obj.get("type", {}).get("key", "")` and looks that up in the closed 2-key constant
   `_TEXT_KEY_BY_TYPE_KEY = {"wiki_concept": "wiki_definition", "wiki_entity": "wiki_facts"}`
   with a hardcoded `"wiki_facts"` default (`ingest.py:439-440, 539-548`). The peer type key
   is data we read, not data we write from; an attacker-controlled `type.key` value can only
   ever resolve to one of two literal property keys or the safe default. There is no
   reflection, no f-string property name, no attacker-influenced key path.

3. **No new credential handling / no secret exposure.** The diff touches no env-var,
   endpoint, auth, or transport code. `WIKI_EXTRACT_ENDPOINT`/`_ollama_url()` usage is
   pre-existing and unchanged.

4. **`f":{kind}"` interpolation is not an injection sink.** The warning suffix
   (`ingest.py`, CS-9) interpolates `kind`, but `kind` is code-supplied and only `"entity"`
   or `"concept"` ever reach the gate (`if kind in ("entity", "concept")`). It lands in an
   internal `result["warnings"]` diagnostic string, not in a prompt, query, shell, or markup
   sink. No risk.

5. **remember.py change is docstring-only** (cross-reference comment for the SF-5 two-helper
   split). No behavioural change.

## BLOCKING

None.

## ADVISORY

1. **SG-2 fail-safe posture is acceptable — accepted risk, not a blocker.** A peer whose
   `get_object` omits `type.key` falls back to `wiki_facts` and (for a true concept peer)
   reads empty text → a silent false-negative (a real concept contradiction goes undetected).
   This is a **detection-completeness gap, not an exposure**: it can only *miss* a finding,
   never fabricate one, write to a wrong object, or leak data. It is pre-existing and equally
   silent on the entity path, and `get_object` responses reliably hydrate `type.key`
   (verified premise from #287). I endorse the deferral. **Accepted risk:** concept
   contradiction coverage is best-effort, not guaranteed. The deferred debug-log on type-key
   fallback (folded into the SG-1 follow-up) is the correct, low-cost closure.

2. **Per-peer `get_object` skip remains silent (same risk class).** A peer that fails to
   fetch is skipped with no warning (`ingest.py:587-589`). Same fail-safe analysis: degrades
   coverage, never integrity or confidentiality. Endorsed deferral.

3. **False-coverage integrity hazard is a process risk, mitigated.** The genuine
   security/integrity concern for *release* is not in the code — it is the data-state risk
   that concept contradictions become *recorded but never surfaced* if the lint-surfacing
   follow-up is forgotten, giving operators false confidence in a clean contradiction column.
   This is mitigated: (a) README and CHANGELOG are explicit that concept contradictions are
   detected/cross-linked but **not yet flagged by `wiki_lint`** (verified in the diff —
   honest, no closed-loop over-claim, severity correctly stated as `critical`); (b) the
   follow-up is a real linked ticket (#426 in the CHANGELOG), satisfying the spec-council's
   closure condition. No further action required from security; I note the accepted residual
   that the wiki's contradiction column is not authoritative for concepts until #426 ships.

## Data-handling / release assessment

No new PII class, destination, transport, retention, or data flow. Concept definition text
is the same data class as entity facts, already processed locally by the same Ollama prompt.
No data-at-rest or in-transit change. Nothing in this deliverable expands the company's or a
client's exposure. Clear to advance to `done` from a data-handling standpoint.

## Sign-off

**I sign off on aldeia-box#325 from a security perspective.** The strategic posture is sound:
no new trust boundary, no new untrusted-data path into the LLM prompt, no credential or
secret surface, no arbitrary-property read, and a fail-safe (coverage-only, never integrity)
degradation model. The two silent observability gaps and the false-coverage hazard are
correctly deferred/disclosed with tracked follow-ups. No veto.
