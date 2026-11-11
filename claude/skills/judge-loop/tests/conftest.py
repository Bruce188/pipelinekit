"""The sb fixture of the loop.py tests."""

from __future__ import annotations

import pytest
from loop_fixtures import Sandbox, build_template


@pytest.fixture(scope="session")
def template(tmp_path_factory):
    return build_template(tmp_path_factory.mktemp("template"))


@pytest.fixture
def sb(tmp_path, monkeypatch, capsys, template):
    return Sandbox(tmp_path, monkeypatch, capsys, template)
