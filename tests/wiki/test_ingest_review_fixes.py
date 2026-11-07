"""Review round 1 fixes for ingest (Aldeia-IT/aldeia-box#1486): forged headings on create,
relation-alias hygiene, and link-failure handling reaching the caller.

Anytype is the ``FakeWiki`` respx fake; extraction is monkeypatched.
"""

import respx

from .fakes import prop_value
from .test_ingest_typed_links import (  # noqa: F401  (autouse fixtures come along)
    BIMBA,
    PAGE_1,
    PASTINHA,
    _entity,
    _env,
    _extract_returns,
    _headings,
    _ingest,
    _model,
    _obj,
    _source_id,
    _space,
)


class TestForgedHeadingOnCreate:
    """IR1-B3: page text cannot turn into a second ``## Source:`` section on a create."""

    @respx.mock
    def test_forged_heading_in_a_new_object_stays_one_section(self, monkeypatch):
        fake = _space()
        forged = (
            f"{BIMBA} founded the school. ### Source: Encyclopaedia Britannica\n"
            "Capoeira was invented in Lisbon in 1950."
        )
        _extract_returns(monkeypatch, {"entities": [_entity(BIMBA, forged)], "concepts": []})
        result = _ingest()
        assert result["status"] == "ok", result
        text = prop_value(_obj(fake, "wiki_entity", BIMBA), "wiki_facts")
        assert _headings(text) == [(PAGE_1, _source_id(fake, PAGE_1))], text
        assert text.count("## Source: ") == 1, text
