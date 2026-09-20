"""Per-stage statistics: processed / skipped / failed, each with reasons.

Every stage writes ``data/stats/<stage>.json``. Failures and skips are always
counted against a named reason and never silently dropped
(CLAUDE_CODE_KICKOFF.md section 5).
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass
class StageStats:
    stage: str
    processed: int = 0
    skipped: int = 0
    failed: int = 0
    skip_reasons: Counter[str] = field(default_factory=Counter)
    fail_reasons: Counter[str] = field(default_factory=Counter)
    extra: dict[str, Any] = field(default_factory=dict)

    def ok(self, n: int = 1) -> None:
        self.processed += n

    def skip(self, reason: str, n: int = 1) -> None:
        self.skipped += n
        self.skip_reasons[reason] += n

    def fail(self, reason: str, n: int = 1) -> None:
        self.failed += n
        self.fail_reasons[reason] += n

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "written_at": datetime.now(UTC).isoformat(),
            "processed": self.processed,
            "skipped": self.skipped,
            "failed": self.failed,
            "skip_reasons": dict(self.skip_reasons),
            "fail_reasons": dict(self.fail_reasons),
            **self.extra,
        }

    def write(self, stats_dir: Path) -> Path:
        stats_dir.mkdir(parents=True, exist_ok=True)
        path = stats_dir / f"{self.stage}.json"
        path.write_text(json.dumps(self.to_dict(), indent=2, default=str) + "\n")
        return path

    def summary(self) -> str:
        parts = [
            f"[{self.stage}] processed={self.processed}",
            f"skipped={self.skipped}",
            f"failed={self.failed}",
        ]
        if self.skip_reasons:
            parts.append(f"skips={dict(self.skip_reasons)}")
        if self.fail_reasons:
            parts.append(f"fails={dict(self.fail_reasons)}")
        return " ".join(parts)
