"""Per-space settings: which spaces opt in to a naming policy (Aldeia-IT/aldeia-box#1430 P2a).

The one place that reads the per-space config file and the two list variables
``WIKI_REFUSE_IDENTIFIER_NAMES_SPACES`` and ``WIKI_STRIP_NAME_TITLES_SPACES``.
``config.refuse_identifier_names_spaces()`` and ``config.strip_name_titles_spaces()``
delegate here; nothing else reads them.

File: TOML at ``WIKI_SPACES_CONFIG``, else ``$XDG_CONFIG_HOME/anytype-llm-wiki/spaces.toml``,
else ``~/.config/anytype-llm-wiki/spaces.toml``::

    [spaces."<space id>"]
    refuse_identifier_names = true
    strip_name_titles = true
    file_back_default = false   # or "gate" (the default): wiki_query's file-back

Everything is read at call time (tests monkeypatch the environment).
"""

import logging
import os
import tomllib
from pathlib import Path

logger = logging.getLogger(__name__)

# setting key in the file -> list variable that overrides it
_ENV_BY_SETTING = {
    "refuse_identifier_names": "WIKI_REFUSE_IDENTIFIER_NAMES_SPACES",
    "strip_name_titles": "WIKI_STRIP_NAME_TITLES_SPACES",
}


_FILE_BACK_KEY = "file_back_default"


def settings_path() -> Path:
    """The per-space settings file path (it need not exist)."""
    explicit = os.environ.get("WIKI_SPACES_CONFIG")
    if explicit:
        return Path(explicit)
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return Path(base) / "anytype-llm-wiki" / "spaces.toml"


def _load_file() -> dict[str, dict]:
    """Parse and validate the file into ``{space id: {setting: bool}}``.

    A missing file is silent and empty. A file that cannot be read, is not TOML,
    has a non-table ``spaces`` or a non-bool value for a known setting logs one
    warning naming the path and is treated as no file (every setting off).
    Unknown keys are ignored.
    """
    path = settings_path()
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return {}
    except OSError as exc:
        logger.warning("wiki spaces config %s ignored: unreadable (%s)", path, exc)
        return {}
    try:
        data = tomllib.loads(raw.decode("utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
        logger.warning("wiki spaces config %s ignored: invalid TOML (%s)", path, exc)
        return {}
    spaces = data.get("spaces", {})
    problem = None
    if not isinstance(spaces, dict):
        problem = "'spaces' is not a table"
    else:
        for space_id, table in spaces.items():
            if not isinstance(table, dict):
                problem = f"spaces.{space_id!r} is not a table"
                break
            bad = next(
                (k for k in _ENV_BY_SETTING if k in table and not isinstance(table[k], bool)),
                None,
            )
            if bad:
                problem = f"spaces.{space_id!r}.{bad} is not true or false"
                break
            if table.get(_FILE_BACK_KEY, "gate") not in ("gate", False):
                problem = f'spaces.{space_id!r}.{_FILE_BACK_KEY} is not "gate" or false'
                break
    if problem:
        logger.warning("wiki spaces config %s ignored: %s", path, problem)
        return {}
    return spaces


def spaces_with(setting: str) -> frozenset[str]:
    """The space IDs that have ``setting`` switched on.

    A set, non-empty list variable for the setting is the answer and the file is
    not consulted. Otherwise the file decides; no file and no variable means no
    space.

    Args:
        setting: ``"refuse_identifier_names"`` or ``"strip_name_titles"``.

    Returns:
        The opted-in space IDs.

    Raises:
        KeyError: for an unknown setting.
    """
    env_name = _ENV_BY_SETTING[setting]
    listed = frozenset(
        part.strip() for part in os.environ.get(env_name, "").split(",") if part.strip()
    )
    if listed:
        return listed
    return frozenset(
        space_id for space_id, table in _load_file().items() if table.get(setting) is True
    )


def file_back_default(space_id: str) -> bool | None:
    """The space's default for ``wiki_query``'s ``file_back`` (Aldeia-IT/aldeia-box#1430).

    Set per space in the file as ``file_back_default = "gate"`` (today's
    behaviour, also the default) or ``false`` (never file back unless the call
    asks). Any other value makes the file malformed (see ``_load_file``). No
    environment override. The caller applies it only when ``file_back`` is None.

    Args:
        space_id: the space being queried.

    Returns:
        ``False`` when the space turns file-back off by default, else ``None``
        (the gate decides).
    """
    table = _load_file().get(space_id, {})
    return False if table.get(_FILE_BACK_KEY, "gate") is False else None
