"""anytype_llm_wiki.wiki — v0.2.0 wiki module package.

This package holds the wiki foundation layer: the transport base client,
the write-plane WikiClient, the canonical type schema, wiki configuration,
and shared utilities (title normalization, credential scrubbing, ingest
locking).

The MCP tool implementation functions (e.g. ``wiki_bootstrap``) are re-exported
here for ``server.py`` to wire. In v0.2.0 only the foundation modules exist;
the next worker adds the tool implementations and their re-exports.
"""
