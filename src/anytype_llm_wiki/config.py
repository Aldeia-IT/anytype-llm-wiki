"""Configuration from environment variables."""

import os
from pathlib import Path

from .textfold import fold

# Load .env if present (for local development / testing)
_env_file = Path(__file__).resolve().parent.parent.parent / ".env"
if _env_file.exists():
    for line in _env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


ANYTYPE_API_URL = os.environ.get("ANYTYPE_API_URL", "http://127.0.0.1:31012")
ANYTYPE_API_KEY = os.environ.get("ANYTYPE_API_KEY", "")
ANYTYPE_API_VERSION = os.environ.get("ANYTYPE_API_VERSION", "2025-11-08")

QDRANT_URL = os.environ.get("QDRANT_URL", "http://127.0.0.1:6333")
QDRANT_API_KEY = os.environ.get("QDRANT_API_KEY", "")
QDRANT_COLLECTION = os.environ.get("QDRANT_COLLECTION", "anytype_semantic")

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "bge-m3")
EMBED_DIMS = int(os.environ.get("EMBED_DIMS", "1024"))

INDEX_STATE_DIR = Path(os.environ.get(
    "INDEX_STATE_DIR",
    os.path.expanduser("~/.local/share/anytype-llm-wiki"),
))
INDEX_STATE_FILE = INDEX_STATE_DIR / "state.json"

# Qdrant chunk-payload schema version. Bumping this forces a one-time backfill
# on the next unscoped reindex (see indexer._run_reindex migration logic). v1 =
# the 6-field payload; v2 adds last_modified_date; v3 adds source_type and
# domain_tags (v2 and v3 force a full re-embed); v4 adds wiki_url on sources
# ingested from a URL (payload-only set_payload backfill from v3, no re-embed;
# Aldeia-IT/aldeia-box#1413).
PAYLOAD_SCHEMA_VERSION = 4


def _parse_title_words(raw: str | None) -> tuple[str, ...] | None:
    """Parse the ``NAME_TIER_TITLE_WORDS`` override (Aldeia-IT/aldeia-box#327 D13).

    Args:
        raw: the env value: comma-separated title words, or ``None`` when unset.

    Returns:
        ``None`` when unset (the name tier then uses its built-in list), else the
        words folded (accents dropped, casefolded) and trimmed, empty entries
        dropped. A set but empty value gives ``()``: no title words at all.
    """
    if raw is None:
        return None
    words = (fold(part).strip() for part in raw.split(","))
    return tuple(word for word in words if word)


# Leading title words the name tier strips from names and queries ("Mestre
# Pastinha" matches "Pastinha"). None = the built-in list in indexer.py. The
# tier reads this attribute at call time.
NAME_TIER_TITLE_WORDS = _parse_title_words(os.environ.get("NAME_TIER_TITLE_WORDS"))
