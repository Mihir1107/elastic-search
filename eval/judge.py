"""Relevance judgments: objective auto-grading plus qrels storage.

Graded 0-3. Where relevance is derivable from the document itself -- a known
phrase, a sender, a date window -- it is graded by rule, which is reproducible
and not a matter of opinion. Conceptual queries carry no rule and are left for a
human to label; ``evaluate_run`` skips unjudged queries rather than scoring them
zero, so an unlabelled query never silently penalises a method.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

GRADE_MIN, GRADE_MAX = 0, 3


@dataclass(frozen=True)
class Judgment:
    query_id: str
    doc_id: str
    grade: int
    source: str  # "auto:<kind>", "llm" (pending human review) or "human"

    def to_dict(self) -> dict[str, Any]:
        return {
            "query_id": self.query_id,
            "doc_id": self.doc_id,
            "grade": self.grade,
            "source": self.source,
        }


def _text_of(doc: Mapping[str, Any]) -> str:
    return f"{doc.get('subject') or ''}\n{doc.get('body') or ''}".lower()


def _date_of(doc: Mapping[str, Any]) -> date | None:
    raw = str(doc.get("date") or "")[:10]
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def _filter_matches(rule: Mapping[str, Any], doc: Mapping[str, Any]) -> bool:
    if "from" in rule and str(doc.get("from") or "").lower() != str(rule["from"]).lower():
        return False
    if "to" in rule:
        recipients = {str(a).lower() for a in (doc.get("to") or [])}
        if str(rule["to"]).lower() not in recipients:
            return False
    if "after" in rule or "before" in rule:
        when = _date_of(doc)
        if when is None:
            return False
        if "after" in rule and when < date.fromisoformat(str(rule["after"])):
            return False
        if "before" in rule and when > date.fromisoformat(str(rule["before"])):
            return False
    return True


def auto_grade(rule: Mapping[str, Any], doc: Mapping[str, Any]) -> int:
    """Apply an objective grading rule to a document. Returns 0-3."""
    kind = str(rule.get("kind", ""))
    text = _text_of(doc)

    if kind == "phrase":
        return 3 if str(rule["phrase"]).lower() in text else 0

    if kind == "filter":
        return 3 if _filter_matches(rule, doc) else 0

    if kind == "terms":
        terms = [str(t).lower() for t in rule.get("terms", [])]
        hits = sum(1 for t in terms if t in text)
        if not terms or hits == 0:
            return 0
        return 3 if hits == len(terms) else 2

    if kind == "both":
        if not _filter_matches(rule, doc):
            return 0
        terms = [str(t).lower() for t in rule.get("terms", [])]
        return 3 if any(t in text for t in terms) else 1

    return 0


def grade_pool(query: Mapping[str, Any], docs: Iterable[Mapping[str, Any]]) -> list[Judgment]:
    """Grade every pooled document for a query that has an auto rule."""
    rule = query.get("auto")
    if not rule:
        return []
    kind = str(rule.get("kind", "unknown"))
    return [
        Judgment(str(query["id"]), str(doc["id"]), auto_grade(rule, doc), f"auto:{kind}")
        for doc in docs
    ]


# ----------------------------------------------------------------- qrels store


def load_qrels(path: Path) -> dict[str, dict[str, int]]:
    """Read qrels.jsonl into {query_id: {doc_id: grade}}."""
    qrels: dict[str, dict[str, int]] = {}
    if not path.exists():
        return qrels
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        qrels.setdefault(str(row["query_id"]), {})[str(row["doc_id"])] = int(row["grade"])
    return qrels


def load_judgments(path: Path) -> list[Judgment]:
    if not path.exists():
        return []
    out: list[Judgment] = []
    for line in path.read_text().splitlines():
        if line.strip():
            row = json.loads(line)
            out.append(
                Judgment(
                    str(row["query_id"]),
                    str(row["doc_id"]),
                    int(row["grade"]),
                    str(row.get("source", "unknown")),
                )
            )
    return out


def _authority(source: str) -> int:
    """Which label wins for one pair: human over LLM over rule."""
    if source == "human":
        return 2
    if source == "llm":
        return 1
    return 0


def save_judgments(path: Path, judgments: Iterable[Judgment]) -> int:
    """Write judgments; for the same pair a human label beats an LLM one beats a rule."""
    best: dict[tuple[str, str], Judgment] = {}
    for judgment in judgments:
        key = (judgment.query_id, judgment.doc_id)
        existing = best.get(key)
        if existing is None or _authority(judgment.source) > _authority(existing.source):
            best[key] = judgment
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = sorted(best.values(), key=lambda j: (j.query_id, j.doc_id))
    path.write_text("".join(json.dumps(j.to_dict()) + "\n" for j in rows))
    return len(rows)
