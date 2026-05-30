# Spec Addendum — post-product council (R1)

**Source:** [`council-product-r1.md`](council-product-r1.md)
**Date:** 2026-05-30
**Target phase:** Implement (tech) — to run after Jan's Decide routing and after #140 is merged
**Status:** Authoritative — the Implement phase MUST honor these items as spec requirements (pre-tag exit criteria for v0.2.0).

## Additional acceptance criteria for the Implement phase

These are gating conditions for cutting the public `v0.2.0` tag. The council vetoed the tag in the current branch state; these conditions clear the veto.

### Must-fix (BLOCKING) — no `v0.2.0` tag until all are satisfied

1. **[CSO-B1]** Correct the EU CRA citation in `SECURITY.md:79`: Article 14 reporting obligations apply from **11 September 2026** (not 11 June 2026; 11 June 2026 is Chapter IV / notification of conformity assessment bodies). Keep the existing voluntary-alignment wording ("aligns with / reflects expectations"); do **not** upgrade to an affirmative "CRA compliant" claim. This is a product-owned committed file and may be fixed immediately — it does not depend on the #140 merge.

2. **[Legal-B1, +CPO, +CA]** Remove the indefensible "first" superlative from **every** README/CHANGELOG reachable at the tagged commit. Currently present at `README.md:3` ("The first open-source LLM wiki…") and `CHANGELOG.md:18` ("the first open-source release…"). Apply the non-superlative replacement from `README-additions.md` §4 / `positioning-verification.md` to the assembled README, and reword the CHANGELOG line for consistency (e.g. "Initial public release (preview) — the start of public versioning"). Removing "first" is mandatory; the exact replacement wording is Jan's/Product's call. Retain `positioning-verification.md` as the dated substantiation record.

3. **[CPO-B1, +CA-B1]** Do not tag or publish until the assembled, current README is in place. Execute the sequence: **merge #140 → rebase #234 onto `main` → apply `README-additions.md` onto the #140 README → re-review the assembled README (Product/council cold-read) → tag.** The assembled README must: use only working install instructions (source install via `uv sync`; the package is NOT on PyPI — remove `uv tool install` / `pip install`), contain a working quick-start (`doctor` → `wiki-bootstrap` → run server), present a coherent roadmap (v0.2.0 = bootstrap+doctor+semantic-search foundation; v0.3.0 = ingestion) using hyphenated CLI names, and contain **no** internal `aldeia-box#` links or internal branch names.

### Must-verify before tag (BLOCKING gates owned by Implement)

4. **[CSO-A4]** Enable an operable private vulnerability-reporting channel before tag: turn on GitHub private vulnerability reporting on the repo and/or publish a contact email on the Aldeia-IT org profile (currently none is visible). The committed 72h-ack / 14-day-triage SLA must be real and monitored.

5. **[CSO-A3, +CA-A4]** Gate the "Supply-chain posture" copy (`README-additions.md` §2 and the CHANGELOG supply-chain bullet) on the underlying controls actually landing: `pyproject.toml` minor-range upper bounds and a CI `uv lock --locked` step. Do **not** publish the present-tense claim before the control exists.

6. **[Legal-A2]** Run the deferred transitive license-scan against the resolved `uv.lock` tree and confirm **no copyleft** (watch AGPL specifically for a network-served MCP). Surface any finding to Legal. Reconcile `NOTICE` against the final resolved dependency set.

7. **[Legal-A6, CSO crossover]** Live-verify the "no telemetry / all data stays local" claim (no network egress beyond documented local Anytype/Qdrant/Ollama endpoints) before the public claim ships.

### Should-fix (advisory, strongly recommended before tag)

8. **[CPO-A1, +CA-A3]** Rename the `MIGRATIONS.md:48` heading "Index and serve" (echoes non-existent `index`/`serve` subcommands) to e.g. "Run the MCP server." Product-owned committed file; may be fixed now.
9. **[Legal-A1]** Reconcile the copyright holder name across `LICENSE:3` and `NOTICE:2` ("Aldeia IT") to the registered legal entity (confirm with Jan; `business.md` names "Aldeia IT Consulting").
10. **[CPO-A3, +CA]** Reconcile the `positioning-verification.md` path during rebase (root vs the `.aldeia/140-...` path the #140 README links) to avoid a broken internal link.
11. **[CPO-A4, +CA-A5]** Refresh the `CONTRIBUTING.md:17-27` project-structure tree against the merged #140 source (add `wiki-bootstrap`/`doctor` modules) or replace with a pointer.
12. **[CPO-A2]** Consider adding the official `anyproto/anytype-mcp` (CRUD/search, no semantic search) to the README comparison framing — "we add semantic search the official MCP lacks" is a sharp, honest differentiator.

## Rationale

Items 1, 8, and 9 are small factual corrections to already-committed product collateral; they could be applied in a product touch-up but are folded here because the next hands-on pass is Implement (post-#140-merge) and they are cheap to batch there. Items 2 and 3 cannot be completed on this branch because the real v0.2.0 README lives on the unmerged #140 branch — applying README fixes on the stale v0.1 base would conflict with and duplicate #140, which is exactly why Product staged rather than edited. Items 4–7 are operational/verification gates that require the live environment and repo settings, explicitly within the Implement (tech) mandate. The council recorded all of these so that "advancing" the ticket does not silently lose the conditions that protect the public release — the single artifact a developer (and Jan's LinkedIn audience) judges first is the README, and it is currently stale.
