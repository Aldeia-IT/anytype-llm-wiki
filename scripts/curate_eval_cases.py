"""Propose expected object IDs for the AC-EVAL2 retrieval eval (Aldeia-IT/aldeia-box#327).

READ-ONLY: the only Qdrant calls are ``scroll`` and ``semantic_search_core`` (a query).
It never writes to the wiki, to Qdrant or to the index state file; its single output is
the ``--output`` JSON file. It prints only a one-line summary (no config values, no
secrets, no chunk text).

The script decides nothing. Every case comes out with ``expected_ids: []``: no rule of
the code under test defines the expected IDs (spec AC-EVAL2). A human reviews the labelled
``proposals`` once, copies the IDs of the objects the name really denotes into
``expected_ids`` (and picks ``right_id`` for each "(context)" case), sets
``"frozen": true`` and keeps the file outside the repo. The eval test errors on an
unfrozen fixture, and on a frozen one whose named cases still have no ``expected_ids``.

Usage:
    uv run python scripts/curate_eval_cases.py --targets targets.json --output proposals.json

``targets.json`` is ``{"cases": [...]}`` (or a bare list). Each target has ``id``,
``group``, ``query``, ``space_id`` and ``types``; ``shared: true`` marks a name that
several objects share. For a shared target the script adds one "(context)" case per
key-equality candidate, with that candidate as ``right_id_proposal``; the human keeps,
drops or adds these cases.

Proposal sources per case (an object may carry several, in ``sources``):
  key_equality     the query's D13 key (``strip_name``) is one of the object's
                   ``indexer.name_keys``
  name_token       every query token (``_tokenize`` of the query key) is in the name tokens
  dense_top20      the top 20 of ``semantic_search_core`` for the query
  name_bm25_top20  the top 20 of a BM25 over object names only

Output: ``{"frozen": false, "cases": [...]}``; each case keeps the target fields plus
``expected_ids`` (always ``[]``, for the human to fill), ``proposals`` (``object_id``,
``name``, ``type``, ``sources``), ``dense_top_ids`` and, for a "(context)" case,
``right_id: null`` with ``right_id_proposal`` (the candidate the context was taken from).
"""

import argparse
import json
import sys
from pathlib import Path

PROPOSAL_DEPTH = 20
DENSE_TOP_IDS = 10


def scroll_objects(client, space_id):
    """Scroll one space and return ``{object_id: {name, type, headings}}`` (read-only).

    Follows Qdrant's ``next_page_offset`` until it is ``None``.
    """
    from qdrant_client.models import FieldCondition, Filter, MatchValue

    from anytype_llm_wiki import config

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


def propose(case, objects, dense_hits):
    """Build the labelled proposal list for one case; ``objects`` is the space's table.

    Returns:
        ``[{object_id, name, type, sources}]``, candidates only (nothing is decided).
    """
    from rank_bm25 import BM25Okapi

    from anytype_llm_wiki.indexer import _tokenize as tokenize
    from anytype_llm_wiki.indexer import name_keys, strip_name

    types = set(case.get("types") or [])
    eligible = {
        oid: o for oid, o in objects.items() if oid and (not types or o["type"] in types)
    }
    sources: dict[str, list[str]] = {}

    def add(oid, source):
        if oid in eligible and source not in sources.setdefault(oid, []):
            sources[oid].append(source)

    query_key = strip_name(case["query"])
    query_tokens = set(tokenize(query_key))
    for oid, obj in eligible.items():
        if query_key and query_key in name_keys(obj["name"]):
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
    from anytype_llm_wiki.indexer import _TRAILING_PAREN_RE

    match = _TRAILING_PAREN_RE.search(obj["name"])
    if match and match.group(1).strip():
        return match.group(1).strip()
    return next((h for h in obj["headings"] if h.strip()), "")


def build_case(case, objects, dense_hits):
    """One output case: the target fields, an empty ``expected_ids`` and the proposals."""
    out = {k: case[k] for k in ("id", "group", "query", "space_id", "types")}
    out["expected_ids"] = []  # the human fills this in; nothing is pre-decided
    out["proposals"] = propose(case, objects, dense_hits)
    out["dense_top_ids"] = [h["object_id"] for h in dense_hits[:DENSE_TOP_IDS]]
    return out


def curate(targets, client, search):
    """Return the proposal document for ``targets`` (read-only).

    Args:
        targets: list of target dicts.
        client: Qdrant client (only ``scroll`` is called).
        search: ``f(query, space_id, types, limit) -> hits`` (``semantic_search_core``).
    """
    tables: dict[str, dict] = {}
    cases = []
    for target in targets:
        space = target["space_id"]
        if space not in tables:
            tables[space] = scroll_objects(client, space)
        objects = tables[space]
        dense = search(target["query"], space, target.get("types"), PROPOSAL_DEPTH)
        base = build_case(target, objects, dense)
        cases.append(base)
        if not target.get("shared"):
            continue
        members = [p for p in base["proposals"] if "key_equality" in p["sources"]]
        for index, member in enumerate(members, start=1):
            phrase = context_phrase(objects[member["object_id"]])
            if not phrase:
                continue
            query = f"{target['query']} ({phrase})"
            variant = {**target, "id": f"{target['id']}-context-{index}", "query": query}
            dense_variant = search(query, space, target.get("types"), PROPOSAL_DEPTH)
            case = build_case(variant, objects, dense_variant)
            case["right_id"] = None  # the human picks it; see right_id_proposal
            case["right_id_proposal"] = member
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
