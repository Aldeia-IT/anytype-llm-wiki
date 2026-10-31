#!/usr/bin/env python3
"""Propose expected object IDs for the AC-EVAL2 retrieval eval (Aldeia-IT/aldeia-box#327).

READ-ONLY: the only Qdrant calls are ``scroll`` and ``semantic_search_core`` (a query).
It never writes to the wiki, to Qdrant or to the index state file; its single output is
the ``--output`` JSON file. It prints only a one-line summary (no config values, no
secrets, no chunk text).

A human reviews the proposals once, edits ``expected_ids``, sets ``"frozen": true`` and
keeps the file outside the repo; the eval test errors on an unfrozen fixture.

Usage:
    uv run python scripts/curate_eval_cases.py --targets targets.json --output proposals.json

``targets.json`` is ``{"cases": [...]}`` (or a bare list). Each target has ``id``,
``group``, ``query``, ``space_id`` and ``types``; ``shared: true`` marks a name that
several objects share (the script then adds a "(context)" case per member).

Proposal sources per case (an object may carry several, in ``sources``):
  key_equality     the D13 name key of the object equals the query key (``strip_name``)
  name_token       every query token (``_tokenize`` of the query key) is in the name tokens
  dense_top20      the top 20 of ``semantic_search_core`` for the query
  name_bm25_top20  the top 20 of a BM25 over object names only

Output: ``{"frozen": false, "cases": [...]}``; each case keeps the target fields plus
``expected_ids`` (the key_equality proposals, for the human to edit), ``proposals``
(``object_id``, ``name``, ``type``, ``sources``), ``dense_top_ids`` and, for shared
members, ``right_id``.
"""

import argparse
import json
import re
import sys
from pathlib import Path

PROPOSAL_DEPTH = 20
DENSE_TOP_IDS = 10
_PAREN_RE = re.compile(r"\(([^()]*)\)\s*$")


def _name_helpers():
    """Return ``(strip_name, tokenize)`` from the indexer (D12 and D13 live there)."""
    from anytype_llm_wiki import indexer

    strip = getattr(indexer, "strip_name", None) or getattr(indexer, "_strip_name", None)
    tokenize = getattr(indexer, "_tokenize", None)
    if strip is None or tokenize is None:
        raise SystemExit(
            "indexer lacks strip_name/_tokenize (spec D12, D13): implement them first"
        )
    return strip, tokenize


def scroll_objects(client, space_id):
    """Scroll one space and return ``{object_id: {name, type, headings}}`` (read-only)."""
    from anytype_llm_wiki import config
    from qdrant_client.models import FieldCondition, Filter, MatchValue

    flt = Filter(must=[FieldCondition(key="space_id", match=MatchValue(value=space_id))])
    objects, offset = {}, None
    while True:
        points, offset = client.scroll(
            collection_name=config.QDRANT_COLLECTION, scroll_filter=flt, limit=1000,
            offset=offset, with_payload=True, with_vectors=False,
        )
        for point in points:
            p = point.payload or {}
            entry = objects.setdefault(p.get("object_id", ""), {
                "name": p.get("object_name", ""), "type": p.get("type_key", ""),
                "headings": [],
            })
            if p.get("heading"):
                entry["headings"].append(p["heading"])
        if offset is None:
            return objects


def _name_keys(name, strip):
    keys = {strip(name)}
    match = _PAREN_RE.search(name)
    if match:
        keys.add(strip(match.group(1)))
    keys.discard("")
    return keys


def propose(case, objects, dense_hits, strip, tokenize):
    """Build the proposal list for one case; ``objects`` is the space's object table."""
    from rank_bm25 import BM25Okapi

    types = set(case.get("types") or [])
    eligible = {
        oid: o for oid, o in objects.items() if oid and (not types or o["type"] in types)
    }
    sources: dict[str, list[str]] = {}

    def add(oid, source):
        if oid in eligible and source not in sources.setdefault(oid, []):
            sources[oid].append(source)

    query_key = strip(case["query"])
    query_tokens = set(tokenize(query_key))
    for oid, obj in eligible.items():
        if query_key and query_key in _name_keys(obj["name"], strip):
            add(oid, "key_equality")
        if query_tokens and query_tokens <= set(tokenize(obj["name"])):
            add(oid, "name_token")
    for hit in dense_hits[:PROPOSAL_DEPTH]:
        add(hit["object_id"], "dense_top20")
    ids = list(eligible)
    corpus = [tokenize(eligible[oid]["name"]) for oid in ids]
    if ids and any(corpus):
        scores = BM25Okapi(corpus).get_scores(tokenize(case["query"]))
        ranked = sorted(zip(scores, ids), key=lambda pair: pair[0], reverse=True)
        for score, oid in ranked[:PROPOSAL_DEPTH]:
            if score > 0:
                add(oid, "name_bm25_top20")
    return [
        {"object_id": oid, "name": eligible[oid]["name"], "type": eligible[oid]["type"],
         "sources": srcs}
        for oid, srcs in sources.items()
    ]


def context_phrase(obj):
    """Context for a shared-name member: its name's parenthetical, else its first heading."""
    match = _PAREN_RE.search(obj["name"])
    if match and match.group(1).strip():
        return match.group(1).strip()
    return next((h for h in obj["headings"] if h.strip()), "")


def build_case(case, objects, dense_hits, strip, tokenize):
    proposals = propose(case, objects, dense_hits, strip, tokenize)
    out = {k: case[k] for k in ("id", "group", "query", "space_id", "types")}
    out["expected_ids"] = [p["object_id"] for p in proposals if "key_equality" in p["sources"]]
    out["proposals"] = proposals
    out["dense_top_ids"] = [h["object_id"] for h in dense_hits[:DENSE_TOP_IDS]]
    return out


def curate(targets, client, search):
    """Return the proposal document for ``targets`` (read-only).

    Args:
        targets: list of target dicts.
        client: Qdrant client (only ``scroll`` is called).
        search: ``f(query, space_id, types, limit) -> hits`` (``semantic_search_core``).
    """
    strip, tokenize = _name_helpers()
    tables: dict[str, dict] = {}
    cases = []
    for target in targets:
        space = target["space_id"]
        objects = tables.setdefault(space, scroll_objects(client, space))
        dense = search(target["query"], space, target.get("types"), PROPOSAL_DEPTH)
        base = build_case(target, objects, dense, strip, tokenize)
        cases.append(base)
        if not target.get("shared"):
            continue
        for index, oid in enumerate(base["expected_ids"], start=1):
            phrase = context_phrase(objects[oid])
            if not phrase:
                continue
            query = f"{target['query']} ({phrase})"
            variant = {**target, "id": f"{target['id']}-context-{index}", "query": query}
            dense_variant = search(query, space, target.get("types"), PROPOSAL_DEPTH)
            case = build_case(variant, objects, dense_variant, strip, tokenize)
            case["expected_ids"] = list(base["expected_ids"])
            case["right_id"] = oid
            cases.append(case)
    return {"frozen": False, "generated_by": "scripts/curate_eval_cases.py", "cases": cases}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--targets", required=True, help="JSON file with the target list")
    parser.add_argument("--output", required=True, help="where to write the proposals")
    args = parser.parse_args(argv)

    raw = json.loads(Path(args.targets).read_text())
    targets = raw["cases"] if isinstance(raw, dict) else raw

    from anytype_llm_wiki import indexer

    def search(query, space_id, types, limit):
        return indexer.semantic_search_core(
            query=query, space_id=space_id, types=types, limit=limit)

    document = curate(targets, indexer._qdrant(), search)
    Path(args.output).write_text(json.dumps(document, indent=2, ensure_ascii=False))
    print(f"wrote {len(document['cases'])} cases to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
