"""Anytype REST API client."""

import httpx

from . import config


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {config.ANYTYPE_API_KEY}",
        "Anytype-Version": config.ANYTYPE_API_VERSION,
        "Content-Type": "application/json",
    }


def _client() -> httpx.Client:
    return httpx.Client(base_url=config.ANYTYPE_API_URL, headers=_headers(), timeout=30)


def list_spaces() -> list[dict]:
    with _client() as c:
        resp = c.get("/v1/spaces", params={"limit": 100})
        resp.raise_for_status()
        return resp.json()["data"]


def list_objects(space_id: str, offset: int = 0, limit: int = 100) -> list[dict]:
    all_objects = []
    with _client() as c:
        while True:
            resp = c.get(f"/v1/spaces/{space_id}/objects", params={"offset": offset, "limit": limit})
            resp.raise_for_status()
            data = resp.json()
            all_objects.extend(data["data"])
            if not data["pagination"]["has_more"]:
                break
            offset += limit
    return all_objects


def get_object(space_id: str, object_id: str) -> dict:
    with _client() as c:
        resp = c.get(f"/v1/spaces/{space_id}/objects/{object_id}", params={"format": "md"})
        resp.raise_for_status()
        return resp.json()["object"]
