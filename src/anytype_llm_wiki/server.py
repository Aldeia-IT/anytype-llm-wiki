"""MCP server exposing semantic search, reindex, and wiki bootstrap tools."""

import sys
from importlib.metadata import PackageNotFoundError, version as _pkg_version

from fastmcp import FastMCP

from .indexer import reindex, semantic_search_core
from .wiki.bootstrap import wiki_bootstrap as _wiki_bootstrap

try:
    _VERSION = _pkg_version("anytype-llm-wiki")
except PackageNotFoundError:  # running from a source tree without install metadata
    _VERSION = "0.2.0"

# Report the package version over MCP (serverInfo.version) instead of falling
# back to FastMCP's own version.
mcp = FastMCP("anytype-llm-wiki", version=_VERSION)


@mcp.tool()
def semantic_search(
    query: str,
    space_id: str | None = None,
    types: list[str] | None = None,
    ingested_after: str | None = None,
    ingested_before: str | None = None,
    limit: int = 10,
) -> list[dict]:
    """Search Anytype objects by semantic similarity.

    Args:
        query: Natural language search query.
        space_id: Optional space ID to filter results.
        types: Optional list of type keys to filter (e.g. ["page", "note"]).
        ingested_after: Optional ISO-8601 datetime lower bound on last_modified_date, inclusive.
            Example: "2026-01-01T00:00:00Z".
        ingested_before: Optional ISO-8601 datetime upper bound on last_modified_date, inclusive.
            Example: "2026-06-30T23:59:59Z".
        limit: Max results to return (default 10).

    Returns:
        List of matching chunks with object name, type, heading, text snippet, and score.
    """
    from pydantic import ValidationError as _PydanticValidationError
    from qdrant_client.models import DatetimeRange as _DatetimeRange

    for name, val in [("ingested_after", ingested_after), ("ingested_before", ingested_before)]:
        if val is not None:
            try:
                _DatetimeRange(gte=val)  # probe only; not stored
            except _PydanticValidationError:
                raise ValueError(
                    f"Invalid date format for {name}: {val!r}. "
                    f"Expected ISO-8601, e.g. 2026-01-01T00:00:00Z"
                )

    return semantic_search_core(
        query=query,
        space_id=space_id,
        types=types,
        ingested_after=ingested_after,
        ingested_before=ingested_before,
        limit=limit,
    )


@mcp.tool()
def reindex_anytype(space_id: str | None = None) -> dict:
    """Trigger incremental reindex of Anytype objects.

    Args:
        space_id: Optional space ID to reindex. If omitted, reindexes all spaces.

    Returns:
        Stats: spaces checked, objects indexed, chunks created, objects removed.
    """
    return reindex(space_id=space_id)


@mcp.tool()
def wiki_bootstrap(space_id: str, domain_tags: list[str] | None = None) -> dict:
    """Idempotently create the wiki schema (Types, Properties, tags, Collection) in a space.

    Args:
        space_id: Target Anytype space ID.
        domain_tags: Optional domain-tag taxonomy. On a first bootstrap these
            replace the defaults; on a re-bootstrap they are union-only (existing
            tags preserved, only new tags created).

    Returns:
        A BootstrapResult dict with per-element created/skipped breakdowns, the
        root Collection id + deeplink, a WikiLog id + deeplink, and a status of
        "ok" | "partial" | "error".
    """
    return _wiki_bootstrap(space_id=space_id, domain_tags=domain_tags)


@mcp.tool()
def wiki_ingest(source: str, space_id: str, domain_hint: str | None = None) -> dict:
    """Ingest a source (URL or local file) into the wiki compile pipeline.

    Fetches the source, extracts/derives entities and concepts, resolves them
    against existing wiki objects, creates/updates typed objects (properties
    only, empty body), writes bidirectional relations, records a WikiLog entry,
    and triggers an incremental reindex.

    Args:
        source: An http(s) URL or an absolute local file path.
        space_id: Target Anytype space ID.
        domain_hint: Optional domain tag; must be in the space's taxonomy.

    Returns:
        An IngestResult dict (source/objects created/updated/skipped, relations,
        wiki_log_id, warnings, status).
    """
    from .wiki.ingest import wiki_ingest as _wiki_ingest

    return _wiki_ingest(source=source, space_id=space_id, domain_hint=domain_hint)


@mcp.tool()
def wiki_remember(
    space_id: str,
    knowledge: str,
    subject_hint: str | None = None,
    kind: str | None = None,
    relations: list[dict] | None = None,
    domain_tags: list[str] | None = None,
    source: str | None = None,
) -> dict:
    """Consolidate narrated, conversational knowledge into typed wiki objects.

    Unlike wiki_ingest (which fetches a URL/file), wiki_remember takes an agent's
    natural-language narration and runs the extract -> resolve -> LLM-consolidate
    -> relations -> WikiLog -> reindex pipeline. The consolidation step merges new
    facts into an existing entity/concept's wiki_facts/wiki_definition rather than
    overwriting them: equivalent facts are deduplicated, genuinely new facts are
    added, superseding facts replace old ones (audited in the WikiLog), and
    contradictions are flagged (wiki_status=needs-review, never silently
    overwritten). Re-asserting the same knowledge converges to a no-op.

    Args:
        space_id: Target Anytype space ID (must be bootstrapped at schema >= 0.3.1).
        knowledge: Natural-language narration (non-empty; <= 32000 characters).
        subject_hint: Optional title to seed entity resolution if extraction is empty.
        kind: Optional "entity" or "concept" hint for the subject_hint fallback.
        relations: Optional [{"from", "to", "label"}] links between named subjects.
        domain_tags: Optional domain tags; each must exist in the space taxonomy.
        source: Optional provenance note; "conversation" in it selects the
            conversation source type, otherwise the agent source type is used.

    Returns:
        A dict with source_object_id, per-object results (objects[]),
        relations_created, conflicts_flagged, wiki_log_id, warnings, and a status
        of "ok" | "partial" | "error".
    """
    from .wiki.remember import wiki_remember as _wiki_remember

    return _wiki_remember(
        space_id=space_id,
        knowledge=knowledge,
        subject_hint=subject_hint,
        kind=kind,
        relations=relations,
        domain_tags=domain_tags,
        source=source,
    )


@mcp.tool()
def wiki_query(
    question: str,
    space_id: str,
    file_back: bool | None = None,
    types: list[str] | None = None,
    ingested_after: str | None = None,
    ingested_before: str | None = None,
) -> dict:
    """Query the typed wiki and return a synthesized answer (tiered retrieval).

    Enumerates the wiki and picks a retrieval tier by object count (Tier 1
    index-navigation below WIKI_INDEX_THRESHOLD, Tier 2 vector-augmented at/above
    it), fetches the candidate objects plus their 1-hop neighborhood, synthesizes
    a prose answer from the bounded context, and — when the answer is clean and
    meets the file-back gate (or file_back=True) — files the question/answer back
    as a typed Query object so the next reindex makes it retrievable (compounding).

    Args:
        question: Natural-language question.
        space_id: Target Anytype space ID (must be bootstrapped at the current schema).
        file_back: True forces filing; False suppresses; None uses the default gate
            (>= 3 cited sources AND >= 100-word answer).
        types: Optional subset of wiki type keys to scope retrieval. Intersected with
            the wiki type set; an empty intersection is a config error.
        ingested_after: Optional ISO-8601 datetime lower bound on last_modified_date, inclusive.
            Example: "2026-01-01T00:00:00Z".
        ingested_before: Optional ISO-8601 datetime upper bound on last_modified_date, inclusive.
            Example: "2026-06-30T23:59:59Z".

    Returns:
        A QueryResult dict (answer, sources_consulted, filed_back, retrieval_mode,
        object_count_at_decision, query/wiki_log ids + deeplinks, warnings, status,
        error, error_category).
    """
    from .wiki.query import wiki_query as _wiki_query

    return _wiki_query(
        question=question,
        space_id=space_id,
        file_back=file_back,
        types=types,
        ingested_after=ingested_after,
        ingested_before=ingested_before,
    )


@mcp.tool()
def wiki_lint(
    space_id: str,
    severity_threshold: str = "all",
    include_duplicates: bool = False,
    adjudicate_duplicates: bool = False,
) -> dict:
    """Run a read-only structural health check over a bootstrapped wiki space.

    Enumerates the wiki once and runs a battery of ten structural checks
    (asymmetric relations, orphans, pipeline orphans, unresolved contradictions,
    staleness, oversized descriptions, empty types, unreviewed/stale needs-review,
    and — opt-in — potential duplicates), assembles a severity-ranked LintReport,
    and files a single WikiLog receipt. wiki_lint mutates nothing else.

    The duplicate sweep is OPT-IN: it runs only when ``include_duplicates=True``.
    The advertised ≤60s / ≤500-object performance budget describes the DEFAULT
    (sweep-off) path; the opt-in sweep embeds the wiki and can exceed that budget
    (and is hard-skipped above WIKI_LINT_MAX_OBJECTS).

    The ``contradiction_unresolved`` check is ACTIVE as of v0.6.0/#287 — the
    ingest pipeline auto-populates ``wiki_contradictions`` on cross-object
    conflict, and this check fires a High finding for any contradiction lacking
    a ``wiki_last_reviewed`` timestamp. Detection is scoped to linked entities
    only (see README), so a green result is not an exhaustive guarantee.

    Args:
        space_id: Target Anytype space ID (must be bootstrapped at the current schema).
        severity_threshold: Minimum severity retained in findings[] — one of
            "all" | "low" | "medium" | "high" | "critical" ("all" includes
            informational; "low" excludes it). Does not affect potential_duplicates[].
        include_duplicates: When True, run the opt-in Qdrant duplicate sweep.
        adjudicate_duplicates: When True, annotate each potential_duplicate with a
            NON-DESTRUCTIVE LLM same/distinct verdict (one local-LLM call per pair)
            to pre-judge the human review queue. Suggestion-only — no graph
            mutation and no model-vetting gate. Best on a vetted model.

    Returns:
        A LintReport dict (object_counts, findings, potential_duplicates, summary,
        elapsed_ms, wiki_log_id, deeplink, warnings, status, error, error_category).
        With ``adjudicate_duplicates``, each potential_duplicates[] entry also
        carries an ``llm_verdict`` ("same"|"distinct") and a sharpened recommendation.
    """
    from .wiki.lint import wiki_lint as _wiki_lint

    return _wiki_lint(
        space_id=space_id,
        severity_threshold=severity_threshold,
        include_duplicates=include_duplicates,
        adjudicate_duplicates=adjudicate_duplicates,
    )


def main():
    # Route known CLI subcommands to the wiki CLI; otherwise run the MCP server.
    from .wiki import cli as wiki_cli

    if len(sys.argv) > 1 and sys.argv[1] in wiki_cli.SUBCOMMANDS:
        sys.exit(wiki_cli.main(sys.argv[1:]))

    # Fail-safe (v0.7.3): the alias-adjudication config is fixed at start time, so
    # refuse to START the MCP server with an UNAPPROVED config — adjudication
    # enabled on an unvetted model (over-merge risk). Fail loud and early here,
    # not lazily on the first ingest. (CLI subcommands above keep their own
    # entry-point guard for one-shot invocations that bypass server startup.)
    from .wiki import config as wiki_config
    adj_err = wiki_config.alias_adjudication_config_error()
    if adj_err:
        print(f"anytype-llm-wiki: refusing to start — {adj_err}", file=sys.stderr)
        sys.exit(2)

    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
