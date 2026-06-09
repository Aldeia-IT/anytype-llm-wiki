"""Command-line interface for the wiki module.

Subcommands:
- ``wiki-bootstrap --space-id <id> [--domain-tags a,b,c] [--dry-run] [--json]``
- ``doctor [--json]``

``main(argv=None)`` is the entry point routed to from ``server.py`` when the
first CLI argument is a known subcommand. Kept intentionally minimal but
functional for the maintainer's pre-release demo (no CLI test in v0.2.0).
"""

import argparse
import json
import sys

from . import types_schema
from .bootstrap import wiki_bootstrap
from .doctor import run_doctor

# Subcommands that server.main() routes here instead of starting the MCP server.
SUBCOMMANDS = (
    "wiki-bootstrap",
    "wiki-ingest",
    "wiki-remember",
    "wiki-query",
    "wiki-lint",
    "wiki-drain",
    "prune-citations",
    "doctor",
)


def _parse_domain_tags(raw: str | None) -> list[str] | None:
    if not raw:
        return None
    tags = [t.strip() for t in raw.split(",") if t.strip()]
    return tags or None


def _dry_run_plan(domain_tags: list[str] | None) -> dict:
    """Build the planned-creations summary without touching Anytype."""
    n_types = len(types_schema.WIKI_TYPES)
    n_props = sum(len(t.get("properties", [])) for t in types_schema.WIKI_TYPES)
    tags = domain_tags if domain_tags is not None else types_schema.DEFAULT_DOMAIN_TAGS
    return {
        "dry_run": True,
        "would_create_types": n_types,
        "would_create_properties": n_props,
        "would_create_tags": len(tags),
        "tags": tags,
        "schema_version": types_schema.WIKI_SCHEMA_VERSION,
    }


def _cmd_bootstrap(args: argparse.Namespace) -> int:
    domain_tags = _parse_domain_tags(args.domain_tags)

    if args.dry_run:
        plan = _dry_run_plan(domain_tags)
        if args.json:
            print(json.dumps(plan, indent=2))
        else:
            print(
                f"[DRY RUN] would create {plan['would_create_types']} types, "
                f"{plan['would_create_properties']} properties, "
                f"{plan['would_create_tags']} tags "
                f"(schema v{plan['schema_version']}) in space {args.space_id}."
            )
            print(f"          tags: {', '.join(plan['tags'])}")
        return 0

    result = wiki_bootstrap(space_id=args.space_id, domain_tags=domain_tags)
    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        status = result.get("status")
        print(f"[wiki-bootstrap] space {args.space_id}: status={status}")
        print(
            f"  types:      {len(result.get('types_created', []))} created, "
            f"{len(result.get('types_skipped', []))} skipped"
        )
        print(
            f"  properties: {len(result.get('properties_created', []))} created, "
            f"{len(result.get('properties_skipped', []))} skipped"
        )
        print(
            f"  tags:       {len(result.get('tags_created', []))} created, "
            f"{len(result.get('tags_skipped', []))} skipped"
        )
        if result.get("root_collection_deeplink"):
            print(f"  collection: {result['root_collection_deeplink']}")
        if "schema_upgrade" in result:
            up = result["schema_upgrade"]
            print(f"  upgrade:    {up.get('from')} -> {up.get('to')}")
        if result.get("error"):
            print(f"  error:      {result['error']}")
        for warning in result.get("warnings", []):
            print(f"  warn:       {warning}")
    return 0 if result.get("status") in ("ok", "partial") else 1


def _cmd_ingest(args: argparse.Namespace) -> int:
    from .ingest import wiki_ingest

    result = wiki_ingest(
        source=args.source, space_id=args.space_id, domain_hint=args.domain_hint
    )
    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        status = result.get("status")
        print(f"[wiki-ingest] space {args.space_id}: status={status}")
        print(f"  source:     {result.get('source_object_id')}")
        print(
            f"  objects:    {len(result.get('objects_created', []))} created, "
            f"{len(result.get('objects_updated', []))} updated, "
            f"{len(result.get('objects_skipped', []))} skipped"
        )
        print(f"  relations:  {result.get('relations_created', 0)}")
        if result.get("wiki_log_id"):
            print(f"  wiki_log:   {result['wiki_log_id']}")
        if result.get("error"):
            print(f"  error:      {result['error']}")
        for warning in result.get("warnings", []):
            print(f"  warn:       {warning}")
    return 0 if result.get("status") in ("ok", "partial") else 1


def _cmd_remember(args: argparse.Namespace) -> int:
    from .remember import wiki_remember

    domain_tags = (
        [t.strip() for t in args.domain_tags.split(",") if t.strip()]
        if args.domain_tags
        else None
    )
    result = wiki_remember(
        space_id=args.space_id,
        knowledge=args.knowledge,
        subject_hint=args.subject_hint,
        kind=args.kind,
        domain_tags=domain_tags,
        source=args.source,
    )
    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        status = result.get("status")
        print(f"[wiki-remember] space {args.space_id}: status={status}")
        print(f"  source:     {result.get('source_object_id')}")
        objects = result.get("objects", [])
        print(f"  objects:    {len(objects)}")
        for obj in objects:
            print(
                f"    - {obj.get('action')}: {obj.get('title')} "
                f"({obj.get('kind')}) {obj.get('object_id') or ''}"
            )
        print(f"  relations:  {result.get('relations_created', 0)}")
        print(f"  conflicts:  {result.get('conflicts_flagged', 0)}")
        if result.get("wiki_log_id"):
            print(f"  wiki_log:   {result['wiki_log_id']}")
        if result.get("error"):
            print(f"  error:      {result['error']}")
        for warning in result.get("warnings", []):
            print(f"  warn:       {warning}")
    return 0 if result.get("status") in ("ok", "partial") else 1


def _cmd_query(args: argparse.Namespace) -> int:
    from .query import wiki_query

    result = wiki_query(
        question=args.question,
        space_id=args.space_id,
        file_back=True if args.file_back else None,
    )
    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        status = result.get("status")
        print(f"[wiki-query] space {args.space_id}: status={status}")
        print(f"  mode:       {result.get('retrieval_mode')} "
              f"(count={result.get('object_count_at_decision')})")
        print(f"  answer:     {result.get('answer')}")
        sources = result.get("sources_consulted", [])
        print(f"  sources:    {len(sources)}")
        for src in sources:
            print(f"    - {src.get('title')} ({src.get('type')}) {src.get('deeplink')}")
        print(f"  filed_back: {result.get('filed_back')}")
        if result.get("query_object_deeplink"):
            print(f"  query_obj:  {result['query_object_deeplink']}")
        if result.get("wiki_log_id"):
            print(f"  wiki_log:   {result['wiki_log_id']}")
        if result.get("error"):
            print(f"  error:      {result['error']}")
        for warning in result.get("warnings", []):
            print(f"  warn:       {warning}")
    return 0 if result.get("status") in ("ok", "partial") else 1


def _cmd_lint(args: argparse.Namespace) -> int:
    from .lint import wiki_lint

    result = wiki_lint(
        space_id=args.space_id,
        severity_threshold=args.severity_threshold,
        include_duplicates=args.include_duplicates,
        adjudicate_duplicates=args.adjudicate_duplicates,
    )
    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        status = result.get("status")
        print(f"[wiki-lint] space {args.space_id}: status={status}")
        summary = result.get("summary", {})
        print(f"  summary:    {summary}")
        print(f"  findings:   {len(result.get('findings', []))}")
        for f in result.get("findings", []):
            print(
                f"    - [{f.get('severity')}] {f.get('check')}: "
                f"{f.get('object_title')} {f.get('detail')}"
            )
        dups = result.get("potential_duplicates", [])
        if dups:
            print(f"  duplicates: {len(dups)}")
            for d in dups:
                print(
                    f"    - {d.get('object_a')} ~ {d.get('object_b')} "
                    f"(score {d.get('similarity_score')})"
                )
        if result.get("wiki_log_id"):
            print(f"  wiki_log:   {result['wiki_log_id']}")
        if result.get("error"):
            print(f"  error:      {result['error']}")
        for warning in result.get("warnings", []):
            print(f"  warn:       {warning}")
        for note in result.get("notes", []):
            print(f"  note:       {note}")
    return 0 if result.get("status") in ("ok", "partial") else 1


def _cmd_doctor(args: argparse.Namespace) -> int:
    report = run_doctor()
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        for check in report.get("checks", []):
            name = check.get("name") or check.get("check") or "?"
            status = check.get("status", "?")
            detail = check.get("detail") or check.get("message") or ""
            print(f"[CHECK] {name} ... {status} ({detail})")
        print(f"exit_code: {report.get('exit_code')}")
    return report.get("exit_code", 1)


def _cmd_drain(args: argparse.Namespace) -> int:
    from .remember import drain_pending

    result = drain_pending(space_id=args.space_id)
    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        print(f"[wiki-drain] space {args.space_id}: status={result.get('status')}")
        print(f"  objects applied: {len(result.get('objects', []))}")
        if result.get("wiki_log_id"):
            print(f"  wiki_log:        {result['wiki_log_id']}")
        for warning in result.get("warnings", []):
            print(f"  warn:            {warning}")
    return 0 if result.get("status") in ("ok", "partial") else 1


def _cmd_prune_citations(args: argparse.Namespace) -> int:
    from .query import prune_stale_citation_edges

    result = prune_stale_citation_edges(space_id=args.space_id)
    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        print(f"[prune-citations] space {args.space_id}: status={result.get('status')}")
        print(f"  objects scanned:  {result.get('objects_scanned')}")
        print(f"  objects modified: {result.get('objects_modified')}")
        print(f"  edges pruned:     {result.get('edges_pruned')}")
        if result.get("error"):
            print(f"  error:            {result['error']}")
        for warning in result.get("warnings", []):
            print(f"  warn:             {warning}")
    return 0 if result.get("status") in ("ok", "partial") else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="anytype-llm-wiki",
        description="anytype-llm-wiki maintenance CLI (bootstrap + doctor).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    bootstrap_p = sub.add_parser(
        "wiki-bootstrap", help="Idempotently create the wiki schema in a space."
    )
    bootstrap_p.add_argument("--space-id", required=True, help="Target Anytype space ID.")
    bootstrap_p.add_argument(
        "--domain-tags",
        default=None,
        help="Comma-separated domain tags (overrides defaults on first bootstrap).",
    )
    bootstrap_p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned creations without calling Anytype.",
    )
    bootstrap_p.add_argument(
        "--json", action="store_true", help="Emit the result as JSON."
    )
    bootstrap_p.set_defaults(func=_cmd_bootstrap)

    ingest_p = sub.add_parser(
        "wiki-ingest", help="Ingest a source (URL or file) into the wiki."
    )
    ingest_p.add_argument("--source", required=True, help="http(s) URL or local file path.")
    ingest_p.add_argument("--space-id", required=True, help="Target Anytype space ID.")
    ingest_p.add_argument(
        "--domain-hint", default=None, help="Optional domain tag (must be in the taxonomy)."
    )
    ingest_p.add_argument("--json", action="store_true", help="Emit the result as JSON.")
    ingest_p.set_defaults(func=_cmd_ingest)

    remember_p = sub.add_parser(
        "wiki-remember",
        help="Consolidate narrated knowledge into typed wiki objects.",
    )
    remember_p.add_argument("--space-id", required=True, help="Target Anytype space ID.")
    remember_p.add_argument(
        "--knowledge", required=True, help="Natural-language narration to remember."
    )
    remember_p.add_argument(
        "--subject-hint", default=None, help="Optional entity/concept title nudge."
    )
    remember_p.add_argument(
        "--kind", default=None, choices=["entity", "concept"],
        help="Optional kind hint for the subject_hint fallback.",
    )
    remember_p.add_argument(
        "--source", default=None, help="Optional descriptive provenance note."
    )
    remember_p.add_argument(
        "--domain-tags", default=None,
        help="Comma-separated domain tags (each must exist in the taxonomy).",
    )
    remember_p.add_argument("--json", action="store_true", help="Emit the result as JSON.")
    remember_p.set_defaults(func=_cmd_remember)

    query_p = sub.add_parser(
        "wiki-query", help="Query the wiki and synthesize an answer."
    )
    query_p.add_argument("--question", required=True, help="Natural-language question.")
    query_p.add_argument("--space-id", required=True, help="Target Anytype space ID.")
    query_p.add_argument(
        "--file-back",
        action="store_true",
        help="Force filing the answer back as a typed Query object.",
    )
    query_p.add_argument("--json", action="store_true", help="Emit the result as JSON.")
    query_p.set_defaults(func=_cmd_query)

    lint_p = sub.add_parser(
        "wiki-lint", help="Run a structural health check over a wiki space."
    )
    lint_p.add_argument("--space-id", required=True, help="Target Anytype space ID.")
    lint_p.add_argument(
        "--severity-threshold",
        default="all",
        help="Minimum severity retained (all|low|medium|high|critical; default all).",
    )
    lint_p.add_argument(
        "--include-duplicates",
        action="store_true",
        default=False,
        help="Run the opt-in Qdrant duplicate sweep (can exceed the ≤60s budget).",
    )
    lint_p.add_argument(
        "--adjudicate-duplicates",
        action="store_true",
        default=False,
        help="Annotate each potential_duplicate with a non-destructive LLM "
             "same/distinct verdict (one local-LLM call per pair). Pre-judges the "
             "human review queue; best on a vetted model.",
    )
    lint_p.add_argument("--json", action="store_true", help="Emit the result as JSON.")
    lint_p.set_defaults(func=_cmd_lint)

    drain_p = sub.add_parser(
        "wiki-drain",
        help="Drain any queued wiki_remember subjects for a space (backstop for "
             "the queue-submit model).",
    )
    drain_p.add_argument("--space-id", required=True, help="Target Anytype space ID.")
    drain_p.add_argument("--json", action="store_true", help="Emit the result as JSON.")
    drain_p.set_defaults(func=_cmd_drain)

    prune_p = sub.add_parser(
        "prune-citations",
        help="Remove stale wiki_query citation edges from entity/concept "
             "relations (one-time cleanup for spaces with old file-back history).",
    )
    prune_p.add_argument("--space-id", required=True, help="Target Anytype space ID.")
    prune_p.add_argument("--json", action="store_true", help="Emit the result as JSON.")
    prune_p.set_defaults(func=_cmd_prune_citations)

    doctor_p = sub.add_parser("doctor", help="Run preflight checks.")
    doctor_p.add_argument(
        "--json", action="store_true", help="Emit the report as JSON."
    )
    doctor_p.set_defaults(func=_cmd_doctor)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
