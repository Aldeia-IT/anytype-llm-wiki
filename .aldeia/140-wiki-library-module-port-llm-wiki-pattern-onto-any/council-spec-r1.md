# Council Meeting — Post-spec (Round 1)

**Date:** 2026-04-22
**Ticket:** #140 — Wiki Library Module: Port LLM Wiki Pattern onto Anytype
**Phase reviewed:** spec
**Client:** anytype-llm-wiki (open-source, MIT-licensed; pipeline tickets in aldeia-box)
**Spec under review:** `.aldeia/140-wiki-library-module-port-llm-wiki-pattern-onto-any/spec.md` — 1910 lines, `status: SPEC`, `review_rounds: 1`, approved by round-2 specialist review.

## Attendance

| Role | Present | Reason |
|------|---------|--------|
| Council Chair | Yes | moderator |
| Chief Security Officer | Yes | minimum roster; SSRF, prompt-injection, write-token, and extraction-exfiltration surfaces are prominent |
| Legal Counsel | Yes | chair decision: MIT OSS distribution, hosted-LLM consent flow, trademark nominative use, README as legal surface |
| Chief Product Officer | Yes | minimum roster |
| QA Director | Yes | chair decision: per-version ACs + test plan are central spec deliverables; prior R1 advisories on concurrent ingest, boundary test, and mock strategy carry forward |
| Infrastructure Lead | Yes | chair decision: `fcntl.flock` concurrency redesign, resource-impact table, schema migrations, doctor command, community deployment burden |
| Chief Technology Officer | Yes | minimum roster; codebase verification across a repo renamed mid-ticket (anytype-rag → anytype-llm-wiki); reviewer diligence audit of R1/R2 |
| Client Advocate | No | anytype-llm-wiki is Jan's own open-source project, not a client engagement; CPO represents Jan's interest. Consistent with product-phase council decision. |

## Context Presented

Post-spec review of ticket #140 — the wiki library module that ports the Karpathy LLM Wiki pattern onto Anytype, distributed publicly as an MIT-licensed pip package via the new `anytype-llm-wiki` repo (formerly `anytype-rag`).

**What was delivered during the spec phase:**

- `spec.md` promoted from PRODUCT (796 lines, carried over from aldeia-box) to SPEC (1910 lines) with per-version Scope/MoSCoW/AC/Deliverables/Dependencies/Risks/Pre-release checklist for v0.2.0, v0.3.0, v0.4.0, v0.5.0; four Mermaid diagrams (delivery-phase dependency graph, ingest, query, lint); concrete return schemas for all four MCP tools (BootstrapResult, IngestResult, QueryResult, LintReport) each carrying `wiki_log_id`; full `normalize_title` pseudocode with explicit Unicode dash-fold table applied BEFORE casefold; SSRF implementation via `socket.getaddrinfo` with defense-in-depth blocklist, scheme/userinfo/port allowlists, streamed size cap; `fcntl.flock` kernel-held concurrent-ingest lock (replaces `O_CREAT|O_EXCL` — eliminates PID-reuse race, stale-lock detection, TOCTOU); three-layer prompt-injection defense (`<source>` fence, pydantic name policy, `is_central` cross-check); `_BaseAnytypeClient` shared transport scaffold; `anytype-llm-wiki doctor` command with 8 checks; Resource Impact table with per-operation RSS/wall-time budgets across 32/16/8 GB tiers; schema-version compatibility checks per tool; CHANGELOG + MIGRATIONS policy; self-cleaning verification script with `trap` cleanup of a throwaway probe object.
- Two rounds of specialist review. Round 1 produced 6 BLOCKING, ~30 SHOULD-FIX, ~37 SUGGESTION findings (completeness, architecture, security, infra). Round 2 verified all BLOCKING and SHOULD-FIX resolved and landed all SUGGESTIONs spot-checked. All 9 ADVISORY findings from the product-phase council were addressed.
- Ported pipeline artifacts: `spec.md` (product), `product-brief.md`, `product-review-r1.md`, `product-review-r2.md`, `council-product-r1.md`, all research files — copied from the aldeia-box worktree where ticket #140 originally lived before the repo move, committed to `.aldeia/140-.../` so the full pipeline history is visible in the public repo.

**Jan's ticket feedback (carried into scope):** "make sure it's well structured and documented withstanding the scrutiny of open source communities"; "delivery has many layers — think about the phases of delivery to spec out exact scope and requirements that must be met at each point." Both addressed directly: the per-version structure is the backbone of the spec; OSS-grade scrutiny is visible in the review files, the security posture, and the Contributor's Map.

## Discussion

### CSO Assessment

**SIGN OFF.** The security posture moved from "adequate with homework" at R1 to "coherent and defensively-layered" at R2.

All seven SSRF invariants are in place (getaddrinfo, multi-address iteration, IPv4-mapped IPv6 normalization, defense-in-depth blocklist, scheme allowlist, userinfo rejection, timeouts + streamed size cap). The CSO specifically endorsed the `is_central` cross-check as "the smartest line in this spec — it treats the extractor's output as untrusted and requires corroboration against the source before granting fast-path treatment." Write-token scope flow (AC v0.2.0 #9 + `[CONFIG ERROR] insufficient_token_scope` with Settings → API remediation pointer) is robust.

The most significant fix between R1 and R2: the verification script originally would have mutated an operator's real Anytype object. Two independent reviewers (security + infra) caught the foot-gun; the spec-phase lead escalated to BLOCKING during consolidation. Fix is `trap cleanup EXIT INT TERM` on a throwaway `__wiki_verify_probe__` type + probe object. "Release-blocker-quality catch."

Residual risks named: DNS rebinding (accepted under single-operator threat model; weakens if operators expose `wiki_ingest` to untrusted callers — see Advisory #1), endpoint-hash-keyed acknowledgement is operator-scoped not network-scoped (hostile DNS / CDN repoint won't re-prompt), port allowlist permits 8080/8443 (intentional but worth documenting), bandit false-positives on SSRF-aware code (pre-agree a baseline).

Cross-thread: flagged Advisory #1 (threat-model paragraph) to CPO for README inclusion; flagged SECURITY.md absence (Advisory #7) to Legal. Both picked up.

### Legal Counsel Assessment

**SIGN OFF WITH CONDITIONS.** MIT license integrity is clean: all new and existing runtime dependencies (httpx BSD-3, markdownify MIT, fastmcp Apache-2.0, qdrant-client Apache-2.0, pydantic v2 MIT, bge-m3 MIT) are MIT-compatible. No GPL/AGPL contamination risk.

**"First Anytype-native LLM wiki" positioning:** the "to our knowledge" qualifier + documented pre-release verification step (searching Anytype forum + anytype-mcp + GitHub) + committed fallback one-liner together constitute a reasonable-diligence defense against false-advertising / unfair-competition theories under both Brazilian CDC Art. 37 and US Lanham Act §43(a). Sufficient.

**README privacy notice:** addresses all five substantive points raised at the product council — localhost-only default, URL-fetch egress, hosted-LLM content transmission, Qdrant/Ollama off-localhost warning with embedding-inversion consideration (G16), and explicit user-as-controller framing with PII responsibility. **GDPR/LGPD publisher posture:** Aldeia-IT as MIT publisher of a locally-executed OSS tool with no telemetry sits outside controller/processor definitions under both regimes. No publisher exposure absent a hosted-instance offering (out of scope).

**Hosted-LLM consent flow (G25):** endpoint-hash-keyed acknowledgement file is proportionate for a single-operator tool. Satisfies informed-consent norms.

Conditions are advisory follow-ups (SECURITY.md + coordinated disclosure, SBOM at tag time, Anytype trademark footer, hosted-LLM provider ToS pass-through reminder, LGPD-specific phrasing refinement, embedding-inversion wording tightening). Legal specifically endorsed SECURITY.md + SBOM as the two items that should land on the v0.2.0 pre-release checklist.

### CPO Assessment

**SIGN OFF WITH CONDITIONS.** The spec is product-ready.

**Per-version scope discipline (structural response to Jan's feedback):** each of v0.2.0/v0.3.0/v0.4.0/v0.5.0 has its own Scope (in/out), MoSCoW, numbered ACs, Deliverables, Dependencies, Risks+Mitigations, Pre-release checklist. Each version is internally shippable — you could freeze development after any tag and have a coherent artifact. **"This directly answers Jan's ticket comment about 'phases of delivery' and is the strongest structural response in the spec."**

**200-object threshold (R1 ADVISORY):** mechanical behavior nailed by AC v0.4.0 #3 and the 199/200/201 boundary test. What's not addressed: whether 200 is the right *default*. The concern was empirical (a user with 20 articles at 8–10 objects/article hits 200 in month one). Recommend v0.4.0 pre-release add one concrete validation step.

**Persona fit:** All three personas served. Primary Jan (each version delivers a workflow he will use); Secondary Anytype community developer (pip-install, doctor, Comparisons table); Tertiary Aldeia reputation signal (README positioning, privacy/content-rights sections, CHANGELOG if adopted per Advisory #4).

**Open biggest product concern:** v0.2.0 as a standalone community release is weak value alone. Adopter gets schema + doctor + verification script — no ingest, no query. The "15-minute bootstrap-to-value" quick-start promise requires v0.3.0 to be honest. **Recommend v0.2.0 ship as a "preview" tag in CHANGELOG prose (not semver prerelease) framed as "reserve a namespace, run preflight, contribute schema feedback" — or, better, hold the PyPI publish until v0.3.0 and tag v0.2.0 only in git.**

Conditions: v0.2.0 framing (ADV #1), 200-threshold empirical validation (ADV #2), positioning-prior-art PR reproducibility (ADV #3), CHANGELOG/Keep-a-Changelog adoption (ADV #4), OQ #3 status contradiction (ADV #5 — marked CLOSED but still "provisional — validation at v0.3.0").

### QA Director Assessment

**SIGN OFF WITH CONDITIONS.** ACs and Test Plan are unusually disciplined for a pre-impl artifact.

**AC quality:** three well-formed examples identified (v0.3.0 #6 normalize_title dash-fold parametrized over 8 codepoints; v0.3.0 #5 concurrent ingest with three independent assertions; v0.4.0 #3 boundary at 199/200/201 zero-ambiguity). One weak AC: v0.2.0 #7 ("`verify-anytype-writes.sh` prints an unambiguous decision") — "unambiguous" is human-judged, not mechanically assertable. Not a blocker because the script is maintainer-local.

**R1 advisories all landed cleanly:**
- Concurrent ingest → AC v0.3.0 #5 + `fcntl.flock`-based serialization + Test Plan line naming three-call scenario
- 200-object boundary → AC v0.4.0 #3 + seed via `WikiClient.create_object` with respx mocks (exactly what S37 asked for)
- Mock strategy → lines 1324–1331 enumerate unit/integration/cassette tiers, `freezegun` for time, `respx` for API-failure simulation, Hypothesis scoped correctly to `ExtractionModel` parsing rather than entity resolution (which uses parametrized tables)

**Regression guard:** adequate. Versioned test layout means v0.3.0's changes to `util.py` run against v0.2.0's `test_util.py`. `_BaseAnytypeClient` changes trip both existing and new client tests.

**Failure-modes table:** 5 of 6 critical rows have ACs. Corrupted `patch-decision.md` is design-documented but not traced to a named AC (minor gap).

**Real test-coverage gap (one advisory):** v0.5.0 MoSCoW says "9 check enum values" but the Test Plan names tests only for 4 of them. `contradiction_unresolved` (passive), `oversized`, `empty_type`, `stale_stub`, and `potential_duplicate` have no named test case. This is the only substantive coverage hole.

Other conditions: pre-release checklists are convention-only (not CI-enforced — a second contributor could tag a release with failing items); performance gates lack a contributor-hardware tier (<30s/<5s/<60s are Jan's Mac Mini M4 numbers only).

### Infrastructure Lead Assessment

**SIGN OFF WITH CONDITIONS.** Spec is operationally deployable; conditions are documentation follow-ups.

**Three biggest infrastructure wins since R1:**
1. `fcntl.flock` adoption (S27/S28) collapses three failure classes (PID-reuse race, TOCTOU-on-stale-lock-replace, SIGKILL-mid-lock-write) into zero. Kernel is the single source of truth for liveness. NFS limitation documented with `WIKI_LOCK_DIR` override. 0o700 dir / 0o600 file permissions (G17) prevent multi-user-host observation.
2. Schema migrations (S31) properly designed: `WIKI_SCHEMA_VERSION` + per-tool entry-time compat check + three outcomes (missing/older/newer) + MIGRATIONS.md. Newer-schema client correctly downgrades to warn-and-continue rather than hard-fail — right call for a single-operator tool.
3. Failure-modes table covers every realistic operational edge: Anytype-500, Ollama unreachable with `ollama_model_not_pulled` hint, Qdrant unreachable with tier-fallback, extraction-JSON malformed, concurrent ingest, reindex failure (B2 — warning not error), empty source, disk full, SIGKILL mid-lock, `patch-decision.md` corrupted, Anytype-Version drift.

**Deployment risk on Mac Mini:** low. Additive code in the existing process; no launchd changes, no containers, no Colima impact. ≤500 MB RSS per tool call is negligible against 32 GB. Ollama and Qdrant resident sets already paid for by v0.1.0.

**What breaks if this fails:** individual tool calls return error responses. No cascading failure. WikiLog preserves the audit trail. Data durability anchored in Anytype's vault, not the module's state — correct architecture for a layer-on-top tool.

Conditions: doctor should add a filesystem-type probe on `WIKI_LOCK_DIR` to warn on NFS/SMB (Adv #1); 16 GB tier needs a model-swap warning when `WIKI_EXTRACT_MODEL` is a ≥7B variant (Adv #2); Qdrant growth estimate should be re-validated against actual v0.1.0 collection size during v0.3.0 pre-release (Adv #3); lint 60s/500-object budget accepted as-is but benchmarks implicit in AC (Adv #4); README needs a single "Prerequisites at a glance" block for 60-second community evaluator decision (Adv #5); verification-script-not-in-CI policy endorsed (Adv #6); all-perf-gates-on-Jan's-hardware is honest (Adv #7); dependency chain realistic for solo maintainer (Adv #8).

### CTO Assessment

**SIGN OFF.** All codebase-verification claims hold under independent spot-check.

**Independent verification performed:**
- `src/anytype_llm_wiki/server.py`: exactly two `@mcp.tool()` registrations (lines 12, 67) — `semantic_search` and `reindex_anytype`. Matches spec claim.
- `src/anytype_llm_wiki/anytype_client.py`: `_client()` constructs fresh `httpx.Client` per call at line 17, each entry point uses `with _client() as c:` (lines 21, 29, 42). Confirms the S14 "divergent sessions" risk is real; `_BaseAnytypeClient` fix is the right minimum intervention.
- `pyproject.toml`: `fastmcp>=2.0.0` at line 10; `name = "anytype-llm-wiki"` at line 2; wheel target `packages = ["src/anytype_llm_wiki"]`; script entrypoint `anytype-llm-wiki = "anytype_llm_wiki.server:main"`. All spec claims hold.
- Grep `anytype_rag|anytype-rag` under `src/`: zero matches. Under `.aldeia/140-*/spec.md`: zero matches. Only surviving mentions are in historical product/research artifacts (intentional) and a single deliberate README historical callout. R2's PASS finding holds independently.
- Git log confirms rename landed in `c31db58 chore: rename package anytype-rag -> anytype-llm-wiki` before spec phase began.

**Reviewer diligence:** real verification, not document-only review. R1 architecture reviewer ran the `normalize_title` pseudocode in Python and empirically caught the U+2011-not-folded-by-NFC bug. R1 infra reviewer flagged the `O_CREAT|O_EXCL` race and escalated to `fcntl.flock`. R1 lead spot-checked `anytype_client.py:16` per-call httpx.Client and `type_key` flow through server.py:42 → indexer.py:95 → chunker.py:21. R2 is a true delta-verification with line-number citations for every resolved finding. R2 verdict earned.

**Design quality:** dash-fold-before-casefold ordering is correct (casefold doesn't touch U+2010–U+2014, U+2212, so folding after would leave inequality). `fcntl.flock` is the right primitive — zero stale-detection code is a win. `_BaseAnytypeClient` scope (transport-only) is appropriately narrow. 6-file v0.2.0 layout is appropriately lean. `patch-decision.md`-as-arbiter + doctor-step-8 enforcement prevents dual-path fallback code.

Conditions: watch for `anytype-rag` leakage into new code during implementation (Adv #1); doctor step-2 short-circuit on Anytype-unreachable (Adv #2); `_BaseAnytypeClient` scope reminder to prevent list/get method creep (Adv #3); `atexit.register` for module-scoped httpx.Client socket cleanup (Adv #4); `wiki_status` reconsideration trigger strengthened by Jan's own daily operator experience (Adv #5).

### Cross-thread resolutions

- **CSO ↔ Legal** on SECURITY.md: both members independently raised `SECURITY.md` + coordinated disclosure as a gap. Consolidated into a single consensus item. Both agreed it should land on the v0.2.0 pre-release checklist, not in a v0.2.x patch.
- **CSO ↔ CPO** on threat-model paragraph: CSO's Advisory #1 (DNS-rebinding / OSS-threat-model drift) was flagged to CPO for README inclusion. CPO picked it up as part of the README-framing advisory.
- **CPO ↔ QA** on 200-threshold default validation: CPO's empirical-default concern was flagged for the v0.4.0 pre-release. QA's R1 advisory on the boundary mechanics is satisfied by AC v0.4.0 #3 independently. The two items are complementary, not duplicative.
- **QA ↔ Infra** on performance gates: QA's observation that all perf ACs cite "Jan's Mac Mini M4" overlaps with Infra's reference-hardware framing advisory. Consolidated: the gates should be marked measured-by-maintainer-at-release-time, with optional degraded contributor tier for local PR validation.
- **CTO ↔ Infra** on `_BaseAnytypeClient` lifecycle: CTO flagged that the spec does not specify teardown for MCP server process; Infra's review of observability/configuration did not surface this because the impact is practically nil. Noted as CTO Advisory #4.
- **CTO ↔ QA** on lint check-count mismatch: QA's Advisory #3 (5 of 9 lint checks have no named test) is the most substantive test-coverage gap the council identified. Inherited from R2-SG2 (MoSCoW wording vs LintReport enum); the spec-phase lead partially resolved this inline but the Test Plan remains incomplete.

## Findings

### BLOCKING

None.

### ADVISORY

1. **[CSO + CPO]** Add an OSS threat-model paragraph to the README before v0.3.0 actually fetches URLs. The spec's DNS-rebinding-as-residual stance assumes a single-operator model; community users wiring `wiki_ingest` behind shared MCP endpoints or auto-ingest pipelines widen this. One paragraph in the README telling operators not to expose `wiki_ingest` to untrusted callers is the minimum mitigation.

2. **[CSO + Legal]** Ship `SECURITY.md` with coordinated-disclosure contact on the v0.2.0 pre-release checklist. MIT-licensed pip-distributed security-sensitive code handling third-party content is expected to provide a disclosure channel (GitHub Security Advisories + email contact + supported-version statement). Two council members independently raised this.

3. **[Legal]** Produce a CycloneDX/SPDX SBOM at tag time via `uv export --format cyclonedx` (or equivalent) attached to each GitHub Release. Not legally required today; trending toward baseline expectation (EU CRA, US EO 14028 derivatives) and increases downstream-consumer trust.

4. **[Legal]** Add a README "Trademarks" footer disclaiming Anytype affiliation and acknowledging Anytype as the mark holder. Pre-v0.2.0 check of Anytype's current brand guidelines for any naming constraints on community integrations. Nominative fair use is defensible; the footer is inexpensive insurance.

5. **[Legal]** Add one sentence to the hosted-LLM privacy notice reminding the operator that the **provider's own Terms of Service, data-retention, and training-on-input policies apply** to that traffic (notably OpenAI's opt-out-to-avoid-training posture, Anthropic's no-train-by-default, Azure/AWS enterprise variants). One sentence; avoids the support question "why did my wiki content end up in a model."

6. **[CPO]** Reconsider v0.2.0's PyPI publication strategy. An adopter who pip-installs v0.2.0 gets schema + doctor + verification script — no ingest, no query. The "15-minute bootstrap-to-value" promise requires v0.3.0. Options: (a) hold the PyPI publish until v0.3.0 and tag v0.2.0 only in git; (b) publish v0.2.0 to PyPI framed explicitly as a preview ("reserve namespace, run preflight, contribute schema feedback"), not as "try the Karpathy pattern." The README must not oversell v0.2.0.

7. **[QA]** Close the lint-check test-coverage gap. v0.5.0 MoSCoW says "9 check enum values" (8 structural + 1 sweep) but the Test Plan's Lint section names tests for only 4 of the 9. Add explicit AC + test-case lines for `contradiction_unresolved` (passive), `oversized`, `empty_type`, `stale_stub`, and `potential_duplicate` before test-writing begins.

8. **[QA + Infra]** Mark the three performance ACs (v0.2.0 <30s bootstrap, v0.4.0 <5s query, v0.5.0 <60s lint/500-objects) as maintainer-measured-at-release-time or add a documented degraded contributor-hardware tier for local PR validation. All three gates currently cite "Jan's Mac Mini M4" — unreproducible for community PR authors.

9. **[QA]** Promote pre-release checklists from convention to CI-enforced where practical. Many items are CI-checkable (pytest, pip-audit, bandit, `uv lock --locked`, gitleaks) and some are not (verification-script rerun, manual demos). Suggest a `.aldeia/pre-release-{version}.md` template the tagger must commit, with an auto-check that all boxes are `[x]` before a tag push. Matters more as soon as there's a second maintainer.

10. **[CPO]** OQ #3 is marked CLOSED but still "provisional — empirical validation tracked as v0.3.0 pre-release." Closed-yet-provisional is a contradictory state. Relabel to "DEFAULT SET, validation gate at v0.3.0 pre-release" or leave open until validated.

11. **[CPO]** Adopt Keep-a-Changelog format in CHANGELOG.md on v0.2.0, with a MIGRATIONS section-header stub for future breaking changes. Low cost, high credibility signal for OSS reviewers.

12. **[CPO]** For the "first Anytype-native LLM wiki" verification step, record the searched queries + dates + zero/non-zero findings verbatim in the v0.2.0 PR description so a future reader can reproduce the verification. A single unrecorded forum search is a weak gate for a public claim.

13. **[CSO]** Tighten the default port allowlist to `{None, 80, 443}` and let operators extend via env var. 8080/8443 are common internal-dev-server ports; defense-in-depth preferred. Low cost.

14. **[CSO]** Add a regression test that a failure from Qdrant with an embedded API key in the URL does not surface that key in `[API ERROR]` strings. The spec's mask set (line 1614) covers Authorization/Bearer but does not assert non-leakage of `QDRANT_API_KEY` or `WIKI_EXTRACT_ENDPOINT` query strings.

15. **[CSO]** Pre-agree a `bandit` baseline file or `# nosec` annotations with rationale for the SSRF fetch layer. Prevents a drive-by contributor PR from being told "bandit says no" and weakening the actual defense.

16. **[CSO]** For v0.4.0 (query), consider whether extracted entity names should be shown verbatim in CLI output vs. length-clamped and control-char-stripped at render time too. Defense-in-depth for prompt-injection-derived names that survived the extraction pipeline.

17. **[CSO]** Note the endpoint-ack limitation: `sha256(endpoint)[:8]` re-prompts on endpoint change but does NOT re-prompt if the same hostname resolves to a new provider (CDN repoint, MITM, hostile DNS). Document in README.

18. **[Infra]** Add a 9th doctor check: `statfs(WIKI_LOCK_DIR)` → WARN if filesystem type is in `{nfs, nfs4, smbfs, cifs, fuse.sshfs}`. `fcntl.flock` doesn't serialize on network filesystems and a community operator whose `$HOME` is on NFS would get a silent non-serializing lock.

19. **[Infra]** Doctor should WARN on 16 GB hosts when `WIKI_EXTRACT_MODEL` is a ≥7B variant, suggesting the 3B fallback. Ollama's model-swap behavior (bge-m3 + qwen2.5:7b back-to-back) triggers swap on 16 GB even when start-of-ingest RAM looks fine.

20. **[Infra]** Re-validate the "~50 MB per 100 sources" Qdrant growth estimate against actual v0.1.0 collection size during v0.3.0 pre-release.

21. **[Infra]** Add a single README "Prerequisites at a glance" block for the 60-second community-evaluator decision: Python 3.11+, uv, Anytype desktop, Qdrant container, Ollama with pulled models, 16 GB min / 32 GB recommended. Call out `anytype-llm-wiki doctor` as the first post-install command.

22. **[CTO]** During implementation, watch for `anytype-rag`/`anytype_rag` leakage into new code snippets or install instructions. Historical callouts in `README.md:5` and the product/research artifacts are appropriate to retain; new code is not.

23. **[CTO]** Consider short-circuiting doctor after a step-2 Anytype-unreachable FAIL for future Anytype-touching checks (current 8 checks are safe; future checks that assume reachability could silently multi-fail).

24. **[CTO]** Add a one-line reminder in the spec that `_BaseAnytypeClient` is transport-only (session + headers + timeout + close()). Implementers will be tempted to lift `list_spaces`/`list_objects`/`get_object` into the base; those are read-plane concerns.

25. **[CTO]** Register `atexit.register(_shared_client.close)` on the module-scoped httpx.Client so lint tools and long test runs don't complain about open sockets. FastMCP doesn't expose a shutdown hook in stdio mode; process exit closes sockets but the explicit registration is hygiene.

26. **[CTO + CPO]** Strengthen the `wiki_status` reconsideration trigger. "≥3 community issues OR v0.4.0 pre-release user reports" may never fire in a low-traffic early OSS project even if the gap is real. Add Jan's own daily operator experience as a third trigger.

## Resolutions

- **CSO's initial DNS-rebinding concern** was raised as part of the OSS-threat-model drift argument. After discussion, both CSO and CPO agreed that a README threat-model paragraph is the cheapest mitigation; no code change is gating implementation start. Consolidated as Advisory #1.
- **Legal's SECURITY.md + SBOM emphasis** was initially framed as two separate advisories; CSO's parallel flag on SECURITY.md confirmed this should be tier-1 (on the v0.2.0 pre-release checklist), while SBOM can sit at tier-2 (v0.2.x patch acceptable if not v0.2.0-blocking).
- **CPO's v0.2.0 standalone-release concern** was discussed against QA's endorsement of per-version shippability. Resolution: the per-version structure is correct engineering; the concern is marketing framing, addressed via Advisory #6 without changing the spec's version boundaries.
- **QA's lint check-count mismatch** (Advisory #7) was flagged by R2 as SG2 and the spec-phase lead resolved the MoSCoW wording inline but not the Test Plan coverage. The council judges the Test Plan gap substantive enough to surface as an advisory item — the spec will advance, but the gap must close before test authoring begins. Non-blocking because test authoring is the next phase's first task.
- **Infra's doctor NFS check** (Advisory #18) and CTO's `_BaseAnytypeClient` scope reminder (Advisory #24) — both agreed these are spec-polish items that can land in the spec itself during pre-implementation and do not gate impl phase start.
- **No council-level dissent.** All six members signed off.

## Recommendation

**Recommended target:** test
**Confidence:** high
**Rationale:** Every council member signed off. Zero BLOCKING findings. Round-2 specialist review had already verified all R1 BLOCKING and SHOULD-FIX resolved. Jan's explicit feedback ("delivery has many layers — spec exact scope and requirements at each point") is directly answered by the per-version Scope/MoSCoW/AC/Deliverables structure — unanimously endorsed as the strongest structural response in the spec. The OSS-scrutiny bar (also Jan's feedback) is met: the spec demonstrates codebase verification, explicit security posture (7 SSRF invariants + 3-layer prompt-injection defense + kernel-held concurrent-ingest lock), and a verification-script-gated approach that prevents silent dual-code-path fallback. Codebase-alignment claims verified independently by the CTO against the real repo.

The 26 advisories span documentation polish, release-engineering discipline, community-evaluator UX, and defense-in-depth hardening. None gate implementation start. The single substantive test-coverage gap (QA Advisory #7: 5 of 9 lint checks have no named test) must close before test authoring begins but is appropriately handled in the next phase's opening steps.

The next natural SDLC phase after spec is **test** — and the QA Director's sign-off on AC observability/determinism means test authoring can proceed. Starting work on v0.2.0 (bootstrap + schema + verification-script + doctor) as the first shippable slice is the CPO's and the spec-phase lead's consistent recommendation; this can happen via test → impl in sequence, or Jan may elect to split v0.2.0 into its own implementation ticket. That routing decision is Jan's via autonomy policy; the council's engineering judgment is that the spec is ready to move forward.

**Dissent:** None. All six council members signed off.
