"""Retrieval tests: ingest a fake KB, verify namespace + filter scoping."""
from __future__ import annotations

from asra_matcher.rag import ingest as ingest_mod
from asra_matcher.rag import retrieve as retrieve_mod


def test_ingest_counts_by_namespace(fake_kb_path, fake_embed, in_memory_chroma_client):
    counts = ingest_mod.ingest(
        rebuild=True,
        kb_path=fake_kb_path,
        embed_fn=fake_embed,
        client=in_memory_chroma_client,
    )
    # fake_kb has at least: 2 category docs, 1 tier doc, 1 software doc.
    assert counts["categories"] >= 2
    assert counts["tiers"] >= 1
    assert counts["software"] >= 1


def test_retrieve_respects_namespace_scope(fake_kb_path, fake_embed, in_memory_chroma_client):
    ingest_mod.ingest(
        rebuild=True,
        kb_path=fake_kb_path,
        embed_fn=fake_embed,
        client=in_memory_chroma_client,
    )
    chunks = retrieve_mod.query(
        "software engineering docker",
        namespaces=["categories"],
        k_per_namespace=2,
        embed_fn=fake_embed,
        client=in_memory_chroma_client,
    )
    assert chunks, "retrieval should return at least one chunk"
    for c in chunks:
        assert c.namespace == "categories"


def test_retrieve_respects_k(fake_kb_path, fake_embed, in_memory_chroma_client):
    ingest_mod.ingest(
        rebuild=True,
        kb_path=fake_kb_path,
        embed_fn=fake_embed,
        client=in_memory_chroma_client,
    )
    chunks = retrieve_mod.query(
        "tier",
        namespaces=["tiers"],
        k_per_namespace=1,
        embed_fn=fake_embed,
        client=in_memory_chroma_client,
    )
    assert len(chunks) <= 1


def test_retrieve_filter_by_category(fake_kb_path, fake_embed, in_memory_chroma_client):
    ingest_mod.ingest(
        rebuild=True,
        kb_path=fake_kb_path,
        embed_fn=fake_embed,
        client=in_memory_chroma_client,
    )
    chunks = retrieve_mod.query(
        "healthcare zoom",
        namespaces=["categories"],
        k_per_namespace=3,
        filters={"categories": {"category": "B"}},
        embed_fn=fake_embed,
        client=in_memory_chroma_client,
    )
    for c in chunks:
        assert c.metadata.get("category") == "B"
