# Council Meeting — Post-impl (Round 1)

**Date:** 2026-06-04
**Ticket:** #289 — anytype-llm-wiki — wiki_remember: LLM-assisted agent memory write (extract → resolve → consolidate)
**Phase reviewed:** impl
**Client:** anytype-llm-wiki (self-hosted, MIT; the operator + autonomous agents are the client)

## Attendance

| Role | Present | Reason |
|------|---------|--------|
| Council Chair | Yes | moderator |
| Chief Security Officer | Yes | minimum — first agent-driven write path; sanitize-on-write, consent, lock |
| Legal Counsel | Yes | minimum — LLM-extracted content (possible PII), consent model, licensing |
| Chief Product Officer | Yes | minimum — consolidation value, trust posture, scope discipline |
| QA Director | Yes | minimum — quality gate, AC coverage, regression risk (ran the suite) |
| Chief Technology Officer | Yes | minimum — wire-contract fidelity (caught B-1 last round), refactor regression |
| Infrastructure Lead | Yes | post-impl: item-9 operator docs are impl/docs-phase; first repeated agent-write path — operational readiness |
| Client Advocate | Yes | self-hosted product — operator is the client; CA-originated audit/recoverability items |

Full council convened: this is the final delivery gate before PR (post-impl), and the ticket touches a security-critical, agent-driven write path with operator-facing operational and recoverability concerns.

## Context Presented

The impl phase delivered `wiki_remember` (v0.3.1) test-first against a 74-test contract: a new `wiki/remember.py` (~680-line orchestration) plus `consolidate()` in `extraction.py`, a new `consolidate.md` anti-injection prompt, schema bump 0.3.0→0.3.1, bootstrap seeding of the `remember` action tag + `wiki_status`/`wiki_source_type` tags, CLI + MCP surfaces, and README/CHANGELOG operator docs (addendum item 9). In-phase impl review ran R1 (NEEDS CHANGES — 1 CRITICAL C1, 1 MAJOR, 2 MINOR) → R2 (APPROVED). Final lead-verified test state: `tests/wiki/` 368 passed / 4 skipped / 2 xfailed; full repo 454 passed; 4 named regression guards green.

The C1 CRITICAL is the headline of this phase: the impl-worker satisfied a wrong-endpoint test mock by hand-rolling a **non-existent space-level `/v1/spaces/{id}/tags`** endpoint instead of the real property-scoped `list_tags` two-step. The suite went green while, against live Anytype, every `wiki_status`/`wiki_source_type`/`wiki_action` write would 404 and silently degrade — making the feature's headline conflict-review flagging **inert in production**. This is structurally the *same defect class* the CTO caught at the post-test council (B-1: search mocked GET, client POSTs) and the standing Mem0 #289 lesson. It was fixed (property-scoped D6 two-step reusing `ingest._resolve_wiki_action_tag`) and re-reviewed to APPROVED.

## Discussion

The council split its diligence by lens and cross-referenced. Three independent verifications anchored the meeting:

- **QA** re-ran the suite from the repo interpreter: **368 passed / 4 skipped / 2 xfailed** (matches the claim exactly), 4 regression guards green, the 3 C1 degrade-branch tests green against the property-scoped endpoint. The 4 skips are all live-only (expected in CI).
- **CTO** verified the C1 fix at source (not via the review's word): no non-property-scoped `/tags` caller remains in `src/`; `remember.py` makes **zero raw HTTP calls** — every wire interaction routes through `WikiClient`, structurally eliminating the fabricated-endpoint failure mode. B-1 fully closed (49/49 search registrations now POST). The `_call_ollama` → `_call_ollama_prompt` refactor is byte-identical on the shipped `extract()` path with a passing regression guard.
- **CPO / Client Advocate** verified the two trust-critical durable-audit findings from last round landed in *shipped code*: supersede writes a durable WikiLog note containing the removed prior text (CPO-A1/CA-A1, `remember.py:491-496`); the conflict-path provenance overwrite is surfaced both via a result-dict warning and a WikiLog note (CA-A2, `remember.py:480, 487-489`) — exceeding the addendum's EITHER/OR requirement.
- **Legal** confirmed both prior-round findings closed in shipped docs (as-is residual disclosed; item-9 docs landed) and that the only dependency change (`markdownify 0.11.x → 0.14.1`) is MIT — no copyleft, no new dependency.
- **Infra** confirmed item-9's five operator disclosures (a–e) are present and accurate in README/CHANGELOG, and that the change does **not** alter the Mac Mini's steady-state resource profile (no new service/model/daemon/port; fail-closed schema gate; backup coverage inherited from Anytype native export).

The single substantive new finding this round is the CSO's A1: the WikiLog `wiki_notes`/`wiki_subject` write (in the shared `ingest._write_wikilog`) does not pass through `sanitize_property_value`, so LLM-derived audit text reaches Anytype unsanitized — a narrow deviation from the spec's B1 "raw LLM output NEVER reaches Anytype" wording. The CSO classified it ADVISORY (audit object, not fact text; pre-exists in the #284 ingest path; the embedding chokepoint still applies `strip_control_chars`). No member escalated it to BLOCKING.

The one concern every lens converged on independently — CSO (A5), CPO (A1), QA (1), CTO (1), Infra (cond. 1), Client Advocate (A1) — is that the C1-fixed tag-resolution path has **never been exercised against a live Anytype instance** this phase (the `@live` smoke skips without `WIKI_TEST_SPACE_ID`). The fix is proven against the *documented* property-scoped contract and now-wire-faithful mocks, but only a live run proves the documented contract matches reality — and this is the exact guarantee that was almost shipped silently broken.

## Findings

### BLOCKING
None.

### ADVISORY

1. **[Unanimous — release-tag gate] Live smoke run not exercised this phase.** AC-R7/AC-R24 (retrievable-after-reindex; real off-machine consent-on-transmit) have NO CI equivalent — they live only in `@pytest.mark.live` tests that skip without `WIKI_TEST_SPACE_ID`. The C1-fixed tag-resolution write path has not touched live Anytype. **The PR merge is approved; the v0.3.1 *release tag* must be gated on a passing live smoke run against a freshly re-bootstrapped space.** Infra adds: that smoke run should include an Anytype export→import round-trip to confirm the new tag/Source/WikiLog objects survive restore.

2. **[CSO-A1] WikiLog audit write bypasses `sanitize_property_value`.** `_write_wikilog` (`ingest.py:241-269`) writes LLM-derived `notes` (conflict/supersede text) and `subject=knowledge[:50]` to Anytype `wiki_notes`/`wiki_subject` without sanitization — a narrow deviation from the B1 absolute. Low risk (audit object; embedding chokepoint still strips control chars; pre-exists in #284 ingest). **Recommended:** wrap `notes`/`subject` in `sanitize_property_value` inside `_write_wikilog` (one line; also benefits ingest), OR correct the spec §8.4 B1 wording to scope "never reaches Anytype unsanitized" to the fact properties. Do not ship the absolute claim alongside the unsanitized audit path.

3. **[CA-A2] Supersede recoverability fidelity is LLM-dependent.** The supersede audit logs whatever the model placed in the `supersedes` field, but `consolidate.md:37` does not require the field to contain the *verbatim* removed text. Worst case: a lossy paraphrase weakens (not nullifies) recoverability. **Recommended:** add one RULE line to `consolidate.md` requiring `supersedes` to carry the verbatim superseded text. Low-cost, not release-blocking.

4. **[CSO-A2 / Legal-A2 — accepted residual] Consent gate is notify-once, non-blocking, self-acking.** Correct for an autonomous-agent path (a blocking prompt deadlocks unattended agents) and disclosed in docs. It is the weakest control in the off-machine-transmit chain; any future move beyond the single-operator model (multi-tenant/hosted) must re-trigger security + legal review and re-open the LGPD/GDPR controller-vs-processor question.

5. **[Infra-A1 / CPO-A3] Reindex-on-every-write defaulted hot.** `WIKI_AUTO_REINDEX` defaults `"true"`; cost scales with total space size, not delta, on the first repeated agent-write path. Docs disclose the `WIKI_AUTO_REINDEX=false` + batched-reindex mitigation. Acceptable for v0.3.1. **Follow-up (v0.3.2):** a one-time advisory when write-rate exceeds a threshold while auto-reindex is on.

6. **[Infra-A2] Monotonic WikiLog growth has no automated pruning/alerting or concrete procedure.** Disclosed but manual. **Follow-up (v0.3.2):** a `wiki-log prune --older-than` helper or a concrete documented procedure.

7. **[m1 — accepted, no change] `sources_overwrite_on_conflict` over-warns on the PATCH-skipped path.** Non-destructive audit signal; documented rationale across impl-review-r1/r2 + fixer debrief. No action.

## Resolutions

All prior-round substantive findings are closed and chair-cross-verified: the test-council B-1 wire-contract defect (search GET→POST) and the impl C1 fabricated-endpoint defect are both fixed at source, not mock-papered; the two durable-audit findings (CPO-A1/CA-A1 supersede note, CA-A2 conflict-overwrite surfacing) landed in shipped code; the item-9 operator disclosures landed in shipped docs; both prior Legal findings are closed. No advisory rose to BLOCKING in discussion. The council's collective position is **ADVANCE** — the PR is approved to open and merge — with the live-smoke run carried as a hard gate on the downstream v0.3.1 release tag.

## Recommendation

**Recommended target:** `done` (approve the PR / advance to delivery)
**Confidence:** high
**Rationale:** Zero BLOCKING findings; all seven members sign off. Three independent verifications (QA ran the suite, CTO traced the wire contract at source, CPO/CA confirmed durable-audit code) confirm the deliverable is green for the *right* reason and the recurring wire-contract defect class is structurally closed. The remaining concerns are operational/documentation, not code defects, and are captured as release-tag conditions in `spec-addendum-post-impl-r1.md`. The PR merge does not require human adjudication; the v0.3.1 release tag does require the live smoke run (tracked downstream, e.g. #234 v0.3.1 tag-prep).
**Dissent:** None on the verdict. Legal signed off unconditionally; the other six signed off with the shared, non-blocking live-smoke-before-tag condition.
