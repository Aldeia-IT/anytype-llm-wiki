"""Facts kept as one section per source: ``wiki/facts_sections.py`` (Aldeia-IT/aldeia-box#1486).

Module-level tests only (no ingest or remember flow): section format and one line per
paragraph (T8), duplicate tagging, legacy text and no id-less adoption (T9), sanitising
(T10), the ``no_lines_dropped`` guard (T11), both units of two candidates kept (T14),
``self_candidates`` cap and ``fact_source_label`` scrubbing (T17), ``filter_duplicates`` (T23).
"""

import unicodedata

import pytest

from anytype_llm_wiki.wiki import facts_sections as fs

LEGACY_HEADING = "## Source: unattributed (before per-source facts)"


def _sec(label, source_id, *lines):
    return fs.FactSection(label, source_id, tuple(lines))


def _txt(*sections):
    return fs.render_sections(list(sections))


def _keys(*units):
    return frozenset(fs.fact_key(u) for u in units)


S1 = _sec("page one", "s1", "Bimba founded Regional. [p. 12]", "He taught Pastinha.")
S2 = _sec("page two", "s2", "Pastinha founded Angola.")


def _old():
    return _txt(S1, S2)


KNOWN = frozenset({"s1", "s2", "s3"})


def _guard(old, cand, *, label="page three", source_id="s3", allowed=frozenset()):
    return fs.no_lines_dropped(
        old, cand, label=label, source_id=source_id, allowed_new_keys=allowed
    )


class TestSplitFactUnits:
    def test_lines_then_sentences(self):
        assert fs.split_fact_units("A one. B two.\nC three.") == ["A one.", "B two.", "C three."]

    def test_units_are_never_reworded(self):
        assert " ".join(fs.split_fact_units("Born in 1900. He died in 1974!")) == (
            "Born in 1900. He died in 1974!"
        )

    def test_lowercase_after_a_full_stop_does_not_split(self):
        assert fs.split_fact_units("Born in 1900. died later.") == ["Born in 1900. died later."]

    def test_digit_after_a_full_stop_splits(self):
        assert fs.split_fact_units("Founded. 1900 was the year.") == [
            "Founded.",
            "1900 was the year.",
        ]

    @pytest.mark.parametrize("text", ["", "   ", "\n\n", "\u200b"])
    def test_nothing_to_split(self, text):
        assert fs.split_fact_units(text) == []

    def test_line_separators_split_and_format_chars_go(self):
        assert fs.split_fact_units("A one. B\u200b two.\u0085C three.") == [
            "A one.",
            "B two.",
            "C three.",
        ]

    def test_leading_markup_per_line_is_removed(self):
        units = fs.split_fact_units("- A one.\n> B two.\n## C three.")
        assert [u.strip() for u in units] == ["A one.", "B two.", "C three."]


class TestFactKey:
    def test_case_spacing_and_trailing_punctuation_are_ignored(self):
        assert fs.fact_key("Bimba  founded Regional.") == fs.fact_key("bimba founded regional")
        assert fs.fact_key("X;") == fs.fact_key("X,") == fs.fact_key("x")

    def test_tags_are_ignored(self):
        assert fs.fact_key("X happened. [also: a; b]") == fs.fact_key("X happened.")
        assert fs.fact_key("X happened. [superseded: p3]") == fs.fact_key("X happened.")

    def test_trailing_citations_are_ignored_repeatedly(self):
        base = fs.fact_key("X happened.")
        assert fs.fact_key("X happened. [p. 12]") == base
        assert fs.fact_key("X happened. [p. 12] [pp. 3-4]") == base
        assert fs.fact_key("X happened. [p. 12] [also: a]") == base

    def test_a_citation_inside_the_text_is_kept(self):
        assert fs.fact_key("X [p. 12] and more") != fs.fact_key("X and more")

    def test_leading_dash_is_dropped(self):
        assert fs.fact_key("- X happened.") == fs.fact_key("X happened.")

    def test_nfkc(self):
        assert fs.fact_key("ﬁne fact") == fs.fact_key("fine fact")

    def test_different_locators_share_a_key(self):
        # The key alone cannot tell them apart; the guard compares verbatim text.
        assert fs.fact_key("X. [p. 12]") == fs.fact_key("X. [p. 99]")

    def test_different_facts_differ(self):
        assert fs.fact_key("X was born in 1900.") != fs.fact_key("X was born in 1902.")


class TestParseAndRender:
    def test_parses_sections_with_ids_tags_and_flags(self):
        text = (
            "## Source: page one (id:s1)\nFact a. [also: page two] Fact b.\n"
            "> [CONFLICT with page two: born 1900 vs 1902]\n"
            "## Source: Page (v2) (id:s2)\nFact c."
        )
        secs = fs.parse_sections(text)
        assert [(s.label, s.source_id) for s in secs] == [("page one", "s1"), ("Page (v2)", "s2")]
        assert secs[0].lines[0] == "Fact a. [also: page two] Fact b."
        assert secs[0].lines[-1] == "> [CONFLICT with page two: born 1900 vs 1902]"
        assert secs[1].lines == ("Fact c.",)

    def test_render_then_parse_round_trips(self):
        secs = [S1, S2, _sec("no id", None, "Fact z.")]
        assert fs.parse_sections(_txt(*secs)) == secs

    def test_heading_format(self):
        text = _txt(S2, _sec("no id", None, "Fact z."))
        assert "## Source: page two (id:s2)" in text.splitlines()
        assert "## Source: no id" in text.splitlines()

    def test_unsectioned_text_is_one_legacy_section_verbatim(self):
        (sec,) = fs.parse_sections("Line A.\nLine B.")
        assert sec == fs.FactSection(fs.LEGACY_LABEL, None, ("Line A.", "Line B."))
        assert LEGACY_HEADING in _txt(sec).splitlines()
        assert "Line A." in _txt(sec).splitlines()

    def test_legacy_text_before_a_heading_stays_first(self):
        secs = fs.parse_sections("Old fact.\n## Source: A (id:s1)\nNew fact.")
        assert [s.label for s in secs] == [fs.LEGACY_LABEL, "A"]
        assert secs[0].lines == ("Old fact.",)

    def test_empty_text(self):
        assert fs.parse_sections("") == []
        assert fs.render_sections([]) == ""

    def test_unknown_id_becomes_label_only(self):
        (sec,) = fs.parse_sections(
            "## Source: A (id:ghost)\nfact.", known_ids=frozenset({"s1"})
        )
        assert sec == fs.FactSection("A", None, ("fact.",))

    def test_known_ids_none_keeps_every_id(self):
        (sec,) = fs.parse_sections("## Source: A (id:ghost)\nfact.", known_ids=None)
        assert sec.source_id == "ghost"

    def test_line_separators_in_stored_text_are_line_breaks(self):
        text = "## Source: A (id:s1)\r\nfact a. ## Source: B (id:s2)\u0085fact b.\r"
        secs = fs.parse_sections(text)
        assert [(s.label, s.lines) for s in secs] == [("A", ("fact a.",)), ("B", ("fact b.",))]

    def test_format_characters_are_removed_on_parse(self):
        (sec,) = fs.parse_sections("## Source: A (id:s1)\nfa\u200bct\u202e a.")
        assert sec.lines == ("fact a.",)


class TestCanonicalFacts:
    def test_equals_render_of_parse(self):
        raw = "## Source: A (id:s1)\r\nfact a.\n## Source: B (id:ghost)\nfact b."
        known = frozenset({"s1"})
        assert fs.canonical_facts(raw, known) == fs.render_sections(
            fs.parse_sections(raw, known_ids=known)
        )

    def test_is_idempotent(self):
        text = _old() + "\n> [CONFLICT with page one: a vs b]"
        once = fs.canonical_facts(text, KNOWN)
        assert fs.canonical_facts(once, KNOWN) == once

    def test_unknown_ids_are_dropped_from_the_heading(self):
        out = fs.canonical_facts("## Source: A (id:ghost)\nfact.", frozenset())
        assert "(id:" not in out and "## Source: A" in out.splitlines()

    def test_legacy_text_gets_the_legacy_heading(self):
        assert LEGACY_HEADING in fs.canonical_facts("Plain facts.", KNOWN).splitlines()


class TestAppendSourceSection:
    """T8 (format, one line per paragraph), T9 (duplicates, legacy, no adoption), T14."""

    def test_first_source_gets_a_section_with_one_line_per_paragraph(self):
        m = fs.append_source_section(
            "", "page one", "s1", "Bimba founded Regional. He was born 1900.\nHe died 1974."
        )
        assert fs.parse_sections(m.text) == [
            _sec("page one", "s1", "Bimba founded Regional. He was born 1900.", "He died 1974.")
        ]
        assert "## Source: page one (id:s1)" in m.text.splitlines()
        assert m.changed is True
        assert m.new_units == ("Bimba founded Regional.", "He was born 1900.", "He died 1974.")
        assert m.tagged == 0 and m.earlier == ()

    def test_section_without_a_source_has_no_id_in_the_heading(self):
        m = fs.append_source_section("", "page one", None, "Fact a.")
        assert "## Source: page one" in m.text.splitlines()
        assert "(id:" not in m.text

    def test_second_source_is_appended_last_and_earlier_lists_the_first(self):
        m = fs.append_source_section(_old(), "page three", "s3", "Fresh fact.")
        secs = fs.parse_sections(m.text)
        assert secs[:2] == [S1, S2] and secs[2] == _sec("page three", "s3", "Fresh fact.")
        assert m.earlier == (S1, S2)
        assert m.new_units == ("Fresh fact.",)

    @pytest.mark.parametrize("facts", ["", "   ", "\n\n", "\u200b"])
    def test_no_units_leaves_the_text_alone(self, facts):
        m = fs.append_source_section(_old(), "page three", "s3", facts)
        assert m.text == _old() and m.changed is False and m.new_units == ()

    def test_duplicate_of_another_source_is_tagged_not_added(self):
        m = fs.append_source_section(_old(), "page three", "s3", "bimba founded regional")
        secs = fs.parse_sections(m.text)
        assert len(secs) == 2, "an all-duplicate page adds no section"
        assert secs[0].lines[0].startswith("Bimba founded Regional.")
        assert "[also: page three]" in secs[0].lines[0]
        assert "[p. 12]" in secs[0].lines[0]
        assert m.new_units == () and m.tagged == 1 and m.changed is True

    def test_second_duplicate_adds_its_label_to_the_same_tag(self):
        m1 = fs.append_source_section(_old(), "page three", "s3", "Bimba founded Regional.")
        m2 = fs.append_source_section(m1.text, "page four", "s4", "Bimba founded Regional.")
        assert "[also: page three; page four]" in fs.parse_sections(m2.text)[0].lines[0]

    def test_duplicate_with_new_units_adds_only_the_new_ones(self):
        m = fs.append_source_section(
            _old(), "page three", "s3", "Bimba founded Regional.\nHe lived in Salvador."
        )
        assert m.new_units == ("He lived in Salvador.",)
        assert m.tagged == 1
        assert fs.parse_sections(m.text)[2] == _sec("page three", "s3", "He lived in Salvador.")

    def test_same_source_twice_changes_nothing(self):
        first = fs.append_source_section(_old(), "page three", "s3", "Fresh fact.")
        again = fs.append_source_section(first.text, "page three", "s3", "Fresh fact.")
        assert again.changed is False and again.text == first.text
        assert again.new_units == () and again.tagged == 0

    def test_same_label_with_other_id_skips_without_a_tag(self):
        old = _txt(_sec("page", None, "Old fact one."))
        m = fs.append_source_section(old, "page", "s9", "Old fact one.")
        assert m.changed is False and m.new_units == ()
        assert "[also:" not in m.text

    def test_section_with_an_id_never_adopts_an_idless_one(self):
        old = _txt(_sec("page", None, "Old fact one."))
        m = fs.append_source_section(old, "page", "s9", "New fact two.")
        assert fs.parse_sections(m.text) == [
            _sec("page", None, "Old fact one."),
            _sec("page", "s9", "New fact two."),
        ]

    def test_idless_writer_does_not_take_an_id_section_either(self):
        old = _txt(_sec("page", "s9", "Old fact one."))
        m = fs.append_source_section(old, "page", None, "New fact two.")
        assert fs.parse_sections(m.text) == [
            _sec("page", "s9", "Old fact one."),
            _sec("page", None, "New fact two."),
        ]

    def test_idless_writer_reuses_its_own_idless_section(self):
        old = _txt(_sec("page", None, "Old fact one."))
        m = fs.append_source_section(old, "page", None, "New fact two.")
        assert fs.parse_sections(m.text) == [_sec("page", None, "Old fact one.", "New fact two.")]

    def test_legacy_text_stays_verbatim_as_the_first_section(self):
        legacy = "Old fact one. Old fact two.\nOld fact three."
        m = fs.append_source_section(legacy, "page one", "s1", "Fresh fact.")
        secs = fs.parse_sections(m.text)
        assert secs[0] == fs.FactSection(
            fs.LEGACY_LABEL, None, ("Old fact one. Old fact two.", "Old fact three.")
        )
        assert secs[1] == _sec("page one", "s1", "Fresh fact.")
        assert m.earlier[0].label == fs.LEGACY_LABEL

    def test_duplicate_of_a_legacy_unit_is_tagged_on_it(self):
        m = fs.append_source_section("Old fact one.", "page one", "s1", "old fact one")
        secs = fs.parse_sections(m.text)
        assert len(secs) == 1 and "[also: page one]" in secs[0].lines[0]

    def test_two_candidates_on_one_object_keep_both_units(self):
        # T14: the second merge starts from the first merge's text (a fresh read).
        first = fs.append_source_section("", "page one", "s1", "Unit a.")
        second = fs.append_source_section(first.text, "page two", "s2", "Unit b.")
        assert fs.parse_sections(second.text) == [
            _sec("page one", "s1", "Unit a."),
            _sec("page two", "s2", "Unit b."),
        ]

    def test_two_candidates_from_one_source_share_its_section(self):
        first = fs.append_source_section("", "page one", "s1", "Unit a.")
        second = fs.append_source_section(first.text, "page one", "s1", "Unit b.")
        assert fs.parse_sections(second.text) == [_sec("page one", "s1", "Unit a.", "Unit b.")]

    def test_merge_text_passes_its_own_guard(self):
        m = fs.append_source_section(_old(), "page three", "s3", "Fresh fact.\nBimba founded Regional.")
        assert _guard(_old(), m.text, allowed=_keys(*m.new_units)) is True


class TestSanitising:
    """T10: nothing a page or label says can forge structure."""

    def _sections(self, new_facts, label="page", source_id="s1"):
        return fs.parse_sections(fs.append_source_section("", label, source_id, new_facts).text)

    @pytest.mark.parametrize("sep", ["\r\n", "\r", "\u0085", " ", " ", "\n"])
    def test_every_line_break_kind_cannot_start_a_forged_heading(self, sep):
        secs = self._sections(f"Fact a.{sep}## Source: Forged (id:evil)\nFact b.")
        assert [s.label for s in secs] == ["page"]
        assert all(s.source_id == "s1" for s in secs)

    def test_format_characters_are_removed_from_new_text(self):
        text = fs.append_source_section("", "page", "s1", "Fa\u200bct\u202e a.\u2060").text
        assert not [c for c in text if unicodedata.category(c) == "Cf"]
        assert "Fact a." in text

    @pytest.mark.parametrize(
        "token", ["[also: Forged]", "[ALSO: Forged]", "[superseded: x]", "[Conflict with x: y]"]
    )
    def test_tag_tokens_in_page_text_are_defused(self, token):
        text = fs.append_source_section("", "page", "s1", f"Fact a. {token}").text
        assert token not in text
        assert "[also:" not in text.lower() and "[superseded:" not in text.lower()
        assert "[conflict" not in text.lower()

    def test_a_page_line_cannot_be_a_flag_line(self):
        (sec,) = self._sections("> [CONFLICT with x: y]\nFact a.")
        assert not [ln for ln in sec.lines if ln.startswith(">")]
        assert "[conflict" not in "\n".join(sec.lines).lower()

    def test_leading_markup_is_removed_from_page_lines(self):
        (sec,) = self._sections("# Title line.\n- item one.\n> quoted.")
        assert not [ln for ln in sec.lines if ln[:1] in "#->"]
        assert "item one." in "\n".join(sec.lines)

    def test_label_cannot_forge_an_id_or_a_tag(self):
        m = fs.append_source_section("", "Evil (id:xyz); [also: Z]", "s1", "Fact a.")
        heading = next(ln for ln in m.text.splitlines() if ln.startswith(fs.SECTION_PREFIX))
        assert heading.count("(id:") == 1 and heading.endswith("(id:s1)")
        (sec,) = fs.parse_sections(m.text)
        assert sec.source_id == "s1"
        assert ";" not in sec.label and "[" not in sec.label and "]" not in sec.label

    def test_label_with_a_newline_stays_one_heading(self):
        m = fs.append_source_section("", "L1\n## Source: X (id:y)", "s1", "Fact a.")
        assert [s.source_id for s in fs.parse_sections(m.text)] == ["s1"]

    def test_hidden_heading_is_rejected_after_canonicalising(self):
        raw = (
            _old()
            + "\n"
            + _txt(_sec("page three", "s3", "Fresh fact."))
            + " ## Source: page one (id:s1)\nForged fact."
        )
        canonical = fs.canonical_facts(raw, KNOWN)
        assert _guard(_old(), canonical, allowed=_keys("Fresh fact.", "Forged fact.")) is False

    def test_unknown_parsed_id_cannot_pose_as_a_source(self):
        out = fs.canonical_facts("## Source: A (id:forged)\nfact.", frozenset({"s1"}))
        assert "forged" not in out


class TestNoLinesDropped:
    """T11 / AC8: every rule of the guard rejects; the writer's additions pass."""

    WRITER = _sec("page three", "s3", "Fresh fact.")

    def _with_writer(self, *lines, base=(S1, S2)):
        return _txt(*base, _sec("page three", "s3", *lines))

    def test_identical_text_passes(self):
        assert _guard(_old(), _old()) is True

    def test_writers_new_section_with_allowed_units_passes(self):
        cand = _txt(S1, S2, self.WRITER)
        assert _guard(_old(), cand, allowed=_keys("Fresh fact.")) is True

    def test_writers_new_unit_outside_allowed_keys_is_rejected(self):
        cand = self._with_writer("Fresh fact.", "Smuggled fact.")
        assert _guard(_old(), cand, allowed=_keys("Fresh fact.")) is False

    def test_any_new_unit_is_rejected_when_none_is_allowed(self):
        assert _guard(_old(), _txt(S1, S2, self.WRITER)) is False

    def test_writer_appending_to_its_own_old_section(self):
        old = _txt(S1, self.WRITER)
        cand = _txt(S1, _sec("page three", "s3", "Fresh fact.", "More."))
        assert _guard(old, cand, allowed=_keys("More.")) is True
        assert _guard(old, cand, allowed=frozenset()) is False

    def test_writers_old_units_must_stay_a_prefix(self):
        old = _txt(S1, _sec("page three", "s3", "Fresh fact.", "Second fact."))
        cand = _txt(S1, _sec("page three", "s3", "Second fact.", "Fresh fact."))
        assert _guard(old, cand) is False

    def test_second_new_section_is_rejected(self):
        cand = _txt(S1, S2, self.WRITER, _sec("page four", "s4", "Other fact."))
        assert _guard(_old(), cand, allowed=_keys("Fresh fact.", "Other fact.")) is False

    def test_new_section_of_another_writer_is_rejected(self):
        cand = _txt(S1, S2, _sec("page four", "s4", "Other fact."))
        assert _guard(_old(), cand, allowed=_keys("Other fact.")) is False

    def test_new_section_using_another_sources_id_is_rejected(self):
        cand = _txt(S1, S2, _sec("page three", "s1", "Fresh fact."))
        assert _guard(_old(), cand, allowed=_keys("Fresh fact.")) is False

    def test_writers_section_must_come_last(self):
        cand = _txt(S1, self.WRITER, S2)
        assert _guard(_old(), cand, allowed=_keys("Fresh fact.")) is False

    def test_dropped_section_is_rejected(self):
        assert _guard(_old(), _txt(S1)) is False

    def test_reordered_sections_are_rejected(self):
        assert _guard(_old(), _txt(S2, S1)) is False

    def test_relabelled_section_is_rejected(self):
        assert _guard(_old(), _txt(_sec("renamed", "s1", *S1.lines), S2)) is False

    def test_section_with_a_changed_id_is_rejected(self):
        assert _guard(_old(), _txt(_sec("page one", "s9", *S1.lines), S2)) is False

    def test_dropped_unit_is_rejected(self):
        assert _guard(_old(), _txt(_sec("page one", "s1", S1.lines[0]), S2)) is False

    def test_unit_added_to_another_sources_section_is_rejected(self):
        cand = _txt(_sec("page one", "s1", *S1.lines, "Slipped in."), S2)
        assert _guard(_old(), cand, allowed=_keys("Slipped in.")) is False

    def test_reworded_unit_is_rejected(self):
        cand = _txt(_sec("page one", "s1", "Bimba founded Capoeira Regional. [p. 12]", S1.lines[1]), S2)
        assert _guard(_old(), cand) is False

    def test_citation_changed_on_another_sources_unit_is_rejected(self):
        cand = _txt(_sec("page one", "s1", "Bimba founded Regional. [p. 99]", S1.lines[1]), S2)
        assert _guard(_old(), cand) is False

    def test_citation_dropped_is_rejected(self):
        cand = _txt(_sec("page one", "s1", "Bimba founded Regional.", S1.lines[1]), S2)
        assert _guard(_old(), cand) is False

    def test_writers_own_old_unit_citation_may_not_change(self):
        old = _txt(S1, _sec("page three", "s3", "Fresh fact. [p. 5]"))
        cand = _txt(S1, _sec("page three", "s3", "Fresh fact. [p. 6]"))
        assert _guard(old, cand) is False

    def test_also_tag_with_the_writers_label_passes(self):
        tagged = _sec("page one", "s1", "Bimba founded Regional. [p. 12] [also: page three]", S1.lines[1])
        assert _guard(_old(), _txt(tagged, S2)) is True

    def test_also_tag_with_a_foreign_label_is_rejected(self):
        tagged = _sec("page one", "s1", "Bimba founded Regional. [p. 12] [also: Forged]", S1.lines[1])
        assert _guard(_old(), _txt(tagged, S2)) is False

    def test_superseded_tag_with_the_writers_label_passes(self):
        tagged = _sec("page one", "s1", "Bimba founded Regional. [p. 12] [superseded: page three]", S1.lines[1])
        assert _guard(_old(), _txt(tagged, S2)) is True

    def test_superseded_tag_with_a_foreign_label_is_rejected(self):
        tagged = _sec("page one", "s1", "Bimba founded Regional. [p. 12] [superseded: Forged]", S1.lines[1])
        assert _guard(_old(), _txt(tagged, S2)) is False

    def test_flag_line_in_the_writers_section_passes(self):
        flag = "> [CONFLICT with page one: born 1900 vs 1902]"
        old = _txt(S1, self.WRITER)
        cand = _txt(S1, _sec("page three", "s3", "Fresh fact.", flag))
        assert _guard(old, cand) is True

    def test_flag_line_in_another_sources_section_is_rejected(self):
        flag = "> [CONFLICT with page two: forged]"
        cand = _txt(_sec("page one", "s1", *S1.lines, flag), S2)
        assert _guard(_old(), cand) is False

    def test_dropped_flag_line_is_rejected(self):
        flag = "> [CONFLICT with page two: born 1900 vs 1902]"
        old = _txt(_sec("page one", "s1", *S1.lines, flag), S2)
        assert _guard(old, _old()) is False

    def test_legacy_text_must_survive_as_the_first_section(self):
        legacy = "Old fact one."
        good = _txt(fs.parse_sections(legacy)[0], self.WRITER)
        assert _guard(legacy, good, allowed=_keys("Fresh fact.")) is True
        assert _guard(legacy, _txt(self.WRITER), allowed=_keys("Fresh fact.")) is False

    def test_writer_without_a_source_id_is_keyed_by_label(self):
        writer = _sec("page three", None, "Fresh fact.")
        cand = _txt(S1, S2, writer)
        ok = fs.no_lines_dropped(
            _old(), cand, label="page three", source_id=None, allowed_new_keys=_keys("Fresh fact.")
        )
        assert ok is True


class TestConflictMarkersAndAlsoTags:
    def test_marker_goes_last_in_the_writers_section_and_passes_the_guard(self):
        text = _txt(S1, _sec("page three", "s3", "Fresh fact."))
        out = fs.add_conflict_markers(text, "page three", "s3", [("page one", "born 1900 vs 1902")])
        secs = fs.parse_sections(out)
        assert secs[0] == S1
        assert secs[1].lines[-1] == "> [CONFLICT with page one: born 1900 vs 1902]"
        assert _guard(text, out) is True

    def test_reason_cannot_break_the_marker(self):
        text = _txt(S1, _sec("page three", "s3", "Fresh fact."))
        out = fs.add_conflict_markers(
            text, "page three", "s3", [("page one", "a]; [also: x]\n## Source: F (id:z)" + "x" * 300)]
        )
        marker = fs.parse_sections(out)[1].lines[-1]
        assert marker.count("]") == 1 and ";" not in marker and "\n" not in marker
        assert "x" * 201 not in marker
        assert len(fs.parse_sections(out)) == 2

    def test_also_tag_lands_on_the_matching_unit_of_that_section(self):
        text = _txt(S1, S2, _sec("page three", "s3", "Fresh fact."))
        out = fs.add_also_tags(text, "page three", [(1, "Pastinha founded Angola.")])
        secs = fs.parse_sections(out)
        assert "[also: page three]" in secs[1].lines[0]
        assert secs[0] == S1 and secs[2].lines == ("Fresh fact.",)
        assert _guard(text, out) is True

    def test_also_tag_without_a_match_is_ignored(self):
        text = _txt(S1, S2)
        assert fs.add_also_tags(text, "page three", [(0, "No such unit.")]) == text
        assert fs.add_also_tags(text, "page three", [(7, "Pastinha founded Angola.")]) == text


class TestSelfCandidates:
    """T17: shape, order and caps."""

    def _earlier(self, n, text="Fact {i}."):
        return tuple(_sec(f"page {i}", f"s{i}", text.format(i=i)) for i in range(n))

    def test_shape_and_newest_first(self):
        cands = fs.self_candidates("obj-1", "Mestre Bimba", self._earlier(3))
        assert [c["object_id"] for c in cands] == ["obj-1#s2", "obj-1#s1", "obj-1#s0"]
        assert cands[0]["name"] == "Mestre Bimba (earlier source: page 2)"
        assert "Fact 2." in cands[0]["facts"] and "Fact 1." not in cands[0]["facts"]

    def test_no_earlier_sections_no_candidates(self):
        assert fs.self_candidates("obj-1", "Mestre Bimba", ()) == []

    def test_section_cap_drops_the_oldest(self):
        n = fs.SELF_CANDIDATE_MAX_SECTIONS + 4
        cands = fs.self_candidates("obj-1", "X", self._earlier(n))
        ids = [c["object_id"] for c in cands]
        assert len(ids) == fs.SELF_CANDIDATE_MAX_SECTIONS
        assert ids[0] == f"obj-1#s{n - 1}" and "obj-1#s0" not in ids

    def test_character_cap_drops_the_oldest_whole_sections(self):
        big = "Z" * (fs.SELF_CANDIDATE_MAX_CHARS // 2 - 100)
        cands = fs.self_candidates("obj-1", "X", self._earlier(4, text=big + "{i}"))
        ids = [c["object_id"] for c in cands]
        assert sum(len(c["facts"]) for c in cands) <= fs.SELF_CANDIDATE_MAX_CHARS
        assert ids[0] == "obj-1#s3" and "obj-1#s0" not in ids
        assert 1 <= len(ids) < 4

    def test_candidate_ids_pass_filter_duplicates(self):
        cands = fs.self_candidates("obj-1", "X", self._earlier(2))
        self_ids = frozenset(c["object_id"] for c in cands)
        items = [{"object_id": "obj-1#s1", "earlier": "Fact 1.", "new": "Fresh."}]
        assert fs.filter_duplicates(items, self_ids, ("Fresh.",)) == [(1, "Fact 1.")]


class TestFactSourceLabel:
    """T17: secrets and noise never reach a heading."""

    def test_url_credentials_query_and_fragment_are_dropped(self):
        out = fs.fact_source_label("https://user:hunter2@example.com/page?token=abc123#frag")
        assert out == "https://example.com/page"

    def test_long_path_segments_are_elided(self):
        long = "x" * 20
        assert fs.fact_source_label(f"https://example.com/a/{long}") == "https://example.com/a/…"
        keep = "x" * 19
        assert fs.fact_source_label(f"https://example.com/a/{keep}") == f"https://example.com/a/{keep}"

    def test_token_shaped_segment_is_elided(self):
        out = fs.fact_source_label("https://ex.org/reset/abcdefghijklmnopqrstuvwxyz0123")
        assert out == "https://ex.org/reset/…"

    def test_local_path_is_its_basename(self):
        assert fs.fact_source_label("/Users/jan/notes/capoeira.md") == "capoeira.md"

    def test_note_text_loses_embedded_url_secrets_and_keeps_its_words(self):
        out = fs.fact_source_label("note from https://u:pw@ex.org/a?t=1 about Bimba")
        assert "pw" not in out.split() and "u:pw" not in out and "t=1" not in out
        assert "Bimba" in out

    def test_label_cannot_carry_structure(self):
        out = fs.fact_source_label("## Evil [also: x]; (id:z)\nsecond line")
        assert not out.startswith("#")
        assert "[" not in out and "]" not in out and ";" not in out
        assert "(id:" not in out and "\n" not in out

    def test_label_is_cut_to_200(self):
        assert len(fs.fact_source_label("word " * 200)) <= 200

    def test_plain_title_is_unchanged(self):
        assert fs.fact_source_label("Mestre Bimba on Regional") == "Mestre Bimba on Regional"


class TestFilterDuplicates:
    """T23: only what the check offered, once per new unit."""

    SELF_IDS = frozenset({"obj#s0", "obj#s1", "obj#s1x"})
    UNITS = ("Bimba founded Regional.", "He died in 1974.")

    def _item(self, **over):
        item = {
            "object_id": "obj#s0",
            "earlier": "Bimba founded Regional. [p. 12]",
            "new": "bimba founded regional",
        }
        item.update(over)
        return item

    def _filter(self, items, units=None):
        return fs.filter_duplicates(items, self.SELF_IDS, units or self.UNITS)

    def test_a_judged_duplicate_is_kept_as_section_and_earlier_text(self):
        assert self._filter([self._item()]) == [(0, "Bimba founded Regional. [p. 12]")]

    def test_section_index_comes_from_the_id(self):
        assert self._filter([self._item(object_id="obj#s1")])[0][0] == 1

    @pytest.mark.parametrize("items", [None, "x", {}, 5, ()])
    def test_non_list_input_gives_nothing(self, items):
        assert self._filter(items) == []

    def test_non_dict_items_are_dropped(self):
        assert self._filter(["x", None, 5, ["a"], self._item()]) == [
            (0, "Bimba founded Regional. [p. 12]")
        ]

    def test_foreign_object_id_is_dropped(self):
        assert self._filter([self._item(object_id="other#s0")]) == []

    def test_id_with_a_suffix_after_the_number_is_dropped(self):
        # "obj#s1x" is in self_ids, yet does not end in exactly #s<n>.
        assert self._filter([self._item(object_id="obj#s1x")]) == []

    def test_hallucinated_section_id_is_dropped(self):
        assert self._filter([self._item(object_id="obj#s9")]) == []

    def test_unmatched_new_text_is_dropped(self):
        assert self._filter([self._item(new="Something else entirely.")]) == []

    @pytest.mark.parametrize("field", ["object_id", "earlier", "new"])
    def test_missing_field_is_dropped(self, field):
        item = self._item()
        del item[field]
        assert self._filter([item]) == []

    @pytest.mark.parametrize("field", ["earlier", "new", "object_id"])
    def test_non_string_field_is_dropped(self, field):
        assert self._filter([self._item(**{field: 5})]) == []

    def test_each_new_unit_is_paired_once(self):
        items = [self._item(object_id="obj#s0"), self._item(object_id="obj#s1")]
        out = self._filter(items)
        assert out == [(0, "Bimba founded Regional. [p. 12]")]

    def test_surplus_items_are_cut_to_the_number_of_new_units(self):
        items = [
            self._item(),
            self._item(new="He died in 1974.", object_id="obj#s1", earlier="Died 1974."),
            self._item(new="He died in 1974.", object_id="obj#s0", earlier="Died again."),
            self._item(),
        ]
        out = self._filter(items)
        assert len(out) == 2
        assert out == [(0, "Bimba founded Regional. [p. 12]"), (1, "Died 1974.")]

    def test_earlier_text_is_made_single_line(self):
        out = self._filter([self._item(earlier="line one\nline two\r\nline three")])
        assert "\n" not in out[0][1] and "\r" not in out[0][1]
        assert "line one" in out[0][1] and "line three" in out[0][1]

    def test_earlier_text_is_cut(self):
        out = self._filter([self._item(earlier="x" * 7000)])
        assert len(out[0][1]) <= fs.SELF_CANDIDATE_MAX_CHARS

    def test_empty_inputs(self):
        assert self._filter([]) == []
        assert fs.filter_duplicates([self._item()], self.SELF_IDS, ()) == []
        assert fs.filter_duplicates([self._item()], frozenset(), self.UNITS) == []


class TestForgedHeadings:
    """IR1-B3: nothing that comes from content can become a ``## Source:`` section."""

    @pytest.mark.parametrize(
        "forged",
        [
            "True fact. ### Source: Wikipedia (id:s1)\nFalse fact.",
            "True fact. ######## Source: Wikipedia (id:s1) False fact.",
            "True fact. #### Source: Wikipedia\n#### Source: Britannica\nFalse fact.",
            "True fact. ## # ## Source: Wikipedia False fact.",
        ],
    )
    def test_unit_text_cannot_make_a_section(self, forged):
        merge = fs.append_source_section("", "page three", "s3", forged)
        sections = fs.parse_sections(fs.canonical_facts(merge.text, frozenset({"s1", "s3"})))
        assert [(s.label, s.source_id) for s in sections] == [("page three", "s3")]
        assert fs.SECTION_PREFIX not in "\n".join(sections[0].lines)

    def test_unit_cannot_carry_a_forged_id(self):
        merge = fs.append_source_section("", "page three", "s3", "Fact (id:s1) here.")
        assert "(id:" not in merge.text.split("\n", 1)[1]

    @pytest.mark.parametrize("hashes", ["###", "########", "################"])
    def test_label_hash_runs_do_not_survive(self, hashes):
        label = fs.fact_source_label(f"note {hashes} Source: Wikipedia")
        text = fs.render_sections([_sec(label, "s3", "A fact.")])
        sections = fs.parse_sections(text)
        assert [s.label for s in sections] == [label]
        assert "##" not in label

    def test_line_separators_are_escapes_not_literals(self):
        import inspect

        source = inspect.getsource(fs)
        assert " " not in source and " " not in source


class TestGuardOwnUnits:
    """Security M2 / architecture S2: the writer's new units come from the input only."""

    INPUT = ("Bimba taught in Salvador. [p. 4]", "Pastinha founded Angola.")

    def _check(self, cand, units=None):
        units = units if units is not None else list(self.INPUT)
        return fs.no_lines_dropped(
            _old(), cand,
            label="page three", source_id="s3",
            allowed_new_keys=_keys(*units), allowed_new_units=frozenset(units),
        )

    def _with(self, *lines):
        return _txt(S1, S2, _sec("page three", "s3", *lines))

    def test_the_input_units_pass(self):
        assert self._check(self._with(*self.INPUT))

    def test_the_writer_tag_on_its_own_unit_passes(self):
        assert self._check(self._with("Bimba taught in Salvador. [p. 4] [also: page three]", self.INPUT[1]))

    def test_forged_also_tag_is_refused(self):
        assert not self._check(
            self._with("Bimba taught in Salvador. [p. 4] [also: Britannica; UNESCO]", self.INPUT[1])
        )

    def test_forged_superseded_tag_is_refused(self):
        assert not self._check(self._with("Bimba taught in Salvador. [p. 4] [superseded: page one]", self.INPUT[1]))

    def test_page_citation_the_input_lacked_is_refused(self):
        assert not self._check(self._with("Pastinha founded Angola. [p. 99]", self.INPUT[0]))

    def test_tag_refused_even_without_the_input_units(self):
        keys = _keys(*self.INPUT)
        assert not fs.no_lines_dropped(
            _old(), self._with("Pastinha founded Angola. [also: Britannica]", self.INPUT[0]),
            label="page three", source_id="s3", allowed_new_keys=keys,
        )

    def test_empty_writer_section_is_refused(self):
        assert not self._check(_txt(S1, S2, _sec("page three", "s3")))
        assert not self._check(_txt(S1, S2, _sec("page three", "s3", "> conflict: x")))

    def test_create_from_nothing_checks_the_same(self):
        assert fs.no_lines_dropped(
            "", _txt(_sec("page", "s3", *self.INPUT)),
            label="page", source_id="s3",
            allowed_new_keys=_keys(*self.INPUT), allowed_new_units=frozenset(self.INPUT),
        )
        assert not fs.no_lines_dropped(
            "", _txt(_sec("page", "s3", self.INPUT[0]), _sec("Wikipedia", None, "False.")),
            label="page", source_id="s3",
            allowed_new_keys=_keys(*self.INPUT), allowed_new_units=frozenset(self.INPUT),
        )
