# Migration Guide

This guide describes the steps to take when upgrading between versions of
`anytype-llm-wiki`. Each release that requires action documents its upgrade path
here. Versions not listed require no migration steps.

## Upgrading to v0.2.0

v0.2.0 is the first public release, so there is no prior public version to
migrate **from**. There is, however, a one-time setup step that v0.2.0
introduces, and which every user — new or upgrading — should follow before
indexing.

### 1. Configure your environment

Ensure your `.env` is populated (see the [README](README.md) for the full list),
including `ANYTYPE_API_KEY`, `ANYTYPE_SPACE_ID`, `QDRANT_URL`, `OLLAMA_BASE_URL`,
and `OLLAMA_EMBEDDING_MODEL`.

### 2. Provision the Wiki object type

Run the bootstrap command to provision the dedicated "Wiki" object type and its
properties in your Anytype space:

```bash
anytype-wiki wiki-bootstrap
```

This command is **idempotent** — it is safe to run on a fresh space or an
existing one, and re-running it will not create duplicates. Pass `--space-id` to
target a specific space, `--dry-run` to preview the changes without applying
them, or `--force` if you need to reconcile an existing setup.

### 3. Confirm the environment is healthy

Run the read-only health check to confirm everything is wired up correctly:

```bash
anytype-wiki doctor
```

`doctor` verifies the Anytype API, Qdrant, Ollama, and embedding-model
availability without modifying anything. It exits `0` only when all checks pass.
Resolve any reported issues before proceeding.

### 4. Index your knowledge base

Once `doctor` reports all green, index your objects:

```bash
anytype-wiki index
```

You are now ready to run `anytype-wiki serve` and connect an MCP client.

## Future versions

Migration notes for v0.3.0 and later releases will be appended to this file as
those versions ship. When upgrading, check this guide for any steps that apply
to the version you are moving to.
