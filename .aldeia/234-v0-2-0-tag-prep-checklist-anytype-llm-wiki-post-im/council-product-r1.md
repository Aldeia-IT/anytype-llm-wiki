# Council Meeting — Post-product (Round 1)

**Date:** 2026-05-30
**Ticket:** #234 — v0.2.0 tag-prep checklist (public-release collateral)
**Phase reviewed:** product
**Client:** anytype-llm-wiki (Aldeia-IT — first public open-source release)

## Attendance

| Role | Present | Reason |
|------|---------|--------|
| Council Chair | Yes | moderator |
| Chief Security Officer | Yes | minimum; SECURITY.md / CRA / data-posture owner |
| Legal Counsel | Yes | minimum; licensing, trademark, positioning-claim owner |
| Chief Product Officer | Yes | minimum; "shine" bar, positioning, release readiness |
| Client Advocate | Yes | chair decision — Aldeia's first public OSS release; Jan's reputational stake + adopter first-impression |
| QA Director | No | no test surface; doc-vs-code accuracy verification explicitly deferred to Implement (CTO-owned) |
| Infrastructure Lead | No | no deployment/ops surface in a docs-only product phase |
| Chief Technology Officer | No | technical/developer docs + live verification explicitly deferred to Implement, where CTO reviews |

## Context Presented

Jan delegated #234 to the Product team to ready the **public-release collateral** for `anytype-llm-wiki` v0.2.0 — the company's first open-sourced module, intended to "shine" for GitHub publication and LinkedIn/social promotion. Deep technical/developer docs, CI, automated license-scanning, and all live-environment verification were explicitly deferred to a later Implement (tech) phase.

Product delivered and committed: `SECURITY.md`, `NOTICE`, `CONTRIBUTING.md`, `CHANGELOG.md`, `MIGRATIONS.md`, `positioning-verification.md`, and a **staged** `README-additions.md` (not applied — see B3). A 4-phase workflow produced drafts; the lead then corrected numerous factual errors (invented commands/flags, wrong binary name, PyPI install commands) against the real implementation before committing.

A structural complication frames the whole review: **#234 was branched from stale v0.1 `main`.** The real v0.2.0 code AND the rewritten v0.2.0 README live on the **unmerged #140 branch**. Product therefore deliberately staged README changes rather than editing the stale base.

## Discussion

The council converged quickly on a shared picture, with strong cross-functional reinforcement:

- **The committed collateral is genuinely strong** — all four members independently judged SECURITY/NOTICE/CONTRIBUTING/CHANGELOG/MIGRATIONS professional and (with the exceptions below) ship-ready. The lead's correction pass closed the draft honesty defects: Client Advocate and CPO both verified the committed files now use the correct binary, flags, deps, and no PyPI install. Credit to Product for scope discipline (no gold-plating; correctly deferred tech items).

- **The README is the dominant risk (CPO ↔ Client Advocate).** Both independently found that the README the world would actually see is the **stale v0.1 document**: broken install commands (`uv tool install` / `pip install` — package is not on PyPI, so the adopter's first copy-paste fails), an empty quick-start code block, a self-contradictory roadmap (ingestion listed under v0.2), a public link to the internal `aldeia-box#140` tracker, and none of the new `wiki-bootstrap`/`doctor` commands. Publishing as-is would produce exactly the embarrassment this release exists to avoid. Both stressed this is a **sequencing** blocker, not a collateral-quality failure — Product's staging decision was correct.

- **Positioning "first" claim (Legal lead, CPO + Client Advocate concurring).** The live README (line 3) and CHANGELOG (line 18) carry "first" claims. Our own committed record `positioning-verification.md` concludes the superlative is **not defensible**: `wethegreenpeople/anytype-mcp` (April 2025) is comparable prior art — Anytype-native, MCP-served, semantic search + RAG via Ollama — and is listed in Anytype's official developer docs. Legal escalated this from the phase summary's "product/legal call" framing to **BLOCKING**, noting the internal record proving knowledge of prior art converts an innocent overstatement into a knowing misrepresentation (false-advertising / unfair-competition exposure). CPO and Client Advocate both argued the swap *strengthens* the marketing story (a publicly-checkable "first" claim invites a humiliating launch-day correction; the honest "MCP-native, local-first, typed" pitch needs no policing).

- **CRA date — a factual error (CSO), resolving a contradiction with Legal.** CSO performed web verification against the European Commission's own CRA pages and found SECURITY.md's claim that Article 14 reporting obligations "apply from 11 June 2026" is **wrong**: 11 June 2026 is when Chapter IV (notification of conformity assessment bodies) applies; Article 14 reporting obligations apply from **11 September 2026**. Legal's A5 had asserted the June date "accurate" without the same verification depth. **Resolution (chair):** the CSO's evidence-based finding prevails — the date is wrong and must be corrected. Legal's substantive guidance stands and is complementary: keep the "aligns with / reflects expectations" voluntary-alignment hedging, do **not** escalate to an affirmative "CRA compliant" claim, and note the CRA's manufacturer obligations may not even bind a free, non-commercial OSS preview (significant carve-outs). A consequence: the phase summary's "hard CRA date gate satisfied at 2026-06-11" framing is incorrect on both counts (wrong date; gate may not apply at all).

- **Supply-chain posture (CSO ↔ Client Advocate).** `README-additions.md` §2 and a CHANGELOG bullet describe present-tense controls (CI `uv lock --locked`, `pyproject.toml` minor-range upper bounds) that the phase summary lists as **not yet implemented** (tech-owned). Documenting a control as enforced before it exists is an overstatement. Both agreed: keep staged, and gate the application of §2 on the controls actually landing in Implement.

## Findings

### BLOCKING

1. **[CSO] CRA Article 14 date is factually wrong in SECURITY.md** — `SECURITY.md:79` states Article 14 reporting obligations "apply from 11 June 2026." Correct date is **11 September 2026** (11 June 2026 = Chapter IV / notification bodies, unrelated to vulnerability reporting; verified against the European Commission CRA pages). A wrong, externally-verifiable legal citation in the security policy of a security-consulting firm's flagship public release is an unacceptable credibility risk. **Action:** change the date to 11 September 2026; keep the existing voluntary-alignment hedging (do not upgrade to a "CRA compliant" claim — Legal A5). Product-owned committed file; one-line fix. *Also correct the same erroneous gate framing carried in the phase summary.*

2. **[Legal; +CPO, +Client Advocate] "First" superlative is not defensible — must not appear in any tagged-commit README/CHANGELOG** — `README.md:3` ("The first open-source LLM wiki…") and `CHANGELOG.md:18` ("the first open-source release…"). `positioning-verification.md` (our own dated, corroborated record) concludes "first" is indefensible for the semantic-search/MCP surface v0.2.0 ships, given `wethegreenpeople/anytype-mcp` prior art listed in Anytype's official docs. The internal record proving knowledge of the prior art aggravates the exposure to a *knowing* misrepresentation. **Action (BLOCKING):** no public `v0.2.0` tag while any README/CHANGELOG reachable at the tagged commit asserts "first" in the semantic-search/MCP sense. Removing "first" is mandatory; the choice of replacement wording (the proposed non-superlative line) is advisory. Apply consistently across README **and** CHANGELOG (the CHANGELOG "first … release of this project" is more defensible but should be reworded for consistency, e.g. "Initial public release (preview)").

3. **[CPO; +Client Advocate] The publishable README is the stale v0.1 document** — `README.md` on this branch has broken install commands (`uv tool install` / `pip install` — package not on PyPI), an empty quick-start code block, a self-contradictory roadmap (ingestion under "v0.2+", dotted `wiki.bootstrap` names), a public link to the internal `aldeia-box#140` tracker, and omits the v0.2.0 `wiki-bootstrap`/`doctor` commands. Tagging/publishing as-is would actively damage the reputation this release is meant to build. **Action:** do not tag until the documented sequence completes — **merge #140 → rebase #234 onto `main` → apply `README-additions.md` onto the #140 README → re-review the assembled README → tag.** This is a sequencing blocker; Product's decision to stage rather than edit the stale base was correct.

### ADVISORY

1. **[CPO; +Client Advocate] MIGRATIONS.md step-4 heading "Index and serve"** (`MIGRATIONS.md:48`) echoes the invented `index`/`serve` subcommands (which do not exist); body text is correct. Rename to e.g. "Run the MCP server." Product-owned, quick fix before tag.
2. **[Legal] Copyright-holder name inconsistency** — `LICENSE:3` and `NOTICE:2` read "Aldeia IT"; `business.md:6` names the entity "Aldeia IT Consulting." Reconcile the copyright notice to the registered legal entity (confirm with Jan) before tag. Low-effort, do once correctly at the OSS provenance root.
3. **[CSO; +Client Advocate] Supply-chain posture documented as enforced before implementation** — `README-additions.md` §2 + CHANGELOG bullet assert present-tense CI `uv lock --locked` and `pyproject.toml` minor-range bounds that are not yet in the repo (tech-owned). Gate application of §2 / the CHANGELOG supply-chain bullet on those controls actually landing in Implement.
4. **[CSO] SECURITY.md reporting channels are not yet operable** — GitHub private vulnerability reporting must be enabled on the repo (the "Report a vulnerability" path), and the Aldeia-IT org-profile email backup is currently absent (CSO fetched the profile: no public email). Enable at least one private channel before tag, so the committed 72h-ack / 14-day-triage SLA is real. Implement / live-verification.
5. **[Legal] NOTICE transitive-license audit deferred** — acceptable and correctly scoped. Gate the tag on the deferred license-scan confirming **no copyleft** (watch AGPL specifically for a network-served MCP) in the resolved `uv.lock` tree; surface any surprise to Legal.
6. **[Legal; CSO crossover] Data-privacy "no telemetry / local-only" claims** must be live-verified (no network egress beyond documented local endpoints) before the public claim ships. Implement live-verification.
7. **[CPO] Differentiation vs the official `anyproto/anytype-mcp` is underused** — "we add semantic search the official MCP lacks" is a sharp, true value prop. Marketing upside to fold into the assembled README during Implement.
8. **[CPO; +Client Advocate] `positioning-verification.md` path mismatch** — committed at repo root here; the #140 README links it at `.aldeia/140-.../positioning-verification.md`. Reconcile path/location during rebase to avoid a broken internal link.
9. **[CPO; +Client Advocate] CONTRIBUTING.md project-structure tree** (`CONTRIBUTING.md:17-27`) was likely seeded from the checklist, not verified against real #140 source; v0.2.0 added `wiki-bootstrap`/`doctor` modules not reflected. Refresh against the merged #140 tree (or replace with a pointer) during Implement.
10. **[Client Advocate] Surface the release go/no-go to Jan explicitly** — the merge→rebase→apply→verify→tag sequence currently lives buried in the phase-summary risks list. Jan (sole decision-maker) should receive it as a one-line decision.
11. **[CSO] Scrub internal `aldeia-box#140` link** from the assembled README before tag (latent; lives on the #140 branch). Verify no internal ticket refs / branch names in the final public README.

## Resolutions

- **CRA-date contradiction (CSO vs Legal) resolved in CSO's favor** on the factual point (date is 11 September 2026, not 11 June 2026), with Legal's hedging/scope guidance retained as complementary. The phase-summary "date gate satisfied" rationale is recorded as incorrect.
- **Positioning re-classified** from the phase summary's "product/legal call" to a **BLOCKING** pre-tag condition (Legal), with CPO + Client Advocate concurring it is also the stronger marketing choice. The *replacement wording* remains an advisory product call.
- **Unanimous agreement** that the committed collateral is high quality and the README/sequencing is the real release gate — not a collateral-quality defect. No member's BLOCKING was downgraded.

## Recommendation

**Recommended target:** `decide`
**Confidence:** high
**Rationale:** The council unanimously sign off on the *quality* of the committed product collateral but **veto a public `v0.2.0` tag** in the current branch state. The release is gated on decisions only Jan (sole decision-maker) can make — merge #140 first, approve the positioning swap, and approve the merge→rebase→apply→verify→tag sequence — plus genuine BLOCKING fixes that should be carried into the next hands-on phase (Implement, post-#140-merge). Routing to **Decide** lets Jan absorb the findings, make the strategic calls, and dispatch Implement with the full picture. The BLOCKING and key advisory items are captured as authoritative acceptance criteria in `spec-addendum-post-product-r1.md` so the Implement phase honors them. A pure product-rework loop is not the right vehicle because the dominant blockers (#140 merge, positioning approval, release sequencing) require Jan, not another product pass.
**Dissent:** None.
