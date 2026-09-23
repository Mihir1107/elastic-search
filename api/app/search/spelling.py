"""Spelling correction for the text the vector leg embeds.

BM25 survives a typo through fuzziness; the embedder does not. "califronia" is
an unknown word to the model and produces a vector near nothing useful, so the
vector leg -- and through RRF the fused list -- degrades on exactly the queries
fuzziness rescues.

The correction comes from Elasticsearch's term suggester, riding on the BM25
request (no extra round trip). Every choice below was measured on the query set
(DECISIONS D35), because each one blocks a failure that actually occurred:

* ``body.exact``, not ``body``. ``body`` uses the english analyzer, so its
  suggestions are stems ("energi", "crisi") -- worse input for the embedder
  than the typo -- and its stopword filter drops words.
* ``suggest_mode: missing``. Only words absent from the index are corrected.
  ``popular`` also rewrites correctly spelled words into commoner neighbours:
  "hiding" -> "hiring", "taking" -> "trading", "fastow" -> "factor".
* ``max_edits: 1``. A real word can be absent from this corpus too, and two
  edits reach far: "spiking" -> "speaking". Single-edit typos (a transposition
  counts as one) are the common case, and all eight typo queries are one.
* A word the embedding model already knows is left alone, whatever the index
  says: "crashing" is missing from the corpus and one edit from "crushing", but
  the model represents it perfectly well. The point is to protect the embedder
  from words it cannot represent, not to normalise vocabulary to the corpus.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from app.search.parser import MIN_FUZZY_LEN, ParsedQuery

SUGGEST_NAME = "spelling"
SUGGEST_FIELD = "body.exact"


@dataclass(frozen=True)
class Correction:
    original: str
    suggested: str
    offset: int
    length: int


def build_suggest(query: ParsedQuery) -> dict[str, Any] | None:
    """The ``suggest`` block for the BM25 request, or None when there is nothing to check."""
    if not query.terms:
        return None
    return {
        SUGGEST_NAME: {
            "text": query.text,
            "term": {
                "field": SUGGEST_FIELD,
                "suggest_mode": "missing",
                "max_edits": 1,
                # Same threshold as fuzziness: short words are too ambiguous.
                "min_word_length": MIN_FUZZY_LEN,
                "size": 1,
            },
        }
    }


def corrections(
    query: ParsedQuery,
    response: Mapping[str, Any],
    is_known_word: Callable[[str], bool] | None = None,
) -> list[Correction]:
    """Every token the suggester had a better spelling for, in query order.

    ``is_known_word`` vetoes a correction for a word the embedder already
    represents. A suggestion whose offsets do not line up with ``query.text``
    is dropped rather than trusted.
    """
    entries = (response.get("suggest") or {}).get(SUGGEST_NAME) or []
    out: list[Correction] = []
    for entry in entries:
        options = entry.get("options") or []
        if not options:
            continue
        start, length = int(entry["offset"]), int(entry["length"])
        original = query.text[start : start + length]
        # The analyzer lowercased the token; only replace what is actually there.
        if original.lower() != str(entry["text"]).lower():
            continue
        if is_known_word is not None and is_known_word(original):
            continue
        out.append(Correction(original, str(options[0]["text"]), start, length))
    return out


def corrected_text(query: ParsedQuery, fixes: list[Correction]) -> str:
    """The free text with each correction applied, phrases untouched.

    Replacement uses the suggester's offsets into ``query.text``, so everything
    the analyzer does not tokenise (punctuation, stopwords) survives verbatim.
    """
    text = query.text
    # Right to left, so an edit never shifts an offset still to be applied.
    for fix in sorted(fixes, key=lambda f: f.offset, reverse=True):
        text = text[: fix.offset] + fix.suggested + text[fix.offset + fix.length :]
    return " ".join([text, *query.phrases]).strip()
