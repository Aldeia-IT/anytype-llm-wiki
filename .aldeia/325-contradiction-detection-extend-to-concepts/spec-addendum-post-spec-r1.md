# Spec Addendum — post-spec council (R1)

**Source:** [`council-spec-r1.md`](council-spec-r1.md)
**Date:** 2026-06-18
**Target phase:** test → impl (the forward phases for the confined core, **if Jan selects scope option (a)** at Decide)
**Status:** Authoritative — the forward phase MUST honor these items as spec requirements.

> **Conditional applicability.** These criteria apply to the **confined-core path** (scope
> option (a): ship CS-1..CS-6 + CS-9, file a surfacing follow-up). If Jan instead folds
> surfacing back into #325 at Decide (option (b)), the ticket returns to the spec phase for
> re-scoping and this addendum is superseded by that larger spec. The council unanimously
> recommends option (a).

## Additional acceptance criteria for the forward (test / impl) phase

1. **[QA-ADV-1] Clean-path negative assertion for CS-9 (test phase).** Add a test asserting
   that on a **clean concept path** (no contradiction detected, no error), the
   `contradiction_detection_degraded:concept` warning is **absent** from `result["warnings"]`.
   CS-9 introduces this new string; AC-C4 only checks its *presence* on the error path. This
   one-line addition closes the only CS-9-introduced behaviour currently verified in a single
   direction. (Mirror the entity `test_detection_degraded_warning_absent_on_clean_path`.)

2. **[CA/CPO-ADV-1] Surfacing follow-up ticket is a closure condition of #325 (impl/merge
   gate).** Before the confined core merges, a dedicated lint-surfacing follow-up ticket MUST be
   created and linked from #325 (and from this work folder's "Recommended Follow-Up" spec
   section). Do not merge the core on the strength of the spec section alone — an unfiled
   follow-up leaves concept contradictions in a false-coverage state (recorded but never
   surfaced by `wiki_lint`). The follow-up's first research task is to verify the Anytype
   `API-update-type` / property-link endpoint exists and is idempotent (Infra-ADV-2 / CSO).

3. **[CA/CPO-ADV-3] README/CHANGELOG must remain explicit that lint surfacing is a follow-up
   (impl phase).** The doc edits MUST state that concept contradictions are detected and
   cross-linked via `wiki_contradictions` but are **not yet flagged by `wiki_lint`** (a planned
   follow-up), so neither the agent fleet nor the OSS community infers a closed integrity loop.
   The severity wording MUST say `critical`, not `High` (SF-R2-1; actual `lint.py:500`).

## Rationale

Items 1 and 3 are concrete, low-cost requirements the forward phase would otherwise have to
re-derive from a 7-file council bundle; inlining them here ensures the test and impl workers
honour them during Task Intake. Item 2 is the council's central condition for endorsing the
re-scope: the confined core's user-visible payoff lives entirely in the follow-up, so the
follow-up must be a committed, tracked work item — not prose in a spec section — for the
re-scope to be a responsible product decision rather than an indefinite deferral. All three are
ADVISORY (zero BLOCKING findings), but they are the conditions under which the council's
unanimous sign-off was given.
