"""Semantic search MCP server for Anytype."""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version

try:
    __version__ = _pkg_version("anytype-llm-wiki")
except PackageNotFoundError:  # running from a source tree without install metadata
    __version__ = "0.2.0"
