# README product additions — apply during Implement phase (post-rebase)

**Why this is a staging file and not a direct README edit:** ticket #234 was branched from
v0.1 `main`. The real v0.2.0 README (with the refined positioning line and the full
"Privacy and data flow" section) lives on the **unmerged** `#140` branch
(`aldeia/wiki-library-module-port-llm-wiki-pattern-onto-any`). Editing the stale v0.1 README on
this branch would conflict with and duplicate `#140`'s work. These additions are written to drop
cleanly onto the **`#140` README** once `#140` is merged and `#234` is rebased onto `main`.

Verified facts these additions rely on (from the `#140` implementation):
- Binary/entry point: `anytype-llm-wiki`. CLI subcommands: `wiki-bootstrap`, `doctor`. No-arg run = MCP server.
- `anytype-llm-wiki wiki-bootstrap --space-id <id> [--domain-tags a,b,c] [--dry-run] [--json]`
- `anytype-llm-wiki doctor [--json]`  (NOTE: `doctor` takes no `--space-id`)
- Default embedding model: `bge-m3`. Direct runtime deps: fastmcp, httpx, qdrant-client, psutil.
- There is NO `index`/`serve` subcommand and NO `--force` flag (the workflow draft invented these).
- The package is NOT on PyPI; install is from source via `uv sync` (do not document `pip install`/`uv tool install`).

---

## 1. Quick-start — version stamp + bootstrap/doctor

Add a version line at the top of the Quick start section and make the v0.2.0 flow explicit:

> **Version: v0.2.0 (preview).** A typical first-time setup takes about 5 minutes. v0.2.0 ships
> the bootstrap + health-check + semantic-search foundation; automated content ingestion arrives
> in v0.3.0.

Use a reproducible source install (the package is not yet on PyPI), then the v0.2.0 flow:

```bash
# Install from source
git clone https://github.com/Aldeia-IT/anytype-llm-wiki.git
cd anytype-llm-wiki
uv sync

# Configure
cp .env.example .env   # set ANYTYPE_API_KEY (+ any non-default endpoints)

# 1. Verify the environment is ready (read-only; exits 0 only when all checks pass)
anytype-llm-wiki doctor

# 2. Provision the wiki schema in your space (idempotent; safe to re-run)
anytype-llm-wiki wiki-bootstrap --space-id <your-space-id>
#    --dry-run to preview, --domain-tags a,b,c to customize tags, --json for scripts

# 3. Register the MCP server with your client (see "Register as MCP server"); run it directly with:
anytype-llm-wiki
```

Also update the v0.1-era tool table / roadmap to the final scope: v0.2.0 = `wiki-bootstrap` +
`doctor` + semantic search; v0.3.0 = content ingestion. (The `#140` README roadmap still lists
`wiki.ingest`/`wiki.query`/`wiki.lint` under v0.2 and uses dotted `wiki.bootstrap` — retag those to
v0.3.0 and to the hyphenated `wiki-bootstrap` CLI name, and remove the internal aldeia-box#140 link.)

## 2. NEW section — "Supply-chain posture" (place after Architecture / before Roadmap)

```markdown
## Supply-chain posture

We pin dependencies in two layers so installs are both reproducible and resilient:

- **`uv.lock` — exact, hashed versions.** Every dependency (direct and transitive) is locked to
  an exact version with a content hash. `uv sync` reproduces the same dependency tree on every
  machine, and CI runs `uv lock --locked` to guarantee the lockfile is in sync with `pyproject.toml`.
- **`pyproject.toml` — compatible ranges with minor-range upper bounds.** Direct dependencies
  declare a lower bound and a minor-range upper bound (for example `>=1.2,<1.3`) so a transitive
  resolution can't silently jump to an unreviewed minor and break the build.

Together these give adopters reproducible installs today and a controlled, reviewed upgrade path
over time.
```
(Tech note for Implement: the minor-range upper bounds are a `pyproject.toml` edit owned by the
tech team — see the tag-prep checklist. This section documents the intent.)

## 3. NEW footer section — "Trademarks" (place at the very bottom, after License)

```markdown
## Trademarks

Anytype is a trademark of Any Association. This project is not affiliated with, sponsored by, or
endorsed by Any Association or the Anytype project. The Anytype name is used solely to identify
the platform this software integrates with.
```

## 4. Positioning claim — RECOMMEND SWAP (decision for Jan / council)

`positioning-verification.md` (committed on this branch) records a real web-search check dated
2026-05-30, independently corroborated. Finding: **`wethegreenpeople/anytype-mcp` (April 2025)** is
comparable prior art — Anytype-native, MCP-served, semantic search + RAG over Anytype via local
Ollama embeddings, and listed in the official Anytype developer docs.

Therefore the `#140` README intro line *"To our knowledge, the first Anytype-native LLM wiki…"*
carries avoidable risk: even hedged, "first" is contestable for the semantic-search/MCP surface
that v0.2.0 actually ships. The typed-wiki differentiation is real but its pipeline ships in v0.3.0.

Recommended replacement intro (non-superlative, still distinctive):

> **An MCP-native semantic search and LLM wiki for your [Anytype](https://anytype.io) knowledge
> base — local-first, typed, and built on Anytype's native Objects, Types, and Relations.**

This is a product/legal call (CPO #20 / Legal #13). If Jan/council prefer to keep the hedged
"first" framing, that is defensible too — but the swap removes an ongoing claim-policing burden.
Whichever is chosen, keep `positioning-verification.md` as the dated record, and align its
referenced path (the `#140` README links it at `.aldeia/140-.../positioning-verification.md`,
but it is currently committed at the repo root on this branch).
