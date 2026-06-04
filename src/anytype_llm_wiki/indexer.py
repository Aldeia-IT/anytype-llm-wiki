"""Incremental indexer: Anytype → chunks → embeddings → Qdrant."""

import json
import uuid
from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from . import config
from .anytype_client import get_object, list_objects, list_spaces
from .chunker import chunk_object
from .embedder import embed


def _qdrant() -> QdrantClient:
    return QdrantClient(url=config.QDRANT_URL, api_key=config.QDRANT_API_KEY or None)


def _ensure_collection(client: QdrantClient) -> None:
    collections = [c.name for c in client.get_collections().collections]
    if config.QDRANT_COLLECTION not in collections:
        client.create_collection(
            collection_name=config.QDRANT_COLLECTION,
            vectors_config=VectorParams(size=config.EMBED_DIMS, distance=Distance.COSINE),
        )


def _load_state() -> dict:
    if config.INDEX_STATE_FILE.exists():
        return json.loads(config.INDEX_STATE_FILE.read_text())
    return {}


def _save_state(state: dict) -> None:
    config.INDEX_STATE_DIR.mkdir(parents=True, exist_ok=True)
    config.INDEX_STATE_FILE.write_text(json.dumps(state, indent=2))


def _get_last_modified(obj: dict) -> str | None:
    """Extract last_modified_date from object properties."""
    for prop in obj.get("properties", []):
        if prop.get("key") == "last_modified_date":
            return prop.get("date")
    return None


def reindex(space_id: str | None = None) -> dict:
    """Run incremental reindex. Returns stats."""
    client = _qdrant()
    _ensure_collection(client)
    state = _load_state()

    spaces = list_spaces() if not space_id else [{"id": space_id}]
    stats = {"spaces": 0, "objects_checked": 0, "objects_indexed": 0, "objects_removed": 0, "chunks": 0}

    for space in spaces:
        sid = space["id"]
        stats["spaces"] += 1
        space_state = state.get(sid, {})
        objects = list_objects(sid)
        current_ids = set()

        for obj_summary in objects:
            oid = obj_summary["id"]
            current_ids.add(oid)
            stats["objects_checked"] += 1

            last_mod = _get_last_modified(obj_summary) or "unknown"
            if space_state.get(oid) == last_mod:
                continue  # unchanged

            # Fetch full object with markdown
            obj = get_object(sid, oid)
            chunks = chunk_object(obj)

            if not chunks:
                continue

            # Delete old vectors for this object
            _delete_object_vectors(client, oid)

            # Embed and upsert
            texts = [c["text"] for c in chunks]
            vectors = embed(texts)

            points = [
                PointStruct(
                    id=str(
                        uuid.uuid5(
                            uuid.NAMESPACE_URL,
                            f"{chunk['object_id']}:{i}:{chunk['heading']}",
                        )
                    ),
                    vector=vec,
                    payload={
                        "object_id": chunk["object_id"],
                        "space_id": chunk["space_id"],
                        "object_name": chunk["object_name"],
                        "type_key": chunk["type_key"],
                        "heading": chunk["heading"],
                        "text": chunk["text"],
                    },
                )
                for i, (chunk, vec) in enumerate(zip(chunks, vectors))
            ]

            client.upsert(collection_name=config.QDRANT_COLLECTION, points=points)
            space_state[oid] = last_mod
            stats["objects_indexed"] += 1
            stats["chunks"] += len(points)

        # Remove vectors for deleted objects
        removed_ids = set(space_state.keys()) - current_ids
        for oid in removed_ids:
            _delete_object_vectors(client, oid)
            del space_state[oid]
            stats["objects_removed"] += 1

        state[sid] = space_state

    _save_state(state)
    return stats


def reembed_object(space_id: str, object_id: str, obj: dict) -> dict:
    """Force a re-embed of a single object (V2-fail bypass / update path).

    Object-scoped: delete the object's existing Qdrant points by object_id,
    then re-chunk + embed + upsert. O(1) in corpus size.
    """
    client = _qdrant()
    _ensure_collection(client)

    chunks = chunk_object(obj)
    _delete_object_vectors(client, object_id)

    if not chunks:
        return {"object_id": object_id, "chunks": 0}

    texts = [c["text"] for c in chunks]
    vectors = embed(texts)

    points = [
        PointStruct(
            id=str(
                uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"{chunk['object_id']}:{i}:{chunk['heading']}",
                )
            ),
            vector=vec,
            payload={
                "object_id": chunk["object_id"],
                "space_id": chunk["space_id"],
                "object_name": chunk["object_name"],
                "type_key": chunk["type_key"],
                "heading": chunk["heading"],
                "text": chunk["text"],
            },
        )
        for i, (chunk, vec) in enumerate(zip(chunks, vectors))
    ]

    client.upsert(collection_name=config.QDRANT_COLLECTION, points=points)
    return {"object_id": object_id, "chunks": len(points)}


def _delete_object_vectors(client: QdrantClient, object_id: str) -> None:
    """Delete all vectors belonging to an object."""
    from qdrant_client.models import FieldCondition, Filter, MatchValue

    client.delete(
        collection_name=config.QDRANT_COLLECTION,
        points_selector=Filter(
            must=[FieldCondition(key="object_id", match=MatchValue(value=object_id))]
        ),
    )
