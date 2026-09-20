"""Stage 6: chunk bodies and compute chunk vectors.

Resumable by design (docs/SPEC.md section 4): vectors are appended to the output as
they are produced and a resumed run skips ids already present, so a long
full-corpus run can be interrupted and continued.

Chunking uses the embedding model's own tokenizer (~200 tokens with overlap)
because BAAI/bge-small-en-v1.5 truncates around 512 tokens -- embedding a whole
body would silently discard most of a long email (spec flaw #10). Batched
encoding replaces the prototype's per-document update loop (flaw #9).

Passage vectors are stored WITHOUT the BGE instruction prefix; that prefix is
applied to the QUERY side only at search time (DECISIONS D3).
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ingest.config import IngestSettings
from ingest.stats import StageStats

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

_VECTOR_PRECISION = 6


def load_model(name: str) -> SentenceTransformer:
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(name)


def chunk_text(
    model: SentenceTransformer,
    text: str,
    chunk_size: int,
    overlap: int,
    max_chunks: int,
) -> list[str]:
    """Split text into overlapping ~chunk_size token windows using the model tokenizer."""
    if not text.strip():
        return []
    tokenizer = model.tokenizer
    ids = tokenizer.encode(text, add_special_tokens=False)
    if not ids:
        return []
    stride = max(1, chunk_size - overlap)
    chunks: list[str] = []
    for start in range(0, len(ids), stride):
        window = ids[start : start + chunk_size]
        if not window:
            break
        piece = tokenizer.decode(window, skip_special_tokens=True).strip()
        if piece:
            chunks.append(piece)
        if len(chunks) >= max_chunks or start + chunk_size >= len(ids):
            break
    return chunks


def embeddable_text(doc: dict[str, Any]) -> str:
    subject = str(doc.get("subject") or "").strip()
    body = str(doc.get("body") or "").strip()
    if subject and body:
        return f"{subject}\n\n{body}"
    return body or subject


def run(
    in_path: Path,
    out_path: Path,
    settings: IngestSettings,
    docs: Iterable[dict[str, Any]] | None = None,
) -> StageStats:
    from ingest.jsonl import read_jsonl

    stats = StageStats("embed")
    source = docs if docs is not None else read_jsonl(in_path)

    done: set[str] = set()
    if out_path.exists():
        for row in read_jsonl(out_path):
            done.add(str(row.get("id")))
        if done:
            stats.skip("already-embedded", len(done))

    model = load_model(settings.embed_model)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    pending: list[dict[str, Any]] = []
    chunk_counts: list[int] = []
    texts: list[str] = []
    total_chunks = 0

    def flush(handle: Any) -> None:
        nonlocal total_chunks
        if not pending:
            return
        vectors: Any = (
            model.encode(
                texts,
                batch_size=settings.embed_batch_size,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
            if texts
            else []
        )
        cursor = 0
        for doc, n in zip(pending, chunk_counts, strict=True):
            chunks = []
            for i in range(n):
                vec = [round(float(x), _VECTOR_PRECISION) for x in vectors[cursor + i]]
                chunks.append({"text": texts[cursor + i], "vector": vec})
            cursor += n
            doc["chunks"] = chunks
            total_chunks += n
            handle.write(json.dumps(doc, ensure_ascii=False, default=str) + "\n")
        handle.flush()
        pending.clear()
        chunk_counts.clear()
        texts.clear()

    with out_path.open("a", encoding="utf-8") as handle:
        for doc in source:
            doc_id = str(doc.get("id"))
            if doc_id in done:
                continue
            pieces = chunk_text(
                model,
                embeddable_text(doc),
                settings.chunk_tokens,
                settings.chunk_overlap,
                settings.max_chunks,
            )
            if not pieces:
                stats.skip("no-embeddable-text")
                doc["chunks"] = []
                handle.write(json.dumps(doc, ensure_ascii=False, default=str) + "\n")
                stats.ok()
                continue
            pending.append(doc)
            chunk_counts.append(len(pieces))
            texts.extend(pieces)
            stats.ok()
            if len(pending) >= 64:
                flush(handle)
        flush(handle)

    stats.extra["model"] = settings.embed_model
    stats.extra["dims"] = settings.embed_dims
    stats.extra["chunks_written"] = total_chunks
    stats.extra["output"] = str(out_path)
    return stats
