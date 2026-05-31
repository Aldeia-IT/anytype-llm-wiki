# #234 — interactive cleanup summary (read me first)

Jan and the lead did an **interactive pass** on this branch after the post-product council
routed it to Decide. This note is the authoritative handoff for the Spec/Implement phases.
It supersedes the staged `README-additions.md` (now consumed and deleted).

## Sequencing — #231 is MERGED; this branch is rebased & reconciled (ready for Implement)

**#231 ("Supply-chain security hardening") MERGED to `main` (b3ee36f, 2026-05-31).** It shipped
the CI/hardening half of this ticket's checklist — these are **DONE on `main`, do not
re-implement here**:

- `.github/workflows/{ci,release,audit}.yml` (merge-gate: `uv lock --check` + frozen install +
  pytest on 3.11/3.13; tag-gate: pip-audit + cache-free build + **build-provenance attestation**
  + **OIDC Trusted Publishing** + the fold-244 scanners bandit/pip-licenses/gitleaks)
- all GitHub Actions SHA-pinned; release builds cache-free; `.github/dependabot.yml`;
  `pyproject.toml` `hatchling==1.29.0` pin; `docs/dependency-intake.md`, `docs/releasing.md`.

**This branch has been re-rebased onto `main` (with #231) and the overlap reconciled:**
- `CONTRIBUTING.md` — git folded #234's "Licensing of contributions" (inbound=outbound + DCO)
  onto #231's file (intake/CI guidance); both present, nothing lost.
- `README.md` — kept #234's full v0.2.0 assembly; took #231's `uv sync --all-extras` dev-setup;
  folded #231's build-provenance verify (`gh attestation verify`) into the **Supply-chain
  posture** section (reframed honestly for the not-yet-on-PyPI status).

Do **not** tag v0.2.0 yet — run Implement for the residual below.

## Done in this interactive pass (committed on this branch)

- **Rebased #234 onto `main`** (which now has #140's merged v0.2.0 code + README).
- **README.md assembled for v0.2.0** (the council's BLOCKING #3 — the publishable README was
  the stale v0.1 doc):
  - Dropped the **"first Anytype-native LLM wiki"** superlative → non-superlative positioning
    line (Jan APPROVED). Removed the stale status note + internal `aldeia-box#140` link + the
    "first"-defense paragraph.
  - Fixed **broken install** (`uv tool install` / `pip install` — not on PyPI) → source install
    via `uv sync`.
  - Added the real v0.2.0 quick-start flow: `doctor` → `wiki-bootstrap` + version stamp.
  - Fixed the empty "Index and search" section and the stale 2-tool table → accurate **3 MCP
    tools** (`semantic_search`, `reindex_anytype`, `wiki_bootstrap`).
  - Fixed the **Auto-reindex** broken command (`anytype-llm-wiki-reindex` is not an entry point)
    → the real `indexer.reindex()` invocation the sample plist uses.
  - **Roadmap retag**: `wiki-bootstrap` + `doctor` moved to *shipped (v0.2.0)*; ingestion
    (`wiki.ingest`/`query`/`lint`) is *v0.3.0*. Schema types verified against
    `wiki/types_schema.py` (Source, Entity, Concept, Comparison, Query, WikiLog).
  - Added **Supply-chain posture** + **Trademarks** sections (CPO/Legal items).
- **SECURITY.md** — corrected CRA Article 14 date **11 June → 11 September 2026** (council
  BLOCKING #1).
- **CHANGELOG.md** — reworded the "first open-source release" line to neutral versioning
  language (council BLOCKING #2 / Jan APPROVED drop-"first").
- **File naming**: moved `positioning-verification.md` from the repo root into this work folder
  (internal process record, not public collateral); deleted the consumed `README-additions.md`.

Product collateral now ship-ready on this branch: README, SECURITY.md, NOTICE, CONTRIBUTING.md,
CHANGELOG.md, MIGRATIONS.md.

## Implement-phase residual (post-#231) — pre-tag acceptance criteria

Authoritative criteria are in **`spec-addendum-post-product-r1.md`** (this folder). Net of #231,
the remaining tag-gating work is:

1. ~~Re-rebase onto `main` after #231 merges.~~ **DONE (2026-05-31)** — rebased onto b3ee36f;
   CONTRIBUTING/README overlap reconciled (see Sequencing above).
2. **Make the README "Supply-chain posture" section true before tag:** #231's CI now supplies the
   `uv lock --check`. The **`pyproject.toml` minor-range upper bounds** (e.g. `>=1.2,<1.3`) are
   **still NOT applied** — #231 pinned only the `hatchling` build dep, not the runtime deps. Add
   the runtime-dep upper bounds (or soften the README claim) before tag.
3. **Version bump** `pyproject.toml` `0.1.0` → `0.2.0` (still 0.1.0).
4. **License-scan / `.bandit` / gitleaks — NOT #234's job (deduped 2026-05-31).** These were
   folded into **#231**'s impl scope (see #231 `spec-addendum-fold-244.md`); they land on #231's
   tag/audit CI. The former tracking ticket **#244 is closed**. Do **not** re-implement them in
   #234. (Likewise `SECURITY.md` is #234's — #231 will not duplicate it.)
5. **Developer-doc polish** (Jan's product/tech split — tech owns dev docs): confirm the exact
   source-install MCP registration command works as written; verify the "FastMCP v3" comparison
   detail.
6. **Live-environment verification** (un-CI-able; needs running Anytype/Qdrant/Ollama):
   `verify-anytype-writes.sh` run + commit `patch-decision.md`; `doctor` green (strict exit-0);
   cross-host bootstrap dedup probe (two hosts + shared vault — `fcntl.flock` is single-host
   only); p95 < 30s bootstrap on the Mac Mini M4; `wiki-bootstrap --space-id <real>` demo. If the
   live run shows the guessed REST endpoints (`/properties`, `/properties/{pk}/options`) differ,
   small `wiki_client.py` fix before tag.
7. **Final checks**: `uv run pytest` green · `pip-audit` clean · `bandit -r src/` clean ·
   `uv lock --locked` green · `gitleaks` clean · then `git tag v0.2.0`.

## Positioning note

`positioning-verification.md` (this folder, dated 2026-05-30) records that
`wethegreenpeople/anytype-mcp` (Apr 2025) is comparable prior art. The honest, non-superlative
framing is now in the README and the Comparison table lists that project openly. Keep this record;
do not reintroduce "first".
