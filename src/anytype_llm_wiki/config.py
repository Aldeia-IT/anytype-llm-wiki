"""Configuration from environment variables."""

import os
from pathlib import Path

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

# Qdrant chunk-payload schema version. Bumping this forces a one-time full
# re-embed on the next reindex (see indexer.reindex migration logic). v1 = the
# 6-field payload; v2 adds last_modified_date; v3 adds source_type and
# domain_tags.
PAYLOAD_SCHEMA_VERSION = 3
