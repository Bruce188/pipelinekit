"""The sb fixture of the loop.py tests."""

from __future__ import annotations

import pytest
from loop_fixtures import (
    Sandbox,
)


@pytest.fixture
def sb(tmp_path, monkeypatch, capsys):
    return Sandbox(tmp_path, monkeypatch, capsys)
