from __future__ import annotations

import pytest
from typer.testing import CliRunner

from ingest.cli import app
from ingest.config import IngestSettings


def test_ingest_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ELASTIC_PASSWORD", raising=False)
    s = IngestSettings(_env_file=None)  # type: ignore[call-arg]
    assert s.index_name == "emails-v1"
    assert s.raw_dir.as_posix() == "data/raw"
    assert s.dev_subset_size == 10_000
    assert s.enron_url.endswith("enron_mail_20150507.tar.gz")


def test_cli_help_lists_stages() -> None:
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    for stage in ("download", "parse", "dedupe", "thread", "embed", "index", "run"):
        assert stage in result.output
