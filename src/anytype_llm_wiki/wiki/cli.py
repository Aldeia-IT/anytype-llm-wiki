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
SUBCOMMANDS = ("wiki-bootstrap", "doctor")


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
