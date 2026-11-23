"""The fixtures of the ship.py tests."""

import pytest
from ship_fixtures import (
    Sandbox,
)


@pytest.fixture
def sb(tmp_path):
    return Sandbox(tmp_path)


@pytest.fixture(autouse=True)
def nobodys_rules(monkeypatch):
    """No test reads the rules file of whoever runs the tests."""
    monkeypatch.setenv("CLAUDE_HOME", "/nonexistent/claude-home")
