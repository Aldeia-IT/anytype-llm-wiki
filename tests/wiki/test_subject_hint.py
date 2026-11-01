"""Unit tests for Aldeia-IT/aldeia-box#1430: subject_hint on wiki_ingest and the
opt-in title strip (D1, N1 = A).

Flows through ``_run_ingest`` / ``_apply_batch`` live in test_subject_hint_flows.py.
"""

import inspect
import re
from pathlib import Path

import pytest

from anytype_llm_wiki import config as root_config
from anytype_llm_wiki import indexer
from anytype_llm_wiki.wiki import config, extraction, ingest, names, remember, util

FIXTURES = Path(__file__).parent / "fixtures"
SRC = Path(__file__).resolve().parents[2] / "src" / "anytype_llm_wiki"


# ---------------------------------------------------------------------------
# config.strip_name_titles_spaces
# ---------------------------------------------------------------------------


class TestStripNameTitlesSpaces:
    def test_default_is_empty(self, monkeypatch):
        monkeypatch.delenv("WIKI_STRIP_NAME_TITLES_SPACES", raising=False)
        assert config.strip_name_titles_spaces() == frozenset()

    def test_lists_are_stripped_and_empty_entries_dropped(self, monkeypatch):
        monkeypatch.setenv("WIKI_STRIP_NAME_TITLES_SPACES", " sp-a, ,sp-b ,")
        assert config.strip_name_titles_spaces() == frozenset({"sp-a", "sp-b"})

    def test_read_at_call_time(self, monkeypatch):
        monkeypatch.setenv("WIKI_STRIP_NAME_TITLES_SPACES", "sp-a")
        assert config.strip_name_titles_spaces() == frozenset({"sp-a"})
        monkeypatch.setenv("WIKI_STRIP_NAME_TITLES_SPACES", "sp-b")
        assert config.strip_name_titles_spaces() == frozenset({"sp-b"})

    @pytest.mark.parametrize(
        "var",
        [
            "WIKI_STRIP_NAME_TITLES_SPACES",
            "WIKI_REFUSE_IDENTIFIER_NAMES_SPACES",
            "WIKI_SPACES_CONFIG",
        ],
    )
    def test_is_the_only_reader_of_the_env_var(self, var):
        """Env list and file resolve in one module (space_settings), config delegates."""
        readers = [
            p.relative_to(SRC).as_posix()
            for p in SRC.rglob("*.py")
            if re.search(rf"""["']{var}["']""", p.read_text(encoding="utf-8"))
        ]
        assert readers == ["wiki/space_settings.py"]


# ---------------------------------------------------------------------------
# indexer.strip_display_title
# ---------------------------------------------------------------------------


class TestStripDisplayTitle:
    @pytest.mark.parametrize(
        "name, expected",
        [
            ("Mestre Bimba", "Bimba"),
            ("mestre bimba", "bimba"),
            ("Mestra Janja", "Janja"),
            ("Contra-Mestre Fulano", "Fulano"),
            ("Contramestre Fulano", "Fulano"),
            ("Contra Mestre Fulano", "Fulano"),
            ("Professor Pastinha de Salvador", "Pastinha de Salvador"),
            ("Mestre  Bimba", "Bimba"),
            ("Mestre Joao Pequeno (Salvador)", "Joao Pequeno (Salvador)"),
            ("Mestre João Grande", "João Grande"),
            ("MESTRE Moraes", "Moraes"),
        ],
    )
    def test_one_leading_title_word_is_removed(self, name, expected):
        assert indexer.strip_display_title(name) == expected

    @pytest.mark.parametrize(
        "name",
        [
            "Bimba",
            "Mestre",
            "Mestre ",
            "Contra-Mestre",
            "Mestre (Salvador)",
            "Mestres de Capoeira",
            "Associação de Capoeira Mestre Bimba",
            "",
        ],
    )
    def test_names_without_a_leading_title_or_only_a_title_stay(self, name):
        assert indexer.strip_display_title(name) == name

    def test_only_one_title_word_is_removed(self):
        assert indexer.strip_display_title("Mestre Professor Fulano") == "Professor Fulano"

    def test_the_rest_of_the_name_keeps_its_case_and_accents(self):
        assert indexer.strip_display_title("Mestre Zé do Lenço") == "Zé do Lenço"

    def test_title_list_override(self, monkeypatch):
        monkeypatch.setattr(root_config, "NAME_TIER_TITLE_WORDS", ("dom", "dona"))
        assert indexer.strip_display_title("Dom Casmurro") == "Casmurro"
        assert indexer.strip_display_title("Mestre Bimba") == "Mestre Bimba"

    def test_empty_title_list_strips_nothing(self, monkeypatch):
        monkeypatch.setattr(root_config, "NAME_TIER_TITLE_WORDS", ())
        assert indexer.strip_display_title("Mestre Bimba") == "Mestre Bimba"

    def test_agrees_with_the_search_key(self):
        """The stripped display name has the same name-tier key as the original."""
        for name in ("Mestre Bimba", "Contra-Mestre Fulano", "Mestra Janja (Rio)"):
            assert indexer.strip_name(indexer.strip_display_title(name)) == indexer.strip_name(name)


# ---------------------------------------------------------------------------
# util.same_subject (moved from remember, shared with ingest)
# ---------------------------------------------------------------------------


class TestSameSubject:
    def test_normalized_title_and_slug_forms(self):
        assert util.same_subject("MESTRE bimba", "Mestre Bimba")
        assert util.same_subject("associacao_de_capoeira", "Associação de Capoeira")
        assert not util.same_subject("Mestre Pastinha", "Mestre Bimba")
        assert not util.same_subject(None, "Mestre Bimba")

    def test_title_strip_only_when_asked(self):
        assert not util.same_subject("Mestre Bimba", "Bimba")
        assert util.same_subject("Mestre Bimba", "Bimba", strip_titles=True)
        assert util.same_subject("Bimba", "Mestre Bimba", strip_titles=True)
        assert not util.same_subject("Mestre Pastinha", "Bimba", strip_titles=True)

    def test_remember_reuses_the_shared_helper(self):
        assert remember.same_subject is util.same_subject
        assert not hasattr(remember, "_same_subject")
        assert not hasattr(remember, "_slug_form")


# ---------------------------------------------------------------------------
# util.plan_primary_subject
# ---------------------------------------------------------------------------


def _cand(name, facts="f", kind="entity"):
    return {"name": name, "facts": facts, "kind": kind}


class TestPlanPrimarySubject:
    def test_ingest_exposes_the_same_function(self):
        assert ingest.plan_primary_subject is util.plan_primary_subject

    def test_fold_renames_the_first_spelling_and_drops_the_others(self):
        cands = [_cand("Capoeira Regional", kind="concept"),
                 _cand("Manoel dos Reis Machado"), _cand("mestre bimba"),
                 _cand("Mestre Bimba"), _cand("Salvador")]
        out, warnings = util.plan_primary_subject(cands, "Mestre Bimba", None)
        assert [c["name"] for c in out] == [
            "Capoeira Regional", "Manoel dos Reis Machado", "Mestre Bimba", "Salvador"
        ]
        assert out[2]["primary"] is True
        assert [c.get("primary") for c in out].count(True) == 1
        assert warnings == []

    def test_titled_candidate_matches_the_bare_hint_in_every_space(self):
        cands = [_cand("Salvador"), _cand("Mestre Bimba", facts="about"), _cand("mestre bimba")]
        out, warnings = util.plan_primary_subject(cands, "Bimba", None)
        assert [c["name"] for c in out] == ["Salvador", "Bimba"]
        assert out[1]["primary"] is True and out[1]["facts"] == "about"
        assert warnings == []

    def test_title_stripped_name_that_differs_from_the_hint_does_not_match(self):
        out, warnings = util.plan_primary_subject([_cand("Mestre Pastinha")], "Bimba", None)
        assert [c["name"] for c in out] == ["Mestre Pastinha"]
        assert len(warnings) == 1 and warnings[0].startswith("subject_hint_unmatched")

    def test_parenthesised_names_stay_distinct(self):
        cands = [_cand("Bimba (Rio)"), _cand("Mestre Bimba (Salvador)")]
        out, warnings = util.plan_primary_subject(cands, "Bimba (Salvador)", None)
        assert [c["name"] for c in out] == ["Bimba (Rio)", "Bimba (Salvador)"]
        assert out[1].get("primary") is True and "primary" not in out[0]
        out, warnings = util.plan_primary_subject(cands, "Bimba", None)
        assert [c["name"] for c in out] == ["Bimba (Rio)", "Mestre Bimba (Salvador)"]
        assert len(warnings) == 1

    def test_title_override_applies_to_the_hint_match(self, monkeypatch):
        monkeypatch.setattr(root_config, "NAME_TIER_TITLE_WORDS", ("dom",))
        out, _ = util.plan_primary_subject([_cand("Mestre Bimba")], "Bimba", None)
        assert out[0]["name"] == "Mestre Bimba"

    def test_fold_keeps_the_facts_of_the_first_match(self):
        cands = [_cand("mestre bimba", facts="first"), _cand("Mestre Bimba", facts="second")]
        out, _ = util.plan_primary_subject(cands, "Mestre Bimba", None)
        assert len(out) == 1 and out[0]["facts"] == "first"

    def test_marked_candidate_is_renamed_to_the_hint(self):
        cands = [_cand("Manoel dos Reis Machado"), _cand("Salvador")]
        out, warnings = util.plan_primary_subject(
            cands, "Mestre Bimba", "manoel dos reis machado"
        )
        assert [c["name"] for c in out] == ["Mestre Bimba", "Salvador"]
        assert out[0]["primary"] is True and out[0]["facts"] == "f"
        assert warnings == []

    def test_fold_wins_over_the_marker(self):
        cands = [_cand("Salvador"), _cand("Mestre Bimba")]
        out, _ = util.plan_primary_subject(cands, "Mestre Bimba", "Salvador")
        assert [c["name"] for c in out] == ["Salvador", "Mestre Bimba"]
        assert out[1]["primary"] is True and "primary" not in out[0]

    @pytest.mark.parametrize("marked", [None, "", "Someone Else", 7])
    def test_unmatched_warns_and_renames_nothing(self, marked):
        cands = [_cand("Manoel dos Reis Machado"), _cand("Salvador")]
        out, warnings = util.plan_primary_subject(cands, "Mestre Bimba", marked)
        assert [c["name"] for c in out] == ["Manoel dos Reis Machado", "Salvador"]
        assert not any(c.get("primary") for c in out)
        assert warnings == [
            'subject_hint_unmatched: no extracted entity is the primary subject "Mestre Bimba"'
        ]

    def test_input_candidates_are_not_mutated(self):
        cands = [_cand("Manoel dos Reis Machado")]
        util.plan_primary_subject(cands, "Mestre Bimba", "Manoel dos Reis Machado")
        assert cands == [_cand("Manoel dos Reis Machado")]

    def test_strip_titles_folds_bare_and_titled_forms(self, monkeypatch):
        cands = [_cand("Mestre Bimba"), _cand("Bimba"), _cand("Mestre Pastinha")]
        out, warnings = util.plan_primary_subject(
            cands, "Mestre Bimba", None, strip_titles=True
        )
        assert [c["name"] for c in out] == ["Bimba", "Pastinha"]
        assert out[0]["primary"] is True and warnings == []

    def test_strip_titles_hint_is_stripped_too(self):
        out, _ = util.plan_primary_subject(
            [_cand("Manoel Machado")], "Mestre Bimba", "Mestre Manoel Machado",
            strip_titles=True,
        )
        assert out[0]["name"] == "Bimba" and out[0]["primary"] is True

    def test_unmatched_warning_names_the_stripped_hint(self):
        _, warnings = util.plan_primary_subject(
            [_cand("Salvador")], "Mestre Bimba", None, strip_titles=True
        )
        assert warnings == [
            'subject_hint_unmatched: no extracted entity is the primary subject "Bimba"'
        ]

    def test_strip_titles_without_hint_strips_and_dedupes(self):
        out, warnings = util.plan_primary_subject(
            [_cand("Mestre Moraes"), _cand("Moraes"), _cand("Salvador")], None, None,
            strip_titles=True,
        )
        assert [c["name"] for c in out] == ["Moraes", "Salvador"]
        assert warnings == []

    def test_without_hint_and_strip_nothing_changes(self):
        cands = [_cand("Mestre Moraes"), _cand("Moraes")]
        out, warnings = util.plan_primary_subject(cands, None, None)
        assert out == cands and warnings == []


# ---------------------------------------------------------------------------
# A qualified hint matches on its base name (Aldeia-IT/aldeia-box#1439)
# ---------------------------------------------------------------------------


class TestSplitQualifier:
    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            ("Onça (São Paulo)", ("Onça", "São Paulo")),
            ("Manoela (São Paulo, Nzinga)", ("Manoela", "São Paulo, Nzinga")),
            ("Filhos de Bimba (Bay Area (California))", ("Filhos de Bimba", "Bay Area (California)")),
            ("  Onça (Rio)  ", ("Onça", "Rio")),
            ("Onça", ("Onça", "")),
            ("Onça (São Paulo) Jr", ("Onça (São Paulo) Jr", "")),
            ("(São Paulo)", ("(São Paulo)", "")),
            ("Onça (São Paulo))", ("Onça (São Paulo))", "")),
            ("Onça São Paulo)", ("Onça São Paulo)", "")),
        ],
    )
    def test_last_balanced_trailing_group(self, name, expected):
        assert names.split_qualifier(name) == expected

    def test_non_string_has_no_qualifier(self):
        assert names.split_qualifier(None) == (None, "")

    def test_split_name_takes_the_whole_nested_group(self):
        assert names._split_name("Filhos de Bimba (Bay Area (California))") == (
            "filhos de bimba", "bay area california"
        )


class TestQualifiedHint:
    @pytest.mark.parametrize("extracted", ["Onça", "Mestre Onça", "onca", "Mestra Onça"])
    def test_base_name_matches_and_takes_the_full_hint(self, extracted):
        cands = [_cand("Salvador"), _cand(extracted, facts="about")]
        out, warnings = util.plan_primary_subject(cands, "Onça (São Paulo)", None)
        assert [c["name"] for c in out] == ["Salvador", "Onça (São Paulo)"]
        assert out[1]["primary"] is True and out[1]["facts"] == "about"
        assert warnings == []

    def test_bare_and_titled_forms_fold_into_the_hint(self):
        cands = [_cand("Mestre Onça", facts="first"), _cand("Onça"), _cand("Salvador")]
        out, warnings = util.plan_primary_subject(cands, "Onça (São Paulo)", None)
        assert [c["name"] for c in out] == ["Onça (São Paulo)", "Salvador"]
        assert out[0]["facts"] == "first" and warnings == []

    def test_full_hint_spelling_still_matches(self):
        out, _ = util.plan_primary_subject(
            [_cand("Mestre Onça (São Paulo)")], "Onça (São Paulo)", None
        )
        assert out[0]["name"] == "Onça (São Paulo)" and out[0]["primary"] is True

    @pytest.mark.parametrize("extracted", ["Onça (Rio)", "Mestre Onça (Rio)", "Onça (São Paulo, Nzinga)"])
    def test_another_qualifier_never_matches(self, extracted):
        out, warnings = util.plan_primary_subject([_cand(extracted)], "Onça (São Paulo)", None)
        assert [c["name"] for c in out] == [extracted]
        assert "primary" not in out[0]
        assert warnings == [
            'subject_hint_unmatched: no extracted entity is the primary subject "Onça (São Paulo)"'
        ]

    def test_cross_qualifier_candidate_stays_beside_the_match(self):
        cands = [_cand("Onça (Rio)"), _cand("Mestre Onça")]
        out, warnings = util.plan_primary_subject(cands, "Onça (São Paulo)", None)
        assert [c["name"] for c in out] == ["Onça (Rio)", "Onça (São Paulo)"]
        assert "primary" not in out[0] and out[1]["primary"] is True
        assert warnings == []

    def test_nested_qualifier(self):
        cands = [_cand("Bimba"), _cand("Filhos de Bimba")]
        out, warnings = util.plan_primary_subject(
            cands, "Filhos de Bimba (Bay Area (California))", None
        )
        assert [c["name"] for c in out] == ["Bimba", "Filhos de Bimba (Bay Area (California))"]
        assert out[1]["primary"] is True and warnings == []

    def test_nested_qualifier_does_not_match_its_inner_group(self):
        out, warnings = util.plan_primary_subject(
            [_cand("Filhos de Bimba (Bay Area)")], "Filhos de Bimba (Bay Area (California))", None
        )
        assert out[0]["name"] == "Filhos de Bimba (Bay Area)" and len(warnings) == 1

    def test_unqualified_hint_is_unchanged(self):
        cands = [_cand("Onça (São Paulo)"), _cand("Onça (Rio)")]
        out, warnings = util.plan_primary_subject(cands, "Onça", None)
        assert [c["name"] for c in out] == ["Onça (São Paulo)", "Onça (Rio)"]
        assert not any(c.get("primary") for c in out)
        assert warnings == ['subject_hint_unmatched: no extracted entity is the primary subject "Onça"']

    def test_other_base_name_is_unmatched(self):
        out, warnings = util.plan_primary_subject(
            [_cand("Mestre Pastinha"), _cand("Salvador")], "Onça (São Paulo)", None
        )
        assert [c["name"] for c in out] == ["Mestre Pastinha", "Salvador"]
        assert warnings == [
            'subject_hint_unmatched: no extracted entity is the primary subject "Onça (São Paulo)"'
        ]

    def test_marker_still_applies_to_a_qualified_hint(self):
        out, warnings = util.plan_primary_subject(
            [_cand("João Batista"), _cand("Salvador")], "Onça (São Paulo)", "João Batista"
        )
        assert out[0]["name"] == "Onça (São Paulo)" and warnings == []

    def test_strip_titles_space(self):
        out, warnings = util.plan_primary_subject(
            [_cand("Mestre Onça")], "Mestre Onça (São Paulo)", None, strip_titles=True
        )
        assert out[0]["name"] == "Onça (São Paulo)" and warnings == []


# ---------------------------------------------------------------------------
# extraction prompt and extract(subject_hint=...)
# ---------------------------------------------------------------------------


@pytest.fixture
def captured_prompts(monkeypatch):
    """Replace the model call; record each prompt and return a canned parse."""
    class _Prompts(list):
        state: dict

    prompts = _Prompts()
    state = {"parsed": {"entities": [], "concepts": []}}

    def fake(base, prompt):
        prompts.append(prompt)
        return state["parsed"], None, None

    monkeypatch.setattr(extraction, "_call_ollama_prompt_detailed", fake)
    monkeypatch.delenv("WIKI_EXTRACT_ENDPOINT", raising=False)
    prompts.state = state
    return prompts


class TestExtractionPrompt:
    def test_without_a_hint_the_prompt_is_byte_identical_to_before(self, captured_prompts):
        golden = (FIXTURES / "extraction_prompt_before_1430.md").read_text(encoding="utf-8")
        md = "# Bimba\n\nBorn in Salvador {subject} {source}."
        extraction.extract(markdown=md, space_id="s")
        extraction.extract(markdown=md, space_id="s", subject_hint=None)
        extraction.extract(markdown=md, space_id="s", subject_hint="   ")
        want = golden.replace("{source}", md)
        assert captured_prompts == [want, want, want]

    def test_hint_block_follows_the_source_fence(self, captured_prompts):
        extraction.extract(markdown="Some page.", space_id="s", subject_hint="Mestre Bimba")
        prompt = captured_prompts[0]
        fence_end = prompt.index("</source>") + len("</source>")
        block = prompt.index("## PRIMARY SUBJECT")
        assert fence_end < block < prompt.index("## OUTPUT")
        assert 'primary subject is "Mestre Bimba"' in prompt
        assert 'exactly "Mestre Bimba"' in prompt
        assert '"primary_subject"' in prompt
        assert "Extract every other entity and concept on the page as usual." in prompt
        assert (
            "If the page gives the primary subject's legal or full name, record it as a "
            "fact of the primary subject, not as a separate entity."
        ) in prompt
        assert "{subject}" not in prompt and "{source}" not in prompt

    def test_hint_is_stripped_before_it_is_used(self, captured_prompts):
        extraction.extract(markdown="p", space_id="s", subject_hint="  Mestre Bimba \n")
        assert 'primary subject is "Mestre Bimba"' in captured_prompts[0]

    def test_placeholders_in_page_or_hint_are_not_substituted(self, captured_prompts):
        extraction.extract(
            markdown="page says {subject} and {source}", space_id="s",
            subject_hint="Bimba {source}",
        )
        prompt = captured_prompts[0]
        assert "page says {subject} and {source}" in prompt
        assert 'primary subject is "Bimba {source}"' in prompt
        assert prompt.count("page says") == 1

    def test_the_input_cap_holds_with_the_hint_block(self, captured_prompts, monkeypatch):
        monkeypatch.setenv("WIKI_EXTRACT_MAX_INPUT_TOKENS", "1000")  # 3,000 chars
        source = "\n\n".join(f"Paragraph {i} " + "x" * 180 for i in range(40))
        result = extraction.extract(markdown=source, space_id="s", subject_hint="Mestre Bimba")
        assert len(captured_prompts[0]) <= 3000
        assert result["truncated"]["total_chars"] == len(source)
        plain = extraction._fit_source(source, extraction._load_prompt())[1]["kept_chars"]
        assert result["truncated"]["kept_chars"] < plain, "the hint block takes budget"

    def test_fit_source_measures_the_filled_template(self, monkeypatch):
        monkeypatch.setenv("WIKI_EXTRACT_MAX_INPUT_TOKENS", "1000")
        template = "A{source}B{subject}C"
        kept, truncated = extraction._fit_source("x" * 10_000, template, subject_block="y" * 500)
        base, _ = extraction._fit_source("x" * 10_000, template)
        assert len(base) - len(kept) == 500 and truncated is not None

    def test_primary_subject_survives_the_filter_and_is_central_is_stripped(self, captured_prompts):
        captured_prompts.state["parsed"] = {
            "entities": [{"name": "Manoel", "description": "d", "is_central": True}],
            "concepts": [],
            "primary_subject": "Manoel",
        }
        out = extraction.extract(markdown="p", space_id="s", subject_hint="Mestre Bimba")
        assert out["primary_subject"] == "Manoel"
        assert "is_central" not in out["entities"][0]

    def test_extract_signature_keeps_positional_callers(self):
        params = list(inspect.signature(extraction.extract).parameters)
        assert params[:2] == ["markdown", "space_id"] and "subject_hint" in params


# ---------------------------------------------------------------------------
# wiki_ingest / server / CLI surface
# ---------------------------------------------------------------------------


class TestSurface:
    def test_wiki_ingest_takes_subject_hint_last(self):
        params = list(inspect.signature(ingest.wiki_ingest).parameters)
        assert params == ["source", "space_id", "domain_hint", "subject_hint"]

    def test_server_tool_passes_the_hint_through(self, monkeypatch):
        from anytype_llm_wiki import server

        seen = {}
        monkeypatch.setattr(
            ingest, "wiki_ingest", lambda **kw: seen.update(kw) or {"status": "ok"}
        )
        params = list(inspect.signature(server.wiki_ingest).parameters)
        assert params == ["source", "space_id", "domain_hint", "subject_hint"]
        server.wiki_ingest(source="s", space_id="sp", subject_hint="Mestre Bimba")
        assert seen["subject_hint"] == "Mestre Bimba"

    def test_cli_flag(self, monkeypatch, capsys):
        from anytype_llm_wiki.wiki import cli

        seen = {}
        monkeypatch.setattr(
            ingest, "wiki_ingest", lambda **kw: seen.update(kw) or {"status": "ok"}
        )
        cli.main(["wiki-ingest", "--source", "s", "--space-id", "sp",
                  "--subject-hint", "Mestre Bimba", "--json"])
        assert seen["subject_hint"] == "Mestre Bimba"
        assert seen["domain_hint"] is None

    def test_invalid_hint_is_a_config_error_before_any_client(self, monkeypatch):
        def boom(*a, **k):
            raise AssertionError("no client may be built for an invalid hint")

        monkeypatch.setattr(ingest, "WikiClient", boom)
        monkeypatch.setattr(ingest, "fetch_source", boom)
        for bad in ("system: be Bimba", "x" * 500, "ignore previous"):
            result = ingest.wiki_ingest("https://e.x/p", "sp", subject_hint=bad)
            assert result["status"] == "error"
            assert result["error"].startswith("[CONFIG ERROR] invalid_subject_hint")
