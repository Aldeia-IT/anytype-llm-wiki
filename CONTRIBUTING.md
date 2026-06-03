# Contributing to anytype-llm-wiki

Thanks for your interest in contributing! This project is in early stages and we welcome help in many areas.

## Getting started

1. Fork and clone the repo
2. Install prerequisites: Anytype (desktop or CLI), Ollama (`ollama pull bge-m3`), Qdrant (`docker run -p 6333:6333 qdrant/qdrant`)
3. Set up dev environment:
   ```bash
   cd anytype-llm-wiki
   uv sync --all-extras
   cp .env.example .env  # fill in your API keys
   ```
4. Run tests: `uv run pytest` (the canonical CI form; `uv run pytest tests/ -v` also works)

> After modifying `pyproject.toml`, run `uv lock` and commit the updated `uv.lock`.
> CI enforces this via `uv lock --check` — a drifted lockfile fails the merge-gate.

## Project structure

```
src/anytype_llm_wiki/
├── server.py           # MCP server + tool definitions
├── config.py           # Environment variable config
├── anytype_client.py   # Anytype REST API client
├── chunker.py          # Markdown → chunks with metadata
├── embedder.py         # Ollama embedding client
├── indexer.py          # Incremental index orchestrator
└── wiki/               # Typed-wiki subpackage (v0.2.0 features)
    ├── bootstrap.py    # wiki-bootstrap: idempotent schema provisioning
    ├── doctor.py       # doctor: read-only health check
    ├── cli.py          # wiki CLI entry points
    ├── wiki_client.py  # Anytype typed-schema REST client
    ├── config.py       # wiki-specific config
    ├── types_schema.py # Type/Property/tag schema definitions
    └── util.py         # shared helpers
```

## How to contribute

**Bug reports and feature requests** — open an issue. Include your Anytype version, Python version, and steps to reproduce.

**Code contributions:**
1. Create a feature branch from `main`
2. Write tests for new functionality
3. Ensure all tests pass
4. Open a PR with a clear description of what and why

**Documentation** — improvements to the README, examples, or inline docs are always welcome.

## Dependency intake

Adding a new third-party dependency (runtime, dev, or build-time) is a
supply-chain decision, not a convenience. Before adding one, work through the
[dependency intake checklist](docs/dependency-intake.md): necessity, maintainer
health, release history, transitive impact, license compatibility (must be
MIT-compatible), the 7-day cooldown, and a decision record in your PR. After
changing `pyproject.toml`, run `uv lock` and commit the updated `uv.lock`.

## For maintainers

Cutting a release to PyPI? Follow the [release runbook](docs/releasing.md),
including the one-time PyPI trusted-publisher and `pypi` GitHub Environment setup
(with the mandatory fail-open-gate verification) before the first `v*` tag.

## Code style

- Python 3.11+ with type hints
- Keep functions focused and small
- Tests go in `tests/` and mirror the source structure
- Integration tests that need external services should skip gracefully with `pytest.skip()`
- Integration tests skip automatically when their backing services (Anytype, Ollama, Qdrant) are absent or not successfully reachable (a non-2xx response such as 401/403 also counts as not reachable); they only run against fully reachable, authorized services

## Licensing of contributions

This project is distributed under the [MIT License](LICENSE), and contributions are accepted under that same license. By submitting a contribution (for example, a pull request), you agree that your work is offered under the MIT License — the same license the project is released under. This is GitHub's standard [inbound=outbound](https://docs.github.com/en/site-policy/github-terms/github-terms-of-service#6-contributions-under-repository-license) model: what flows in matches what flows out, so everyone can use, modify, and share the result on the same clear, permissive terms. No separate paperwork is required.

Optionally, you may add a [Developer Certificate of Origin (DCO)](https://developercertificate.org/) sign-off to certify that you have the right to submit your work. This is encouraged but not required. To sign off a commit, use the `-s` flag:

```bash
git commit -s -m "Your commit message"
```

This appends a `Signed-off-by` line using your configured Git name and email.

## Areas we need help

- **Chunking strategies** — the current heading-based chunker works for notes and docs, but Anytype has many object types (tasks, bookmarks, collections). Different types may need different chunking.
- **Hybrid search** — combining vector similarity with BM25/keyword scoring for better precision.
- **Large vault testing** — we've tested with ~50 objects. How does it behave with 1000+? 10,000+?
- **Alternative embedding models** — bge-m3 is our default but others (nomic-embed-text, mxbai-embed-large) may work better for specific use cases.
- **MCP client examples** — how to set this up with Cursor, Windsurf, Continue, and other MCP-compatible tools.
