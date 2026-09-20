"""Query understanding: turn one search box string into a structured query.

This is the layer that replaces the prototype's "pick your query type" dropdown
(spec flaw #2). The user types one string; this decides what it means.

Supported syntax::

    raptor partnership              free text (hybrid: BM25 + vector)
    "hiding losses"                 quoted phrase (exact, on the .exact subfields)
    from:kenneth.lay@enron.com      address filter (exact term on the keyword field)
    from:"Kenneth Lay"              name filter (match on the .text subfield)
    to:x  cc:x  subject:x           further field operators
    before:2001-12-31 after:2001-07-01   date range

Safety (spec flaw #13): user input is never placed into a ``wildcard``,
``regexp``, ``query_string`` or ``simple_query_string`` query, so ``*``/``?`` and
regex metacharacters carry no special meaning anywhere downstream -- they are
just characters that the analyzer discards. Input length and term count are
capped so a pathological query cannot turn into a pathological ES request.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

MAX_QUERY_CHARS = 512
MAX_TERMS = 32
MAX_VALUES_PER_FIELD = 16

#: Fuzziness only applies to terms of 5+ characters. Elasticsearch's
#: ``AUTO:[low],[high]`` expresses exactly that in one clause: 0 edits below
#: ``low``, 1 edit up to ``high``, 2 above.
#: https://www.elastic.co/docs/reference/elasticsearch/rest-apis/common-options#fuzziness
FUZZINESS = "AUTO:5,8"
MIN_FUZZY_LEN = 5

_FIELD_OPS = frozenset({"from", "to", "cc", "subject", "before", "after"})
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def is_address(value: str) -> bool:
    """True when a from:/to:/cc: value should be matched as an exact address."""
    return "@" in value


@dataclass(frozen=True)
class ParsedQuery:
    raw: str
    text: str = ""
    terms: tuple[str, ...] = ()
    phrases: tuple[str, ...] = ()
    from_: tuple[str, ...] = ()
    to: tuple[str, ...] = ()
    cc: tuple[str, ...] = ()
    subject: tuple[str, ...] = ()
    after: date | None = None
    before: date | None = None
    warnings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def has_text(self) -> bool:
        return bool(self.terms or self.phrases)

    @property
    def has_filters(self) -> bool:
        return bool(self.from_ or self.to or self.cc or self.subject or self.after or self.before)

    @property
    def is_empty(self) -> bool:
        return not self.has_text and not self.has_filters

    @property
    def semantic_text(self) -> str:
        """Text handed to the embedding model: free text plus any quoted phrases."""
        return " ".join([*self.terms, *self.phrases]).strip()

    def fuzziness_for(self, term: str) -> str | None:
        return FUZZINESS if len(term) >= MIN_FUZZY_LEN else None


@dataclass
class _Token:
    field: str | None
    value: str
    quoted: bool


def _tokenize(raw: str) -> list[_Token]:
    """Split into (field, value, quoted) tokens, respecting quotes."""
    tokens: list[_Token] = []
    i, n = 0, len(raw)
    while i < n:
        if raw[i].isspace():
            i += 1
            continue

        # Optional leading "field:" prefix.
        name: str | None = None
        match = re.match(r"([A-Za-z_]+):", raw[i:])
        if match and match.group(1).lower() in _FIELD_OPS:
            name = match.group(1).lower()
            i += match.end()
            if i >= n or raw[i].isspace():
                tokens.append(_Token(name, "", False))
                continue

        if raw[i] == '"':
            close = raw.find('"', i + 1)
            if close == -1:  # unterminated quote: take the remainder
                tokens.append(_Token(name, raw[i + 1 :].strip(), True))
                break
            tokens.append(_Token(name, raw[i + 1 : close], True))
            i = close + 1
        else:
            j = i
            while j < n and not raw[j].isspace():
                j += 1
            tokens.append(_Token(name, raw[i:j], False))
            i = j
    return tokens


def _parse_date(value: str) -> date | None:
    if not _DATE_RE.match(value):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def parse(raw: str) -> ParsedQuery:
    """Parse a raw search box string. Never raises on user input."""
    original = raw or ""
    warnings: list[str] = []

    cleaned = _CONTROL.sub(" ", original)
    if len(cleaned) > MAX_QUERY_CHARS:
        cleaned = cleaned[:MAX_QUERY_CHARS]
        warnings.append(f"query truncated to {MAX_QUERY_CHARS} characters")

    if '"' in cleaned and cleaned.count('"') % 2 == 1:
        warnings.append("unbalanced quote; treated the remainder as a phrase")

    buckets: dict[str, list[str]] = {"from": [], "to": [], "cc": [], "subject": []}
    phrases: list[str] = []
    terms: list[str] = []
    after: date | None = None
    before: date | None = None

    for token in _tokenize(cleaned):
        value = token.value.strip()
        name = token.field

        if name is None:
            if not value:
                continue
            (phrases if token.quoted else terms).append(value)
            continue

        if not value:
            warnings.append(f"ignored empty {name}: operator")
            continue

        if name in ("before", "after"):
            parsed_date = _parse_date(value)
            if parsed_date is None:
                warnings.append(f"ignored {name}:{value} (expected YYYY-MM-DD)")
                continue
            if name == "after":
                after = parsed_date
            else:
                before = parsed_date
            continue

        bucket = buckets[name]
        if len(bucket) >= MAX_VALUES_PER_FIELD:
            warnings.append(f"ignored extra {name}: values beyond {MAX_VALUES_PER_FIELD}")
            continue
        bucket.append(value.lower() if name != "subject" else value)

    if after and before and after > before:
        warnings.append("after: is later than before:; the range matches nothing")

    if len(terms) > MAX_TERMS:
        terms = terms[:MAX_TERMS]
        warnings.append(f"only the first {MAX_TERMS} free-text terms were used")

    return ParsedQuery(
        raw=original,
        text=" ".join(terms),
        terms=tuple(terms),
        phrases=tuple(p for p in phrases if p),
        from_=tuple(buckets["from"]),
        to=tuple(buckets["to"]),
        cc=tuple(buckets["cc"]),
        subject=tuple(buckets["subject"]),
        after=after,
        before=before,
        warnings=tuple(warnings),
    )
