"""Walk the kb/ folder, chunk markdown, embed, and write to Chroma. Idempotent."""
from __future__ import annotations

import hashlib
import os
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import yaml

from . import embed as embed_mod
from . import store as store_mod

CHUNK_TOKENS = 400
OVERLAP_TOKENS = 50
# Rough token approximation: 1 token ≈ 4 chars of English. Cheap, deterministic,
# avoids a tiktoken-style dependency.
_CHARS_PER_TOKEN = 4
CHUNK_CHARS = CHUNK_TOKENS * _CHARS_PER_TOKEN
OVERLAP_CHARS = OVERLAP_TOKENS * _CHARS_PER_TOKEN


@dataclass(frozen=True)
class Chunk:
    id: str
    text: str
    namespace: str
    metadata: dict
    hash: str


def _kb_path() -> Path:
    return Path(os.environ.get("ASRA_KB_PATH", "./kb")).resolve()


_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    meta = yaml.safe_load(m.group(1)) or {}
    body = m.group(2)
    return meta, body


def _split_sections(body: str) -> list[str]:
    """Split on top-level `##` headers; keep short docs as a single section."""
    parts = re.split(r"\n(?=## )", body)
    return [p.strip() for p in parts if p.strip()]


def _chunk_section(section: str) -> list[str]:
    if len(section) <= CHUNK_CHARS:
        return [section]
    chunks: list[str] = []
    start = 0
    while start < len(section):
        end = min(len(section), start + CHUNK_CHARS)
        chunks.append(section[start:end])
        if end == len(section):
            break
        start = end - OVERLAP_CHARS
        if start < 0:
            start = 0
    return chunks


def _hash(text: str, meta: dict) -> str:
    h = hashlib.sha256()
    h.update(text.encode("utf-8"))
    h.update(repr(sorted(meta.items())).encode("utf-8"))
    return h.hexdigest()[:16]


def _summary_chunk(meta: dict, body: str) -> str | None:
    """The first paragraph (≤ 80 words) acts as the embed-able summary."""
    paragraphs = re.split(r"\n\s*\n", body.strip(), maxsplit=1)
    if not paragraphs:
        return None
    first = paragraphs[0].strip()
    if not first or first.startswith("#"):
        return None
    return first


def discover_files(kb_path: Path | None = None) -> list[Path]:
    p = kb_path or _kb_path()
    return sorted(p.rglob("*.md"))


def build_chunks(files: Iterable[Path], kb_root: Path) -> list[Chunk]:
    chunks: list[Chunk] = []
    for f in files:
        raw = f.read_text(encoding="utf-8")
        meta, body = _parse_frontmatter(raw)
        namespace = meta.get("namespace")
        if namespace not in store_mod.NAMESPACES:
            # Skip docs without a recognized namespace.
            continue
        rel = str(f.relative_to(kb_root))
        common_meta = {
            "source_path": rel,
            "namespace": namespace,
            "category": meta.get("category"),
            "tier": meta.get("tier"),
            "tags": meta.get("tags"),
            "synthetic": meta.get("synthetic", False),
            "last_reviewed": meta.get("last_reviewed"),
        }
        # 1. Summary chunk (acts as the primary handle for retrieval).
        summary = _summary_chunk(meta, body)
        if summary:
            sm = dict(common_meta)
            sm["chunk_kind"] = "summary"
            sm["chunk_index"] = 0
            chunks.append(
                Chunk(
                    id=f"{rel}::summary",
                    text=summary,
                    namespace=namespace,
                    metadata=sm,
                    hash=_hash(summary, sm),
                )
            )
        # 2. Section chunks.
        sections = _split_sections(body)
        idx = 1
        for section in sections:
            for piece in _chunk_section(section):
                if not piece.strip():
                    continue
                m = dict(common_meta)
                m["chunk_kind"] = "section"
                m["chunk_index"] = idx
                chunks.append(
                    Chunk(
                        id=f"{rel}::s{idx}",
                        text=piece,
                        namespace=namespace,
                        metadata=m,
                        hash=_hash(piece, m),
                    )
                )
                idx += 1
    return chunks


def ingest(
    *,
    rebuild: bool = False,
    kb_path: Path | None = None,
    embed_fn=None,
    client=None,
) -> dict[str, int]:
    """Ingest all kb/*.md files into Chroma. Returns counts per namespace.

    Parameters
    ----------
    rebuild:
        If True, wipe all collections before ingesting.
    embed_fn:
        Override for the embedding function (used by tests).
    client:
        Override Chroma client (used by tests for an in-memory client).
    """
    kb_root = (kb_path or _kb_path()).resolve()
    files = discover_files(kb_root)
    chunks = build_chunks(files, kb_root)

    if rebuild:
        store_mod.reset_all(client=client)

    embed_fn = embed_fn or embed_mod.embed_documents

    # Group by namespace.
    by_ns: dict[str, list[Chunk]] = {ns: [] for ns in store_mod.NAMESPACES}
    for c in chunks:
        by_ns[c.namespace].append(c)

    counts: dict[str, int] = {}
    for ns, ns_chunks in by_ns.items():
        if not ns_chunks:
            counts[ns] = 0
            continue
        # Idempotency: only re-embed chunks whose hash changed.
        coll = store_mod.get_collection(ns, client=client)
        existing = {}
        try:
            got = coll.get(ids=[c.id for c in ns_chunks], include=["metadatas"])
            for i, _id in enumerate(got.get("ids", [])):
                meta = got.get("metadatas", [])[i] or {}
                existing[_id] = meta.get("content_hash")
        except Exception:
            existing = {}
        to_embed = [c for c in ns_chunks if existing.get(c.id) != c.hash]
        if to_embed:
            vectors = embed_fn([c.text for c in to_embed])
            metas = []
            for c in to_embed:
                m = dict(c.metadata)
                m["content_hash"] = c.hash
                metas.append(m)
            store_mod.upsert(
                ns,
                ids=[c.id for c in to_embed],
                documents=[c.text for c in to_embed],
                embeddings=vectors,
                metadatas=metas,
                client=client,
            )
        counts[ns] = len(ns_chunks)
    return counts
