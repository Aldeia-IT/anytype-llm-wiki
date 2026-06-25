"""WikiClient — the write-plane Anytype client for the wiki module.

Inherits transport from ``_BaseAnytypeClient`` and adds the create/update/search
methods the bootstrap and (future) extraction pipelines need. Also exposes
internal list-helpers (``list_types``, ``list_properties``, ``list_tags``,
``list_objects``) used by the next worker's bootstrap for idempotency. Those
helpers tolerate a missing ``pagination`` key (treated as ``has_more=False``).
"""

from ._base_client import _BaseAnytypeClient


class WikiClient(_BaseAnytypeClient):
    """Write-plane client: create/update objects, types, properties, tags; search."""

    # -- write plane -------------------------------------------------------

    def create_type(self, space_id: str, type_def: dict) -> dict:
        """POST a new type. Returns the created type dict."""
        c = self._client()
        resp = c.post(f"/v1/spaces/{space_id}/types", json=type_def)
        resp.raise_for_status()
        return resp.json()["type"]

    def get_type(self, space_id: str, type_id: str) -> dict:
        """GET a single type by id. Returns the type dict (the value under the "type" key)."""
        c = self._client()
        resp = c.get(f"/v1/spaces/{space_id}/types/{type_id}")
        resp.raise_for_status()
        return resp.json()["type"]

    def update_type(self, space_id: str, type_id: str, type_def: dict) -> dict:
        """PATCH an existing type. Returns the updated type dict.

        Refuses an empty/None ``properties`` payload — under Anytype's replace-not-merge
        semantics a {"properties": []} PATCH would wipe every user property on the type.
        """
        # type_def is dict per annotation; an empty/missing properties list must be refused —
        # a {"properties": []} PATCH would wipe every user property under replace-not-merge.
        props = type_def.get("properties")
        if not props:
            raise ValueError(
                "update_type refused: empty or missing 'properties' payload would "
                "destroy all properties on the type under replace-not-merge semantics"
            )
        c = self._client()
        resp = c.patch(f"/v1/spaces/{space_id}/types/{type_id}", json=type_def)
        resp.raise_for_status()
        return resp.json()["type"]

    def create_property(self, space_id: str, type_key: str, prop_def: dict) -> dict:
        """POST a new property. Returns the created property dict.

        ``type_key`` is accepted for caller convenience; the property is created
        at the space level (Anytype properties are space-scoped).
        """
        c = self._client()
        resp = c.post(f"/v1/spaces/{space_id}/properties", json=prop_def)
        resp.raise_for_status()
        return resp.json()["property"]

    def create_tag(self, space_id: str, property_id: str, tag) -> dict:
        """POST a new tag (select/multi-select option). Returns the created tag dict.

        The Anytype API keys this endpoint by the property's *id* (not its key)
        and exposes it under ``/tags`` (not ``/options``). ``color`` is REQUIRED
        and must be drawn from ``types_schema.TAG_COLOR_PALETTE``. ``tag`` may be
        a plain name (str) or a dict carrying at least ``name`` and ``color``.
        """
        c = self._client()
        body = tag if isinstance(tag, dict) else {"name": tag}
        resp = c.post(
            f"/v1/spaces/{space_id}/properties/{property_id}/tags",
            json=body,
        )
        resp.raise_for_status()
        return resp.json()["tag"]

    def create_object(
        self,
        space_id: str,
        type_key: str,
        name: str,
        properties: list | None = None,
        body: str | None = None,
    ) -> dict:
        """POST a new object. Returns the created object dict.

        ``properties`` must be a *list* of PropertyLinkWithValue entries, each a
        ``{"key": <property_key>, <typed_field>: <value>}`` dict (e.g.
        ``{"key": "wiki_excerpt", "text": "..."}``). The Anytype API rejects a
        bare ``{key: value}`` mapping. Omitted when empty/None.
        """
        c = self._client()
        payload: dict = {"type_key": type_key, "name": name}
        if properties:
            payload["properties"] = properties
        if body is not None:
            payload["body"] = body
        resp = c.post(f"/v1/spaces/{space_id}/objects", json=payload)
        resp.raise_for_status()
        return resp.json()["object"]

    def update_object(self, space_id: str, object_id: str, patch: dict) -> dict:
        """PATCH an existing object. Returns the updated object dict."""
        c = self._client()
        resp = c.patch(f"/v1/spaces/{space_id}/objects/{object_id}", json=patch)
        resp.raise_for_status()
        return resp.json()["object"]

    def delete_object(self, space_id: str, object_id: str) -> None:
        """DELETE an object (used to roll back a half-written bidi relation)."""
        c = self._client()
        resp = c.delete(f"/v1/spaces/{space_id}/objects/{object_id}")
        resp.raise_for_status()

    def search(self, space_id: str, query: str, filter: dict | None = None) -> list[dict]:
        """POST a search query. Returns the list of matching objects.

        A convenience ``filter={"type_key": X}`` is translated to the canonical
        FilterExpression shape; any other filter dict is passed through unchanged.
        """
        c = self._client()
        payload: dict = {"query": query}
        if filter:
            if set(filter.keys()) == {"type_key"}:
                payload["filter"] = {
                    "condition": "and",
                    "filters": [
                        {
                            "key": "type_key",
                            "condition": "eq",
                            "value": filter["type_key"],
                        }
                    ],
                }
            else:
                payload["filter"] = filter
        resp = c.post(f"/v1/spaces/{space_id}/search", json=payload)
        resp.raise_for_status()
        return resp.json()["data"]

    # -- list helpers (for Worker 2 bootstrap idempotency) -----------------

    def list_types(self, space_id: str) -> list[dict]:
        """GET all types in a space, paginating while pagination.has_more is true."""
        return self._paginated_get(f"/v1/spaces/{space_id}/types")

    def list_properties(self, space_id: str) -> list[dict]:
        """GET all properties in a space, paginating while pagination.has_more is true."""
        return self._paginated_get(f"/v1/spaces/{space_id}/properties")

    def list_tags(self, space_id: str, property_id: str) -> list[dict]:
        """GET all tags for a property (keyed by property *id*), paginating fully.

        Endpoint is ``/properties/{property_id}/tags`` (not ``.../options``).
        """
        return self._paginated_get(
            f"/v1/spaces/{space_id}/properties/{property_id}/tags"
        )

    def list_objects(self, space_id: str, offset: int = 0, limit: int = 100) -> list[dict]:
        """GET all objects in a space, paginating while pagination.has_more is true."""
        return self._paginated_get(
            f"/v1/spaces/{space_id}/objects", offset=offset, limit=limit
        )

    def _paginated_get(self, path: str, offset: int = 0, limit: int = 100) -> list[dict]:
        """Fetch a paginated GET endpoint, accumulating data[].

        Tolerates a missing ``pagination`` key by treating it as has_more=False.
        """
        c = self._client()
        results: list[dict] = []
        while True:
            resp = c.get(path, params={"offset": offset, "limit": limit})
            resp.raise_for_status()
            data = resp.json()
            results.extend(data.get("data", []))
            pagination = data.get("pagination") or {}
            if not pagination.get("has_more", False):
                break
            offset += limit
        return results
