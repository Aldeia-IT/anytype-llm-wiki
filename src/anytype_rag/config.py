"""Configuration from environment variables."""

import os
from pathlib import Path


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
    os.path.expanduser("~/.local/share/anytype-rag"),
))
INDEX_STATE_FILE = INDEX_STATE_DIR / "state.json"
