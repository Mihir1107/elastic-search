"""Query-side embedding.

BGE retrieval is asymmetric: passages are embedded bare (that is what ingest
stored) while queries get an instruction prefix. Applying it only here is
DECISIONS D3. The model is loaded lazily so importing the app stays cheap.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

_lock = threading.Lock()
_model: SentenceTransformer | None = None

#: Bounds concurrent forward passes across the embedder and the reranker. torch
#: already spreads one pass over several cores; letting every request thread
#: start its own just makes them all slower. A threading (not asyncio)
#: semaphore, acquired inside the worker thread, so it never blocks the event
#: loop and is not tied to one loop.
_gate = threading.BoundedSemaphore(2)
_gate_size = 2
_gate_lock = threading.Lock()


def configure_cache(size: int) -> None:
    """Resize the query-vector cache (``Settings.embed_cache_size``)."""
    _vectors.size = max(0, size)


def configure_gate(size: int) -> None:
    """Resize the inference gate (called with ``Settings.model_concurrency``)."""
    global _gate, _gate_size
    size = max(1, size)
    with _gate_lock:
        if size != _gate_size:
            _gate, _gate_size = threading.BoundedSemaphore(size), size


def gated[T](fn: Callable[[], T]) -> T:
    """Run ``fn`` under the inference gate. Call from a worker thread."""
    with _gate:
        return fn()


class _LRU:
    """A small thread-safe LRU for query vectors."""

    def __init__(self, size: int) -> None:
        self.size = size
        self._data: OrderedDict[tuple[str, str, str], list[float]] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: tuple[str, str, str]) -> list[float] | None:
        with self._lock:
            value = self._data.get(key)
            if value is not None:
                self._data.move_to_end(key)
            return value

    def put(self, key: tuple[str, str, str], value: list[float]) -> None:
        with self._lock:
            self._data[key] = value
            self._data.move_to_end(key)
            while len(self._data) > self.size:
                self._data.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()


_vectors = _LRU(1024)


def get_model(name: str) -> SentenceTransformer:
    global _model
    with _lock:
        if _model is None:
            from sentence_transformers import SentenceTransformer

            _model = SentenceTransformer(name)
        return _model


def embed_query(text: str, model_name: str, prefix: str = "") -> list[float]:
    """The query's vector, from the cache when this exact text was seen recently.

    Paging, re-running and exporting a search all embed the same text again;
    the model is deterministic, so the vector can be reused.
    """
    key = (model_name, prefix, text)
    cached = _vectors.get(key)
    if cached is not None:
        return cached
    model = get_model(model_name)
    vector: Any = gated(
        lambda: model.encode(
            [f"{prefix}{text}"], normalize_embeddings=True, show_progress_bar=False
        )
    )
    result = [float(x) for x in vector[0]]
    _vectors.put(key, result)
    return result


def is_known_word(word: str, model_name: str) -> bool:
    """True when the model's vocabulary holds ``word`` as one whole token.

    A misspelling is split into sub-word pieces ("califronia" -> cal ##if
    ##ronia); a word the model learned is not. Spelling correction uses this to
    leave alone words the model represents, even when the corpus lacks them.
    """
    tokenizer = get_model(model_name).tokenizer
    return len(tokenizer.tokenize(word.lower())) == 1


def reset_cache() -> None:
    """Test hook."""
    global _model
    with _lock:
        _model = None
    _vectors.clear()
