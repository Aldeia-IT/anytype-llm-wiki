# Council Review — TEST phase (R1) — Legal / Compliance Counsel

**Ticket:** #289 anytype-llm-wiki `wiki_remember` (v0.3.1 LLM-assisted agent memory write)
**Phase reviewed:** test-gate (failing-test suite, TDD)
**Reviewer:** General Counsel (legal/compliance/privacy)
**Date:** 2026-06-04
**Verdict:** SIGN-OFF (no BLOCKING findings)

---

## Framing

anytype-llm-wiki is an MIT-licensed, self-hosted, local-first tool. The operator runs it on
their own machine, against their own Anytype space, with their own LLM endpoint of choice. In the
default configuration **no data leaves the machine** (on-device Ollama). The single off-machine
path (`WIKI_EXTRACT_ENDPOINT` pointed at a non-local LLM) is opt-in and operator-configured.

The correct legal model here is: **the operator is the sole data controller of their own space.**
There is no Aldeia-IT-as-processor relationship, no third-party data subjects whose data the
*tool* routes by default, and no telemetry. GDPR/LGPD controller-processor framing, DPAs, cookie
consent, right-to-erasure mechanics, and SaaS/AGPL contamination concerns do **not** attach to
this deliverable — they would be a category error against a local-first MIT tool. I have
deliberately not applied them. What *does* matter legally is narrower and the team has addressed
it: (1) that the one off-machine transmission is disclosed before it happens, and (2) that the
tool does not silently exfiltrate or persist data the operator did not intend. I evaluated the
test gate against those two, plus license/fixture hygiene.

---

## Findings

### ADVISORY-1 — Off-machine consent disclosure is enforced by test, but ordering assertion is conditional

**Description.** AC-R-S1 requires `check_remote_endpoint_consent(endpoint)` to fire on the real
`wiki_remember` entry path *before* any off-machine transmit when `WIKI_EXTRACT_ENDPOINT` is
non-local. `test_consent_banner_fires_on_live_path` (tests/wiki/test_remember.py:2736) correctly
drives the **real** entry point (not an isolated helper — satisfying addendum item 3), sets a
non-local endpoint, records a call-order list, and asserts consent precedes `extract` (the first
off-machine call). This is the legally load-bearing transparency control and it is backed by a
test. Good.

The one soft spot: the ordering assertion is wrapped in `if extract_calls:` (line 2798). If a
future regression caused `extract` never to be reached, the "consent-before-transmit" assertion
would vacuously pass on the strength of the "consent was called at all" assertion alone. For a
HARD GATE this is slightly weaker than ideal. It is not a blocker — consent IS asserted to fire,
and on the live path extract is reached — but the impl reviewer should confirm the ordering
assertion is exercised non-vacuously (extract is in fact called in this test's mock setup, so it
is, today).

**Legal basis.** Transparency / no-surprise-transmission. When operator content can be sent to a
third-party LLM, the disclosure must demonstrably precede the send. This is the one place where a
self-hosted tool still carries a duty-to-disclose, because the off-machine recipient is outside
the operator's machine and may have its own retention/training terms.

**Recommended action.** Accept as-is for the test gate. Note for impl: keep the assertion
non-vacuous (extract must be reached in the consent test).

### ADVISORY-2 — "Notify-once + non-blocking" consent model is an accepted residual, correctly scoped — confirm it reaches operator docs

**Description.** Per G2 (spec §8.2) and addendum item 9(e), the consent gate is a non-interactive,
self-acknowledging notify-once banner: on first off-machine use it logs a warning, writes its own
ack file (`sha256(endpoint)[:8]`), and proceeds; subsequent calls are silent. There is no enforced
human approval step. The spec explicitly accepts this under the single-operator threat model.

From a legal standpoint this is **acceptable to lock in at test time** for this product. This is
not a consumer-facing consent-banner-as-legal-basis scenario (where notify-once would be
inadequate). The operator who set `WIKI_EXTRACT_ENDPOINT` IS the party "consenting," and they are
the same party who controls and reads the data. A self-ack notice that the operator's own config
choice will transmit content off-machine is a proportionate disclosure, not a consent-of-a-third-
party. The residual (an agent transmits off-machine after a single self-ack) is real but is the
operator's own configured behavior.

The one thing I require: this behavior must be **disclosed to downstream community operators in
user-facing docs**, because a self-hosting third party who adopts this tool is NOT the same person
who wrote the threat-model and could reasonably assume the banner blocks. Addendum item 9(e)
correctly schedules exactly this for the impl/docs phase ("narrated `knowledge` is stored as-is
... and the off-machine consent banner is notify-once and non-blocking"). It is **deferred, not
dropped** — confirmed.

**Legal basis.** Adequate disclosure to downstream adopters; avoiding a misrepresentation-by-
omission that the banner provides stronger protection than it does.

**Recommended action.** No test-gate action. Carry item 9(e) as a hard docs deliverable in the
impl phase (see ADVISORY-4). I flag this to the CSO as a security/legal crossover (consent gate is
non-blocking by design).

### ADVISORY-3 — Data minimization: `knowledge` stored as-is is an accepted, *documented* limitation, not a hidden gap — backed by the scrub/sanitize tests that exist

**Description.** Item 9(e) states narrated `knowledge` is stored as-is; only URL credentials are
scrubbed (via `scrub_credentials`), not arbitrary secrets. I checked whether the documented
privacy commitments are actually backed by tests and whether the residual is honestly disclosed:

- **Sanitize-on-write is rigorously tested.** `test_consolidated_text_sanitized_on_write`
  (test_remember.py:1034) embeds a U+200C bidi/control codepoint in the LLM `consolidated_text`,
  captures the actual PATCH payload, and asserts the written `wiki_facts` value equals
  `sanitize_property_value(consolidated_text)` **byte-for-byte** (not "contains", not "non-empty",
  not "was called"). This proves raw LLM output never reaches Anytype unsanitized (B1 / AC-R27).
  This is exactly the standard of proof the addendum (item 4) demanded, and it is met.
- **Credential scrub on provenance** (SF4): the `source` note and the lock `source_ref` are routed
  through `scrub_credentials` (strips URL query string / userinfo) before write. This is the
  documented scope — URL credentials, not arbitrary secrets — and it matches compliance.md
  ("No PII handling beyond what users put in their Anytype notes").
- **The residual (arbitrary secrets in `knowledge` are stored verbatim) is explicitly an accepted,
  documented limitation**, scheduled for operator-facing docs in item 9(e). It is NOT an unstated
  gap. That is the legally important distinction: a documented limitation in a tool where the
  operator is the sole controller of their own space is a defensible product decision; a silent one
  would not be. The data stays in the operator's own E2E-encrypted Anytype space (per
  compliance.md), so "stored as-is" means stored in the user's own vault, not exfiltrated.

The only data that leaves the machine is what the operator chose to send to their chosen LLM via
the opt-in endpoint — and sanitize/scrub do not change that the LLM sees the raw `knowledge`. That
is inherent to using an LLM and is covered by the consent disclosure (ADVISORY-1/2), not by
sanitization. The test coverage is **sufficient relative to the documented commitment.**

**Legal basis.** Data minimization proportionality; honest disclosure of limitations (no
deceptive-omission exposure to downstream adopters).

**Recommended action.** None at the test gate. The "stored as-is / only URL credentials scrubbed"
disclosure must land in operator docs (item 9(e)) — see ADVISORY-4.

### ADVISORY-4 — Privacy posture must be reflected in operator-facing docs (deferral confirmed correct)

**Description.** Three privacy-relevant disclosures are correctly deferred to the impl/docs phase
via addendum item 9, not dropped: (e) `knowledge` stored as-is + notify-once non-blocking consent
banner; and the operational items (a)-(d). For a tool published to a privacy-focused community
(Anytype), getting the privacy posture into README/CHANGELOG is the proportionate legal guardrail
— it is what converts an internal threat-model assumption into an adequate disclosure to third-
party adopters. The deferral to docs phase is correct (these are not test-phase artifacts), and
the addendum makes them authoritative impl-phase requirements ("the impl/docs phase MUST honor
item 9"). Confirmed: **deferred, not dropped.**

**Recommended action.** The council (and specifically Infra/CSO/CA per item 9) must verify in the
impl/docs review that item 9(e) actually ships. I will want to see it before final sign-off on the
impl phase.

### License / IP / fixture hygiene — CLEAR

- **License:** MIT, permissive. No GPL/AGPL contamination concern (no copyleft dependency
  introduced by this surface; the change is internal Python + a static prompt file). No SaaS/AGPL
  trigger — this is self-hosted, not offered as a network service by Aldeia-IT.
- **Test fixtures:** I scanned tests/wiki/test_remember.py. All credentials/endpoints are
  synthetic placeholders (`test-remember-key`, `api.example.com`). No real secrets, no embedded
  third-party copyrighted content, no real personal data in fixtures. No attribution obligation
  triggered.
- **Prompt file** (`wiki/prompts/consolidate.md`): authored in-house, anti-injection framed; no
  third-party IP.
- **IP exposure:** The novel surface (LLM consolidation contract) is original work product; no
  patent/trade-secret exposure introduced by advancing tests.

---

## Crossover notes

- **To CSO:** The off-machine consent gate is **non-blocking by design** (self-ack, notify-once)
  and the `knowledge` payload is sent raw to the configured LLM. These are the two
  data-protection/legal crossover points. I am comfortable with both under the single-operator
  threat model; flagging so security and legal stay aligned, and so the docs disclosure (item 9e)
  is jointly owned.

## Pipeline-quality note (constructive)

Nothing here needed to be caught earlier — the privacy controls (consent gate, sanitize-on-write,
credential scrub) were specified in the product/spec phase and the test gate faithfully enforces
them with substantive, non-tautological assertions. This is the pipeline working as intended:
privacy commitments are backed by tests before impl. Good posture.

---

## Sign-off

**I SIGN OFF on advancing the TEST phase to impl from a legal/compliance perspective.**

- **BLOCKING findings: 0.**
- **ADVISORY findings: 4** (consent ordering assertion is conditional but non-vacuous today;
  notify-once consent model accepted as documented; `knowledge`-stored-as-is is a documented not
  hidden limitation; privacy docs correctly deferred to impl).

The documented privacy commitments (consent-before-off-machine-transmit, sanitize-on-write,
URL-credential scrub) are each backed by a test that drives the real entry point with substantive
assertions. Nothing legally risky is being advanced to impl. My only carry-forward condition is
**not** a test-gate blocker: addendum item 9(e) (operator-facing disclosure that `knowledge` is
stored as-is and the consent banner is notify-once/non-blocking) must actually ship in the
impl/docs phase — I will confirm it at the impl review.
