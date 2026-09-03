"""Deterministic, domain-independent identities adapted from generic graph ideas."""

from __future__ import annotations

from uuid import UUID, uuid5


_NAMESPACE = UUID("8f87b47c-c46f-4bcf-9404-b53674377058")


def stable_id(kind: str, authority: str, external_id: str) -> str:
    """Return an opaque stable ID without exposing a storage primary key."""

    material = "\x00".join((kind.strip().lower(), authority.strip().lower(), external_id.strip()))
    return f"{kind.strip().lower()}:{uuid5(_NAMESPACE, material)}"


def stable_relationship_id(
    relation_type: str,
    source_id: str,
    target_id: str,
    discriminator: str = "",
) -> str:
    """Identify a relationship independently of mutable evidence or metadata."""

    material = "\x00".join((relation_type, source_id, target_id, discriminator))
    return f"relationship:{uuid5(_NAMESPACE, material)}"

