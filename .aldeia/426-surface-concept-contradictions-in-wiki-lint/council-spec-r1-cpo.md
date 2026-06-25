# CPO Council Assessment — Post-Spec R1 — #426

## Sign-off: APPROVE

## BLOCKING findings

None.

## ADVISORY findings

1. **User-facing value of `types_reconciled` reporting is real but under-exploited.**
   The reconcile step records `{type_key, type_id, properties_added}` in the bootstrap result.
   For the actual consumers (the fleet + Jan), the migration story is "re-run `wiki_bootstrap`."
   The spec correctly makes re-bootstrap REQUIRED (SF-4) and documents it in MIGRATIONS.md, but
   there is no in-product nudge connecting the two: a stale space that runs the new `wiki_lint`
   before re-bootstrapping fires `critical` with no clearable field. The spec already names this
   exact broken-UX scenario and chose re-bootstrap docs as the mitigation, explicitly deferring
   the optional lint guidance-warning. From a product/UX angle that deferral is acceptable for a
   small, controlled internal fleet where Jan controls rollout sequencing — but the guidance-warning
   is the genuinely user-friendly version. Impact: a self-administered operator who skips the
   migration step gets a confusing un-resolvable critical. Recommended action: keep deferred, but
   when this lands, confirm the rollout sequencing (lint gate + reconcile shipping together) is
   actually enforced at release time, not just stated in the spec. Track the guidance-warning as a
   fast-follow if any operator hits the confusing state.

2. **The "false coverage" framing holds up — but the value is signal-integrity, not a new feature.**
   This is internal plumbing, and that should be stated plainly so expectations are calibrated.
   The product value is real and non-marginal: contradiction detection already ships (#325), the
   contradictions are already recorded, and `wiki_lint` is the canonical health channel the fleet
   and Jan consume. A detection that never reaches the consumer's dashboard is effectively dead
   coverage — worse than absent, because it creates false confidence that concept contradictions
   are being surfaced. Closing that gap restores trust in the lint signal. Impact: positive, but
   value accrues to signal-integrity/operator-trust, not to a visible new capability — measure
   success by whether concept contradictions actually start getting resolved, not by feature usage.
   Recommended action: none; framing is sound. Noted only to keep scope expectations honest.

3. **Generalizing reconcile to all six WIKI_TYPES is justified scope, not gold-plating —
   but it is the one place scope was widened beyond the literal ticket.**
   The literal ticket needs only `wiki_last_reviewed` added to `wiki_concept`. The spec instead
   builds a general read-modify-write property reconcile across all WIKI_TYPES (§3, SF-5). This is
   the correct engineering call: a one-off migration would leave the same bootstrap gap for the
   next schema addition, and the alternative (delete-and-recreate) is destructive. The generalized
   loop is a no-op for the five types with no missing properties, so the marginal cost is one extra
   GET per type at steady state. Impact: slightly more surface area and a destructive-PATCH footgun
   to maintain, but it pays for itself by making future schema evolution safe-by-construction. The
   replace-not-merge risk is heavily mitigated (monotonic-union guard, pagination guard, empty-payload
   refusal, audit log, regression test). Recommended action: accept. This is the right increment,
   not creep.

## SPLIT RECOMMENDATION

None.

This ticket is a tightly-scoped follow-up with a single coherent user outcome: make recorded
concept contradictions visible through `wiki_lint`. The four code changes (schema field, two
client methods, bootstrap reconcile, lint gate) are not independently shippable from a product
standpoint — they form one dependency chain. Shipping the lint gate (§4) without the schema field
and bootstrap reconcile (§1, §3) would produce exactly the un-resolvable-critical broken UX the
ticket exists to prevent; the spec correctly mandates they ship together (SF-4). There is no
independent, separately-validatable user increment hiding inside this scope. A split would create
a half-finished user journey that breaks an existing health signal — the opposite of cleaner
increments. The bootstrap reconcile generalization (advisory #3) is a plumbing dependency of this
ticket, not a separate user-facing concern. No decomposition warranted.

## Rationale

This is the right next increment: it closes a genuine false-coverage gap where shipped, recorded
contradiction detection never reaches the canonical consumer channel (`wiki_lint`) used by the
fleet and Jan — restoring integrity to a health signal people rely on. Scope is tight and
well-bounded, the two deferred items (format-mismatch correction, optional lint guidance-warning)
are reasonable and explicitly documented, and the one scope widening (general reconcile) is a
sound safety-and-maintainability call rather than gold-plating. The destructive-PATCH risk is the
central concern and is mitigated by-construction across both spec review rounds. I sign off from a
product perspective with the advisory that release sequencing (lint gate + reconcile together) be
enforced, not merely asserted, so no operator hits the un-resolvable-critical state.
