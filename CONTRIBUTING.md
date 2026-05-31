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
└── indexer.py          # Incremental index orchestrator
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

## Areas we need help

- **Chunking strategies** — the current heading-based chunker works for notes and docs, but Anytype has many object types (tasks, bookmarks, collections). Different types may need different chunking.
- **Hybrid search** — combining vector similarity with BM25/keyword scoring for better precision.
- **Large vault testing** — we've tested with ~50 objects. How does it behave with 1000+? 10,000+?
- **Alternative embedding models** — bge-m3 is our default but others (nomic-embed-text, mxbai-embed-large) may work better for specific use cases.
- **MCP client examples** — how to set this up with Cursor, Windsurf, Continue, and other MCP-compatible tools.
