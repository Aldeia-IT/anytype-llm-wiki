# Spec Addendum — post-test council (R1)

**Source:** [`council-test-r1.md`](council-test-r1.md)
**Date:** 2026-06-03
**Target phase:** impl (then pre-publish)
**Status:** Authoritative — the impl phase MUST honor these items as spec requirements. They are the post-test council's ADVISORY findings, precise enough to serve as an impl-phase brief. The spec body (§4/§7/§8/§9/§10) and the post-spec-r2 addendum already pin the substantive contracts; this addendum captures the execution constraints and test-coverage gaps the impl lead must close so the green-CI suite cannot mask a broken promise.

## Additional acceptance criteria for the impl phase

1. **[CSO-ADV-1 — HARD GATE] Wire the consent banner into the live `wiki_ingest` path AND gate it with an integration test.** The AC-S2.2 unit test (`test_remote_endpoint_consent_banner_fires`) exercises only the isolated `check_remote_endpoint_consent` helper. Impl MUST place the consent/ack check on the real `wiki_ingest` code path ahead of the first off-machine transmission, AND add an integration test that drives the real `wiki_ingest` entry with a non-local `WIKI_EXTRACT_ENDPOINT` and no ack file, asserting the banner/ack check fires BEFORE any non-local HTTP call (spy on transmit ordering). This is the §10.1 BLOCKING-2 privacy gate for a "local-first" first public release; it MUST NOT reduce to the helper unit test. The impl reviewer MUST verify placement explicitly.

2. **[Lock wiring — HARD GATE] Wire `space_ingest_lock` into the `wiki_ingest` entry path AND add a CI-runnable acquisition test.** AC#5 primitive coverage is complete, but no test fails if `wiki_ingest` never acquires the lock. Impl MUST acquire `space_ingest_lock` on the `wiki_ingest` entry path AND add a CI-runnable test (no multiprocessing needed — mock at the `space_ingest_lock` boundary) asserting `wiki_ingest` raises `[DATA ERROR] ingest_in_progress` when the space lock is already held. The impl reviewer MUST verify the wire-up.

3. **[QA-ADV-1] Harden the two vacuous-loop guard tests before/at impl.** `test_update_path_no_body_key` (AC-L1, `tests/wiki/test_ingest.py:721`) and `test_create_wiki_object_empty_body` (AC-P7 create-side, `:763`) iterate captured payloads with no prior non-empty assertion and would pass vacuously if the path never fires. Impl MUST add `assert update_payloads` / `assert any(p.get("type_key") in <wiki_type_keys> for p in create_payloads)` before the respective loops so the body-PATCH-deprecation (AC-L1) and empty-body invariant (AC-P7) guards cannot pass without the path actually executing.

4. **[CSO-ADV-2] SSRF validation MUST operate on the resolved IP, with bypass-encoding tests added.** Impl MUST validate the **resolved `ipaddress` object** and reject non-global addresses categorically (covers RFC1918, loopback, link-local `169.254.169.254` in one rule), NOT string-match the textual host. Add fetch tests asserting `ssrf_blocked` for `http://[::1]:31012/`, `http://0.0.0.0/`, and at least one numeric-encoded loopback (e.g. `http://2130706433/` or `http://0x7f.0.0.1/`).

5. **[CTO-ADV-2] Resolve the AC#16/SF2 sanitizer-placement decision explicitly.** `test_property_value_sanitized` asserts on `chunk_object` output, pinning sanitization to the chunker; spec §4.1 SF2's canonical home is "on write." Impl MUST either sanitize in the chunker (recommended — it is the embedding chokepoint, satisfies the test) OR relax the test to assert on the written property value. Make the call explicitly; do not let it surface as a surprise red during impl.

6. **[CTO-ADV-3] `force_reembed_object` signature is a test-driven contract.** `tests/test_indexer.py:262` binds impl to `force_reembed_object(space_id, object_id, obj)` in `wiki.ingest` (the V2-fail object-scoped re-embed). Impl MUST implement that name/signature or update the test in lockstep — do not leave a dangling import.

## Optional / lower-priority impl items

7. **[QA-ADV-2] AC#14 warn-and-continue branch** has no direct behavioral test (covered indirectly via `_max_version`/read-order). Impl MAY add a one-line test seeding a synthetic `"9.9.9"` schema marker asserting a warn-level log + continued execution. Acceptable to ship without.

8. **[QA-ADV-4] Tighten disjunctive error assertions.** Several error-path tests pass on either the specific code OR the generic `[CONFIG ERROR]`/`ok` banner. Impl MAY tighten to require the specific error string once exact codes are pinned. Low priority.

## Pre-publish (tag-time) gates — carried forward, re-seat Legal + Infra at the post-impl/PR gate

9. **[Process] Run the non-skippable live gates AC-P2 / AC-P7 / V3 green** against live Anytype + Qdrant + Ollama before the PyPI tag (spec §10.1). The publish runbook MUST NOT permit a `-m "not live"` shortcut at tag — these are the only end-to-end proof the v0.2.0 indexer gap is closed.

10. **[Carried from post-spec-r2 addendum, still binding]** README data-flow callout prominence (CA-ADV, addendum 7 — human eyeball at publish), NOTICE/dependency-tree gate generated from the resolved venv via `pip-licenses --from=mixed` + manual vendored-Rust check (Legal-ADV, addendum 8), Qdrant collection in backup rotation with restore tested for the v0.3.0 data volume (Infra-ADV, addendum 9), and the AC#18 partial-state-idempotency + V4 marker-home release-blocking **recorded decisions** (spec §10.1/§12). Re-seat Legal Counsel and Infrastructure Lead at the post-impl/PR final gate to execute these.

## Rationale

The council reached unanimous sign-off with zero BLOCKING findings; the test suite is comprehensive, traceable, and substantively asserted. What remains are **execution constraints the green-CI suite cannot self-enforce**: two live-wiring gaps where a test passes against a helper/primitive but nothing fails if impl forgets to connect it to the production path (the consent banner — the headline local-first promise — and the concurrent-ingest lock), two test-hardening items (vacuous loops, SSRF resolved-IP validation), and two contract-alignment items (sanitizer home, `force_reembed_object` signature). Capturing them inline as authoritative impl-phase acceptance criteria — rather than leaving them in the meeting summary the next lead must remember to re-read — ensures the defense-in-depth the spec council mandated actually lands in the implementation and the release checklist. Note: the test phase-summary's "Risks and Open Items" lists the AC#5 lock-wiring gap but OMITS the consent-banner wiring gap (item 1); both are now pinned here so the impl lead sees both "passes-against-helper-but-not-gated-on-live-path" risks.
