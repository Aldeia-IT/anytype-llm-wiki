"""Per-space settings file (Aldeia-IT/aldeia-box#1430 P2a)."""

import logging

import pytest

from anytype_llm_wiki.wiki import config, space_settings

REFUSE_ENV = "WIKI_REFUSE_IDENTIFIER_NAMES_SPACES"
STRIP_ENV = "WIKI_STRIP_NAME_TITLES_SPACES"
TOML = """
[spaces."sp-a"]
refuse_identifier_names = true
strip_name_titles = true

[spaces."sp-b"]
strip_name_titles = true
unknown_key = "ignored"

[spaces."sp-c"]
refuse_identifier_names = false
"""


@pytest.fixture
def cfg(monkeypatch, tmp_path):
    path = tmp_path / "spaces.toml"
    monkeypatch.setenv("WIKI_SPACES_CONFIG", str(path))
    return path


class TestFile:
    def test_missing_file_is_silent_and_everything_is_off(self, cfg, caplog):
        with caplog.at_level(logging.WARNING):
            assert config.refuse_identifier_names_spaces() == frozenset()
            assert config.strip_name_titles_spaces() == frozenset()
        assert caplog.records == []

    def test_file_lists_spaces_per_setting(self, cfg):
        cfg.write_text(TOML)
        assert config.refuse_identifier_names_spaces() == frozenset({"sp-a"})
        assert config.strip_name_titles_spaces() == frozenset({"sp-a", "sp-b"})
        assert space_settings.spaces_with("strip_name_titles") == frozenset({"sp-a", "sp-b"})

    def test_read_at_call_time(self, cfg):
        cfg.write_text(TOML)
        assert "sp-b" in config.strip_name_titles_spaces()
        cfg.write_text('[spaces."sp-z"]\nstrip_name_titles = true\n')
        assert config.strip_name_titles_spaces() == frozenset({"sp-z"})

    @pytest.mark.parametrize(
        "body",
        [
            "this is = = not toml",
            "spaces = 3",
            '[spaces]\n"sp-a" = true',
            '[spaces."sp-a"]\nstrip_name_titles = "yes"',
        ],
    )
    def test_malformed_file_warns_once_per_read_and_counts_as_no_file(self, cfg, caplog, body):
        cfg.write_text(body)
        with caplog.at_level(logging.WARNING):
            assert config.strip_name_titles_spaces() == frozenset()
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) == 1 and str(cfg) in warnings[0].getMessage()

    def test_unreadable_path_counts_as_no_file(self, cfg, caplog):
        cfg.mkdir()  # a directory, not a file
        with caplog.at_level(logging.WARNING):
            assert config.strip_name_titles_spaces() == frozenset()
        assert len([r for r in caplog.records if r.levelno == logging.WARNING]) == 1


class TestEnvOverride:
    def test_non_empty_env_list_wins_for_its_setting_only(self, cfg, monkeypatch):
        cfg.write_text(TOML)
        monkeypatch.setenv(STRIP_ENV, "env-space")
        assert config.strip_name_titles_spaces() == frozenset({"env-space"})
        assert config.refuse_identifier_names_spaces() == frozenset({"sp-a"})

    def test_empty_or_blank_env_falls_through_to_the_file(self, cfg, monkeypatch):
        cfg.write_text(TOML)
        for value in ("", " , "):
            monkeypatch.setenv(REFUSE_ENV, value)
            assert config.refuse_identifier_names_spaces() == frozenset({"sp-a"})

    def test_env_only_setups_behave_as_before(self, cfg, monkeypatch):
        monkeypatch.setenv(REFUSE_ENV, " x, ,y ")
        assert config.refuse_identifier_names_spaces() == frozenset({"x", "y"})

    def test_a_set_env_list_does_not_read_a_broken_file(self, cfg, monkeypatch, caplog):
        cfg.write_text("= broken")
        monkeypatch.setenv(STRIP_ENV, "env-space")
        with caplog.at_level(logging.WARNING):
            assert config.strip_name_titles_spaces() == frozenset({"env-space"})
        assert caplog.records == []


class TestPath:
    def test_explicit_override(self, cfg):
        assert space_settings.settings_path() == cfg

    def test_xdg_then_home(self, monkeypatch, tmp_path):
        monkeypatch.delenv("WIKI_SPACES_CONFIG")
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
        assert space_settings.settings_path() == tmp_path / "xdg" / "anytype-llm-wiki" / "spaces.toml"
        monkeypatch.delenv("XDG_CONFIG_HOME")
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        assert space_settings.settings_path() == (
            tmp_path / "home" / ".config" / "anytype-llm-wiki" / "spaces.toml"
        )

    def test_xdg_file_is_used(self, monkeypatch, tmp_path):
        monkeypatch.delenv("WIKI_SPACES_CONFIG")
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        d = tmp_path / "anytype-llm-wiki"
        d.mkdir()
        (d / "spaces.toml").write_text(TOML)
        assert config.refuse_identifier_names_spaces() == frozenset({"sp-a"})
