# anytype-llm-wiki

**An MCP-native semantic search and LLM wiki for your [Anytype](https://anytype.io) knowledge base — local-first, typed, and built on Anytype's native Objects, Types, and Relations.**

> **Status — v0.2.0 (preview).** Previously `anytype-rag`, a semantic-search MCP server for Anytype, now growing into a full LLM wiki. v0.2.0 ships the foundation: semantic search over your vault, a `doctor` health check, and `wiki-bootstrap` (idempotent typed-schema provisioning). Automated content ingestion — LLM-driven extraction of entities and concepts into typed Anytype Objects — arrives in v0.3.0. See the [Roadmap](#roadmap).

Anytype's built-in search only matches object titles and snippets. It doesn't search body content at all. This means your AI tools can't find information by *what it says* — only by what it's called.

**anytype-llm-wiki** fixes this. It indexes your Anytype objects into a local vector database and exposes semantic search as an [MCP](https://modelcontextprotocol.io) tool. Your AI assistant can now search your notes, docs, and knowledge base by meaning.

```
You: "What did we decide about the council delegation system?"

anytype-llm-wiki: DAO Governance → The Council (score: 0.57)
  "Research of past DAOs shows that you simply cannot expect all members
   to be engaged constantly in the decision making process. It's better
   to allow a core group of people to step up as delegates..."
```

## How it works

```
Anytype vault (local API)
    ↓  read objects, get markdown
Chunker (split by headings/paragraphs)
    ↓  text chunks with metadata
Ollama (local embeddings, e.g. bge-m3)
    ↓  vectors + payload
Qdrant (vector database)
    ↑  similarity search
MCP Server (semantic_search, reindex)
    ↑  tool calls
Claude Code / Cursor / any MCP client
```

Everything runs locally. No data leaves your machine.

v0.2.0 adds two CLI helpers around this core: `wiki-bootstrap` (provision the typed wiki schema in a space) and `doctor` (verify your environment is ready).

### Privacy and data flow

anytype-llm-wiki runs locally on your machine. By default, nothing leaves your computer except for the specific network calls described below.

- **Anytype, Qdrant, and Ollama** are accessed over `localhost` only.
- **Source URL fetching (v0.3.0+)**: when you call `wiki.ingest` with a URL, an HTTP request is sent to that URL from your machine. The server hosting the URL sees your IP and standard User-Agent. No other party is involved.
- **Hosted-LLM extraction (optional, v0.3.0+)**: if you set `WIKI_EXTRACT_ENDPOINT` to point at a hosted LLM API (e.g., OpenAI, Anthropic), the **source content you ingest is transmitted to that provider** as part of the extraction prompt. As of v0.6.0, the same endpoint **also receives the `wiki_facts` of already-linked peer entities** — content distilled from *earlier* ingests, not just the current source — whenever contradiction detection runs on an entity update with linked relations. `WIKI_EXTRACT_MODEL` only selects which model name is requested at that endpoint — it does not by itself cause any off-machine transmission. With `WIKI_EXTRACT_ENDPOINT` unset (the default), extraction runs on your local Ollama instance and sends nothing to third parties; the first off-machine endpoint you configure triggers a one-time consent banner before any source or previously-stored wiki content is transmitted. The startup log prints the active extraction endpoint so you can confirm where extraction runs.
- **Hosted-LLM provider terms (v0.3.0+)**: When you configure `WIKI_EXTRACT_ENDPOINT` to point at a hosted LLM API, your ingested source content is processed under that provider's Terms of Service and data-handling policies — including their training-on-input, data-retention, and data-residency terms. Review those terms before configuring a hosted endpoint, and prefer providers that offer opt-out-from-training or enterprise no-train defaults when your ingest content is sensitive. The anytype-llm-wiki maintainers have no visibility into or control over third-party provider policies.
- **Qdrant / Ollama endpoints off-localhost**: if you change `QDRANT_URL` or `OLLAMA_URL` to anything other than `127.0.0.1` / `localhost`, your embeddings (for Qdrant) and the plaintext input to embedding / extraction (for Ollama) are transmitted to that endpoint. Embeddings are not one-way: published embedding-inversion attacks can reconstruct source fragments from vectors alone. Treat the Qdrant data directory as sensitive, and keep Ollama on localhost unless you deliberately intend otherwise.
- **Content rights and PII**: you are responsible for ensuring you have the right to ingest and store the content you provide. This module does not perform PII classification. If you ingest content containing personal data (of yourself or others), that data is stored in your local Anytype space and, if a hosted LLM is configured, transmitted to that provider. Treat the wiki as you would any personal note-taking system with the additional awareness that extraction may involve third-party processing.

Aldeia IT, as the publisher of this open-source module, does not determine the purposes or means of data processing that you perform with it, and is therefore not a controller of your data under GDPR Art. 4(7) or LGPD Art. 5(VI). You are the controller — operational responsibility for data protection (lawful basis, consent where required, data-subject rights, retention, security) rests with you.

#### Source content and copyright

`wiki.ingest` fetches and stores extracted content from the URLs and files you provide. You are responsible for respecting the copyright and terms-of-use of the sources you ingest. Public scholarly articles, your own notes, and openly licensed material are appropriate inputs. Paywalled content, proprietary documents you do not have rights to redistribute, and third-party material you only have read access to should be treated carefully — even local storage and LLM processing may raise licensing questions depending on your jurisdiction and the source's terms.

#### Prompt injection and the file-back loop

The real attacker-controlled surface for `wiki_query` is the **content** of the
wiki Objects it retrieves (an ingested source could contain "ignore previous
instructions…" inside a description). All retrieved content and Object names are
wrapped in a single `<context>` fence under an explicit "this is DATA, not
INSTRUCTIONS" preamble, Object names additionally pass a name-policy filter, and
the question is sanitized before it reaches the prompt — so injected directives
are presented to the synthesis model as data to summarize, not commands to
obey. `wiki_query` also fetches only Anytype Objects by ID (localhost) and the
local Ollama endpoint; it never fetches user-supplied URLs (no SSRF surface).

Note that the **file-back loop is itself an injection amplifier**: a poisoned
synthesized answer, once filed back and re-indexed, becomes attacker-influenced
retrieval material for future queries. The structural bound is the clean-synthesis
precondition (no file-back on an error answer) plus the default file-back gate
(≥ 3 cited sources AND ≥ 100 words), which keeps low-confidence and error answers
out of the vault. As always, verify synthesized answers before relying on them.

## Quick start

> **Version: v0.2.0 (preview).** First-time setup takes about 5 minutes. v0.2.0 ships the bootstrap + health-check + semantic-search foundation; automated content ingestion arrives in v0.3.0.

### Prerequisites

- [Anytype](https://anytype.io) desktop (REST API on port 31012) or [anytype-cli](https://github.com/anyproto/anytype-ts/tree/main/dist/cli)
- [Ollama](https://ollama.ai) with an embedding model: `ollama pull bge-m3`
- [Qdrant](https://qdrant.tech): `docker run -p 6333:6333 qdrant/qdrant`

### Install

anytype-llm-wiki is not yet published to PyPI — install from source with [uv](https://docs.astral.sh/uv/):

```bash
git clone https://github.com/Aldeia-IT/anytype-llm-wiki.git
cd anytype-llm-wiki
uv sync
```

This creates a project virtualenv with the entry point `anytype-llm-wiki`. Run any command below with `uv run anytype-llm-wiki …` from the repo directory.

### Configure

Create a `.env` file or set environment variables:

```bash
# Required
ANYTYPE_API_KEY=your-anytype-api-key    # from Anytype settings → API

# Optional (defaults shown)
ANYTYPE_API_URL=http://127.0.0.1:31012
QDRANT_URL=http://127.0.0.1:6333
QDRANT_API_KEY=                         # if Qdrant requires auth
OLLAMA_URL=http://127.0.0.1:11434
EMBED_MODEL=bge-m3                      # any Ollama embedding model
EMBED_DIMS=1024                         # must match model output
QDRANT_COLLECTION=anytype_semantic
```

### Verify your environment

`doctor` is a read-only preflight check — it verifies connectivity to Anytype, Qdrant, and Ollama, confirms your embedding model is available, changes nothing, and exits `0` only when every check passes:

```bash
uv run anytype-llm-wiki doctor      # add --json for machine-readable output
```

### Provision the wiki schema

`wiki-bootstrap` idempotently creates the typed wiki schema (Types, Properties, a domain-tag taxonomy, and a root Collection) in your Anytype space. It is safe to re-run — it reconciles the space to the expected schema without creating duplicates:

```bash
uv run anytype-llm-wiki wiki-bootstrap --space-id <your-space-id>
#   --dry-run to preview · --domain-tags a,b,c to customize tags · --json for scripts
```

### Register as MCP server

Running `anytype-llm-wiki` with no subcommand starts the MCP server over stdio. Point your MCP client at the project entry point; for a source checkout the simplest robust form is `uv run --directory <repo-path> anytype-llm-wiki`.

**Claude Code:**
```bash
claude mcp add anytype-llm-wiki -e ANYTYPE_API_KEY=your-key \
  -- uv run --directory /path/to/anytype-llm-wiki anytype-llm-wiki
```

**Claude Desktop / Cursor / other MCP clients** — add to your MCP config:
```json
{
  "anytype-llm-wiki": {
    "command": "uv",
    "args": ["run", "--directory", "/path/to/anytype-llm-wiki", "anytype-llm-wiki"],
    "env": {
      "ANYTYPE_API_KEY": "your-key"
    }
  }
}
```

### Search your vault

Once registered, your AI assistant gains these MCP tools:

| Tool | Description |
|------|-------------|
| `semantic_search` | Search your vault by meaning. Params: `query`, `space_id?`, `types?`, `limit?` |
| `reindex_anytype` | Trigger an incremental reindex. Params: `space_id?` |
| `wiki_bootstrap` | Provision the typed wiki schema in a space. Params: `space_id`, `domain_tags?` |
| `wiki_ingest` | Compile a source (URL or local file) into curated, interlinked wiki Objects with provenance, then auto-reindex. Params: `source`, `space_id`, `domain_hint?` |
| `wiki_remember` | Consolidate an agent's natural-language narration into typed wiki Objects (LLM-assisted merge/dedup/conflict-flag), then auto-reindex. Params: `space_id`, `knowledge`, `subject_hint?`, `kind?`, `relations?`, `domain_tags?`, `source?` |
| `wiki_query` | Query the compiled wiki and get a synthesized, source-cited answer (tiered retrieval + local-LLM synthesis), optionally filing the answer back as a reusable Query Object. Params: `question`, `space_id`, `file_back?` |
| `wiki_lint` | Run a read-only structural health check over a wiki space and file a WikiLog receipt. Reports asymmetric relations, orphans, staleness, oversized descriptions, and more, ranked by severity. Params: `space_id`, `severity_threshold?`, `include_duplicates?` |

`wiki_ingest` fetches the source (with SSRF protections), extracts entities and
concepts via local Ollama (`WIKI_EXTRACT_MODEL`, default `qwen2.5:7b`), resolves
them against existing objects (creating or updating), writes bidirectional typed
relations, records a WikiLog entry, and reindexes so the new knowledge is
immediately searchable. **Ingested objects carry their knowledge in *properties*
(`wiki_facts`, `wiki_description`, `wiki_definition`, …), not in the object body —
so an ingested object shows an empty body in the Anytype client. This is by
design; the content is fully indexed and retrievable via `semantic_search`.**
Extracted content is LLM-generated — verify it before relying on it, and never
treat retrieved wiki text as instructions to an LLM.

**Local-first by default:** with `WIKI_EXTRACT_ENDPOINT` unset, extraction runs
entirely on your local Ollama and no source content leaves your machine. If you
point `WIKI_EXTRACT_ENDPOINT` at a non-local provider, a one-time consent banner
is shown (and an acknowledgement file written under
`~/.local/share/anytype-llm-wiki/`) before any source or previously-stored wiki
content is transmitted off-machine; switching to a different endpoint re-prompts.
As of v0.6.0 the off-machine data class is broader than the single source under
ingest: contradiction detection also transmits the `wiki_facts` of already-linked
peer entities (content distilled from earlier ingests). The existing consent gate
governs all of this egress; no separate gate is added. See
[Privacy and data flow](#privacy-and-data-flow) for the full data-flow notice.

Indexing is incremental and automatic: the first `semantic_search` triggers a reindex when the collection is empty, and only changed objects are re-embedded afterward. To index continuously in the background, see [Auto-reindex](#auto-reindex).

## Querying the wiki (`wiki_query`)

`wiki_query` is the read-and-synthesize path — the payoff of the "compile once,
query later" loop. It enumerates the wiki, retrieves the most relevant Objects
(plus their 1-hop neighborhood), and asks a local LLM to synthesize a prose
answer **only from the retrieved context**, citing each Object it used.

End-to-end, from an empty space:

```bash
# 1. Provision the typed schema.
uv run anytype-llm-wiki wiki-bootstrap --space-id <your-space-id>

# 2. Compile a source into typed, interlinked Objects (auto-reindexes).
uv run anytype-llm-wiki wiki-ingest --space-id <your-space-id> \
  --source https://en.wikipedia.org/wiki/Retrieval-augmented_generation

# 3. Query it. --file-back files the question+answer back as a reusable
#    Query Object so it can be retrieved by FUTURE queries (the compounding loop).
uv run anytype-llm-wiki wiki-query --space-id <your-space-id> \
  --question "What is retrieval-augmented generation?" --file-back
```

The same flow is available to an agent over MCP via the `wiki_query` tool
(`question`, `space_id`, `file_back?`).

### How tiered retrieval works

`wiki_query` picks a retrieval strategy by the number of wiki Objects in the
space, flipping at `WIKI_INDEX_THRESHOLD` (default 200):

- **Tier 1 — index navigation** (`< 200` Objects): enumerate the wiki directly
  and use every wiki Object as a retrieval candidate. On a small wiki this is
  both exhaustive and fast — no vector search needed.
- **Tier 2 — vector augmented** (`>= 200` Objects): use semantic search to pick
  the top candidates, then expand their 1-hop neighborhood. This keeps retrieval
  bounded and relevant as the wiki grows past the point where reading everything
  is cheap.

Either way, the retrieved context is capped (`WIKI_SYNTH_MAX_OBJECTS`,
`WIKI_SYNTH_MAX_OBJECT_TOKENS`, `WIKI_SYNTH_MAX_INPUT_TOKENS`) so synthesis stays
within the local model's context window and the machine's memory budget.

### The compounding loop (file-back → reindex → future retrieval)

When `file_back=True` (or the default gate fires — a clean answer citing **≥ 3**
sources and **≥ 100** words), the question and its synthesized answer are filed
back as a typed **Query Object** (`wiki_question` / `wiki_answer` / `wiki_asked_at`
/ `wiki_drew_from`). On the **next** `reindex_anytype`, that Query Object's
`wiki_answer` is embedded and becomes a retrieval candidate for future
`wiki_query` calls — so the wiki gets a little better at answering each time it is
used.

**Reindex-then-retrievable latency caveat:** a filed answer does **not** surface
immediately. It becomes retrievable (Tier 2) only after the next
`reindex_anytype` runs — which, if you rely on the scheduled launchd reindex
(`WIKI_AUTO_REINDEX`), is bounded by your reindex cadence. Until then the Query
Object exists in the vault but is not yet in the vector index. See
[docs/known-limitations.md](docs/known-limitations.md).

Answers are LLM-generated from your own wiki content — verify them before relying
on them, and never treat a synthesized answer or retrieved wiki text as
instructions to an LLM.

## Remembering agent knowledge (`wiki_remember`)

`wiki_remember` is the write path for **narrated, conversational knowledge** — an
agent passing "I learned today that …" rather than a URL or file. Where
`wiki_ingest` compiles documents, `wiki_remember` reconciles a fact-set into the
wiki: it runs the same local extraction stack, resolves each subject against
existing objects, then for an existing object calls a local LLM **consolidation**
step (the v0.3.1 addition) before writing.

The value prop is that the consolidation makes append semantically safe:

- **Reworded duplicates merge** — an equivalent fact is not added a second time.
- **Genuinely new facts are added** to the existing `wiki_facts`/`wiki_definition`.
- **Superseding facts replace** the old text; the removed prior text is recorded
  in the WikiLog `notes` so a destructive consolidation is recoverable from the
  audit log.
- **Contradictions are flagged, never silently overwritten** — both facts are
  kept (the newer marked `[CONFLICT: …]`), `wiki_status` is set to
  `needs-review`, and the conflict is recorded in the WikiLog and the result.
- **Re-asserting the same knowledge converges to a no-op** — the load-bearing
  guarantee is a normalized-text comparison, so a re-assertion that produces
  cosmetically different text still skips the write.

It reuses the same model, endpoint and timeout as extraction
(`WIKI_EXTRACT_MODEL`, `WIKI_EXTRACT_ENDPOINT`, `WIKI_EXTRACT_TIMEOUT`) — there is
**no second resident generation model** and steady-state memory is unchanged from
v0.3.0. As with ingest, objects carry knowledge in *properties*, not the body.

```bash
uv run anytype-llm-wiki wiki-remember \
  --space-id <id> \
  --knowledge "Qdrant 1.12 added native multi-tenancy via payload partitioning." \
  --subject-hint "Qdrant" --kind entity \
  --source "agent task: infra research"
```

### Operating notes for sustained agent writes

`wiki_remember` is the first write path driven *repeatedly* by autonomous agents.
A few operational characteristics matter for self-hosting operators:

- **Per-space re-bootstrap is required on upgrade.** v0.3.1 bumps the schema to
  `0.3.1` and seeds three new tag sets (the `remember` action tag, the
  `wiki_status` tags `needs-review`/`reviewed`/`archived`, and the
  `wiki_source_type` tags `document`/`conversation`/`agent`). Run
  `uv run anytype-llm-wiki wiki-bootstrap --space-id <id>` **once per space**.
  Re-bootstrap is **idempotent and union-only** — existing tags/properties are
  preserved, only missing ones are created. A space left at `0.3.0` returns
  `[CONFIG ERROR] wiki_schema_outdated` from `wiki_remember` until re-bootstrapped.
  **Rollback is clean and additive:** the new tags are harmless under reverted
  v0.3.0 code (which simply ignores them) — no destructive migration, and
  reverting the code does not require removing tags.
- **Auto-reindex cost scales with total space size, not the write delta.** Each
  write triggers an incremental reindex whose cost grows with the whole space, so
  a high write rate can make reindexing the dominant cost. To decouple write
  latency from index cost, set `WIKI_AUTO_REINDEX=false` and run a single
  **scheduled, batched reindex** (see [Auto-reindex](#auto-reindex)) instead.
- **The WikiLog grows monotonically.** Every `wiki_remember` (and `wiki_ingest`)
  call appends a WikiLog object; under sustained agent writes the WikiLog grows
  without bound and benefits from **periodic pruning** of old entries.
- **`ingest_in_progress` is expected, retryable back-pressure.** `wiki_remember`
  and `wiki_ingest` share one per-space lock, so a write while another is in
  flight on the *same* space fails fast with `[DATA ERROR] ingest_in_progress` —
  this is fail-fast back-pressure to retry, not an error to debug. The lock does
  **not** block across spaces, and the worst-case hold time is bounded at
  `8 × WIKI_EXTRACT_TIMEOUT` (the subject cap × the per-consolidation timeout).
- **Narrated `knowledge` is stored as-is.** Only URL credentials in the optional
  `source` note are scrubbed; arbitrary secrets embedded in `knowledge` are **not**
  redacted — do not narrate secrets you would not want stored in the wiki. When
  `WIKI_EXTRACT_ENDPOINT` is non-local, the off-machine consent banner is
  **notify-once and non-blocking** (it self-acknowledges and proceeds).

## Linting the wiki (`wiki_lint`)

`wiki_lint` is the **read-only structural health check** for a bootstrapped wiki
space. It enumerates the wiki once, runs a battery of checks, ranks the results by
severity, and files a single `wiki_log` receipt. It mutates nothing else — there is
no auto-fix; `wiki_lint` only reports.

```bash
uv run python -m anytype_llm_wiki.wiki.cli wiki-lint --space-id <your-space-id> --json
```

The same flow is available to an agent over MCP via the `wiki_lint` tool
(`space_id`, `severity_threshold?`, `include_duplicates?`).

### What it checks

| Check | Severity | What it flags |
|-------|----------|---------------|
| `asymmetric_relation` | Critical | A → B relation with no reciprocal B → A link |
| `orphan` | High | Object with no inbound/outbound relations, older than the grace period |
| `pipeline_orphan` | High | Zero-relation Object created near a recorded ingest `relation_rollback` failure (±300s heuristic) |
| `contradiction_unresolved` | High | Entity with unresolved `wiki_contradictions` and no review timestamp — **active in v0.6.0; scoped (see below)** |
| `unreviewed_needs_review` | High | Object still marked `needs-review` (any age) |
| `stale` | Medium | `last_modified` predates the source ingest timestamp by > 90 days |
| `stale_needs_review` | Medium | `needs-review` Object whose source is older than the cutoff |
| `oversized` | Low | Description longer than the oversized cap (reports a char count, never the body) |
| `empty_type` | Informational | A wiki content type with zero Objects |
| `potential_duplicate` | Informational | Two Objects in the `[0.70, 0.85)` similarity band — **opt-in only (see below)** |

Filter the report with `--severity-threshold` (`all` | `low` | `medium` | `high` |
`critical`; `all` includes informational, `low` and above exclude it).

### The duplicate sweep is opt-in

The `potential_duplicate` sweep embeds the wiki and runs a Qdrant similarity search
per Object, so it is **disabled by default**. Pass `--include-duplicates` (MCP:
`include_duplicates=True`) to enable it. The advertised performance budget (≤60s for
a wiki of ≤500 Objects) describes the **default, sweep-off path only** — the opt-in
sweep can exceed that budget and is hard-skipped entirely above `WIKI_LINT_MAX_OBJECTS`
(with a warning).

### `contradiction_unresolved` is active in v0.6.0 — but scoped

As of v0.6.0 ([#287](https://github.com/Aldeia-IT/aldeia-box/issues/287)) the ingest
pipeline auto-populates `wiki_contradictions` bidirectionally at ingest time, so the
`contradiction_unresolved` lint check is now **active**. Detection never overwrites
either object's facts: both positions are retained, the link is recorded on both
objects, and `wiki_last_reviewed` is left null until an operator reviews.

Two scope limitations matter — do not over-trust a clean contradiction column:

- **Linked entities only.** v0.6.0 detects contradictions between linked entities
  only; contradictions between unlinked entities are not yet caught (planned via a
  semantic pre-filter). The candidate set is bounded by each entity's existing
  `wiki_relations`, so an entity that contradicts another it is not linked to will
  not surface a finding.
- **Entity-only; concept scope deferred.** Detection runs for `wiki_entity` objects
  only. `wiki_concept` objects are out of scope in v0.6.0 (the `wiki_last_reviewed`
  property is absent from the Concept type).

## Auto-reindex

For continuous indexing, run a reindex on a schedule. Reindex is available as the `reindex_anytype` MCP tool and as a one-line module call you can drive from cron or launchd.

**Linux/macOS (cron) — every 30 minutes:**
```bash
# Edit with: crontab -e
*/30 * * * * cd /path/to/anytype-llm-wiki && ANYTYPE_API_KEY=your-key \
  uv run python -c "from anytype_llm_wiki.indexer import reindex; reindex()"
```

**macOS (launchd):** a sample plist is provided at `com.aldeia.anytype-llm-wiki-reindex.plist`. Edit the absolute `uv` path (find it with `which uv`), the `--directory` path to your repo checkout, and `ANYTYPE_API_KEY` for your install, then:
```bash
cp com.aldeia.anytype-llm-wiki-reindex.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.aldeia.anytype-llm-wiki-reindex.plist
```

**Log rotation:** the launchd job appends to `~/Library/Logs/anytype-llm-wiki/reindex.log` every 30 minutes with no built-in rotation, so the file grows unbounded over time. On macOS, rotate it with a `newsyslog.d` fragment:
```
# /etc/newsyslog.d/anytype-llm-wiki.conf
# logfilename                                                [owner:group]  mode count size  when  flags
/Users/YOUR_USER/Library/Logs/anytype-llm-wiki/reindex.log                  644   7     1024  *     J
```
This keeps 7 compressed (`J` = bzip2) rotations, rolling at ~1 MB. Adjust `count`/`size` to taste, and replace `YOUR_USER` with your username.

## Performance

Benchmarked on a Mac Mini (Apple Silicon):

| Operation | Time |
|-----------|------|
| Single search query | **0.22s** |
| Index 50 chunks | 0.73s |
| Full reindex (500 chunks) | ~7s |

Search is fast enough for interactive use. Indexing is fast enough to run frequently.

## Configuration reference

| Variable | Default | Description |
|----------|---------|-------------|
| `ANYTYPE_API_URL` | `http://127.0.0.1:31012` | Anytype REST API endpoint |
| `ANYTYPE_API_KEY` | *(required)* | Bearer token from Anytype settings |
| `ANYTYPE_API_VERSION` | `2025-11-08` | API version header |
| `QDRANT_URL` | `http://127.0.0.1:6333` | Qdrant endpoint |
| `QDRANT_API_KEY` | *(empty)* | Qdrant API key (if auth enabled) |
| `QDRANT_COLLECTION` | `anytype_semantic` | Qdrant collection name |
| `OLLAMA_URL` | `http://127.0.0.1:11434` | Ollama API endpoint |
| `EMBED_MODEL` | `bge-m3` | Ollama embedding model |
| `EMBED_DIMS` | `1024` | Vector dimensions (must match model) |
| `INDEX_STATE_DIR` | `~/.local/share/anytype-llm-wiki` | Where index state is stored |
| `WIKI_INDEX_THRESHOLD` | `200` | `wiki_query` Object count at which retrieval flips Tier 1 → Tier 2 (`>=` is Tier 2) |
| `WIKI_FILE_BACK_MIN_SOURCES` | `3` | `wiki_query` default file-back gate: min cited sources |
| `WIKI_FILE_BACK_MIN_WORDS` | `100` | `wiki_query` default file-back gate: min answer words |
| `WIKI_SYNTH_MAX_INPUT_TOKENS` | `8192` | `wiki_query` total synthesis context cap (token estimate = chars // 4) |
| `WIKI_SYNTH_MAX_OBJECTS` | `24` | `wiki_query` max Objects fed to synthesis |
| `WIKI_SYNTH_MAX_OBJECT_TOKENS` | `1024` | `wiki_query` per-Object head-truncation cap |
| `WIKI_LINT_OVERSIZED_CHARS` | `2000` | `wiki_lint` description length above which `oversized` fires |
| `WIKI_LINT_ORPHAN_GRACE_DAYS` | `7` | `wiki_lint` age grace before an unlinked Object is an `orphan` |
| `WIKI_LINT_STALE_NEEDS_REVIEW_DAYS` | `30` | `wiki_lint` needs-review age cutoff for `stale_needs_review` |
| `WIKI_LINT_MAX_OBJECTS` | `2000` | `wiki_lint` duplicate sweep auto-skips above this Object count |
| `WIKI_LINT_PIPELINE_WINDOW_SECONDS` | `300` | `wiki_lint` ±window for the `pipeline_orphan` timestamp heuristic |
| `WIKI_LINT_DUPLICATE_MAX_SCORE` | `0.85` | `wiki_lint` upper bound (exclusive) of the `[0.70, 0.85)` duplicate band |

**You do not need to set any of the `WIKI_LINT_*` knobs** — the defaults are
sensible for a typical wiki. They are exposed only for operators tuning a large or
unusual space. Note `pipeline_orphan` is an honest ±300s timestamp heuristic: it
correlates a zero-relation Object against a recorded ingest `relation_rollback`
failure and has false negatives by design (it cannot prove an Object is *not* a
pipeline orphan).

`wiki_query` synthesis reuses `WIKI_EXTRACT_TIMEOUT` (default 600s) as its
read-timeout ceiling; this is a deliberate accepted ceiling, and a slow-synthesis
warning is logged when a single synthesis call exceeds 60s. Zero/negative values
for the integer variables above fall back to their defaults (and `WIKI_LINT_DUPLICATE_MAX_SCORE`
values outside `[0, 1]` fall back too).

## Architecture

**Anytype client** — reads objects via the REST API, handles pagination and auth.

**Chunker** — splits markdown by headings (`##`, `###`, `####`), falls back to paragraph splitting for large sections. Each chunk carries metadata: object ID, space ID, object name, type, heading.

**Embedder** — calls Ollama's `/api/embed` endpoint. Supports batch embedding for efficient indexing.

**Indexer** — incremental by default. Tracks `last_modified_date` per object in a JSON state file. Only fetches and re-embeds objects that changed since the last run. Cleans up vectors for deleted objects.

**MCP server** — [FastMCP](https://github.com/jlowin/fastmcp) server exposing `semantic_search`, `reindex_anytype`, `wiki_bootstrap`, `wiki_ingest`, `wiki_remember`, `wiki_query`, and `wiki_lint` as tools over stdio.

**Wiki bootstrap** — idempotently provisions the typed wiki schema (Types, Properties, a domain-tag taxonomy, and a root Collection) in an Anytype space, with an in-place schema-upgrade path. Keyed by `type_key` so re-runs reconcile rather than duplicate.

**Doctor** — a read-only preflight that checks Anytype, Qdrant, and Ollama connectivity and embedding-model availability, exiting non-zero if anything isn't ready.

## Supply-chain posture

We pin dependencies in two layers so installs are both reproducible and resilient:

- **`uv.lock` — exact, hashed versions.** Every dependency (direct and transitive) is locked to an exact version with a content hash. `uv sync` reproduces the same dependency tree on every machine, and CI runs `uv lock --check` to guarantee the lockfile stays in sync with `pyproject.toml`.
- **`pyproject.toml` — compatible ranges with a next-major upper bound.** Each direct dependency declares a lower bound and an upper bound at the next major version (for example `>=1.2,<2.0`) so a transitive resolution can't silently cross a major version and break the build.

Together these give adopters reproducible installs today and a controlled, reviewed upgrade path over time.

**Build provenance.** The release workflow builds artifacts cache-free and signs them with a [SLSA build-provenance attestation](https://docs.github.com/actions/security-guides/using-artifact-attestations). v0.2.0 ships as a git tag and is installed from source (not published to PyPI); once release wheels are published, you'll be able to verify any wheel was built by this repository before trusting it:

```bash
# Verify a downloaded wheel (substitute the actual version)
gh attestation verify anytype_llm_wiki-X.Y.Z-py3-none-any.whl \
  --repo Aldeia-IT/anytype-llm-wiki
```

(`gh attestation verify` does not accept globs — verify each artifact file individually.)

## Roadmap

v0.2.0 ships the foundation — semantic search plus the typed-wiki bootstrap and a health check. The LLM-wiki pipeline (content ingestion and synthesis) follows in v0.3.0.

**v0.2.0 (shipped)**
- [x] Semantic search via MCP, with incremental indexing and change detection
- [x] Auto-reindex (launchd/cron)
- [x] `wiki-bootstrap` — idempotently provision the typed wiki schema (Source, Entity, Concept, Comparison, Query, WikiLog), a domain-tag taxonomy, and a root Collection in an Anytype space
- [x] `doctor` — read-only environment preflight (Anytype, Qdrant, Ollama, embedding model)

**v0.3.0 (LLM wiki pipeline, in design)**
- [ ] `wiki.ingest` — LLM-driven extraction of entities and concepts from source URLs/files, upserted as typed Anytype Objects with bidirectional Relations
- [ ] `wiki.query` — synthesized answers with object citations; optional file-back as a Query object
- [ ] `wiki.lint` — detect orphans, staleness, contradiction drift, oversized objects, and tag-taxonomy violations

Longer-term
- [ ] Hybrid search — semantic similarity + keyword matching + metadata filters
- [ ] Cross-space federation with access control
- [ ] Relationship-aware retrieval — follow Anytype Relations to pull connected context
- [ ] Configurable chunking strategies per object type
- [ ] PyPI publishing
- [ ] Webhook-based indexing when Anytype adds webhook support

## Comparison with alternatives

| | anytype-llm-wiki | [wethegreenpeople/anytype-mcp](https://github.com/wethegreenpeople/anytype-mcp) |
|---|---|---|
| Vector DB | Qdrant (production-grade) | ChromaDB |
| Embedding | Any Ollama model (default: bge-m3, multilingual) | mxbai-embed-large |
| Incremental indexing | Yes (timestamp-based) | Full re-embed on start |
| MCP framework | FastMCP v3 | fastmcp |
| Python version | 3.11+ | 3.13+ |
| Package manager | uv / pip | uv |
| Body content search | Yes | Yes |
| **Typed wiki pipeline (v0.2+)** | **Planned** | — |

The official [`anyproto/anytype-mcp`](https://github.com/anyproto/anytype-mcp) exposes Anytype object access over the API but does not provide built-in semantic / vector search. anytype-llm-wiki's embedding-backed semantic retrieval is its core differentiator over that API-access MCP.

## Contributing

Contributions welcome! This project is maintained by [Aldeia IT](https://github.com/Aldeia-IT).

```bash
# Clone and set up dev environment
git clone https://github.com/Aldeia-IT/anytype-llm-wiki.git
cd anytype-llm-wiki
uv sync --all-extras

# Create .env with your API keys (see .env.example)
cp .env.example .env

# Run tests (requires Anytype, Ollama, and Qdrant running locally)
uv run pytest tests/ -v
```

Areas where help is most welcome:
- **Typed wiki pipeline** (v0.2+) — contributors who have followed Karpathy's LLM-wiki pattern on filesystem will find the design familiar
- **Chunking strategies** for different Anytype object types
- **Hybrid search** implementation (semantic + BM25/keyword)
- **Testing** with large vaults (1000+ objects)
- **Documentation** and examples for different MCP clients

## License

MIT. See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution licensing (inbound = outbound).

## Trademarks

Anytype is a trademark of Any Association. This project is not affiliated with, sponsored by, or endorsed by Any Association or the Anytype project. The Anytype name is used solely to identify the platform this software integrates with.
