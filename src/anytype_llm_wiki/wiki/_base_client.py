"""Transport-only base for Anytype API clients.

``_BaseAnytypeClient`` owns the HTTP transport concerns shared by the
read-plane (``AnytypeReadClient``) and write-plane (``WikiClient``) clients:
building authenticated headers, constructing a reusable ``httpx.Client``, and
closing it. It deliberately defines NO read-plane or write-plane API methods —
those live on the subclasses (spec S14 separation of concerns).

Environment is resolved at CALL TIME, never cached at import time. Tests inject
``ANYTYPE_API_KEY`` / ``ANYTYPE_API_URL`` / ``ANYTYPE_API_VERSION`` via
``monkeypatch.setenv`` after the module is imported and assert the headers and
base URL reflect the injected values.
"""

import os

import httpx

# Defaults mirror anytype_llm_wiki.config (do not import-cache them here).
_DEFAULT_API_URL = "http://127.0.0.1:31012"
_DEFAULT_API_VERSION = "2025-11-08"
_DEFAULT_API_KEY = ""

_TIMEOUT = 30


def _resolve_base_url() -> str:
    """Resolve the Anytype API base URL from the environment at call time."""
    return os.environ.get("ANYTYPE_API_URL", _DEFAULT_API_URL)


def _resolve_api_key() -> str:
    """Resolve the Anytype API key from the environment at call time."""
    return os.environ.get("ANYTYPE_API_KEY", _DEFAULT_API_KEY)


def _resolve_api_version() -> str:
    """Resolve the Anytype API version from the environment at call time."""
    return os.environ.get("ANYTYPE_API_VERSION", _DEFAULT_API_VERSION)


class _BaseAnytypeClient:
    """Transport-only base: session + headers + timeout + close().

    Subclasses add the actual read/write API methods.
    """

    def __init__(self, base_url: str | None = None) -> None:
        # Resolve base_url at construction time from the explicit arg or env.
        self._base_url_override = base_url
        self._http: httpx.Client | None = None

    def _headers(self) -> dict[str, str]:
        """Build authenticated request headers, reading credentials at call time."""
        return {
            "Authorization": f"Bearer {_resolve_api_key()}",
            "Anytype-Version": _resolve_api_version(),
            "Content-Type": "application/json",
        }

    def _client(self) -> httpx.Client:
        """Return a reusable httpx.Client for this instance.

        Built lazily so env injected after construction is still honored on the
        first real call.
        """
        if self._http is None:
            base_url = self._base_url_override or _resolve_base_url()
            self._http = httpx.Client(
                base_url=base_url,
                headers=self._headers(),
                timeout=_TIMEOUT,
            )
        return self._http

    def close(self) -> None:
        """Close the underlying httpx.Client. Safe to call when not yet opened."""
        if self._http is not None:
            self._http.close()
            self._http = None
