# Compliance Context

## License

MIT — open-source, permissive.

## Data Privacy

- Local-first by default: all data stays local, no telemetry. The one explicit opt-in exception is remote LLM extraction via `WIKI_EXTRACT_ENDPOINT` (off by default, on-device Ollama otherwise); when set to a non-local endpoint it transmits fetched source content off-machine, gated by a first-run consent banner.
- Anytype content is E2E encrypted at rest; this tool reads via the local API after decryption.
- Qdrant stores vector embeddings + metadata (object names, types, chunk text). No encryption at the Qdrant layer — acceptable for local-only deployment.
- No PII handling beyond what users put in their Anytype notes.

## Secrets

- Anytype API key and Qdrant API key passed via environment variables.
- Never committed to the repo. Documented in README as required config.
