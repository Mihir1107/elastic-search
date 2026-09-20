"""Unit tests for the maildir parser (no Elasticsearch required)."""

from __future__ import annotations

from pathlib import Path

from ingest.parse import (
    normalise_subject,
    parse_message,
    select_message_files,
    split_quoted,
)

FULL_MESSAGE = """Message-ID: <1234567.1075855377439.JavaMail.evans@thyme>
Date: Mon, 14 May 2001 16:39:00 -0700 (PDT)
From: phillip.allen@enron.com
To: tim.belden@enron.com, john.doe@ENRON.com
Cc: Jeff.Skilling@enron.com
Bcc: ken.lay@enron.com
Subject: Re: Raptor partnership structure
Mime-Version: 1.0
Content-Type: text/plain; charset=us-ascii
X-From: Phillip K Allen
X-To: Tim Belden
X-Folder: \\Phillip_Allen_Dec2000\\Notes Folders\\Sent
X-Origin: Allen-P
X-FileName: pallen.nsf

Here is my read on the structure. We should discuss before the call.

-----Original Message-----
From: tim.belden@enron.com
Sent: Monday, May 14, 2001 9:00 AM
To: phillip.allen@enron.com
Subject: Raptor partnership structure

What do you think about the hedge?
"""

NO_DATE_NO_ID = """From: no.id@enron.com
To: someone@enron.com
Subject: Missing headers

Body without a message id or a date.
"""

BAD_DATE = """Message-ID: <bad-date@enron.com>
Date: not a real date
From: a@enron.com
To: b@enron.com
Subject: Bad date

Body here.
"""

LATIN1_BODY = (
    b"Message-ID: <latin1@enron.com>\r\n"
    b"Date: Tue, 15 May 2001 09:00:00 -0500 (CDT)\r\n"
    b"From: c@enron.com\r\nTo: d@enron.com\r\nSubject: Caf\xe9 meeting\r\n\r\n"
    b"Cost was 45\xa3 at the caf\xe9.\r\n"
)


def _write(maildir: Path, rel: str, content: str | bytes) -> Path:
    path = maildir / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")
    return path


def test_parses_all_recipient_lists_and_utc_date(tmp_path: Path) -> None:
    maildir = tmp_path / "maildir"
    path = _write(maildir, "allen-p/sent/1.", FULL_MESSAGE)
    doc = parse_message(path, maildir)

    assert doc["from"] == "phillip.allen@enron.com"
    # CC and BCC must survive (kickoff flaw #11: the prototype dropped CC).
    assert doc["to"] == ["tim.belden@enron.com", "john.doe@ENRON.com"]
    assert doc["cc"] == ["Jeff.Skilling@enron.com"]
    assert doc["bcc"] == ["ken.lay@enron.com"]
    assert doc["mailbox"] == "allen-p"
    assert doc["folder"] == "sent"
    assert doc["message_id"] == "1234567.1075855377439.JavaMail.evans@thyme"
    assert doc["from_name"] == "Phillip K Allen"
    # 16:39 -0700 == 23:39 UTC
    assert doc["date"] == "2001-05-14T23:39:00+00:00"


def test_quoted_reply_is_split_off_the_body(tmp_path: Path) -> None:
    maildir = tmp_path / "maildir"
    path = _write(maildir, "allen-p/sent/1.", FULL_MESSAGE)
    doc = parse_message(path, maildir)

    assert "Here is my read on the structure" in doc["body"]
    assert "Original Message" not in doc["body"]
    assert "What do you think about the hedge?" in doc["quoted_text"]


def test_missing_message_id_and_date_are_tolerated(tmp_path: Path) -> None:
    maildir = tmp_path / "maildir"
    path = _write(maildir, "doe-j/inbox/2.", NO_DATE_NO_ID)
    doc = parse_message(path, maildir)

    assert doc["message_id"] == ""
    assert doc["date"] is None
    assert doc["_date_reason"] == "date-missing"
    assert doc["body"].startswith("Body without a message id")


def test_unparseable_date_is_counted_not_fatal(tmp_path: Path) -> None:
    maildir = tmp_path / "maildir"
    path = _write(maildir, "doe-j/inbox/3.", BAD_DATE)
    doc = parse_message(path, maildir)

    assert doc["date"] is None
    assert doc["_date_reason"] in {"date-unparseable", "date-missing"}
    assert doc["subject"] == "Bad date"


def test_non_utf8_bytes_do_not_crash(tmp_path: Path) -> None:
    maildir = tmp_path / "maildir"
    path = _write(maildir, "doe-j/inbox/4.", LATIN1_BODY)
    doc = parse_message(path, maildir)
    assert isinstance(doc["body"], str)
    assert "meeting" in doc["subject"]


def test_split_quoted_handles_angle_bracket_quotes() -> None:
    body = "My reply here.\n\n> previous line one\n> previous line two"
    new, quoted = split_quoted(body)
    assert new == "My reply here."
    assert "previous line one" in quoted


def test_split_quoted_without_quotes_returns_empty_quote() -> None:
    new, quoted = split_quoted("Just a plain note.")
    assert new == "Just a plain note."
    assert quoted == ""


def test_normalise_subject_strips_reply_prefixes() -> None:
    assert normalise_subject("Re: Fwd: RE:  Raptor  deal") == "Raptor deal"
    assert normalise_subject("Plain") == "Plain"


def test_dev_subset_selection_is_deterministic_and_exact(tmp_path: Path) -> None:
    maildir = tmp_path / "maildir"
    for box in ("allen-p", "belden-t", "skilling-j", "lay-k"):
        for i in range(10):
            _write(maildir, f"{box}/inbox/{i}.", FULL_MESSAGE)

    first = select_message_files(maildir, "dev", 25)
    second = select_message_files(maildir, "dev", 25)
    assert len(first) == 25
    assert first == second, "dev subset must be reproducible"

    everything = select_message_files(maildir, "full", 25)
    assert len(everything) == 40


NOTES_DN = """Message-ID: <notes-dn@enron.com>
Date: Wed, 17 Oct 2001 18:32:27 -0000
From: jae.black@enron.com
To: /o=enron/ou=na/cn=recipients/cn=notesaddr/cn=a478079f-612229@enron.com,
\twilliam.abler@enron.com
Subject: FW: Operation Clean Sweep

Body.
"""


def test_lotus_notes_distinguished_names_are_not_dropped(tmp_path: Path) -> None:
    """getaddresses cannot parse X.400/Notes DNs; the recipient must still survive."""
    maildir = tmp_path / "maildir"
    path = _write(maildir, "forney-j/inbox/6.", NOTES_DN)
    doc = parse_message(path, maildir)

    assert "william.abler@enron.com" in doc["to"]
    recovered = [a for a in doc["to"] if "a478079f-612229@enron.com" in a]
    assert recovered, f"Notes DN recipient was dropped: {doc['to']}"
