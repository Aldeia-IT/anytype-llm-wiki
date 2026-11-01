"""Name-aware hybrid retrieval tests (Aldeia-IT/aldeia-box#327, spec v2).

Red until the implementation exists. Tests drive the REAL build path
(``_build_bm25_index`` / ``_bm25_search``, name tier, fusion) and monkeypatch only
``_qdrant`` and ``embed_query`` (spec section 6: "real build path"). New module-level
symbols are touched inside test bodies (or with ``raising=False`` in fixtures) so the
file collects cleanly before the code exists.

The dense side is a fake that applies the Qdrant filter it is handed (space, types,
source_type, domain_tags; date ranges are not evaluated). Spaces are isolated by
that filter in the fake exactly as Qdrant does.

Each test names its acceptance criterion (AC-*) in the name or docstring.
"""

import contextlib
import json
import threading
import time
from types import SimpleNamespace

import httpx
import pytest

from anytype_llm_wiki import config
from tests.test_indexer import (
    _LAST_MOD,
    FakeQdrantClientWithSearch,
    _entity_obj,
    _source_obj,
)

SPACE = "sp"


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------


def _point(point_id, object_id, name, text, *, space=SPACE, type_key="wiki_entity",
           heading="", source_type=None, domain_tags=None, wiki_url=None):
    payload = {
        "object_id": object_id, "object_name": name, "text": text, "heading": heading,
        "type_key": type_key, "space_id": space,
    }
    if source_type is not None:
        payload["source_type"] = source_type
    if domain_tags is not None:
        payload["domain_tags"] = domain_tags
    if wiki_url is not None:
        payload["wiki_url"] = wiki_url
    return SimpleNamespace(id=point_id, payload=payload, score=0.0)


def _fillers(count, *, space=SPACE, prefix="fill"):
    """Chunks that never match a query word used in these tests."""
    return [
        _point(f"{prefix}-{i}", f"{prefix}-obj-{i}", f"Filler{prefix}{i}",
               f"lorem ipsum dolor{i} sit amet", space=space)
        for i in range(count)
    ]


def _filter_matches(query_filter, payload):
    """Evaluate a qdrant Filter against a payload (date ranges always pass)."""
    from qdrant_client.models import Filter, MatchAny

    if query_filter is None:
        return True

    def cond_ok(cond):
        if isinstance(cond, Filter):
            must = all(cond_ok(c) for c in (cond.must or []))
            should = any(cond_ok(c) for c in cond.should) if cond.should else True
            return must and should
        if getattr(cond, "range", None) is not None:
            return True
        value = payload.get(cond.key)
        if isinstance(cond.match, MatchAny):
            values = value if isinstance(value, list) else [value]
            return any(v in cond.match.any for v in values)
        if isinstance(value, list):
            return cond.match.value in value
        return value == cond.match.value

    return cond_ok(query_filter)


class FakeHybridQdrant:
    """Fake Qdrant: ``scroll`` (honours scroll_filter) and ``query_points`` (dense)."""

    def __init__(self, points, dense_ids=(), dense_error=None, on_scroll=None,
                 page_size=None):
        self.points = list(points)
        self.dense_ids = list(dense_ids)
        self.dense_error = dense_error
        self.on_scroll = on_scroll
        self.page_size = page_size  # None: one page; else min(limit, page_size) per page
        self.scroll_calls = []
        self.query_calls = []

    def scroll(self, collection_name, scroll_filter=None, limit=1000, offset=None,
               with_payload=True, with_vectors=False):
        self.scroll_calls.append({"filter": scroll_filter, "limit": limit, "offset": offset})
        if self.on_scroll is not None:
            self.on_scroll()
        chosen = [p for p in self.points if _filter_matches(scroll_filter, p.payload)]
        if self.page_size is None:
            return chosen, None
        start = 0 if offset is None else int(offset.removeprefix("page-"))
        end = start + min(limit, self.page_size)
        # An opaque string offset, as Qdrant returns a point id: a caller must pass it back.
        return chosen[start:end], (f"page-{end}" if end < len(chosen) else None)

    def query_points(self, collection_name, query, query_filter=None, limit=10,
                     with_payload=True):
        self.query_calls.append({"filter": query_filter, "limit": limit})
        if self.dense_error is not None:
            raise self.dense_error
        by_id = {p.id: p for p in self.points}
        ordered = [by_id[i] for i in self.dense_ids if i in by_id]
        ordered = [p for p in ordered if _filter_matches(query_filter, p.payload)]
        hits = [
            SimpleNamespace(id=p.id, payload=p.payload, score=round(0.9 - 0.01 * rank, 4))
            for rank, p in enumerate(ordered[:limit])
        ]
        return SimpleNamespace(points=hits)


def _scroll_spaces(fake):
    """The space ids each recorded scroll was filtered on (``None`` = unfiltered)."""
    spaces = []
    for call in fake.scroll_calls:
        flt = call["filter"]
        found = [
            c.match.value for c in (getattr(flt, "must", None) or [])
            if getattr(c, "key", None) == "space_id"
        ]
        spaces.append(found[0] if found else None)
    return spaces


def _set_versions(versions):
    """Write ``_bm25_corpus_versions`` into the (patched) state file, keeping other keys."""
    state = json.loads(config.INDEX_STATE_FILE.read_text()) if config.INDEX_STATE_FILE.exists() else {}
    state["_bm25_corpus_versions"] = dict(versions)
    config.INDEX_STATE_FILE.write_text(json.dumps(state))


def _read_versions():
    if not config.INDEX_STATE_FILE.exists():
        return {}
    return json.loads(config.INDEX_STATE_FILE.read_text()).get("_bm25_corpus_versions", {})


@pytest.fixture
def ix(monkeypatch, tmp_path):
    """The indexer module with an isolated state file and cleared per-space BM25 state."""
    from anytype_llm_wiki import indexer

    monkeypatch.setattr(config, "INDEX_STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(config, "INDEX_STATE_DIR", tmp_path)
    monkeypatch.setattr(indexer, "embed_query", lambda q: [0.1] * config.EMBED_DIMS)
    monkeypatch.setattr(indexer, "_bm25_indexes", {})
    monkeypatch.setattr(indexer, "_bm25_built_versions", {})
    monkeypatch.setattr(indexer, "_bm25_empty_versions", {})
    return indexer


def _install(ix, monkeypatch, fake):
    monkeypatch.setattr(ix, "_qdrant", lambda: fake)
    return fake


def _search(ix, query, *, space=SPACE, limit=10, **kwargs):
    return ix.hybrid_search_core(query=query, space_id=space, limit=limit, **kwargs)


def _oids(hits):
    return [h["object_id"] for h in hits]


def _names(hits):
    return [h["object_name"] for h in hits]


D14_KEYS = {"object_name", "object_id", "type", "heading", "text", "score"}


# ---------------------------------------------------------------------------
# AC-TOK
# ---------------------------------------------------------------------------


def _tok(text):
    from anytype_llm_wiki.indexer import _tokenize

    return set(_tokenize(text))


def test_ac_tok_punctuation_dropped():
    assert _tok("Hats,") == _tok("hats") == {"hats"}


def test_ac_tok_hyphenated_token_yields_whole_and_parts():
    assert _tok("sg-3") == {"sg-3", "sg", "3"}


def test_ac_tok_underscored_token_yields_whole_and_parts():
    assert _tok("wiki_entity") == {"wiki_entity", "wiki", "entity"}


def test_ac_tok_apostrophe_token_yields_whole_and_parts():
    assert _tok("d'Angola") == {"d'angola", "d", "angola"}


def test_ac_tok_diacritics_fold():
    assert _tok("Zulu") == _tok("Zulú")
    assert _tok("Aberre") == _tok("Aberrê")


def test_ac_tok_stopwords_dropped_english_and_portuguese():
    assert _tok("the Mestre of Salvador") == {"mestre", "salvador"}
    assert _tok("Mestre para Salvador com Bimba") == {"mestre", "salvador", "bimba"}


def test_ac_tok_stopword_parts_dropped_too():
    assert "the" not in _tok("the-mestre")
    assert "mestre" in _tok("the-mestre")


def test_ac_tok_all_stopword_query_yields_no_tokens():
    assert _tok("what is the") == set()
    assert _tok("para com de") == set()
    assert _tok("") == set()


# ---------------------------------------------------------------------------
# AC-INDEX
# ---------------------------------------------------------------------------


def test_ac_index_object_name_is_searchable(ix, monkeypatch):
    """AC-INDEX: 'Hats Protocol' finds the object whose text lacks the phrase."""
    pts = [_point("pA", "oA", "Hats Protocol", "roles onchain trees")] + _fillers(6)
    _install(ix, monkeypatch, FakeHybridQdrant(pts, dense_ids=["fill-0"]))
    out = _search(ix, "Hats Protocol governance")
    assert "oA" in _oids(out)


def test_ac_index_heading_is_searchable(ix, monkeypatch):
    pts = [_point("pH", "oH", "Gamma Doc", "unrelated words only", heading="Quorum Rules")]
    pts += _fillers(6)
    _install(ix, monkeypatch, FakeHybridQdrant(pts, dense_ids=["fill-0"]))
    assert "oH" in _oids(_search(ix, "quorum rules"))


def test_ac_index_name_counts_twice(ix, monkeypatch):
    """AC-INDEX: a name match outranks a single text match of equal length.

    Y precedes X in the corpus so a tie (name counted once) would put Y first.
    """
    pts = [
        _point("pY", "oY", "Other Beta", "zebra one"),
        _point("pX", "oX", "Zebra Alpha", "one two"),
    ] + _fillers(6)
    _install(ix, monkeypatch, FakeHybridQdrant(pts))
    out = _oids(_search(ix, "zebra stripes"))
    assert "oX" in out and "oY" in out
    assert out.index("oX") < out.index("oY")


def test_ac_h7_full_text_indexed_but_hit_text_truncated(ix, monkeypatch):
    """AC-H7 / D11: the BM25 document uses the full text; the stored hit text is [:500]."""
    long_text = " ".join(f"word{i}" for i in range(400)) + " needleterm"
    assert len(long_text) > 500
    pts = [_point("pL", "oL", "Long Doc", long_text)] + _fillers(6)
    _install(ix, monkeypatch, FakeHybridQdrant(pts))
    out = _search(ix, "needleterm")
    assert _oids(out) == ["oL"]
    assert len(out[0]["text"]) <= 500


# ---------------------------------------------------------------------------
# AC-TIER
# ---------------------------------------------------------------------------


def _decoy_scenario(target_name, query, *, target_type="wiki_entity"):
    """A target plus three decoys whose text is the query repeated (BM25 and dense lead)."""
    import re

    words = re.sub(r"[^\w\s'-]", " ", query)
    decoy_text = (" " + words) * 5
    pts = [_point(f"d{i}", f"dec{i}", f"Notes {i}", decoy_text) for i in range(3)]
    pts.append(_point("tgt", "target", target_name, "capoeira angola history",
                      type_key=target_type))
    pts += _fillers(5)
    return pts, ["d0", "d1", "d2", "tgt"]


@pytest.mark.parametrize("target_name, query", [
    ("Mestre Pastinha", "Mestre Pastinha"),
    ("Mestre Pastinha", "pastinha"),
    ("Mestre Pastinha", "Mestre Pastinha (Salvador)"),
    ("Mestre Pastinha", "PASTINHA"),
    ("Mestre Bimba", "Mestre Bimba?"),
    ("Cobra Mansa", "Cobra Mansa,"),
    ("Foca", "Contra-Mestre Foca"),
    ("Contra-Mestre Foca", "foca"),
    ("Mestre Zulú", "mestre zulu"),
    ("Zulu", "Mestre Zulú"),
    ("Aberrê", "Aberre"),
    ("Matrix (Synapse + Element)", "Synapse Element"),
    ("Matrix (Synapse + Element)", "Matrix"),
    ("Mestre", "Mestre"),
])
def test_ac_tier_exact_name_ranks_first(ix, monkeypatch, target_name, query):
    """AC-TIER tier 1: title, context, punctuation and diacritics are ignored."""
    pts, dense_ids = _decoy_scenario(target_name, query)
    _install(ix, monkeypatch, FakeHybridQdrant(pts, dense_ids=dense_ids))
    out = _search(ix, query)
    assert out, "expected hits"
    assert out[0]["object_id"] == "target", _names(out)


def test_ac_tier_two_partial_name_after_exact_before_untiered(ix, monkeypatch):
    """AC-TIER tier 2: every query word in the name, after tier 1, before untiered."""
    pts = [
        _point("dd", "decoy", "Server Notes", "matrix synapse " * 6),
        _point("t2", "tier2", "Matrix Synapse Admin Guide", "setup steps"),
        _point("t1", "tier1", "Matrix Synapse", "overview"),
    ] + _fillers(5)
    _install(ix, monkeypatch, FakeHybridQdrant(pts, dense_ids=["dd", "t2", "t1"]))
    out = _search(ix, "Matrix Synapse")
    assert _oids(out)[:3] == ["tier1", "tier2", "decoy"]
    assert out[0]["score"] > out[1]["score"] > out[2]["score"]


def test_ac_tier_two_hyphenated_query_word(ix, monkeypatch):
    """AC-TIER: 'SG-3' puts the object whose name contains it ahead of untiered chunks."""
    pts = [
        _point("dd", "decoy", "Plan Notes", "sg-3 " * 8),
        _point("t2", "tier2", "SG-3 Hardening Plan", "steps"),
    ] + _fillers(5)
    _install(ix, monkeypatch, FakeHybridQdrant(pts, dense_ids=["dd", "t2"]))
    assert _oids(_search(ix, "SG-3"))[0] == "tier2"


def test_ac_tier_several_same_name_objects_all_in_tier_one(ix, monkeypatch):
    pts = [_point(f"d{i}", f"dec{i}", f"Notes {i}", "cobra mansa " * 6) for i in range(3)]
    pts += [_point(f"c{i}", f"cm{i}", "Cobra Mansa", f"bio part {i}") for i in range(3)]
    pts += _fillers(5)
    _install(ix, monkeypatch, FakeHybridQdrant(
        pts, dense_ids=["d0", "d1", "d2", "c0", "c1", "c2"]))
    out = _search(ix, "Cobra Mansa")
    assert set(_oids(out)[:3]) == {"cm0", "cm1", "cm2"}


def test_ac_tier_empty_key_gives_no_tier(ix, monkeypatch):
    """AC-TIER: a query with an empty key never tiers (even an object whose name is empty-keyed)."""
    pts = [_point("q", "qmark", "???", "punctuation page")] + _fillers(5)
    _install(ix, monkeypatch, FakeHybridQdrant(pts, dense_ids=["q"]))
    out = _search(ix, "???")
    assert out and all(h["score"] < 1.0 for h in out)


def test_ac_tier_tier_never_applied_across_spaces(ix, monkeypatch):
    """AC-TIER + AC-XSPACE: the name table is per space."""
    pts = [_point("pb", "other-space", "Pastinha", "bio", space="sp_B")]
    pts += [_point("pa", "this-space", "Notes", "pastinha " * 4, space="sp_A")]
    pts += _fillers(5, space="sp_A", prefix="a") + _fillers(5, space="sp_B", prefix="b")
    _install(ix, monkeypatch, FakeHybridQdrant(pts, dense_ids=["pa"]))
    assert "other-space" not in _oids(_search(ix, "Pastinha", space="sp_A"))


# ---------------------------------------------------------------------------
# AC-TIER-CFG
# ---------------------------------------------------------------------------


def test_ac_tier_cfg_parse_unset_gives_none():
    assert config._parse_title_words(None) is None


def test_ac_tier_cfg_parse_empty_gives_empty_tuple():
    assert config._parse_title_words("") == ()


def test_ac_tier_cfg_parse_list_is_folded_and_trimmed():
    assert config._parse_title_words(" Doutor , Dr ,PROFESSOR, Capão ") == (
        "doutor", "dr", "professor", "capao",
    )


def test_ac_tier_cfg_attribute_exists():
    assert hasattr(config, "NAME_TIER_TITLE_WORDS")


def _title_scenario(ix, monkeypatch, object_name, query):
    pts = [_point(f"d{i}", f"dec{i}", f"Notes {i}", (query + " ") * 6) for i in range(3)]
    pts.append(_point("tgt", "target", object_name, "bio"))
    pts += _fillers(5)
    _reset_index_state(ix, monkeypatch)  # each scenario is a new corpus at version 0
    _install(ix, monkeypatch, FakeHybridQdrant(pts, dense_ids=["d0", "d1", "d2", "tgt"]))
    return _search(ix, query)


def test_ac_tier_cfg_patched_list_is_used(ix, monkeypatch):
    monkeypatch.setattr(config, "NAME_TIER_TITLE_WORDS", ("doutor",), raising=False)
    assert _title_scenario(ix, monkeypatch, "Ana", "Doutor Ana")[0]["object_id"] == "target"


def test_ac_tier_cfg_none_uses_builtin_list(ix, monkeypatch):
    monkeypatch.setattr(config, "NAME_TIER_TITLE_WORDS", None, raising=False)
    assert _title_scenario(ix, monkeypatch, "Pastinha", "Mestre Pastinha")[0]["object_id"] == "target"
    # 'doutor' is not built in: 'Doutor Ana' is not reduced to 'ana'.
    assert _title_scenario(ix, monkeypatch, "Ana", "Doutor Ana")[0]["object_id"] != "target"


def test_ac_tier_cfg_empty_tuple_strips_nothing(ix, monkeypatch):
    monkeypatch.setattr(config, "NAME_TIER_TITLE_WORDS", (), raising=False)
    out = _title_scenario(ix, monkeypatch, "Pastinha", "Mestre Pastinha")
    assert out[0]["object_id"] != "target"
    # control: with no title words an exact full-name match is still tier 1
    exact = _title_scenario(ix, monkeypatch, "Mestre Pastinha", "Mestre Pastinha")
    assert exact[0]["object_id"] == "target"


# ---------------------------------------------------------------------------
# AC-DEPTH
# ---------------------------------------------------------------------------


def _depth_corpus(extra):
    """60 decoys outscore every ``extra`` chunk on 'orion' (beyond depth 50), plus fillers."""
    decoys = [
        _point(f"star-{i}", f"star-obj-{i}", f"Star {i}", "orion " * 6)
        for i in range(60)
    ]
    long_tail = " ".join(f"w{j}" for j in range(40))
    return decoys, [e(long_tail) if callable(e) else e for e in extra], _fillers(100)


def _depth_search(ix, monkeypatch, extra, query="orion", limit=3, **kwargs):
    decoys, extras, fill = _depth_corpus(extra)
    fake = FakeHybridQdrant(decoys + extras + fill, dense_ids=[p.id for p in decoys])
    _install(ix, monkeypatch, fake)
    return _search(ix, query, limit=limit, **kwargs)


def test_ac_depth_tier_one_entrant_is_in_output_ordered_by_bm25(ix, monkeypatch):
    extra = [
        lambda tail: _point("ta-weak", "oTA", "Orion", tail),
        lambda tail: _point("ta-strong", "oTA", "Orion", "orion " + tail),
        lambda tail: _point("tb", "oTB", "Orion", tail),
    ]
    out = _depth_search(ix, monkeypatch, extra, limit=3)
    assert _oids(out)[:2] == ["oTA", "oTB"]
    # one chunk enters per object: the highest BM25 one
    assert _oids(out).count("oTA") == 1
    assert out[0]["text"].startswith("orion")


def test_ac_depth_tier_two_object_does_not_enter(ix, monkeypatch):
    extra = [
        lambda tail: _point("t2", "oT2", "Orion Nebula Guide", tail),
        lambda tail: _point("t1", "oT1", "Orion", tail),  # control: tier 1 does enter
    ]
    out = _depth_search(ix, monkeypatch, extra, limit=5)
    assert "oT1" in _oids(out)
    assert "oT2" not in _oids(out)


def test_ac_depth_entrant_respects_type_and_date_gate(ix, monkeypatch):
    """AC-DEPTH + D5: the entrant is subject to the gate (type and date rule)."""
    extra = [lambda tail: _point("ta", "oTA", "Orion", tail)]
    assert "oTA" in _oids(_depth_search(ix, monkeypatch, extra, limit=3))  # positive control
    wrong_type = _depth_search(ix, monkeypatch, extra, limit=3, types=["wiki_concept"])
    assert "oTA" not in _oids(wrong_type)
    dated = _depth_search(ix, monkeypatch, extra, limit=3, ingested_after="2026-01-01")
    assert "oTA" not in _oids(dated)


# ---------------------------------------------------------------------------
# AC-SCORE-MONO and AC-CHUNK
# ---------------------------------------------------------------------------


def _multi_chunk_corpus():
    def chunks(prefix, oid, name, count):
        return [_point(f"{prefix}{i}", oid, name, f"section {i} about topics {prefix}")
                for i in range(count)]

    pts = chunks("a", "oA", "Cobra Mansa", 3) + chunks("b", "oB", "Cobra Mansa", 3)
    pts += chunks("g", "oG", "Cobra Mansa Capoeira Group", 2)
    pts += [_point(f"d{i}", f"dec{i}", f"Notes {i}", "cobra mansa " * 5) for i in range(3)]
    pts += _fillers(5)
    dense = ["d0", "d1", "d2", "g0", "g1", "a0", "b0"]
    return pts, dense


def test_ac_chunk_first_chunks_precede_any_second_chunk(ix, monkeypatch):
    """AC-CHUNK: N same-name objects: all N first chunks precede any second chunk."""
    pts, dense = _multi_chunk_corpus()
    _install(ix, monkeypatch, FakeHybridQdrant(pts, dense_ids=dense))
    out = _search(ix, "Cobra Mansa", limit=20)
    assert set(_oids(out)[:2]) == {"oA", "oB"}
    assert set(_oids(out)[2:6]) == {"oA", "oB"}
    assert _oids(out).count("oA") == 3 and _oids(out).count("oB") == 3


def test_ac_chunk_small_limit_keeps_every_same_name_object(ix, monkeypatch):
    pts, dense = _multi_chunk_corpus()
    _install(ix, monkeypatch, FakeHybridQdrant(pts, dense_ids=dense))
    assert set(_oids(_search(ix, "Cobra Mansa", limit=2))) == {"oA", "oB"}


def test_ac_score_mono_bands_and_offsets(ix, monkeypatch):
    """AC-SCORE-MONO: non-increasing scores, strict between bands, D8 offsets."""
    pts, dense = _multi_chunk_corpus()
    _install(ix, monkeypatch, FakeHybridQdrant(pts, dense_ids=dense))
    out = _search(ix, "Cobra Mansa", limit=20)
    scores = [h["score"] for h in out]
    assert scores == sorted(scores, reverse=True)
    assert sorted(out, key=lambda h: -h["score"]) == out  # stable re-sort is a no-op
    # bands: tier-1 firsts (0,1) > tier-1 others (2..5) > tier-2 first (6) > tier-2 second (7)
    assert scores[1] > scores[2]
    assert scores[5] > scores[6] > scores[7]
    assert _oids(out)[6] == "oG" and _oids(out)[7] == "oG"
    # untiered chunks are all below the lowest tier-2 chunk
    assert all(s < scores[7] for s in scores[8:])
    assert 2.5 <= scores[0] < 2.54
    assert 2.0 <= scores[2] < 2.04
    assert 1.5 <= scores[6] < 1.54
    assert 1.0 <= scores[7] < 1.04
    assert scores[8] < 0.05


def test_ac_score_mono_tier2_object_cap_keeps_tier_one_object(ix, monkeypatch):
    """AC-SCORE-MONO: Tier-2's object cap keeps a tier-1 object over higher-RRF untiered ones."""
    from anytype_llm_wiki.wiki import config as wiki_config
    from anytype_llm_wiki.wiki import query as q

    pts = [_point(f"d{i}", f"dec{i}", f"Notes {i}", "pastinha " * 8) for i in range(4)]
    pts.append(_point("t", "target", "Mestre Pastinha", "bio"))
    pts += _fillers(5)
    _install(ix, monkeypatch, FakeHybridQdrant(
        pts, dense_ids=["d0", "d1", "d2", "d3", "t"]))
    hits = _search(ix, "Pastinha", limit=10)
    seen, candidates = set(), []
    for hit in hits:  # the Tier-2 dedup: first (best-scored) chunk per object
        if hit["object_id"] in seen:
            continue
        seen.add(hit["object_id"])
        candidates.append({
            "object_id": hit["object_id"], "score": hit["score"],
            "obj": {"id": hit["object_id"], "name": hit["object_name"], "properties": []},
        })
    monkeypatch.setattr(wiki_config, "synth_max_objects", lambda: 1)
    kept = q._build_context(candidates, [])[1]
    assert [c["object_id"] for c in kept] == ["target"]


# ---------------------------------------------------------------------------
# AC-SPACE, AC-NOSPACE, AC-XSPACE
# ---------------------------------------------------------------------------


def _space_corpus(space, zebra_chunks, lion_chunks):
    """Single-term chunks of identical length; only per-space IDF orders 'zebra lion'."""
    pts = []
    for i in range(zebra_chunks):
        pts.append(_point(f"{space}-z{i}", f"{space}-z{i}", f"zn{space}{i}", "zebra xx yy",
                          space=space))
    for i in range(lion_chunks):
        pts.append(_point(f"{space}-l{i}", f"{space}-l{i}", f"ln{space}{i}", "lion xx yy",
                          space=space))
    return pts


def _two_space_points():
    a = _space_corpus("spA", 1, 4) + _fillers(5, space="spA", prefix="fa")
    b = _space_corpus("spB", 8, 1) + _fillers(1, space="spB", prefix="fb")
    return a, b


def _reset_index_state(ix, monkeypatch):
    """Forget every built BM25 index and every recorded build version."""
    monkeypatch.setattr(ix, "_bm25_indexes", {})
    monkeypatch.setattr(ix, "_bm25_built_versions", {})
    monkeypatch.setattr(ix, "_bm25_empty_versions", {})


def _order_alone(ix, monkeypatch, points, space):
    _reset_index_state(ix, monkeypatch)
    _install(ix, monkeypatch, FakeHybridQdrant(points))
    return _oids(_search(ix, "zebra lion", space=space, limit=20))


@pytest.mark.parametrize("space", ["spA", "spB"])
def test_ac_space_bm25_order_equals_single_space_index(ix, monkeypatch, space):
    """AC-SPACE: no cross-space IDF."""
    a, b = _two_space_points()
    alone = _order_alone(ix, monkeypatch, a if space == "spA" else b, space)
    assert alone, "expected BM25 hits"
    _install(ix, monkeypatch, FakeHybridQdrant(a + b))
    _reset_index_state(ix, monkeypatch)
    combined = _oids(_search(ix, "zebra lion", space=space, limit=20))
    assert combined == alone


def test_ac_space_scrolls_are_scoped_to_the_space(ix, monkeypatch):
    a, b = _two_space_points()
    fake = _install(ix, monkeypatch, FakeHybridQdrant(a + b))
    _search(ix, "zebra lion", space="spA")
    _search(ix, "zebra lion", space="spB")
    assert sorted(_scroll_spaces(fake)) == ["spA", "spB"]


def test_ac_space_bump_rebuilds_only_that_space(ix, monkeypatch):
    a, b = _two_space_points()
    fake = _install(ix, monkeypatch, FakeHybridQdrant(a + b))
    _set_versions({"spA": 1, "spB": 1})
    _search(ix, "zebra lion", space="spA")
    _search(ix, "zebra lion", space="spB")
    assert len(fake.scroll_calls) == 2
    _search(ix, "zebra lion", space="spA")
    _search(ix, "zebra lion", space="spB")
    assert len(fake.scroll_calls) == 2  # nothing stale
    _set_versions({"spA": 2, "spB": 1})
    _search(ix, "zebra lion", space="spB")
    assert len(fake.scroll_calls) == 2  # spB untouched by spA's bump
    _search(ix, "zebra lion", space="spA")
    assert _scroll_spaces(fake) == ["spA", "spB", "spA"]
    assert "spB" in ix._bm25_indexes and "spA" in ix._bm25_indexes


@pytest.mark.parametrize("unscoped", [None, ""])
def test_ac_nospace_is_dense_only(ix, monkeypatch, unscoped):
    """AC-NOSPACE: falsy space_id: dense-only, no BM25, no tier, no scroll."""
    pts = [
        _point("d0", "dense-first", "Notes", "unrelated text"),
        _point("t", "named", "Pastinha", "bio"),
        _point("bm", "bm25-only", "Other", "pastinha " * 6),
    ] + _fillers(5)
    fake = _install(ix, monkeypatch, FakeHybridQdrant(pts, dense_ids=["d0", "t"]))
    out = ix.hybrid_search_core(query="Pastinha", space_id=unscoped, limit=10)
    assert fake.scroll_calls == []
    assert _oids(out) == ["dense-first", "named"]  # no tier lift, no BM25-only entrant
    assert out[0]["score"] == pytest.approx(0.9, abs=1e-4)  # cosine kept


def test_ac_nospace_tool_description_tells_callers_to_pass_space_id():
    import re

    from anytype_llm_wiki import server

    doc = getattr(server.semantic_search, "__doc__", None) or getattr(
        getattr(server.semantic_search, "fn", None), "__doc__", "") or ""
    assert re.search(r"(?i)name[- ]lookups?|look(?:ing)? up[^.]*\bnames?", doc), doc
    assert "space_id" in doc


def test_ac_xspace_bm25_chunk_of_another_space_never_admitted(ix, monkeypatch):
    pts = [
        _point("p_target", "obj_target", "Alpha", "contradiction detection", space="sp_A"),
        _point("p_other", "obj_other", "Contradiction", "contradiction detection", space="sp_B"),
        _point("p_dense", "obj_dense", "Beta", "unrelated dense hit", space="sp_A"),
    ] + _fillers(4, space="sp_A", prefix="a")
    fake = _install(ix, monkeypatch, FakeHybridQdrant(pts, dense_ids=["p_dense"]))
    out = _search(ix, "contradiction detection", space="sp_A")
    assert "obj_other" not in _oids(out)
    assert "obj_target" in _oids(out)
    assert _scroll_spaces(fake) == ["sp_A"]


# ---------------------------------------------------------------------------
# AC-URL and AC-H4
# ---------------------------------------------------------------------------


def test_ac_url_bm25_only_source_hit_carries_wiki_url(ix, monkeypatch):
    pts = [
        _point("ps", "oS", "Some Page", "orion telescope notes", type_key="wiki_source",
               source_type="document", domain_tags=["ai"], wiki_url="https://example.org/p?x=1"),
        _point("pn", "oN", "Local Note", "orion telescope notes", type_key="wiki_source"),
    ] + _fillers(6)
    _install(ix, monkeypatch, FakeHybridQdrant(pts))
    out = {h["object_id"]: h for h in _search(ix, "orion telescope", types=["wiki_source"])}
    assert out["oS"]["wiki_url"] == "https://example.org/p?x=1"
    assert set(out["oS"]) == D14_KEYS | {"wiki_url"}
    assert "wiki_url" not in out["oN"]
    assert set(out["oN"]) == D14_KEYS


def test_ac_url_name_tier_entrant_carries_wiki_url(ix, monkeypatch):
    extra = [lambda tail: _point("ts", "oTS", "Orion", tail, type_key="wiki_source",
                                 wiki_url="https://example.org/orion")]
    out = _depth_search(ix, monkeypatch, extra, limit=3)
    hit = next(h for h in out if h["object_id"] == "oTS")
    assert hit["wiki_url"] == "https://example.org/orion"
    assert set(hit) == D14_KEYS | {"wiki_url"}


def test_ac_h4_output_keys_are_exactly_the_hit_shape(ix, monkeypatch):
    pts = [
        _point("p1", "o1", "Alpha", "contradiction detection"),
        _point("p2", "o2", "Beta", "contradiction only", source_type="document",
               domain_tags=["ml"]),
    ] + _fillers(5)
    _install(ix, monkeypatch, FakeHybridQdrant(pts, dense_ids=["p1"]))
    out = _search(ix, "contradiction detection")
    assert out
    for hit in out:
        assert set(hit) == D14_KEYS


# ---------------------------------------------------------------------------
# Carried ACs: fusion, fallback, limit, gates
# ---------------------------------------------------------------------------


def test_ac_h2b_fusion_end_to_end(ix, monkeypatch):
    """AC-H2b: dual-list chunk first, once, RRF score; BM25-only chunk recalled."""
    pts = [
        _point("p_shared", "o1", "Alpha", "contradiction detection"),
        _point("p_bm25", "o2", "Beta", "contradiction only here"),
        _point("p_dense", "o3", "Gamma", "unrelated dense neighbor"),
    ] + _fillers(5)
    _install(ix, monkeypatch, FakeHybridQdrant(pts, dense_ids=["p_shared", "p_dense"]))
    out = _search(ix, "contradiction detection", limit=3)
    ids = _oids(out)
    assert ids[0] == "o1" and ids.count("o1") == 1
    assert "o2" in ids
    assert out[0]["score"] == pytest.approx(2 / 61, rel=1e-3)
    assert all(h["score"] < out[0]["score"] for h in out[1:])


def test_ac_h3_bm25_failure_falls_back_to_dense_with_one_warning(ix, monkeypatch, caplog):
    pts = [_point("p1", "o1", "Alpha", "SECRETCHUNKTEXT body")] + _fillers(3)
    _install(ix, monkeypatch, FakeHybridQdrant(pts, dense_ids=["p1"]))

    def boom(*args, **kwargs):
        raise RuntimeError("index exploded")

    monkeypatch.setattr(ix, "_ensure_bm25_fresh", boom)
    with caplog.at_level("WARNING"):
        out = _search(ix, "t", limit=10)
    assert _oids(out) == ["o1"] and out[0]["score"] == pytest.approx(0.9, abs=1e-4)
    warns = [r for r in caplog.records if "bm25_fallback" in r.getMessage()]
    assert len(warns) == 1
    assert "SECRETCHUNKTEXT" not in warns[0].getMessage()


def test_ac_h3_missing_rank_bm25_falls_back_to_dense(ix, monkeypatch):
    import sys

    pts = [_point("p1", "o1", "Alpha", "body")] + _fillers(3)
    _install(ix, monkeypatch, FakeHybridQdrant(pts, dense_ids=["p1"]))
    monkeypatch.setitem(sys.modules, "rank_bm25", None)
    out = _search(ix, "t")
    assert _oids(out) == ["o1"] and out[0]["score"] == pytest.approx(0.9, abs=1e-4)


def test_ac_h5_limit_respected_and_non_positive_is_empty(ix, monkeypatch):
    pts = [_point(f"p{i}", f"o{i}", f"N{i}", "shared term") for i in range(12)] + _fillers(5)
    fake = _install(ix, monkeypatch, FakeHybridQdrant(
        pts, dense_ids=[f"p{i}" for i in range(12)]))
    assert len(_search(ix, "shared term", limit=5)) == 5
    calls = (len(fake.query_calls), len(fake.scroll_calls))
    assert _search(ix, "shared term", limit=0) == []
    assert _search(ix, "shared term", limit=-1) == []
    assert (len(fake.query_calls), len(fake.scroll_calls)) == calls  # no work done


def test_ac_h6_bm25_only_chunk_of_excluded_type_is_dropped(ix, monkeypatch):
    pts = [
        _point("pE", "oE", "Alpha", "gamma topic", type_key="wiki_entity"),
        _point("pS", "oS", "Beta", "gamma topic gamma topic", type_key="wiki_source"),
    ] + _fillers(6)
    _install(ix, monkeypatch, FakeHybridQdrant(pts, dense_ids=["pE"]))
    out = _search(ix, "gamma topic", types=["wiki_entity"])
    assert "oS" not in _oids(out) and "oE" in _oids(out)


def test_ac_h6b_and_qa4_domain_tags_gate_through_real_build(ix, monkeypatch):
    """AC-H6b / AC-QA4: the mismatching chunk scores > 0 and reaches the gate."""
    pts = [
        _point("p_ml", "obj_ml", "Alpha", "machine learning algorithm", domain_tags=["ml"]),
        _point("p_fin", "obj_fin", "Beta", "machine financial analysis",
               domain_tags=["finance"]),
        _point("p_none", "obj_none", "Gamma", "machine untagged page"),
        _point("p_dense", "obj_dense", "Delta", "dense retrieval baseline", domain_tags=["ml"]),
    ] + _fillers(5)
    _install(ix, monkeypatch, FakeHybridQdrant(pts, dense_ids=["p_dense"]))
    ids = set(_oids(_search(ix, "machine learning", domain_tags=["ml"])))
    assert "obj_ml" in ids
    assert "obj_fin" not in ids
    assert "obj_none" not in ids  # absent tags default to []
    unfiltered = set(_oids(_search(ix, "machine learning")))
    assert {"obj_fin", "obj_none"} <= unfiltered


def test_ac_h12_dual_list_chunk_not_displaced_by_raw_bm25_magnitude(ix, monkeypatch):
    pts = [
        _point("pX", "oX", "Obj X", "contradiction detection notes " + "filler " * 3),
        _point("pY", "oY", "Obj Y", "contradiction detection " * 8),
    ] + _fillers(6)
    _install(ix, monkeypatch, FakeHybridQdrant(pts, dense_ids=["pX"]))
    out = _search(ix, "contradiction detection")
    assert _oids(out)[0] == "oX"  # dense rank 0 plus BM25 rank 1 beats BM25 rank 0 alone
    scores = [h["score"] for h in out]
    assert scores == sorted(scores, reverse=True)
    assert max(scores) < 0.05  # RRF magnitudes, never raw BM25


def test_ac_h13_dense_outage_propagates(ix, monkeypatch):
    pts = [_point("p1", "o1", "Alpha", "body")] + _fillers(3)
    _install(ix, monkeypatch, FakeHybridQdrant(
        pts, dense_error=httpx.ConnectError("qdrant down")))
    with pytest.raises(httpx.HTTPError):
        _search(ix, "body")


def test_ac_h14_date_filter_drops_non_dense_chunks_keeps_dense(ix, monkeypatch):
    pts = [
        _point("pD", "oD", "Alpha", "gamma topic"),
        _point("pX", "oX", "Beta", "gamma topic gamma topic"),
    ] + _fillers(6)
    _install(ix, monkeypatch, FakeHybridQdrant(pts, dense_ids=["pD"]))
    assert {"oD", "oX"} <= set(_oids(_search(ix, "gamma topic")))  # control
    dated = set(_oids(_search(ix, "gamma topic", ingested_after="2026-01-01")))
    assert "oD" in dated and "oX" not in dated


# ---------------------------------------------------------------------------
# AC-H8, AC-H9: build, empty scroll, freshness, concurrency
# ---------------------------------------------------------------------------


def test_ac_h7_build_creates_one_space_index_per_space(ix, monkeypatch):
    a, b = _two_space_points()
    fake = _install(ix, monkeypatch, FakeHybridQdrant(a + b))
    ix._ensure_bm25_fresh("spA")
    assert set(ix._bm25_indexes) == {"spA"}
    assert type(ix._bm25_indexes["spA"]).__name__ == "_SpaceIndex"
    assert _scroll_spaces(fake) == ["spA"]


def test_ac_h8_empty_scroll_keeps_prior_index_and_records_version(ix, monkeypatch):
    pts = [_point("p1", "o1", "Alpha", "body text")] + _fillers(3)
    fake = _install(ix, monkeypatch, FakeHybridQdrant(pts))
    _set_versions({SPACE: 1})
    ix._ensure_bm25_fresh(SPACE)
    prior = ix._bm25_indexes[SPACE]
    fake.points = []
    _set_versions({SPACE: 2})
    ix._ensure_bm25_fresh(SPACE)
    assert ix._bm25_indexes[SPACE] is prior
    assert ix._bm25_built_versions[SPACE] == 2


def test_ac_h8_cold_empty_space_stays_absent_and_answers_dense_only(ix, monkeypatch):
    fake = _install(ix, monkeypatch, FakeHybridQdrant([], dense_ids=[]))
    ix._ensure_bm25_fresh("empty-space")
    assert "empty-space" not in ix._bm25_indexes
    assert _search(ix, "anything", space="empty-space") == []
    assert fake.query_calls  # the dense call still ran


def test_ir3_cold_empty_space_is_not_rescrolled_until_its_version_changes(ix, monkeypatch):
    fake = _install(ix, monkeypatch, FakeHybridQdrant([], dense_ids=[]))
    _set_versions({"empty-space": 1})
    _search(ix, "anything", space="empty-space")
    _search(ix, "anything", space="empty-space")
    assert _scroll_spaces(fake) == ["empty-space"]  # known empty at version 1: no re-scroll
    assert "empty-space" not in ix._bm25_indexes
    fake.points = [_point("p1", "o1", "Alpha", "body", space="empty-space")]
    _set_versions({"empty-space": 2})
    assert _oids(_search(ix, "Alpha", space="empty-space")) == ["o1"]
    assert _scroll_spaces(fake) == ["empty-space", "empty-space"]
    assert "empty-space" in ix._bm25_indexes
    assert "empty-space" not in ix._bm25_empty_versions


def test_ir2_build_reads_every_scroll_page_and_passes_the_offset_back(ix, monkeypatch):
    pts = [_point(f"p{i}", f"o{i}", f"Name{i}", f"text {i}") for i in range(7)]
    fake = _install(ix, monkeypatch, FakeHybridQdrant(pts, page_size=3))
    ix._ensure_bm25_fresh(SPACE)
    assert ix._bm25_indexes[SPACE].point_ids == [f"p{i}" for i in range(7)]
    assert [c["offset"] for c in fake.scroll_calls] == [None, "page-3", "page-6"]
    assert _oids(_search(ix, "Name6"))[0] == "o6"  # a third-page object is searchable


def test_ac_h9_rebuilds_a_space_only_when_its_version_differs(ix, monkeypatch):
    pts = [_point("p1", "o1", "Alpha", "body text")] + _fillers(3)
    fake = _install(ix, monkeypatch, FakeHybridQdrant(pts))
    _set_versions({SPACE: 5, "other": 1})
    ix._ensure_bm25_fresh(SPACE)
    ix._ensure_bm25_fresh(SPACE)
    assert len(fake.scroll_calls) == 1
    _set_versions({SPACE: 5, "other": 9})  # another space's bump
    ix._ensure_bm25_fresh(SPACE)
    assert len(fake.scroll_calls) == 1
    _set_versions({SPACE: 6, "other": 9})
    ix._ensure_bm25_fresh(SPACE)
    assert len(fake.scroll_calls) == 2


def test_ac_h9_bump_during_build_triggers_rebuild_on_next_query(ix, monkeypatch):
    pts = [_point("p1", "o1", "Alpha", "body text")] + _fillers(3)
    fired = []

    def bump_once():
        if not fired:
            fired.append(True)
            _set_versions({SPACE: 2})

    fake = _install(ix, monkeypatch, FakeHybridQdrant(pts, on_scroll=bump_once))
    _set_versions({SPACE: 1})
    ix._ensure_bm25_fresh(SPACE)
    assert ix._bm25_built_versions[SPACE] == 1  # version read before the scroll
    ix._ensure_bm25_fresh(SPACE)
    assert len(fake.scroll_calls) == 2
    assert ix._bm25_built_versions[SPACE] == 2
    ix._ensure_bm25_fresh(SPACE)
    assert len(fake.scroll_calls) == 2


def test_ac_h9_concurrent_first_queries_build_once(ix, monkeypatch):
    pts = [_point("p1", "o1", "Alpha", "body text")] + _fillers(3)
    fake = _install(ix, monkeypatch, FakeHybridQdrant(
        pts, on_scroll=lambda: time.sleep(0.3)))
    _set_versions({SPACE: 1})
    assert hasattr(ix, "_bm25_build_lock")
    errors = []

    def run():
        try:
            ix._ensure_bm25_fresh(SPACE)
        except Exception as exc:  # noqa: BLE001 - surfaced by the assert below
            errors.append(exc)

    threads = [threading.Thread(target=run) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert len(fake.scroll_calls) == 1


# ---------------------------------------------------------------------------
# AC-H10: per-space stamps
# ---------------------------------------------------------------------------


def _reindex_env(monkeypatch, tmp_path, *, state, objects, stored=4):
    """Wire reindex() over spaces. ``objects`` is {space: {oid: object dict}}."""
    from anytype_llm_wiki import indexer

    state = dict(state)
    state["_payload_schema_version"] = stored
    state_file = tmp_path / "state.json"
    state_file.write_text(json.dumps(state))
    monkeypatch.setattr(config, "INDEX_STATE_FILE", state_file)
    monkeypatch.setattr(config, "INDEX_STATE_DIR", tmp_path)
    monkeypatch.setattr(config, "PAYLOAD_SCHEMA_VERSION", 4)
    fake = FakeQdrantClientWithSearch()
    monkeypatch.setattr(indexer, "_qdrant", lambda: fake)
    monkeypatch.setattr(indexer, "list_spaces", lambda: [{"id": s} for s in objects])

    def _summary(obj):
        return {"id": obj["id"], "type": obj["type"],
                "properties": [{"key": "last_modified_date", "date": _LAST_MOD}]}

    monkeypatch.setattr(indexer, "list_objects",
                        lambda sid: [_summary(o) for o in objects[sid].values()])
    monkeypatch.setattr(indexer, "get_object", lambda sid, oid: objects[sid][oid])
    monkeypatch.setattr(indexer, "embed",
                        lambda texts: [[0.1] * config.EMBED_DIMS for _ in texts])
    return indexer, fake, state_file


def _in_space(obj, space):
    return {**obj, "space_id": space}


def test_ac_h10_reindex_bumps_only_the_space_it_indexed(monkeypatch, tmp_path):
    objects = {
        "sp-1": {"ent-1": _in_space(_entity_obj("ent-1"), "sp-1")},
        "sp-2": {"ent-2": _in_space(_entity_obj("ent-2"), "sp-2")},
    }
    state = {"sp-1": {"ent-1": "2025-01-01T00:00:00Z"}, "sp-2": {"ent-2": _LAST_MOD}}
    indexer, _, state_file = _reindex_env(monkeypatch, tmp_path, state=state, objects=objects)
    indexer.reindex()
    versions = json.loads(state_file.read_text())["_bm25_corpus_versions"]
    assert versions.get("sp-1") == 1
    assert versions.get("sp-2", 0) == 0


def test_ac_h10_noop_reindex_bumps_nothing(monkeypatch, tmp_path):
    objects = {"sp-1": {"ent-1": _in_space(_entity_obj("ent-1"), "sp-1")}}
    state = {"sp-1": {"ent-1": _LAST_MOD}, "_bm25_corpus_versions": {"sp-1": 3}}
    indexer, _, state_file = _reindex_env(monkeypatch, tmp_path, state=state, objects=objects)
    indexer.reindex()
    saved = json.loads(state_file.read_text())
    assert saved["_bm25_corpus_versions"] == {"sp-1": 3}
    assert "bm25_corpus_version" not in saved  # the v1 global stamp is gone


def test_ac_h10_reindex_bumps_the_space_it_removed_from(monkeypatch, tmp_path):
    objects = {
        "sp-1": {"ent-1": _in_space(_entity_obj("ent-1"), "sp-1")},
        "sp-2": {"ent-2": _in_space(_entity_obj("ent-2"), "sp-2")},
    }
    state = {
        "sp-1": {"ent-1": _LAST_MOD},
        "sp-2": {"ent-2": _LAST_MOD, "gone": _LAST_MOD},
    }
    indexer, _, state_file = _reindex_env(monkeypatch, tmp_path, state=state, objects=objects)
    indexer.reindex()
    versions = json.loads(state_file.read_text())["_bm25_corpus_versions"]
    assert versions.get("sp-2") == 1 and versions.get("sp-1", 0) == 0


def test_ac_h10_reindex_bumps_the_space_it_backfilled(monkeypatch, tmp_path):
    objects = {
        "sp-1": {"ent-1": _in_space(_entity_obj("ent-1"), "sp-1")},
        "sp-2": {"src-2": _in_space(_source_obj("src-2"), "sp-2")},
    }
    state = {"sp-1": {"ent-1": _LAST_MOD}, "sp-2": {"src-2": _LAST_MOD}}
    indexer, fake, state_file = _reindex_env(
        monkeypatch, tmp_path, state=state, objects=objects, stored=3)
    indexer.reindex()
    assert fake.set_payload_calls, "setup: the wiki_url backfill must run"
    versions = json.loads(state_file.read_text())["_bm25_corpus_versions"]
    assert versions.get("sp-2") == 1 and versions.get("sp-1", 0) == 0


def _reembed_env(monkeypatch, tmp_path):
    from anytype_llm_wiki import indexer

    monkeypatch.setattr(config, "INDEX_STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(config, "INDEX_STATE_DIR", tmp_path)
    fake = FakeQdrantClientWithSearch()
    monkeypatch.setattr(indexer, "_qdrant", lambda: fake)
    monkeypatch.setattr(indexer, "embed",
                        lambda texts: [[0.1] * config.EMBED_DIMS for _ in texts])
    return indexer, fake


_REEMBED_OBJ = {
    "id": "obj-1", "space_id": "sp-1", "name": "X", "type": {"key": "wiki_entity"},
    "markdown": "# H\nbody", "properties": [],
}


def test_ac_h10_reembed_bumps_its_space_on_the_upsert_path(monkeypatch, tmp_path):
    indexer, fake = _reembed_env(monkeypatch, tmp_path)
    indexer.reembed_object("sp-1", "obj-1", _REEMBED_OBJ)
    assert fake.upserted_points
    assert _read_versions() == {"sp-1": 1}
    indexer.reembed_object("sp-2", "obj-2", {**_REEMBED_OBJ, "id": "obj-2", "space_id": "sp-2"})
    assert _read_versions() == {"sp-1": 1, "sp-2": 1}


def test_ac_h10_reembed_bumps_its_space_on_the_delete_only_path(monkeypatch, tmp_path):
    indexer, fake = _reembed_env(monkeypatch, tmp_path)
    empty = {**_REEMBED_OBJ, "markdown": "", "properties": []}
    result = indexer.reembed_object("sp-1", "obj-1", empty)
    assert result["chunks"] == 0 and not fake.upserted_points
    assert _read_versions() == {"sp-1": 1}


def test_ac_h10_reembed_bumps_inside_the_reindex_lock(monkeypatch, tmp_path):
    indexer, _ = _reembed_env(monkeypatch, tmp_path)
    inside = []
    saved_inside = []

    @contextlib.contextmanager
    def lock():
        inside.append(True)
        try:
            yield True
        finally:
            inside.pop()

    real_save = indexer._save_state

    def tracking_save(state):
        saved_inside.append(bool(inside))
        real_save(state)

    monkeypatch.setattr(indexer, "_reindex_lock", lock)
    monkeypatch.setattr(indexer, "_save_state", tracking_save)
    indexer.reembed_object("sp-1", "obj-1", _REEMBED_OBJ)
    assert saved_inside == [True]


def test_ac_h10_reembed_skips_the_bump_when_lock_not_acquired(monkeypatch, tmp_path):
    indexer, fake = _reembed_env(monkeypatch, tmp_path)

    @contextlib.contextmanager
    def busy():
        yield False

    monkeypatch.setattr(indexer, "_reindex_lock", busy)
    indexer.reembed_object("sp-1", "obj-1", _REEMBED_OBJ)
    assert fake.upserted_points
    assert _read_versions() == {}


# ---------------------------------------------------------------------------
# AC-H11 (call path pins) and AC-DEP
# ---------------------------------------------------------------------------


def test_ac_h11_wiki_lint_still_uses_the_dense_core():
    import inspect

    from anytype_llm_wiki.wiki import lint

    source = inspect.getsource(lint)
    assert "semantic_search_core(" in source
    assert "hybrid_search_core" not in source


def test_ac_h11_server_semantic_search_forwards_arguments_to_hybrid(monkeypatch):
    from anytype_llm_wiki import indexer
    from anytype_llm_wiki.server import semantic_search

    seen = {}
    monkeypatch.setattr(indexer, "hybrid_search_core", lambda **kw: seen.update(kw) or [])
    semantic_search(query="Pastinha", space_id="sp-9", types=["wiki_entity"], limit=4)
    assert seen["query"] == "Pastinha" and seen["space_id"] == "sp-9"
    assert seen["types"] == ["wiki_entity"] and seen["limit"] == 4


def test_ac_dep_rank_bm25_declared_and_locked():
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    assert "rank-bm25" in (root / "pyproject.toml").read_text()
    assert 'name = "rank-bm25"' in (root / "uv.lock").read_text()


# ---------------------------------------------------------------------------
# name_keys: the public D13 key derivation the curation script shares
# ---------------------------------------------------------------------------


def test_name_keys_returns_the_stripped_base_and_parenthetical(ix, monkeypatch):
    monkeypatch.setattr(config, "NAME_TIER_TITLE_WORDS", None)
    assert ix.name_keys("Mestre Cobra Mansa (FICA)") == {"cobra mansa", "fica"}
    assert ix.name_keys("Mestra Janja") == {"janja"}
    assert ix.name_keys("(Salvador)") == {"salvador"}
    assert ix.name_keys("!!!") == set()
    monkeypatch.setattr(config, "NAME_TIER_TITLE_WORDS", ["doutor"])
    assert ix.name_keys("Doutor Mestre Bimba") == {"mestre bimba"}  # read at call time
