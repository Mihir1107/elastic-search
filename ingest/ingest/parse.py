"""Stage 2: parse maildir messages with Python's ``email`` stdlib.

Deliberately NOT string splitting (kickoff flaw #11). Extracts message ids,
threading headers, all recipient lists including CC/BCC, a UTC ISO-8601 date,
the subject, the body with quoted replies split into ``quoted_text``, the
mailbox owner / folder path, and any attachment names. Messages that cannot be
parsed, or whose date is unusable, are counted against a named reason and the
document is still kept where possible -- never silently dropped.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterator
from datetime import UTC
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import getaddresses, parsedate_to_datetime
from pathlib import Path
from typing import Any

from ingest.stats import StageStats

# Markers that begin a quoted/forwarded region in Enron mail. Conservative on
# purpose: a bare "From:" line is NOT treated as a marker because it appears in
# legitimate bodies and would truncate real content.
_QUOTE_MARKERS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^\s*-{2,}\s*Original Message\s*-{2,}", re.IGNORECASE),
    re.compile(r"^\s*-{2,}\s*Forwarded by\b", re.IGNORECASE),
    re.compile(r"^\s*_{10,}\s*$"),
    re.compile(r"^\s*On\b.{0,160}\bwrote:\s*$", re.IGNORECASE),
)

_RE_PREFIX = re.compile(r"^\s*(?:(?:re|fw|fwd|aw|sv)\s*:\s*)+", re.IGNORECASE)
_WS = re.compile(r"[ \t]+")


def split_quoted(body: str) -> tuple[str, str]:
    """Split a body into (new_text, quoted_text).

    The split point is the first quote marker line or the start of a contiguous
    run of ">"-prefixed lines, whichever comes first.
    """
    lines = body.splitlines()
    cut: int | None = None
    for i, line in enumerate(lines):
        if any(m.match(line) for m in _QUOTE_MARKERS):
            cut = i
            break
        if line.lstrip().startswith(">"):
            cut = i
            break
    if cut is None:
        return body.strip(), ""
    return "\n".join(lines[:cut]).strip(), "\n".join(lines[cut:]).strip()


def normalise_subject(subject: str) -> str:
    """Strip Re:/Fw:/Fwd: prefixes and collapse whitespace (for thread fallback)."""
    return _WS.sub(" ", _RE_PREFIX.sub("", subject or "")).strip()


def _addresses(msg: EmailMessage, header: str) -> tuple[list[str], list[str]]:
    """Return (addresses, display_names) for a header, tolerating malformed values."""
    raw = msg.get_all(header)
    if not raw:
        return [], []
    try:
        pairs = getaddresses([str(v) for v in raw])
    except (ValueError, TypeError):
        return [], []
    addrs = [a.strip() for _, a in pairs if a and "@" in a]
    names = [n.strip() for n, _ in pairs if n and n.strip()]
    return addrs, names


def _header(msg: EmailMessage, name: str) -> str:
    value = msg.get(name)
    return "" if value is None else str(value).strip()


def _parse_date(raw: str) -> tuple[str | None, str | None]:
    """Return (iso_utc, failure_reason)."""
    if not raw:
        return None, "date-missing"
    try:
        dt = parsedate_to_datetime(raw)
    except (TypeError, ValueError, IndexError):
        return None, "date-unparseable"
    if dt is None:
        return None, "date-unparseable"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).isoformat(), None


def _body_text(msg: EmailMessage) -> str:
    try:
        part = msg.get_body(preferencelist=("plain",))
        if part is not None:
            content = part.get_content()
            if isinstance(content, str):
                return content
    except (KeyError, LookupError, ValueError, TypeError):
        pass
    payload = msg.get_payload(decode=True)
    if isinstance(payload, bytes):
        return payload.decode("utf-8", errors="replace")
    raw = msg.get_payload()
    return raw if isinstance(raw, str) else ""


def _attachments(msg: EmailMessage) -> list[str]:
    names: list[str] = []
    try:
        for part in msg.iter_attachments():
            filename = part.get_filename()
            if filename:
                names.append(str(filename))
    except (AttributeError, ValueError, TypeError):
        return names
    return names


def parse_message(path: Path, maildir: Path) -> dict[str, Any]:
    """Parse one maildir file into a flat document. Raises on unreadable input."""
    with path.open("rb") as fh:
        msg = BytesParser(policy=policy.default).parse(fh)

    rel = path.relative_to(maildir)
    mailbox = rel.parts[0] if rel.parts else ""
    folder = "/".join(rel.parts[1:-1]) if len(rel.parts) > 2 else ""

    from_addrs, from_names = _addresses(msg, "From")
    to_addrs, _ = _addresses(msg, "To")
    cc_addrs, _ = _addresses(msg, "Cc")
    bcc_addrs, _ = _addresses(msg, "Bcc")

    date_iso, date_reason = _parse_date(_header(msg, "Date"))

    raw_body = _body_text(msg)
    body, quoted = split_quoted(raw_body)

    message_id = _header(msg, "Message-ID").strip("<>")
    in_reply_to = _header(msg, "In-Reply-To").strip("<>")
    references = [r.strip("<>") for r in _header(msg, "References").split() if r.strip("<>")]
    attachments = _attachments(msg)
    x_from = _header(msg, "X-From")

    return {
        "source_path": str(rel),
        "mailbox": mailbox,
        "folder": folder,
        "message_id": message_id,
        "in_reply_to": in_reply_to,
        "references": references,
        "from": from_addrs[0] if from_addrs else "",
        "from_name": x_from or (from_names[0] if from_names else ""),
        "to": to_addrs,
        "cc": cc_addrs,
        "bcc": bcc_addrs,
        "subject": _header(msg, "Subject"),
        "date": date_iso,
        "date_raw": _header(msg, "Date"),
        "body": body,
        "quoted_text": quoted,
        "has_attachment": bool(attachments),
        "attachment_names": attachments,
        "_date_reason": date_reason,
    }


def _mailbox_message_files(mailbox_dir: Path) -> list[Path]:
    return sorted(p for p in mailbox_dir.rglob("*") if p.is_file())


def select_message_files(maildir: Path, subset: str, target: int) -> list[Path]:
    """Deterministically select message files.

    ``full`` takes every mailbox. ``dev`` walks mailboxes in a stable
    hash-derived order (so the sample is not alphabetically biased) and keeps
    whole mailboxes until ``target`` messages are reached, truncating the last
    one so the count is exactly ``target``. Keeping mailboxes whole preserves the
    cross-mailbox duplicates and intra-mailbox threads that stages 4 and 5 exist
    to handle.
    """
    mailboxes = sorted(p for p in maildir.iterdir() if p.is_dir())
    if subset == "full":
        files: list[Path] = []
        for mb in mailboxes:
            files.extend(_mailbox_message_files(mb))
        return files

    ordered = sorted(mailboxes, key=lambda p: hashlib.sha1(p.name.encode()).hexdigest())
    selected: list[Path] = []
    for mb in ordered:
        if len(selected) >= target:
            break
        selected.extend(_mailbox_message_files(mb))
    return selected[:target]


def parse_all(maildir: Path, files: list[Path], stats: StageStats) -> Iterator[dict[str, Any]]:
    for path in files:
        try:
            doc = parse_message(path, maildir)
        except (OSError, ValueError, TypeError, IndexError, UnicodeError) as exc:
            stats.fail(f"parse-error:{type(exc).__name__}")
            continue
        reason = doc.pop("_date_reason", None)
        if reason:
            stats.skip(reason)  # kept, but the unusable date is counted
        if not doc["from"]:
            stats.skip("from-missing")
        if not doc["message_id"]:
            stats.skip("message-id-missing")
        stats.ok()
        yield doc


def run(maildir: Path, out_path: Path, subset: str, target: int) -> StageStats:
    from ingest.jsonl import write_jsonl

    stats = StageStats("parse")
    files = select_message_files(maildir, subset, target)
    stats.extra["subset"] = subset
    stats.extra["selected_files"] = len(files)
    stats.extra["mailboxes"] = sorted({f.relative_to(maildir).parts[0] for f in files})
    written = write_jsonl(out_path, parse_all(maildir, files, stats))
    stats.extra["written"] = written
    stats.extra["output"] = str(out_path)
    return stats


__all__ = [
    "normalise_subject",
    "parse_message",
    "run",
    "select_message_files",
    "split_quoted",
]
