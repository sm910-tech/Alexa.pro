"""
tests/test_api.py — Integration tests for FastAPI endpoints

Run with:  pytest tests/test_api.py -v
"""

import pytest
from httpx import AsyncClient, ASGITransport

# Add backend to path when running from project root
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from main import app


@pytest.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


@pytest.mark.asyncio
async def test_health(client):
    """Health endpoint returns 200 with expected keys."""
    res = await client.get("/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert "message" in body


@pytest.mark.asyncio
async def test_chat_returns_reply(client):
    """Chat endpoint returns a reply string for a simple query."""
    res = await client.post(
        "/chat",
        json={"message": "What time is it?"},
    )
    assert res.status_code == 200
    body = res.json()
    assert isinstance(body["reply"], str)
    assert len(body["reply"]) > 0


@pytest.mark.asyncio
async def test_chat_rejects_empty_message(client):
    """Chat endpoint rejects an empty message with 422."""
    res = await client.post("/chat", json={"message": ""})
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_chat_rejects_missing_message(client):
    """Chat endpoint requires the message field."""
    res = await client.post("/chat", json={})
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_weather_returns_data(client):
    """Weather endpoint returns expected keys."""
    res = await client.get("/weather")
    assert res.status_code == 200
    body = res.json()
    assert "temp" in body
    assert "description" in body


@pytest.mark.asyncio
async def test_reminders_crud(client):
    """Create, list, update and delete a reminder."""
    # Create
    res = await client.post("/reminders", json={"text": "Test reminder"})
    assert res.status_code == 201
    reminder = res.json()
    assert reminder["text"] == "Test reminder"
    assert reminder["done"] is False
    rid = reminder["id"]

    # List
    res = await client.get("/reminders")
    assert res.status_code == 200
    ids = [r["id"] for r in res.json()]
    assert rid in ids

    # Update
    res = await client.put(f"/reminders/{rid}", json={"done": True})
    assert res.status_code == 200
    assert res.json()["done"] is True

    # Delete
    res = await client.delete(f"/reminders/{rid}")
    assert res.status_code == 204

    # Confirm deletion
    res = await client.delete(f"/reminders/{rid}")
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_reminder_not_found(client):
    """Updating or deleting a missing reminder returns 404."""
    fake_id = "00000000-0000-0000-0000-000000000000"
    res = await client.put(f"/reminders/{fake_id}", json={"done": True})
    assert res.status_code == 404

    res = await client.delete(f"/reminders/{fake_id}")
    assert res.status_code == 404
