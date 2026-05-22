"""Anytype REST API client.

v0.2.0 (BLOCKING-CTO-1): the read-plane API now lives on ``AnytypeReadClient``,
which inherits the shared transport contract from ``_BaseAnytypeClient``. The
module-level free functions (``list_spaces``, ``list_objects``, ``get_object``)
are preserved as thin wrappers that construct an ``AnytypeReadClient`` and
delegate — keeping ``indexer.py``'s import surface unchanged.
"""

from .wiki._base_client import _BaseAnytypeClient


class AnytypeReadClient(_BaseAnytypeClient):
    """Read-plane Anytype client: list spaces/objects and fetch a single object."""

    def list_spaces(self) -> list[dict]:
        """GET all spaces (up to 100). Returns the list of space dicts."""
        c = self._client()
        resp = c.get("/v1/spaces", params={"limit": 100})
        resp.raise_for_status()
        return resp.json()["data"]

    def list_objects(self, space_id: str, offset: int = 0, limit: int = 100) -> list[dict]:
        """GET all objects in a space, paginating via pagination.has_more.

        Tolerates a missing ``pagination`` key (treated as has_more=False).
        """
        all_objects: list[dict] = []
        c = self._client()
        while True:
            resp = c.get(
                f"/v1/spaces/{space_id}/objects",
                params={"offset": offset, "limit": limit},
            )
            resp.raise_for_status()
            data = resp.json()
            all_objects.extend(data.get("data", []))
            pagination = data.get("pagination") or {}
            if not pagination.get("has_more", False):
                break
            offset += limit
        return all_objects

    def get_object(self, space_id: str, object_id: str) -> dict:
        """GET a single object rendered as markdown. Returns the object dict."""
        c = self._client()
        resp = c.get(
            f"/v1/spaces/{space_id}/objects/{object_id}",
            params={"format": "md"},
        )
        resp.raise_for_status()
        return resp.json()["object"]


# ---------------------------------------------------------------------------
# Module-level wrappers (preserve the legacy import surface used by indexer.py)
# ---------------------------------------------------------------------------


def list_spaces() -> list[dict]:
    client = AnytypeReadClient()
    try:
        return client.list_spaces()
    finally:
        client.close()


def list_objects(space_id: str, offset: int = 0, limit: int = 100) -> list[dict]:
    client = AnytypeReadClient()
    try:
        return client.list_objects(space_id, offset=offset, limit=limit)
    finally:
        client.close()


def get_object(space_id: str, object_id: str) -> dict:
    client = AnytypeReadClient()
    try:
        return client.get_object(space_id, object_id)
    finally:
        client.close()
