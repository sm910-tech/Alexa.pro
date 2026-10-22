"""
tests/test_tools.py — Unit tests for individual tool modules

Run with:  pytest tests/test_tools.py -v
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))


# ── Clock ─────────────────────────────────────────────────────────

from tools.clock import get_time, get_date, get_datetime


def test_get_time_returns_string():
    result = get_time()
    assert isinstance(result, str)
    assert "It's" in result
    assert ("AM" in result or "PM" in result)


def test_get_date_returns_string():
    result = get_date()
    assert isinstance(result, str)
    assert "Today is" in result


def test_get_datetime_keys():
    result = get_datetime()
    for key in ("iso", "time", "date", "weekday", "year"):
        assert key in result


def test_get_time_with_timezone():
    result = get_time("America/New_York")
    assert isinstance(result, str)
    # Invalid tz should fall back gracefully
    result2 = get_time("Not/ATimezone")
    assert isinstance(result2, str)


# ── Calculator ────────────────────────────────────────────────────

from tools.calculator import safe_calculate


def test_addition():
    assert safe_calculate("2 + 2") == "4"


def test_multiplication():
    assert safe_calculate("6 * 7") == "42"


def test_division():
    assert safe_calculate("10 / 4") == "2.5"


def test_percentage_of():
    assert safe_calculate("15% of 240") == "36"


def test_percent_word():
    assert safe_calculate("20 percent of 50") == "10"


def test_exponent():
    assert safe_calculate("2 ** 10") == "1024"


def test_parentheses():
    assert safe_calculate("(12 + 8) * 3") == "60"


def test_division_by_zero():
    result = safe_calculate("10 / 0")
    assert result is not None and "zero" in result.lower()


def test_empty_expression():
    assert safe_calculate("") is None


def test_malicious_expression_rejected():
    # These should return None, not execute code
    assert safe_calculate("__import__('os').getcwd()") is None
    assert safe_calculate("open('/etc/passwd').read()") is None


# ── Reminders ─────────────────────────────────────────────────────

from tools.reminders import ReminderStore
import tempfile, json
from unittest.mock import patch


def test_reminder_create():
    store = ReminderStore()
    r = store.create("Buy milk")
    assert r["text"] == "Buy milk"
    assert r["done"] is False
    assert "id" in r


def test_reminder_list_pending():
    store = ReminderStore()
    store._reminders = []
    store.create("Task A")
    b = store.create("Task B")
    store.update(b["id"], done=True)
    pending = store.list_pending()
    assert len(pending) == 1
    assert pending[0]["text"] == "Task A"


def test_reminder_update():
    store = ReminderStore()
    store._reminders = []
    r = store.create("Dentist appointment")
    updated = store.update(r["id"], done=True)
    assert updated["done"] is True


def test_reminder_delete():
    store = ReminderStore()
    store._reminders = []
    r = store.create("Temporary task")
    result = store.delete(r["id"])
    assert result is True
    assert store.list_pending() == []


def test_reminder_delete_missing():
    store = ReminderStore()
    result = store.delete("nonexistent-id")
    assert result is False


def test_reminder_update_missing():
    store = ReminderStore()
    result = store.update("nonexistent-id", done=True)
    assert result is None
