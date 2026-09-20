"""Spot-check parsed documents against their raw maildir files.

Phase 1 gate: verify parsed output against the source. The raw-side extraction
here is deliberately naive and INDEPENDENT of ingest.parse -- comparing the
parser against itself would prove nothing.

Usage: uv run python scripts/spotcheck.py [N]
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ingest"))

from ingest.config import get_settings

_ADDR = re.compile(r"[\w.\-+']+@[\w.\-]+")


def raw_headers(path: Path) -> dict[str, str]:
    """Crude header split: everything before the first blank line."""
    raw = path.read_bytes().decode("utf-8", errors="replace")
    head, _, _ = raw.partition("\n\n")
    headers: dict[str, str] = {}
    current = ""
    for line in head.splitlines():
        if line[:1] in (" ", "\t") and current:
            headers[current] += " " + line.strip()
            continue
        key, sep, value = line.partition(":")
        if sep:
            current = key.strip().lower()
            headers[current] = value.strip()
    return headers


def raw_body(path: Path) -> str:
    raw = path.read_bytes().decode("utf-8", errors="replace")
    _, _, body = raw.partition("\n\n")
    return body


def check(doc: dict[str, object], maildir: Path) -> list[str]:
    problems: list[str] = []
    path = maildir / str(doc["source_path"])
    if not path.exists():
        return [f"source file missing: {path}"]
    headers = raw_headers(path)

    raw_from = set(_ADDR.findall(headers.get("from", "")))
    if doc["from"] and str(doc["from"]).lower() not in {a.lower() for a in raw_from}:
        problems.append(f"from {doc['from']!r} not in raw From {sorted(raw_from)}")

    for field, header in (("to", "to"), ("cc", "cc"), ("bcc", "bcc")):
        raw_addrs = {a.lower() for a in _ADDR.findall(headers.get(header, ""))}
        parsed = {str(a).lower() for a in (doc.get(field) or [])}  # type: ignore[union-attr]
        missing = raw_addrs - parsed
        if missing:
            problems.append(f"{field}: raw has {sorted(missing)} not in parsed")

    raw_subject = " ".join(headers.get("subject", "").split())
    if raw_subject != " ".join(str(doc.get("subject") or "").split()):
        problems.append(f"subject mismatch: raw={raw_subject!r} parsed={doc.get('subject')!r}")

    if headers.get("date") and not doc.get("date"):
        problems.append(f"raw Date {headers['date']!r} but parsed date is null")

    if headers.get("message-id", "").strip("<>") != str(doc.get("message_id") or ""):
        problems.append("message_id mismatch")

    # Body + quoted_text should together account for the raw body's first line.
    combined = f"{doc.get('body') or ''}\n{doc.get('quoted_text') or ''}"
    first = next((ln.strip() for ln in raw_body(path).splitlines() if ln.strip()), "")
    if first and first not in combined:
        problems.append(f"first body line missing from body+quoted: {first[:60]!r}")
    return problems


def main() -> int:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    settings = get_settings()
    parsed_path = settings.parsed_path
    if not parsed_path.exists():
        print(f"no parsed output at {parsed_path}; run 'make ingest-dev' first")
        return 2

    rows = [json.loads(line) for line in parsed_path.read_text().splitlines() if line.strip()]
    if not rows:
        print("parsed.jsonl is empty")
        return 2

    step = max(1, len(rows) // n)
    sample = rows[::step][:n]

    failures = 0
    for i, doc in enumerate(sample, 1):
        problems = check(doc, settings.maildir)
        status = "OK  " if not problems else "FAIL"
        if problems:
            failures += 1
        print(f"{status} [{i:>2}] {doc['source_path']}")
        print(
            f"        from={doc['from']!r} to={len(doc.get('to') or [])} "
            f"cc={len(doc.get('cc') or [])} bcc={len(doc.get('bcc') or [])} "
            f"date={doc.get('date')} subject={str(doc.get('subject'))[:48]!r}"
        )
        for problem in problems:
            print(f"        - {problem}")

    print(f"\nspot-check: {len(sample) - failures}/{len(sample)} documents match their raw source")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
