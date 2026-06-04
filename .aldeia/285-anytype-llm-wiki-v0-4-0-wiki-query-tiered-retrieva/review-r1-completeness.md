# Review R1 — Completeness & Requirements (wiki_query v0.4.0, ticket #285)

**Verdict: NEEDS REVISION**

**Findings by severity:** BLOCKING 4 · SHOULD-FIX 6 · SUGGESTION 3

Reviewer mandate: Completeness & Requirements only. Diagrams/tables treated as normative.
All section/line refs are to the spec under review unless prefixed `master:`.

---

## Summary

The increment spec is well-grounded: it correctly delegates the data-flow diagram,
signature, QueryResult schema, tier definitions, file-back policy, compounding, and
deeplink format to the master spec by explicit citation, and it locks the four open
decisions (FilterExpression no-op, multi-type OR fix, synthesis helper, file-back write).
The ticket's five deliverables are all present. However, there are concrete completeness
gaps that block sign-off:

1. The **QueryResult `status` field is never defined** (no ok/partial/error transition
   rules), and several fields have no populating path for the empty/failure/partial cases —
   exactly the Mem0 "declared-but-never-populated" blind spot the checklist calls out.
2. The schema carries no `error` field, but the spec emits `[CONFIG ERROR]`/`[API ERROR]`
   strings and research says errors land in `result["error"]` — an unresolved coherence gap.
3. The **"filed query retrievable after reindex" core contract has no CI-runnable backstop**
   — AC #7 explicitly says "No AC gating this in CI," which directly contradicts the
   scope brief's #284-lesson requirement.
4. The **empty-wiki / zero-candidate path (count==0)** is unspecified end-to-end.

---

## BLOCKING

### B1 — `status` field has no definition or transition rules
**Where:** QueryResult schema §lines 195-196; pipeline prose §256-264; ACs §462-477.
**Issue:** `status: "ok|partial|error"` is reproduced from the master but the spec never
states which conditions yield each value. When is `partial` returned (synthesis succeeded
but file-back write failed? some neighbor fetches failed? name redactions occurred?)?
When is `ok` vs `partial`? The WikiLog block (§282) says "success or partial" implying a
distinction exists, and the live test (§450) asserts `status in ("ok","partial")` — but no
rule defines the boundary. This is untestable as written.
**Fix:** Add a "Status determination" subsection with an explicit table, e.g.: `error` =
any `[CONFIG ERROR]`/`[API ERROR]` returned (pre-check fail, Qdrant-down-at-threshold);
`partial` = answer produced but ≥1 degradation (file-back attempted-and-failed, a neighbor
fetch failed, a name redacted, WikiLog write failed); `ok` = answer produced, no
degradations. Map each warning/error path to a status.

### B2 — No `error` field in QueryResult, but error strings are emitted
**Where:** Schema §177-197 (no `error` key); error strings §236, §305-314; research Q9
("strings appear in `result["error"]`... no `error_category` in ingest/remember").
**Issue:** The QueryResult schema has `warnings[]` and `status` but no `error` field. Yet
the spec returns `[API ERROR] qdrant_unavailable` (§236) and `[CONFIG ERROR] ...` pre-check
strings (§305-314). Where do these land in the returned dict? Into `warnings[]`? A new
`error` key? This is undefined, and it makes the error ACs (#9, #10, #12) untestable —
a test cannot assert on a field the schema does not name. Research Q9 also flags the open
question of whether `wiki_query` adds `error_category` (bootstrap does, ingest/remember
don't); the spec never resolves it.
**Fix:** Explicitly extend the QueryResult contract for `wiki_query`: state the error
string is returned in a named field (recommend `error` to match ingest/remember
`result["error"]`) with `status: "error"`, and state whether `error_category` is included
(recommend: match ingest/remember = no `error_category`). Reconcile the schema block so
every AC that asserts an error string names the field it reads.

### B3 — "Filed query retrievable after reindex" contract has NO CI backstop
**Where:** AC #7 §468; scope brief lines 96-103 ("#284 lesson — do NOT repeat").
**Issue:** The scope brief is explicit: the three core promises — (1) answer + ≥1 cited
source, (2) retrieval_mode reflects count, (3) **a filed Query object is retrievable on a
subsequent query after reindex** — MUST each have a CI-runnable mocked backstop; the live
test is additive only. Promises (1) and (2) have backstops (ACs #4, #1-3). Promise (3) does
NOT: AC #7 reads "No AC gating this in CI — it is a documented prerequisite (verify via
live test after reindex)." That is precisely the anti-pattern #284 was flagged for.
**Fix:** Add a CI-runnable test (and AC) that mocks the compounding loop at the seam: a
filed Query object (with `wiki_answer`) is fed through the chunker/`_chunk_properties` path
(or a mocked `_semantic_search_core` returning a `wiki_query`-type hit) and asserts it
surfaces as a Tier-2 candidate. The #284-dependency note can remain, but the contract that
the pipeline *consumes* a filed Query as a source must be CI-verified, not live-only.

### B4 — Empty-wiki / zero-candidate path is unspecified end-to-end
**Where:** Tiered Retrieval §199-237; Synthesis §256-264; checklist item 5.
**Issue:** What happens when `object_count_at_decision == 0` (freshly bootstrapped/empty
wiki)? `count < threshold` routes to Tier 1, which enumerates zero candidates. The spec
never states: what is `retrieval_mode` at count==0 (still `index_navigation`? a distinct
value?); what does `synthesize()` receive with an empty `context_objects` list; what is
`answer`/`status`/`sources_consulted` when there is nothing to synthesize from. Tier 2 with
zero `semantic_search` hits has the same gap. Checklist item 2 explicitly asks "what is
retrieval_mode when count==0."
**Fix:** Specify the zero-candidate behavior: e.g. skip the LLM call, return
`answer=""` (or a fixed "no relevant wiki content found" message), `sources_consulted=[]`,
`status="ok"` (empty is a valid answer, not an error), `filed_back=false`, and a warning
like `no_candidates_found`. State `retrieval_mode` at count==0 explicitly. Add an AC + test.

---

## SHOULD-FIX

### S1 — Synthesis-returns-empty / synthesis-error path not mapped to result fields
**Where:** Synthesis §256-264; Decision 3 §127 (`[CONFIG ERROR] model_not_pulled`).
**Issue:** Decision 3 says `synthesize()` returns the error string `[CONFIG ERROR]
model_not_pulled: {model}` on a missing model, and free-form prose otherwise. But the
pipeline section never says what `wiki_query` does when `synthesize()` returns that error
string (does `answer` literally become the error string? does `status` become `error`? is
file-back suppressed?), nor what happens if the model returns empty/whitespace prose. The
file-back gate (§270-271) does `len(answer.split()) >= MIN_WORDS` — an error string would
pass the word count and could trip file-back of a non-answer.
**Fix:** Specify: synthesis error string → `status="error"`, surfaced in the `error` field
(per B2), file-back suppressed, no WikiLog `created`. Empty prose → `status="partial"` (or
treat as zero-answer), file-back suppressed. Guard the file-back gate against error/empty
answers explicitly.

### S2 — `sources_consulted` deduplication across Tier-1 + neighborhood not specified
**Where:** Synthesis §259-263; 1-hop §238-251 (cache dedups *fetches*, not *sources*).
**Issue:** Checklist item 5 calls out "duplicate candidates from Tier-1 and neighborhood
expansion." The per-run cache prevents duplicate *fetches*, but a candidate can also appear
as another candidate's 1-hop neighbor. The spec does not state that `sources_consulted` is
de-duplicated by `object_id`. Without it, the same object could be listed twice and could be
double-counted toward `WIKI_FILE_BACK_MIN_SOURCES`.
**Fix:** State that `sources_consulted` is deduplicated by `object_id`, and that the
file-back source count is over the *unique* contributing objects.

### S3 — "objects whose content contributed to the answer" is underspecified (ambiguity)
**Where:** §262 ("`sources_consulted` ... built from objects whose content contributed to
the answer").
**Issue:** There is no mechanism to know which objects the LLM actually used — the synthesis
returns free-form prose, not a structured citation list. Is `sources_consulted` = all
context objects passed in, or only those the model cited by title? This materially affects
the file-back gate (`len(sources_consulted) >= 3`) and AC #6.
**Fix:** Pin a deterministic definition: recommend `sources_consulted` = the set of unique
context objects passed into the synthesis prompt (candidates + 1-hop neighbors,
deduplicated). If title-based citation parsing is intended, that is a parser that must be
specified and tested — but simplest/testable is "all context objects."

### S4 — Cited-object-deleted-between-fetch-and-file-back edge case unhandled
**Where:** File-Back Gate §275-278; checklist item 5.
**Issue:** Step 2 writes `wiki_drew_from` with the cited source IDs, and step 3 calls
`_write_bidirectional_relations`. If a cited object was deleted between fetch and file-back,
the PATCH may fail or write a dangling relation. The spec does not say whether file-back is
best-effort (warn + `status=partial`) or aborts. (The cache holds the object, but the live
write target may be gone.)
**Fix:** State file-back relation writes are best-effort: a failed PATCH → warning +
`status="partial"`, the Query object is still created (answer is durable), `filed_back`
remains `true` if the object was created. Add to the status table (B1).

### S5 — Word-count definition for the 100-word gate is ambiguous
**Where:** File-Back Gate §271 (`len(answer.split()) >= WIKI_FILE_BACK_MIN_WORDS`).
**Issue:** `answer.split()` on whitespace is a reasonable definition, but it is stated only
inside the gate pseudocode, not as a normative rule, and the AC (#6) restates it. Markdown
punctuation, code fences, or an error string would all count as "words." Combined with S1,
an error string easily clears 100 words.
**Fix:** Promote `len(answer.split())` (whitespace tokens) to a one-line normative
definition near the gate and reference it from AC #6; explicitly exclude the error/empty
cases per S1.

### S6 — `object_count_at_decision` source-of-truth vs Tier-2 path coherence
**Where:** Tiered Retrieval §201 (count = enumerate all four wiki types); Tier 2 §228.
**Issue:** The object count drives the tier decision and is enumerated via `list_objects`
+ client-side filter (Tier 1's mechanism). On the Tier-2 path the spec still needs that full
enumeration to *compute* the count before it can decide to use Tier 2 — i.e. Tier 2 always
pays the Tier-1 enumeration cost first. This is implied but never stated, and the Resource
Impact section (§405-408) describes Tier 2 as "1 Qdrant query + O(results) get_object" with
no enumeration cost. Coherence gap between §201 and §408, and an unstated dependency.
**Fix:** State explicitly that the count is always computed via the `list_objects`
enumeration (regardless of tier), and reconcile the Resource Impact Tier-2 line to include
the enumeration cost.

---

## SUGGESTION

### G1 — Tie behavior at the threshold is correct but only the upper bound is stated
**Where:** §202 ("Mode flips at `count >= threshold` (200 inclusive)").
The boundary is unambiguous (`>=`), and the matrix (§211-217) covers 199/200/201/99/100.
Good. Minor: consider adding count==0 to the matrix once B4 is resolved.

### G2 — `file_back` precedence is clear; consider stating it as one ordered rule
**Where:** §268-273. The precedence (True forces, False suppresses, None uses thresholds)
is correct and matches master §511 and ticket. Optional: collapse to a single ordered
"first match wins" list (False → suppress; True → file; None → threshold) to remove any
chance of a two-reading interpretation.

### G3 — Anti-bloat: Decision 2 pseudocode could be a reference (non-blocking)
**Where:** §91-100 reproduces the Qdrant filter construction. This is genuinely new
(it's the locked fix, not in the master), so reproduction is justified. No action needed —
noting only that the `_semantic_search_core` extraction is described twice (§102-103 and
the Reused-Helpers table §512); a single source would be tighter. SUGGESTION only.

---

## Checklist coverage notes (for the record)

- **Req completeness (item 1):** All 5 ticket deliverables map to sections — signature
  §160-170; tiered retrieval+threshold+boundary §199-217; 1-hop cached neighborhood
  §238-251; file-back policy+override §266-273; QA#25+QA#30 pre-checks §296-316. Present.
- **QueryResult field coverage (item 2):** Gaps in B1 (status), B2 (error field), B4
  (retrieval_mode at count==0), S1 (answer on synth error/empty). `filed_back`,
  `query_object_id/deeplink`, `wiki_log_id/deeplink`, `object_count_at_decision`,
  `sources_consulted` have populating paths (modulo S2/S3). `query_object_id=null when not
  filed` is implied by schema `|null` but never stated in prose — fold into B1/B2 fix.
- **Acceptance criteria (item 3):** Ticket ACs all have a corresponding AC; boundary matrix
  covered (AC #3). The reindex-retrievability contract fails the CI-backstop requirement
  (B3).
- **Ambiguity (item 4):** S3 (contributed-to-answer), S5 (word count), B1 (status). file_back
  precedence OK (G2). Tie behavior OK (G1).
- **Edge cases (item 5):** zero candidates (B4), synthesis empty (S1), deleted cited object
  (S4), duplicate candidates (S2) — all currently unspecified.
- **Internal coherence (item 6):** master diagram (normative) vs prose — pipeline prose
  matches the diagram steps. Schema-vs-error-handling mismatch (B2); Resource-Impact-vs-count
  mismatch (S6). No diagram/pseudocode drift found in the tier routing itself.
- **Anti-bloat (item 7):** Spec is lean (~540 lines, 15 ACs) and within the scope brief's
  ≤~15 AC target. Only G3 noted.

---

## Conditions to clear NEEDS REVISION → APPROVED
Resolve B1–B4 (status rules, error field, CI reindex backstop, empty-wiki path). S1–S6 are
strongly recommended before implementation (they will otherwise surface as test-phase
ambiguities). SUGGESTIONS optional.
