"""Vector retrieval across one or more namespaces."""
from __future__ import annotations

from typing import Any, Iterable

from ..models import RetrievedChunk
from . import embed as embed_mod
from . import store as store_mod


def query(
    text: str,
    *,
    namespaces: Iterable[str],
    k_per_namespace: int = 4,
    filters: dict[str, dict[str, Any]] | None = None,
    embed_fn=None,
    client=None,
) -> list[RetrievedChunk]:
    """Retrieve `k_per_namespace` chunks from each namespace; merge into one list.

    `filters` is keyed by namespace and contains a Chroma `where` clause.
    Results are returned sorted by similarity descending.
    """
    embed_fn = embed_fn or embed_mod.embed_texts
    [vec] = embed_fn([text])
    chunks: list[RetrievedChunk] = []
    for ns in namespaces:
        where = (filters or {}).get(ns)
        rows = store_mod.query(
            ns,
            query_embedding=vec,
            k=k_per_namespace,
            where=where,
            client=client,
        )
        for r in rows:
            meta = dict(r.get("metadata") or {})
            chunks.append(
                RetrievedChunk(
                    text=r["document"],
                    source_path=meta.get("source_path") or r["id"],
                    namespace=ns,
                    metadata=meta,
                    similarity=float(r["similarity"]),
                )
            )
    chunks.sort(key=lambda c: c.similarity, reverse=True)
    return chunks
