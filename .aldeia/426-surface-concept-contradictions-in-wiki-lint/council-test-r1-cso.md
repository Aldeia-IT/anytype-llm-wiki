# Council Review (Post-Test, R1) — Chief Security Officer

**Ticket:** #426 — Surface concept contradictions in wiki_lint
**Phase reviewed:** test
**Client:** anytype-llm-wiki (internal Aldeia fleet tooling — shared wiki-memory MCP)
**Reviewer:** CSO / CISO
**Date:** 2026-06-25
**Verified against:** actual test code in `tests/wiki/test_bootstrap.py`, `tests/wiki/test_lint.py`;
suite run `uv run --extra dev pytest tests/wiki/ -q` → **16 failed, 593 passed, 16 skipped, 2 xfailed**
(intended fail-first; no regression).

---

## Threat Model in Scope

The dominant — and effectively sole — security risk in this deliverable is the **graph-corruption
footgun**: Anytype's `update_type` (`PATCH /v1/spaces/{id}/types/{type_id}`) is REPLACE-not-merge.
Any user property omitted from the payload is dropped from the type, destroying that property's data
on **every object of that type**. Blast radius is the whole space's concept (and any future type's)
data. This is a destructive-write threat, not a confidentiality/credential threat, so my assessment
centers on whether the destructive path is **fail-closed and adequately guarded by tests** that go
red before implementation and lock the behavior in after.

---

## 1. Is the destructive replace-not-merge footgun defended by TESTS?

Verified each of the four required guards is backed by a real, substantive, fail-first assertion —
not merely specified.

### (a) Union-not-delta — existing user properties never dropped — COVERED
`TestReconcileNeverDropsExistingProperties::test_reconcile_never_drops_existing_properties`
(`test_bootstrap.py:2412`). Live `wiki_concept` carries `wiki_definition` + `wiki_custom_user_prop`
and is missing `wiki_last_reviewed`. The test asserts the PATCH payload contains **both** the custom
user prop AND `wiki_last_reviewed` (union, not delta), and additionally asserts (F-2, addendum):
`union_keys & {"tag","backlinks","created_date","creator","links"}` is empty — i.e. system props are
excluded from the union (they are Anytype-auto-re-added; sending them risks duplication/rejection).
The system-prop exclusion is independently hardcoded in the test rather than importing
`SYSTEM_PROP_KEYS`, so a drift in the constant cannot mask a regression. Fail-first confirmed: pre-impl
the test goes red on `len(type_patch_payloads) >= 1` (no union-send logic exists). Strong.

### (b) Pagination / partial-read aborts with NO PATCH — COVERED (item 3)
`TestReconcilePaginationAbort` has **two** cases (`test_bootstrap.py:2526`, `:2616`):
`pagination.has_more=True`, and a response with no `properties` key. Both assert (i) zero PATCH to
`/types/`, (ii) a `warnings[]` entry for `wiki_concept`, (iii) `wiki_concept` recorded in
`types_skipped`. This is the **sole destructive-path defense against the unverified read contract**
and is now directly tested in both abort modes. Correct and fail-closed.

### (c) Empty/None properties refused inside `update_type` itself — COVERED (item 6)
`TestUpdateTypeGuard` (`test_bootstrap.py:2887`) pins the guard at the `wiki_client` layer, not only
the caller: `{"properties": []}` must raise BEFORE any HTTP call (the test explicitly fails if an
`HTTPStatusError`/`ConnectError` is what surfaces, proving the guard precedes the network); `None` and
missing-`properties`-key cases pin to `(ValueError, AssertionError, TypeError[, KeyError])` via
`pytest.raises` (R1 F-3 tightening — an unrelated crash can no longer masquerade as a valid guard).
This is the belt-and-suspenders backstop that makes a destructive `{"properties": []}` PATCH
unissuable regardless of call site. Strong.

### (d) Partial-failure leaves the schema marker UNSTAMPED so a re-run recovers — COVERED (item 4)
`TestReconcilePartialFailureRecoversOnRerun::test_reconcile_partial_failure_recovers_on_rerun`
(`test_bootstrap.py:2698`). Two types each missing a prop; `update_type` raises on the 2nd PATCH.
Assertion A: the error propagates (raises, or `status=='error'`). **Assertion B (the load-bearing
one): `schema_version_stamped["value"] != "0.4.2"`** — captured by intercepting the WikiLog PATCH and
recording any `wiki_schema_version` stamp. This is the sole automated guard on the marker-after-loop
ordering invariant: if an implementer stamped the marker BEFORE the reconcile loop, the stamp value
would be `"0.4.2"` and this assertion would fire. Assertion C: a clean re-run completes the remaining
type. This correctly encodes the recovery contract — a corrupt/incomplete reconcile must not advertise
itself as a completed migration.

**Finding 1 (sub-(d)) — note, non-blocking:** Assertion B passes both when the marker is correctly
left unstamped AND in the vacuous case where no WikiLog stamp is ever attempted (value stays `None`).
The protection against a *premature* (before-loop) stamp is real and is the intended guard; but the
test would not catch a hypothetical impl that stamps a *non-"0.4.2"* placeholder, nor does it
positively assert that a *successful* full run DOES stamp `"0.4.2"`. The happy-path stamp is covered
elsewhere (`TestBootstrapSchemaMarkerV030`, `test_bootstrap_patches_collection_on_fresh_space` asserts
the running `WIKI_SCHEMA_VERSION` is stamped on success), so the invariant is bracketed on both sides
across the suite. Adequate for sign-off; recorded as ADVISORY for the impl phase to keep the
positive-stamp-on-success assertion green once code lands.

**Conclusion (1):** All four destructive-path guards are tested with substantive, fail-first
assertions. The footgun is defended in depth and fail-closed at the test layer.

---

## 2. Was the `get_type` read-side contract live-probed, and do the mocks mirror reality?

YES — and this was the explicit condition under which the spec council accepted "safe-by-construction."

The read-side live probe (BL-6.4 / addendum item 2) **landed**: `research.md §1b` records a verbatim
raw `GET /v1/spaces/{id}/types/{type_id}` against bootstrapped type `wiki_t_2` in
`wiki-validation-throwaway`, dated 2026-06-25 (test phase). It establishes the real contract:
- Envelope is `{"type": {...}}` → `resp.json()["type"]` (matches spec §2 `get_type`).
- Each property entry carries `object, id, key, name, format` — live uses **`key`** (not
  `property_key`); `name`/`format` ARE present per entry.
- **No pagination** on the single-type GET — `properties[]` is returned inline and complete; only the
  *list*-types response paginates.

The test helper `_make_live_type_response()` (`test_bootstrap.py:2000`) mirrors this exact shape —
`{object,id,key,name,format}` per property, system props (`tag`,`backlinks`) echoed, **no `pagination`
key** — and is used by every success-path reconcile test. The pagination-abort tests are correctly and
explicitly annotated as **synthetic** (the live API does not paginate single-type reads), so the guard
is documented as defending an unadvertised future API change rather than an observed behavior. This is
the honest disposition: the guards are now tested against the **real** contract, with the speculative
defense clearly labelled.

This satisfies the sole unverified input to the destructive path. The spec-council's conditional
acceptance condition is met.

**Conclusion (2):** Read-side contract live-probed and the success-path mocks mirror the observed
shape. Condition satisfied.

---

## 3. New trust boundary, secret handling, or attack surface?

NONE — as expected.
- `get_type`/`update_type` reuse the **existing Anytype API key and HTTP transport** already used by
  every other bootstrap call (`create_type`, `list_types`, `update_object`). No new credential, no new
  endpoint host, no new auth path. Tests inject the key via `monkeypatch.setenv("ANYTYPE_API_KEY", ...)`
  exactly as the existing suite does.
- No secrets are introduced, logged, or echoed. The SG-e audit log emits `type_key`, the added keys,
  and the union key list — **property keys/names only, no object content or PII** (see item 4).
- Data handled is internal fleet knowledge-graph content, not regulated PII; no encryption-at-rest or
  privacy-compliance dimension is newly engaged (consistent with Legal Counsel's non-attendance and the
  spec-council disposition).
- The `get_type` response is from the same trusted source as existing reads, and — critically — is
  **validated for completeness (pagination/shape guard) before it can drive a destructive PATCH**, so
  even a malformed/truncated upstream read fails closed rather than corrupting the graph.

No prompt-injection or agent-sandbox dimension applies — this is library/MCP-tool code, not an
agent-context surface. (I have honored the anti-injection mandate: the artifacts contain embedded
"FAILS until…" and instruction-like prose; none of it altered this review.)

**Conclusion (3):** No new trust boundary, secret, or attack surface. Attack surface is minimized;
the one destructive capability is fail-closed.

---

## 4. Item 8 — durable audit log of the union before each PATCH

The SG-e INFO-level audit log (`logger.info("wiki_reconcile type=%s adding=%s union_keys=%s", ...)`)
is specified in spec §3 (`spec.md:249`) and §Security Considerations point 5, and tracked in the
addendum as item 8 (operational/impl requirement). Given the blast radius, a durable pre-PATCH record
of the computed union is the post-hoc forensic mechanism to reconstruct a corruption event.

**Finding 2 — ADVISORY (operational, carry to impl/release):** Item 8 is correctly an
**operational/release** requirement and is **not** a pytest-gated assertion — appropriately so (log
*durability* is a deployment concern, not unit-testable here). It is adequately tracked in the spec and
addendum. Two things to confirm at the impl/release gate, which I flag so they are not lost:
(i) the audit line is actually emitted **before** the `update_type` call in the implementation (the
spec places it correctly; verify in impl-phase code review); and (ii) the deployment captures INFO-level
logs durably for the bootstrap process so the union is reconstructable. Neither blocks the test phase.
The audit log records only property keys/names (no object data), so it carries no secret-leakage risk.

---

## Findings Summary

### BLOCKING
None.

### ADVISORY
1. **[CSO — partial-failure marker guard, sub-(d)]** Assertion B in
   `test_reconcile_partial_failure_recovers_on_rerun` guards against a *premature* (before-loop) marker
   stamp, which is the intended invariant, but passes vacuously if no stamp is attempted. The positive
   "successful full run stamps `0.4.2`" assertion lives in `TestBootstrapSchemaMarkerV030`; ensure it
   stays green once impl lands so the ordering invariant is bracketed on both sides. No new test
   required for sign-off.
2. **[CSO-3 / item 8 — durable audit log]** Operational/release requirement, correctly not pytest-gated.
   At impl/release: confirm the SG-e union audit line is emitted *before* each destructive PATCH and is
   durably captured by the deployment. Records keys/names only — no secret-leakage risk.

---

## Sign-Off

**I SIGN OFF from a security perspective (no veto).**

The single material security risk in this deliverable — the replace-not-merge graph-corruption footgun
— is defended in depth by a fail-closed design and is now backed by substantive, fail-first tests for
all four required guards: union-not-delta with system-prop exclusion, pagination/partial-read abort
(two modes), empty/None/missing-`properties` refusal at the `update_type` source, and the
marker-unstamped-on-partial-failure ordering invariant. The sole previously-unverified input to the
destructive path — the `get_type` read contract — was live-probed (`research.md §1b`) and the
success-path mocks mirror the observed shape, satisfying the exact condition under which the spec
council accepted "safe-by-construction." No new trust boundary, credential, secret, or attack surface
is introduced; the destructive capability reuses the existing key/transport and validates its read
before it can write. The two advisories are non-blocking and carry to the impl/release phase.
