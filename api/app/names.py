"""Human-readable display names for senders.

The corpus stores ``X-From`` verbatim, and in this dataset that header is often
not a name at all::

    Hall, Steve C. </O=ENRON/OU=NA/CN=RECIPIENTS/CN=SHALL>
    "Neeley, Myrna" <MNeeley@caiso.com>
    john.arnold@enron.com

Rendering that raw puts a Lotus Notes distinguished name in front of the user,
so the address part is dropped, quotes are removed, and "Last, First" is turned
round. Anything that still does not look like a name returns empty, which lets
the UI fall back to deriving one from the address.
"""

from __future__ import annotations

import re

_ANGLE = re.compile(r"<[^>]*>")
_WS = re.compile(r"\s+")
#: A leftover directory path or attribute assignment means it was never a name.
_NOT_A_NAME = re.compile(r"[=/@]")
MAX_NAME_CHARS = 64


def display_name(raw: str) -> str:
    """Best human name for a sender, or "" when there isn't one."""
    if not raw:
        return ""
    name = _ANGLE.sub(" ", str(raw))
    name = _WS.sub(" ", name).strip().strip('"').strip("'").strip()
    if not name or _NOT_A_NAME.search(name):
        return ""
    # "Hall, Steve C." reads better as "Steve C. Hall".
    if name.count(",") == 1:
        last, first = (part.strip() for part in name.split(","))
        if last and first:
            name = f"{first} {last}"
    return name[:MAX_NAME_CHARS]
