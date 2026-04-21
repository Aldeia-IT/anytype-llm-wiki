# Business Context

## Identity

- **Project:** anytype-llm-wiki
- **Owner:** Jan Scheufen (Aldeia IT Consulting)
- **Type:** Open-source tool / internal infrastructure
- **Stage:** Greenfield

## What It Is

An MCP server that provides semantic search over Anytype knowledge bases. Reads objects from the Anytype REST API, chunks and embeds content locally (Ollama/bge-m3), stores vectors in Qdrant, and exposes search as an MCP tool for AI coding assistants.

## Why It Exists

Anytype's built-in search only matches on object name and snippet — it does not search body content at all. This means agents cannot find information by what it says, only by title. Even basic full-text search of note content requires an external index.

## Dual Purpose

1. **Internal:** Powers semantic search over Aldeia IT's Anytype knowledge base (business notes, project planning, meeting notes, contacts) for Claude Code and IronClaw agents.
2. **Public:** Published as an open-source tool for the Anytype community. Builds reputation and serves as marketing for Aldeia IT's AI pipeline tooling.

## Relationship to Aldeia IT

- Uses existing infrastructure: Qdrant (Docker), Ollama/bge-m3, Anytype CLI
- Registered as MCP server alongside `mem0` and `anytype` (the official read/write MCP)
- Part of a broader open-source strategy (#84 AI SDLC Playbook, #85 gh-projects MCP extraction)

## Business Model

Free and open-source. No direct revenue. Value is reputation + marketing funnel.

## Competitive Landscape

One community project exists: `wethegreenpeople/anytype-mcp` (16 stars, ChromaDB + mxbai-embed-large). It validates the approach but uses different infrastructure and has documented performance issues. We build against our own stack (Qdrant + bge-m3) and aim for a cleaner, more configurable implementation.
