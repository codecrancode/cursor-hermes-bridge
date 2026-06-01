"""Tests for the cursor_logs adapter."""
from __future__ import annotations

import pytest

from app.adapters.cursor_logs import CursorLogsAdapter


@pytest.fixture
def logs_adapter():
    return CursorLogsAdapter()


def test_adapter_name(logs_adapter: CursorLogsAdapter):
    assert logs_adapter.name == "cursor_logs"


def test_adapter_available(logs_adapter: CursorLogsAdapter):
    result = logs_adapter.is_available()
    assert isinstance(result, bool)
