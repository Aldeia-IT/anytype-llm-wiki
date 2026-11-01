"""Dry-run wiki_ingest's fetch and extraction on real pages (Aldeia-IT/aldeia-box#1427).

READ-ONLY: per URL, strictly one at a time, it runs ``fetch_source`` (SSRF-checked
fetch, boilerplate strip, usable-content verdict) and then ``extract()`` against
the configured Ollama (``WIKI_EXTRACT_MODEL``, ``WIKI_EXTRACT_ENDPOINT``). It
imports no Anytype or Qdrant client, creates no object and writes nothing but
stdout: one JSON object per page.

Usage:
    uv run python scripts/ingest_dry_run.py [--refuse-identifier-names] <url> [<url> ...]

Each object carries: ``url``, ``fetch_seconds``, ``chars_before_strip`` /
``chars_after_strip`` (markdown of the whole page vs the main content),
``excerpt`` (the first 1000 chars, what ingest stores as ``wiki_excerpt``),
``unusable`` (the usable-content gate's refusal reason, or null),
``entities`` / ``concepts`` (name and facts), ``relation_count``,
``extraction_error``, ``truncated``, ``extraction_seconds``, and
``refused_names``: the names ingest would refuse. Names failing the base name
policy are always listed; with ``--refuse-identifier-names`` the identifier-like
names are listed too, as if the space were in
``WIKI_REFUSE_IDENTIFIER_NAMES_SPACES``. A page the gate refuses is not sent to
the model. ``fetch_error`` is set when the fetch itself failed.
"""

import argparse
import json
import sys
import time

from anytype_llm_wiki.wiki.extraction import extract, is_identifier_like_name, sanitize_name
from anytype_llm_wiki.wiki.fetch import _to_markdown, fetch_source

_EXCERPT_CHARS = 1000
_DEGRADED_PREFIX = "extraction_degraded: "


def _items(extracted: dict, key: str, kind: str) -> list[dict]:
    """Name and facts of each extracted entity or concept (ingest's mapping)."""
    out = []
    for item in extracted.get(key) or []:
        if not isinstance(item, dict) or not item.get("name"):
            continue
        if kind == "concept":
            facts = item.get("definition") or item.get("description") or ""
        else:
            facts = item.get("description") or item.get("definition") or ""
        out.append({"name": item["name"], "facts": facts})
    return out


def _refused(names: list[str], refuse_identifiers: bool) -> list[str]:
    refused = []
    for name in names:
        clean = sanitize_name(name)
        if clean is None or (refuse_identifiers and is_identifier_like_name(clean)):
            refused.append(name)
    return refused


def dry_run(url: str, refuse_identifiers: bool) -> dict:
    """Fetch and extract one page; return the report object."""
    report = {
        "url": url,
        "fetch_seconds": None,
        "fetch_error": None,
        "chars_before_strip": None,
        "chars_after_strip": None,
        "excerpt": "",
        "unusable": None,
        "entities": [],
        "concepts": [],
        "relation_count": 0,
        "extraction_error": None,
        "truncated": None,
        "extraction_seconds": None,
        "refused_names": [],
    }
    started = time.monotonic()
    fetched = fetch_source(url)
    report["fetch_seconds"] = round(time.monotonic() - started, 2)
    markdown = fetched["markdown"]
    if markdown.startswith("[DATA ERROR]"):
        report["fetch_error"] = markdown
        return report
    raw = fetched["raw"] if fetched["raw"] is not None else markdown
    report["chars_before_strip"] = len(
        _to_markdown(raw, fetched["content_type"] or "", strip=False)
    )
    report["chars_after_strip"] = len(markdown)
    report["excerpt"] = markdown[:_EXCERPT_CHARS]
    report["unusable"] = fetched["unusable"]
    if fetched["unusable"]:
        return report

    started = time.monotonic()
    extracted = extract(markdown=markdown, space_id="dry-run")
    report["extraction_seconds"] = round(time.monotonic() - started, 2)
    error = extracted.get("error")
    report["extraction_error"] = str(error).removeprefix(_DEGRADED_PREFIX) if error else None
    report["truncated"] = extracted.get("truncated")
    report["entities"] = _items(extracted, "entities", "entity")
    report["concepts"] = _items(extracted, "concepts", "concept")
    relations = extracted.get("relations")
    report["relation_count"] = len(relations) if isinstance(relations, list) else 0
    names = [i["name"] for i in report["entities"] + report["concepts"]]
    report["refused_names"] = _refused(names, refuse_identifiers)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--refuse-identifier-names",
        action="store_true",
        help="report identifier-like names as refused (as in a listed space)",
    )
    parser.add_argument("urls", nargs="+", help="http(s) URLs to dry-run, one at a time")
    args = parser.parse_args(argv)
    for url in args.urls:
        report = dry_run(url, args.refuse_identifier_names)
        print(json.dumps(report, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
