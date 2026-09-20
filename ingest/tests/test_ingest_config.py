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


def test_es_hosts_splits_a_comma_separated_list() -> None:
    """Shared with the API: a bulk load should not hinge on one named node."""
    s = IngestSettings(
        _env_file=None,  # type: ignore[call-arg]
        es_host="https://localhost:9200,https://localhost:9201",
    )
    assert s.es_hosts == ["https://localhost:9200", "https://localhost:9201"]


def test_es_hosts_is_a_single_element_list_for_one_host() -> None:
    s = IngestSettings(_env_file=None, es_host="https://localhost:9200")  # type: ignore[call-arg]
    assert s.es_hosts == ["https://localhost:9200"]
