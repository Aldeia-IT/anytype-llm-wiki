# Council Meeting — Post-Spec (Round 1)

**Date:** 2026-06-03
**Ticket:** #284 — anytype-llm-wiki v0.3.0 — `wiki_ingest` compile pipeline
**Phase reviewed:** spec (status SPEC; internal review R2 APPROVED, zero open findings)
**Client:** anytype-llm-wiki (open-source MIT; **v0.3.0 is the first public PyPI release**)

## Attendance

| Role | Present | Reason |
|------|---------|--------|
| Council Chair | Yes | moderator |
| Chief Security Officer | Yes | minimum; SSRF + prompt-injection + new embedding surface + first public release |
| Chief Product Officer | Yes | minimum |
| Chief Technology Officer | Yes | minimum; verify code-grounded claims + reviewer diligence |
| QA Director | Yes | heavy AC/test surface; deferred live gates; provisional thresholds |
| Infrastructure Lead | Yes | repo domains infrastructure/agent-operations; indexer/Ollama/Qdrant/fcntl, deployment |
| Legal Counsel | Yes | first public PyPI release; dependency licensing; off-machine extraction disclosure |
| Client Advocate | Yes | rich `.aldeia/context/`; open-source community is a distinct stakeholder |

Near-full council seated deliberately: a first public release with material surface across every governance angle.

## Context Presented

v0.3.0 `wiki_ingest` is the "compile" step of the wiki ("compile once, query later"). It is an **increment spec** that references the council-approved master spec (#140) and concentrates on: (1) closing a newly-discovered **release-blocker retrieval gap** — curated wiki objects store knowledge in *properties* but the indexer only embedded the markdown *body*, so freshly-curated wikis produced `objects_indexed: 0` and were invisible to `semantic_search`; (2) reconciling the schema-version marker home (Decision 2) and `wiki_action` select-tag pre-creation (Decision 3) — two v0.2.0 loose ends; (3) **locking three now-verified Anytype API constraints** (body-PATCH silently ignored, type-key FilterExpression no-op, property-PATCH works) and deleting the master spec's speculative dual code paths. The spec is unusually code-grounded and was driven by the lesson of v0.2.0, which shipped a *guessed* Anytype write contract that was wrong end-to-end.

## Discussion

The council split cleanly into two camps that did not contradict each other — they reviewed different surfaces.

**The four sign-offs (CSO, CTO, Legal, Infrastructure).** The CTO performed the deepest verification: he spot-checked ~14 load-bearing `file:line` claims against the worktree source (`chunker.py:14-19`, `types_schema.py:25` = `"0.2.0"`, `bootstrap.py:123-129/248-254/374-387/410-418/480-485`, `indexer.py:64-75`, `wiki_client.py:85-109`, `patch-decision.md`) and found **zero inaccuracies**. He judged the empty-body-on-create invariant (Decision 1 / §5.1) structurally sound on both create and update — the single `chunk_object` call site (`indexer.py:75`) makes the branch analysis complete — and judged the spec-phase review **diligent and code-grounded** (R1's B2 "locally-reasonable / globally-broken" catch is real; the fix is coherent). The CSO confirmed the SSRF/injection/secrets posture is mature and — importantly — now *pinned by ACs* (AC-L1/L2/S1, AC#16 value-sanitization) rather than prose, closing the silent-regression class. Infrastructure confirmed the qwen2.5:7b resource envelope fits the Mac Mini (~9-10 GB co-resident) and the fcntl.flock design is correct. Legal cleared the MIT posture.

**The three BLOCKING camps (CPO, QA, Client Advocate) converged on one theme.** Independently, all three flagged that the spec's verification strength is **inverted**: mechanical chunker unit tests are MUST/CI-runnable, but the thing that *is* the product — end-to-end retrievability of an ingested object — is verified only by `@pytest.mark.live` ACs (AC-P2, AC-P7) and a SHOULD-level gate (V3). QA additionally found a hard coverage hole: **AC-P2 (create-side end-to-end retrieval) has no test row in §9 at all** — it is an acceptance criterion with no verification artifact. All three named this the exact v0.2.0-class risk (an unverified core contract) repeating one phase later, under pre-release time pressure, on a first public release. This is the dominant finding of the meeting and it is triangulated by three independent reviewers, with no dissent from the other four (their lenses simply did not cover test-gate strength).

The Client Advocate raised a second BLOCKING item the other reviewers echoed at advisory level: the optional off-machine `WIKI_EXTRACT_ENDPOINT` contradicts the project's headline **"local-first / no cloud"** promise (`product.md`, `compliance.md`) for public users who point it at a hosted LLM. Legal (Advisory 3) and CSO (A2) concurred the disclosure must be firmed and the consent banner confirmed to ship; the context docs are now stale.

Legal flagged a factual defect in the spec's own checklist (Advisory 1): §10.1/§11 name the wrong pydantic transitive tree (lists markdownify's `beautifulsoup4`+`six`, omits `pydantic-core`/`typing-extensions`/`annotated-types`; `typing-extensions` is **PSF-2.0, not MIT**; `pydantic-core` bundles vendored Rust crates). Legal asked this be a hard pre-publish gate.

## Findings

### BLOCKING

1. **[CPO-B1 / QA-B1 / QA-B2 / CA-B1] The core retrievability promise is verified only by deferred/optional gates — the v0.2.0-class risk repeating.** (a) **AC-P2** (after `wiki_ingest` creates an entity, `semantic_search` returns it) has **no §9 test row** — an AC with no verification artifact (QA-B1). (b) Gate **V3** (`objects_indexed > 0` on the 22-object `llm-wiki-test` space — the exact metric that was 0 in the repro) is only a **SHOULD**; it should be **MUST/release-blocking** (CPO-B1, CA-B1). (c) **No CI-runnable seam test** backstops the live-only path `chunk_object → indexer → embed → Qdrant upsert → semantic_search`; a future refactor of `indexer.py` (dropping `properties[]` before `chunk_object`, or re-introducing a `last_modified_date` short-circuit) would regress silently with a fully green CI (QA-B2). **Recommended action:** add a §9.2 live row for AC-P2 (or fold a *named-entity* retrieval assertion into V3, not just aggregate `objects_indexed`); promote V3 to MUST/release-blocking and name AC-P2/AC-P7 as non-skippable pre-tag gates in §10.1; mandate at least one CI-runnable integration test with a mocked/fake Qdrant+embedder asserting a property-only (empty-body) object's reindex produces a Qdrant upsert carrying the property chunk's `text`/`heading`. This backstops the live gates rather than replacing them.

2. **[CA-B2 | concurred: Legal-Adv3, CSO-A2] First public release ships a "local-first / no cloud" tool that can silently send source content off-machine.** `WIKI_EXTRACT_ENDPOINT` pointed at a hosted LLM exfiltrates fetched source content (and, for local-file ingest, the operator's own notes), directly contradicting `product.md` ("Local-first… No cloud dependencies") and `compliance.md` ("No cloud services, no telemetry"). The §11 docs plan treats this as a one-line note. **Recommended action:** confirm/specify the endpoint defaults to on-device Ollama (local-by-default) with a conspicuous opt-in; promote the disclosure from a doc note to an **AC** (e.g. AC-S2) binding a prominent README data-flow callout; confirm the master spec's first-run off-machine **consent banner** actually ships and fires in v0.3.0 (currently only the credential *scrub* AC-S1 is pinned, not the consent banner); reconcile `compliance.md`/`product.md` to "local-first by default, explicit opt-in remote-extraction exception."

### ADVISORY

1. **[Legal-Adv1 — treat as hard pre-publish gate]** Correct the §10.1/§11 NOTICE & `pip-licenses` dependency list to the actual pydantic v2 tree (`pydantic-core` MIT, `typing-extensions` **PSF-2.0 not MIT**, `annotated-types` MIT) plus markdownify's (`beautifulsoup4`, `six`); change "all MIT" → "all OSI-permissive (MIT/PSF/BSD)"; generate NOTICE from the **resolved venv** (`pip-licenses --from=mixed`), not a hand-curated list; note `pydantic-core` bundles vendored Rust crates a Python-level scan won't see. Accurate attribution is MIT's one substantive obligation and this is the first public distribution.
2. **[Legal-Adv2 / CA-A2]** Add a README "Responsible ingestion" note: users own the copyright/ToS/robots status of sources they ingest; stored `wiki_excerpt` + derived facts may carry source-license obligations (Wikipedia = CC BY-SA attribution/share-alike). Optionally send an identifying User-Agent. *(GC note: source-handling/usage-policy thinking ideally surfaces in the **product** phase for content-ingesting features, not at legal sign-off.)*
3. **[Legal-Adv4 / CA-A4 / CSO-A1]** Add an "LLM-extracted — verify before relying" provenance caveat to the README; ensure the master "do not trust retrieved wiki content as instructions" note actually appears in the v0.3.0 README, since this release is the first to make property values retrievable (the widened embedding surface, SF2).
4. **[CSO-A2]** Pin (AC or checklist) that the off-machine extraction **first-run consent banner** ships and fires when `WIKI_EXTRACT_ENDPOINT` is non-local. *(Folded into BLOCKING-2.)*
5. **[CSO-A4]** Carry the master CSO-Advisory-#6 annotated `.bandit` baseline into the §10.1 checklist so "bandit clean" means clean-against-a-rationale-documented-baseline, not blanket `# nosec` suppression of the intentional SSRF primitives in `fetch.py`.
6. **[CPO-B2 → advisory]** Gate MIGRATIONS.md / known-limitations.md #2 finalization to the **V4-selected** marker branch so the first public migration story doesn't describe the unshipped option.
7. **[QA-A1 / Infra-A3]** Reconcile the V2-fail wording: §4.1 says release-blocking full-reindex; §10.2 still says "file a follow-up ticket." Add a deterministic test that the full-reindex bypass fires on the update path; prefer an **object-scoped** re-embed (delete+re-upsert by `object_id` payload filter) over a whole-space sweep, which grows with corpus size.
8. **[QA-A2/A3/A5/A6]** Add §9 rows for: the post-upgrade round-trip (AC-M5, currently only half-tested); the *delta'd* inherited AC#8 response shape (`objects_skipped: []`); the SF9 guard test asserting exactly one marker mechanism ships; the known-limitations G5 "v0.5.0→v0.3.0" doc correction as a §10.1 checklist item.
9. **[QA-A7 / CPO-A2]** Treat the AC#18 idempotency disposition as a release-blocking *recorded* decision; confirm the "document duplicate-Source workaround" branch is acceptable product behavior (it visibly weakens AC#2 idempotence under partial failure).
10. **[CPO-A1 / CA-A2 / Infra-A1]** Document provisional dedup thresholds and the hardware/extraction-quality dependency (qwen2.5:3b on 16 GB is degraded) honestly in the README; ensure first-run flow routes users through `doctor` so the RAM-fit WARN is seen; add an Ollama-OOM-mid-extraction row to the failure-modes table.
11. **[CPO-A3 / CA-A6]** README retrievability note should pre-empt "why is the body empty?" — operators inspecting an ingested object in the Anytype client see an empty body (the invariant) and may conclude ingest is broken.
12. **[Infra-A2/A4]** File the deferred `wiki_facts` soft-cap ticket; add a Qdrant collection-size / Colima-RSS watch for the long-running internal deployment; confirm `reindex_anytype` concurrency safety (deterministic Qdrant point IDs) or guard the launchd-reindex vs post-ingest-reindex overlap with a flock.
13. **[CTO-A1/A2/A3]** Pin the canonical path AC#15 reads for `patch-decision.md` (it lives under the #140 parent dir, no #284 copy); tag AC-M5 "gated on V4 PASS"; note V3 implicitly validates the unproven `markdown`-key assumption in the `format=md` response.

## Resolutions

No findings were withdrawn during discussion. The four sign-offs and the three BLOCKING positions are **not in conflict** — they cover different surfaces (technical accuracy/security/ops/legal vs. test-gate strength/release honesty). The CTO's "no blocking" verdict is scoped to technical accuracy and reviewer diligence and does not contradict the QA/CPO/CA test-coverage findings; the gap they found is in test-strategy rigor (over-reliance on deferred live gates), not in the spec's technical correctness. The council records consensus that the **design is sound and the spec is ~90% done** — the BLOCKING items are surgical amendments to §8/§9/§10/§11, not a redesign.

## Recommendation

**Recommended target:** spec (focused Round-3 revision)
**Confidence:** high
**Rationale:** The spec is technically excellent — every load-bearing code claim verified true, the design coherent, the v0.2.0 lesson correctly encoded (lock verified constraints, delete speculative paths). But three independent reviewers raised BLOCKING findings that converge on the single most important property of this release: that the retrieval gap it exists to close is *provably* closed before ship. As written, that proof rests on a SHOULD gate, a live test with **no test row at all** for the create path, and no CI backstop — the same shape of "unverified core contract" that broke v0.2.0, deferred one phase. The cleanest place to close these is the spec itself (add the AC-P2 test row, promote V3 to MUST, mandate a CI seam test, pin the local-first disclosure AC, correct the NOTICE tree). These are bounded, well-specified edits; a targeted spec R3 makes the document genuinely self-contained for the test phase rather than relying on an addendum the next phase must remember to honor.

**Alternative for the decision-maker:** If Jan prefers to advance to the test phase now and carry the three BLOCKING clusters as hard, tracked acceptance criteria (the findings above are precise enough to serve as a test-phase brief), that is a defensible call given the design is sound — but the council's majority recommendation is to bake them into the spec first, because the central failure mode here is exactly "ship before the core promise is verified."

**Dissent:** None unresolved. CSO, CTO, Legal, and Infrastructure signed off on their surfaces with advisories only; CPO, QA, and Client Advocate hold conditional/veto positions pending the BLOCKING items. No member contradicts another.

*Note (training wheels):* `config/council.yaml` `autonomous: []`, so this recommendation routes to Decide for Jan's ruling regardless of target.
