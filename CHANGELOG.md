# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Roadmap

- **Coming in v0.3.0: automated content ingestion.** Scheduled, hands-off
  ingestion that keeps your Qdrant index continuously in sync with your Anytype
  knowledge base, so semantic search always reflects the latest content without
  manual re-indexing.

## [0.2.0] - 2026-05-30

First public release (preview). This is the first open-source release of
`anytype-llm-wiki` and marks the start of public versioning.

### Added

- **`wiki-bootstrap` command** — provisions a dedicated "Wiki" object type and
  its supporting properties in an Anytype space. The operation is idempotent, so
  it is safe to run repeatedly; re-running reconciles the space to the expected
  shape without creating duplicates. Supports `--space-id`, `--dry-run`, and
  `--force`.
- **`doctor` command** — a read-only health check that verifies connectivity and
  readiness across the Anytype API, Qdrant, and Ollama, and confirms the
  configured embedding model is available. It changes nothing and exits `0` only
  when every check is green, making it suitable for setup validation and CI
  gating. Supports `--space-id`.
- **Public-release collateral** — security policy (`SECURITY.md`), third-party
  attribution (`NOTICE`), contribution and licensing guidance
  (`CONTRIBUTING.md`), and documentation of the project's supply-chain posture
  (two-layer dependency pinning: exact, hashed versions in `uv.lock` for
  reproducible installs, with compatible ranges declared in `pyproject.toml`).

### Foundation

This release builds on the existing `index` and `serve` commands:

- `index` — indexes Anytype objects into the Qdrant vector database using local
  Ollama embeddings (`--full` for a complete re-index).
- `serve` — runs the MCP server that exposes semantic search to MCP clients such
  as Claude Desktop.

[Unreleased]: https://github.com/Aldeia-IT/anytype-llm-wiki/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/Aldeia-IT/anytype-llm-wiki/releases/tag/v0.2.0
