"""Local cross-encoder reranking.

Runs in this process, never through Elasticsearch's ``text_similarity_reranker``
retriever, which the prototype found returns 403 on a Basic licence (spec
flaw #5 and section 4). A cross-encoder scores the (query, document) pair
jointly rather than comparing two independent embeddings, which is more accurate
and much more expensive -- hence it only rescores the top of the fused list, and
its latency is reported as its own number so it can never hide inside the total.
"""

from __future__ import annotations

import threading
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from app.search.fusion import FusedHit

if TYPE_CHECKING:
    from sentence_transformers import CrossEncoder

_lock = threading.Lock()
_model: CrossEncoder | None = None

#: Cross-encoders truncate; keep the pair well inside the model's window.
MAX_DOC_CHARS = 1200
MAX_LENGTH = 512


def get_reranker(name: str) -> CrossEncoder:
    global _model
    with _lock:
        if _model is None:
            from sentence_transformers import CrossEncoder

            _model = CrossEncoder(name, max_length=MAX_LENGTH)
        return _model


def reset_cache() -> None:
    """Test hook."""
    global _model
    with _lock:
        _model = None


def document_text(hit: FusedHit) -> str:
    """What the cross-encoder reads: subject plus the most relevant text we have."""
    source = hit.source
    subject = str(source.get("subject") or "").strip()
    body = hit.chunk or str(source.get("body") or "")
    body = " ".join(body.split())[:MAX_DOC_CHARS]
    return f"{subject}\n{body}".strip()


def rerank(
    query_text: str,
    hits: Sequence[FusedHit],
    model_name: str,
    window: int,
) -> list[FusedHit]:
    """Rescore the top ``window`` hits; anything past the window keeps its place.

    Returns a new list. Scores are replaced by the cross-encoder score, and the
    ordering below the window is preserved so pagination past it stays stable.
    """
    head = list(hits[:window])
    tail = list(hits[window:])
    if not head or not query_text.strip():
        return list(hits)

    model = get_reranker(model_name)
    pairs = [(query_text, document_text(hit)) for hit in head]
    scores: Any = model.predict(pairs, show_progress_bar=False)

    for hit, score in zip(head, scores, strict=True):
        hit.score = float(score)
    head.sort(key=lambda h: (-h.score, h.doc_id))
    return head + tail
