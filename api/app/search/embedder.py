"""Query-side embedding.

BGE retrieval is asymmetric: passages are embedded bare (that is what ingest
stored) while queries get an instruction prefix. Applying it only here is
DECISIONS D3. The model is loaded lazily so importing the app stays cheap.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

_lock = threading.Lock()
_model: SentenceTransformer | None = None


def get_model(name: str) -> SentenceTransformer:
    global _model
    with _lock:
        if _model is None:
            from sentence_transformers import SentenceTransformer

            _model = SentenceTransformer(name)
        return _model


def embed_query(text: str, model_name: str, prefix: str = "") -> list[float]:
    model = get_model(model_name)
    vector: Any = model.encode(
        [f"{prefix}{text}"], normalize_embeddings=True, show_progress_bar=False
    )
    return [float(x) for x in vector[0]]


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
