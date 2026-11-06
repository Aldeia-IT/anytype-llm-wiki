"""Repair of the chain relations stored before typed links (Aldeia-IT/aldeia-box#1486).

STUB: signatures only, every body raises ``NotImplementedError``.
"""

from __future__ import annotations


def classify_space(objects: list[dict]) -> dict:
    """Classify a space ``ingest-only``, ``mixed`` or ``unknown`` from read-only evidence."""
    raise NotImplementedError("not implemented")


def plan_chain_repair(space_id: str) -> dict:
    """Read-only plan: classification, per-object relation ids to clear, digest."""
    raise NotImplementedError("not implemented")


def apply_chain_repair(space_id: str, *, expect_digest: str) -> dict:
    """Clear the planned ids; refuses a non-ingest-only space or a digest mismatch."""
    raise NotImplementedError("not implemented")
