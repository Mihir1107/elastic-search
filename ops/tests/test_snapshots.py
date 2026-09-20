"""Unit tests for snapshot naming and version bumping (no cluster needed)."""

from __future__ import annotations

import pytest

from ops.snapshots.repo import next_version


def test_next_version_bumps_past_the_current_index() -> None:
    assert next_version("emails-v1", ["emails-v1"]) == "emails-v2"


def test_next_version_skips_versions_that_already_exist() -> None:
    """A restore must never land on a name in use -- emails-v2 may be serving."""
    assert next_version("emails-v1", ["emails-v1", "emails-v2", "emails-v3"]) == "emails-v4"


def test_next_version_handles_a_base_containing_digits() -> None:
    assert next_version("emails-2026-v9", ["emails-2026-v9"]) == "emails-2026-v10"


def test_next_version_rejects_an_unversioned_index() -> None:
    with pytest.raises(ValueError, match="not versioned"):
        next_version("emails", ["emails"])
