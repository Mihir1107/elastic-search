"""Stage 6: chunk bodies and compute chunk vectors.

Resumable by design (docs/SPEC.md section 4), without letting a re-run serve stale
data. Vectors are the expensive part, so they are reused -- but only for a document
whose embeddable text is unchanged, and every output row is rebuilt from the fresh
input, so a changed ``thread_id`` or a repaired body always flows through. The run
writes to ``<out>.partial``, which replaces the output only on completion; an
interrupted run resumes from it. (Earlier the stage skipped any id already in the
output, so re-running the pipeline silently kept old threads and old text: D33, D36.)

Chunking uses the embedding model's own tokenizer (~200 tokens with overlap)
because BAAI/bge-small-en-v1.5 truncates around 512 tokens -- embedding a whole
body would silently discard most of a long email (spec flaw #10). Batched
encoding replaces the prototype's per-document update loop (flaw #9).

Passage vectors are stored WITHOUT the BGE instruction prefix; that prefix is
applied to the QUERY side only at search time (DECISIONS D3).
"""

from __future__ import annotations

import hashlib
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


def _text_fingerprint(doc: dict[str, Any], settings: IngestSettings) -> str:
    """What the vectors depend on: the text and every setting that shapes the chunks."""
    key = [
        embeddable_text(doc),
        settings.embed_model,
        settings.chunk_tokens,
        settings.chunk_overlap,
        settings.max_chunks,
    ]
    return hashlib.sha1(json.dumps(key).encode("utf-8")).hexdigest()


def _row_fingerprint(doc: dict[str, Any]) -> str:
    """The whole input document, so a resumed run redoes rows whose input changed."""
    fields = {k: v for k, v in doc.items() if k != "chunks"}
    return hashlib.sha1(json.dumps(fields, sort_keys=True, default=str).encode()).hexdigest()


def _index_previous(path: Path, settings: IngestSettings) -> dict[str, tuple[int, str]]:
    """id -> (byte offset, text fingerprint) for each row of a previous output.

    Offsets rather than rows: the full vector file does not fit comfortably in
    memory, and only the rows being reused are ever read back.
    """
    found: dict[str, tuple[int, str]] = {}
    if not path.exists():
        return found
    with path.open("rb") as handle:
        offset = handle.tell()
        for line in iter(handle.readline, b""):
            if line.strip():
                row = json.loads(line)
                found[str(row.get("id"))] = (offset, _text_fingerprint(row, settings))
            offset = handle.tell()
    return found


def run(
    in_path: Path,
    out_path: Path,
    settings: IngestSettings,
    docs: Iterable[dict[str, Any]] | None = None,
) -> StageStats:
    from ingest.jsonl import read_jsonl

    stats = StageStats("embed")
    source = docs if docs is not None else read_jsonl(in_path)

    partial = out_path.with_name(out_path.name + ".partial")
    # Rows already written by an interrupted run of this same input.
    done: dict[str, str] = {}
    if partial.exists():
        for row in read_jsonl(partial):
            done[str(row.get("id"))] = _row_fingerprint(row)
    previous = _index_previous(out_path, settings)
    reused = 0

    model = load_model(settings.embed_model)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    previous_handle = out_path.open("rb") if previous else None

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

    with partial.open("a", encoding="utf-8") as handle:
        for doc in source:
            doc_id = str(doc.get("id"))
            if done.get(doc_id) == _row_fingerprint(doc):
                stats.skip("already-written")
                continue
            hit = previous.get(doc_id)
            if hit and previous_handle and hit[1] == _text_fingerprint(doc, settings):
                previous_handle.seek(hit[0])
                old = json.loads(previous_handle.readline())
                # Fresh metadata, reused vectors: only the text decides the vectors.
                handle.write(
                    json.dumps(
                        {**doc, "chunks": old.get("chunks") or []}, ensure_ascii=False, default=str
                    )
                    + "\n"
                )
                reused += 1
                stats.ok()
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

    if previous_handle:
        previous_handle.close()
    partial.replace(out_path)
    stats.extra["vectors_reused"] = reused
    stats.extra["model"] = settings.embed_model
    stats.extra["dims"] = settings.embed_dims
    stats.extra["chunks_written"] = total_chunks
    stats.extra["output"] = str(out_path)
    return stats
