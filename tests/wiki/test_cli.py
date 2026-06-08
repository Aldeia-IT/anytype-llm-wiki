"""CLI routing guards.

`server.main()` only routes argv to the wiki CLI when `argv[1] in
cli.SUBCOMMANDS`. If a subparser is registered in `build_parser()` but missing
from `SUBCOMMANDS` (or vice versa), the command silently starts the MCP server
instead of running — which is exactly how `prune-citations`/`wiki-drain` shipped
unreachable in v0.7.0. These tests pin the two lists together.
"""

import argparse

from anytype_llm_wiki.wiki import cli


def _subparser_names(parser: argparse.ArgumentParser) -> set[str]:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return set(action.choices.keys())
    return set()


def test_subcommands_registry_matches_parser():
    """Every build_parser() subcommand must be in SUBCOMMANDS and vice versa, so
    server.main() routes exactly the commands the parser implements."""
    parser_names = _subparser_names(cli.build_parser())
    registry = set(cli.SUBCOMMANDS)
    assert parser_names == registry, (
        "CLI subparser names and SUBCOMMANDS routing registry have drifted.\n"
        f"  in parser but not routed: {sorted(parser_names - registry)}\n"
        f"  routed but not in parser: {sorted(registry - parser_names)}"
    )


def test_new_maintenance_commands_are_routed():
    """Explicit guard for the v0.7.0 regression: the maintenance commands route."""
    for name in ("prune-citations", "wiki-drain"):
        assert name in cli.SUBCOMMANDS, f"{name} must be routed by server.main()"


def test_every_subcommand_has_a_handler():
    """Each subcommand parses to a callable handler (func)."""
    parser = cli.build_parser()
    for name in cli.SUBCOMMANDS:
        # Commands that need --space-id still parse with it supplied.
        argv = [name]
        if name != "doctor":
            argv += ["--space-id", "s"]
        if name == "wiki-ingest":
            argv += ["--source", "https://example.com/x"]
        if name == "wiki-remember":
            argv += ["--knowledge", "x"]
        if name == "wiki-query":
            argv += ["--question", "x"]
        ns = parser.parse_args(argv)
        assert callable(getattr(ns, "func", None)), f"{name} has no handler"
