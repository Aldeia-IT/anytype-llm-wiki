"""Shared Anytype fake for the wiki tests (Aldeia-IT/aldeia-box#1427, #1486).

``FakeWiki`` is a respx-backed in-memory Anytype: search by normalised name,
create/patch/get/list objects, a canned page host, a ``read_only`` switch and
request-level failure injection. The tests build real ``WikiClient`` and
``AnytypeReadClient`` instances on top of it (``wiki_client()``, ``read_client()``)
so the wire shapes are the production ones. Call ``install()`` inside a
``respx.mock`` context, and set the ``ANYTYPE_*`` env vars first.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import httpx
import respx

ANYTYPE_BASE = "http://127.0.0.1:31012"
SPACE = "space-real-pages-001"
LALAUE = (Path(__file__).parent / "fixtures" / "pages" / "lalaue_shaped.html").read_text(
    encoding="utf-8"
)

_OBJECT_PATH = re.compile(r"/v1/spaces/[^/]+/objects/(?P<oid>[^/]+)$")


def schema_ok() -> dict:
    """The wiki collection with the current schema version (bootstrap sees a ready space)."""
    from anytype_llm_wiki.wiki.types_schema import WIKI_SCHEMA_VERSION

    return {
        "data": [
            {
                "id": "coll-wiki-001",
                "name": "Wiki",
                "type": {"key": "collection"},
                "properties": [{"key": "wiki_schema_version", "text": WIKI_SCHEMA_VERSION}],
            }
        ],
        "pagination": {"has_more": False},
    }


def prop_value(obj_or_payload: dict, key: str):
    """The ``objects``/``text`` value of property ``key`` in an object or a create/PATCH payload."""
    for p in obj_or_payload.get("properties") or []:
        if isinstance(p, dict) and p.get("key") == key:
            if "objects" in p:
                return [o["id"] if isinstance(o, dict) else o for o in p["objects"]]
            return p.get("text")
    return None


class FakeWiki:
    """In-memory Anytype: search by normalized name, create/patch/get/list objects, log writes.

    ``page_body``/``page_status`` drive the canned page host. ``serve_objects`` makes the
    ``/objects`` list return the stored objects (default: the schema collection, which the
    ingest tests rely on). ``search_with_properties`` makes a search hit carry the stored properties (the production
    search does); the default keeps the property-less hits the ingest tests were written
    against. ``search_aliases`` maps a normalised query to the normalised stored name it
    should find (a search that is fuzzier than exact). ``read_only`` answers every create and PATCH with 403 and records
    it in ``blocked`` instead of storing it.
    """

    def __init__(
        self,
        page_body: str | None = LALAUE,
        page_status: int = 200,
        *,
        read_only: bool = False,
        serve_objects: bool = False,
        search_with_properties: bool = False,
        search_aliases: dict[str, str] | None = None,
    ):
        self.store: dict = {}
        self.objects: dict[str, dict] = {}
        self.created: list[dict] = []
        self.patched: list[dict] = []
        self.patch_attempts: list[tuple[str, dict]] = []
        self.requests: list[tuple[str, str]] = []
        self.blocked: list[tuple[str, str]] = []
        self.page_body = page_body
        self.page_status = page_status
        self.read_only = read_only
        self.serve_objects = serve_objects
        self.search_with_properties = search_with_properties
        self.search_aliases = {k: v for k, v in (search_aliases or {}).items()}
        self.n = 0
        self._failures: list[dict] = []

    # -- clients ---------------------------------------------------------

    def wiki_client(self):
        """A real ``WikiClient`` (talks to this fake through respx)."""
        from anytype_llm_wiki.wiki.wiki_client import WikiClient

        return WikiClient()

    def read_client(self):
        """A real ``AnytypeReadClient`` (talks to this fake through respx)."""
        from anytype_llm_wiki.anytype_client import AnytypeReadClient

        return AnytypeReadClient()

    # -- setup -----------------------------------------------------------

    def install(self):
        respx.get(url__startswith=ANYTYPE_BASE).mock(side_effect=self._get)
        respx.get(url__startswith="https://lalaue.example/").mock(side_effect=self._page)
        respx.post(url__startswith=ANYTYPE_BASE).mock(side_effect=self._post)
        respx.patch(url__startswith=ANYTYPE_BASE).mock(side_effect=self._patch)

    def seed(
        self,
        type_key: str,
        name: str,
        properties: list[dict] | None = None,
        object_id: str | None = None,
    ) -> str:
        """Store an object as if it already existed in the space; returns its id."""
        from anytype_llm_wiki.wiki.util import normalize_title

        self.n += 1
        oid = object_id or f"obj-{self.n}"
        self.objects[oid] = {
            "id": oid,
            "name": name,
            "type": {"key": type_key},
            "properties": [dict(p) for p in (properties or [])],
        }
        self.store[(normalize_title(name), type_key)] = {"id": oid, "name": name}
        return oid

    def fail(
        self,
        method: str,
        *,
        object_id: str | None = None,
        type_key: str | None = None,
        nth: int = 1,
        times: int = 1,
        status: int = 500,
    ) -> None:
        """Answer matching ``method`` requests with ``status``, from the ``nth`` match on.

        ``object_id`` matches the id in the URL path (GET/PATCH); ``type_key`` matches
        the ``type_key`` of a create payload (POST). ``times`` consecutive matches fail.
        """
        self._failures.append(
            {
                "method": method.upper(),
                "object_id": object_id,
                "type_key": type_key,
                "nth": nth,
                "times": times,
                "status": status,
                "seen": 0,
            }
        )

    # -- handlers --------------------------------------------------------

    def _injected(self, method: str, request, payload: dict | None = None):
        match = _OBJECT_PATH.search(request.url.path)
        oid = match.group("oid") if match else None
        for rule in self._failures:
            if rule["method"] != method:
                continue
            if rule["object_id"] is not None and rule["object_id"] != oid:
                continue
            if rule["type_key"] is not None and rule["type_key"] != (payload or {}).get(
                "type_key"
            ):
                continue
            rule["seen"] += 1
            if rule["nth"] <= rule["seen"] < rule["nth"] + rule["times"]:
                return httpx.Response(rule["status"], json={"message": "injected failure"})
        return None

    def _get(self, request):
        self.requests.append(("GET", request.url.path))
        failed = self._injected("GET", request)
        if failed is not None:
            return failed
        match = _OBJECT_PATH.search(request.url.path)
        if match:
            obj = self.objects.get(match.group("oid"))
            if obj is None:
                return httpx.Response(404, json={"message": "not found"})
            return httpx.Response(200, json={"object": obj})
        if self.serve_objects and request.url.path.endswith("/objects"):
            return httpx.Response(
                200,
                json={"data": list(self.objects.values()), "pagination": {"has_more": False}},
            )
        return httpx.Response(200, json=schema_ok())

    def _page(self, request):
        return httpx.Response(
            self.page_status,
            text=self.page_body or "",
            headers={"content-type": "text/html; charset=utf-8"},
        )

    def _post(self, request):
        from anytype_llm_wiki.wiki.util import normalize_title

        url = str(request.url)
        payload = json.loads(request.content or b"{}")
        self.requests.append(("POST", request.url.path))
        if "/search" in url:
            q = normalize_title(payload.get("query", ""))
            q = self.search_aliases.get(q, q)
            data = [
                {
                    "id": o["id"],
                    "name": o["name"],
                    "type": {"key": tk},
                    "properties": (
                        self.objects.get(o["id"], {}).get("properties", [])
                        if self.search_with_properties
                        else []
                    ),
                }
                for (n, tk), o in self.store.items()
                if n == q
            ]
            return httpx.Response(200, json={"data": data, "pagination": {"has_more": False}})
        if "/objects" in url:
            if self.read_only:
                self.blocked.append(("POST", payload.get("type_key", "")))
                return httpx.Response(403, json={"message": "read only"})
            failed = self._injected("POST", request, payload)
            if failed is not None:
                return failed
            self.n += 1
            oid = f"obj-{self.n}"
            name = payload.get("name", "")
            tk = payload.get("type_key", "")
            self.store[(normalize_title(name), tk)] = {"id": oid, "name": name}
            self.objects[oid] = {
                "id": oid,
                "name": name,
                "type": {"key": tk},
                "properties": [dict(p) for p in payload.get("properties") or []],
            }
            self.created.append(payload)
            return httpx.Response(201, json={"object": {"id": oid, "name": name}})
        return httpx.Response(200, json={})

    def _patch(self, request):
        payload = json.loads(request.content or b"{}")
        match = _OBJECT_PATH.search(request.url.path)
        oid = match.group("oid") if match else ""
        self.requests.append(("PATCH", request.url.path))
        self.patch_attempts.append((oid, payload))
        if self.read_only:
            self.blocked.append(("PATCH", oid))
            return httpx.Response(403, json={"message": "read only"})
        failed = self._injected("PATCH", request)
        if failed is not None:
            return failed
        self.patched.append(payload)
        obj = self.objects.get(oid)
        if obj is not None:
            for new in payload.get("properties") or []:
                obj["properties"] = [p for p in obj["properties"] if p.get("key") != new["key"]]
                obj["properties"].append(dict(new))
        return httpx.Response(200, json={"object": {"id": oid or "patched"}})

    # -- inspection ------------------------------------------------------

    def created_of(self, type_key: str) -> list[dict]:
        return [p for p in self.created if p.get("type_key") == type_key]

    def wiki_objects(self) -> list[dict]:
        return [
            p for p in self.created if p.get("type_key") not in ("wiki_source", "wiki_log")
        ]

    def patches_of(self, object_id: str) -> list[dict]:
        """Successful PATCH payloads sent to ``object_id``, in order."""
        return [p for oid, p in self.patch_attempts if oid == object_id and p in self.patched]
