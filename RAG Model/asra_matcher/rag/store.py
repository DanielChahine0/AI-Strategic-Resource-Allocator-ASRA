"""Chroma store wrapper. One persistent collection per logical namespace."""
from __future__ import annotations

import os
from collections.abc import Sequence
from typing import Any

NAMESPACES = ("categories", "tiers", "software", "policies", "decisions")


def _chroma_path() -> str:
    return os.environ.get("ASRA_CHROMA_PATH", "./chroma_db")


def _client(path: str | None = None):
    import chromadb  # type: ignore

    return chromadb.PersistentClient(path=path or _chroma_path())


def get_collection(namespace: str, *, client=None, embedding_function=None):
    """Return (or create) a Chroma collection for the given namespace."""
    if namespace not in NAMESPACES:
        raise ValueError(f"unknown namespace: {namespace}")
    cli = client or _client()
    # We supply our own embeddings, so no embedding_function is required.
    return cli.get_or_create_collection(
        name=f"asra_{namespace}",
        metadata={"hnsw:space": "cosine"},
    )


def upsert(
    namespace: str,
    *,
    ids: Sequence[str],
    documents: Sequence[str],
    embeddings: Sequence[Sequence[float]],
    metadatas: Sequence[dict[str, Any]],
    client=None,
) -> None:
    coll = get_collection(namespace, client=client)
    coll.upsert(
        ids=list(ids),
        documents=list(documents),
        embeddings=[list(e) for e in embeddings],
        metadatas=[_sanitize(m) for m in metadatas],
    )


def query(
    namespace: str,
    *,
    query_embedding: Sequence[float],
    k: int,
    where: dict[str, Any] | None = None,
    client=None,
) -> list[dict[str, Any]]:
    coll = get_collection(namespace, client=client)
    res = coll.query(
        query_embeddings=[list(query_embedding)],
        n_results=k,
        where=_sanitize(where) if where else None,
    )
    out: list[dict[str, Any]] = []
    ids = res.get("ids", [[]])[0]
    docs = res.get("documents", [[]])[0]
    metas = res.get("metadatas", [[]])[0]
    dists = res.get("distances", [[]])[0]
    for i, _id in enumerate(ids):
        out.append(
            {
                "id": _id,
                "document": docs[i] if i < len(docs) else "",
                "metadata": metas[i] if i < len(metas) else {},
                # Convert cosine distance → similarity in [0,1].
                "similarity": max(0.0, 1.0 - float(dists[i])) if i < len(dists) else 0.0,
                "namespace": namespace,
            }
        )
    return out


def count(namespace: str, *, client=None) -> int:
    return get_collection(namespace, client=client).count()


def reset_all(client=None) -> None:
    cli = client or _client()
    for ns in NAMESPACES:
        try:
            cli.delete_collection(name=f"asra_{ns}")
        except Exception:
            pass


def _sanitize(m: dict[str, Any] | None) -> dict[str, Any]:
    """Chroma metadata must be primitives. Stringify lists for the `tags` field."""
    if not m:
        return {}
    out: dict[str, Any] = {}
    for k, v in m.items():
        if v is None:
            continue
        if isinstance(v, (list, tuple)):
            out[k] = ",".join(str(x) for x in v)
        elif isinstance(v, (str, int, float, bool)):
            out[k] = v
        else:
            out[k] = str(v)
    return out
