"""
main.py — FastAPI application server

Endpoints:
    GET  /health         → server status check
    POST /chat           → main conversation endpoint
    GET  /weather        → current weather (real API or labelled demo data)
    GET  /reminders      → list reminders
    POST /reminders      → create a reminder
    PUT  /reminders/{id} → update/complete a reminder
    DELETE /reminders/{id} → delete a reminder
"""

import os
import json
import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from assistant import Assistant
from schemas import ChatRequest, ChatResponse, ReminderCreate, ReminderUpdate
from tools.weather import get_weather
from tools.reminders import ReminderStore

# ── Logging ───────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
log = logging.getLogger(__name__)

# ── App ────────────────────────────────────────────────────────────
app = FastAPI(
    title="Alexa Pro Backend",
    description="AI assistant backend with tool execution and session management",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],        # Restrict to your frontend URL in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Shared instances ───────────────────────────────────────────────
assistant     = Assistant()
reminder_store = ReminderStore()

# ── Routes ────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    """Simple liveness probe used by the frontend status indicator."""
    return {"status": "ok", "message": "Alexa Pro backend is running"}


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """
    Main conversation endpoint.

    Accepts a user message plus optional conversation history,
    runs it through the AI assistant (which may invoke tools),
    and returns the reply plus any tool_results the frontend
    should act on (e.g. timers, reminders).
    """
    log.info("Chat message received: %.80s…", req.message)
    try:
        result = await assistant.respond(
            message=req.message,
            history=req.history or [],
        )
        return result
    except Exception as exc:
        log.error("Assistant error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/weather")
async def weather():
    """Return current weather. Falls back to labelled demo data if unavailable."""
    return await get_weather()


# ── Reminder endpoints ─────────────────────────────────────────────

@app.get("/reminders")
async def list_reminders():
    return reminder_store.list_all()


@app.post("/reminders", status_code=201)
async def create_reminder(data: ReminderCreate):
    reminder = reminder_store.create(data.text, data.due_at)
    return reminder


@app.put("/reminders/{reminder_id}")
async def update_reminder(reminder_id: str, data: ReminderUpdate):
    updated = reminder_store.update(reminder_id, data.done, data.text)
    if updated is None:
        raise HTTPException(status_code=404, detail="Reminder not found")
    return updated


@app.delete("/reminders/{reminder_id}", status_code=204)
async def delete_reminder(reminder_id: str):
    if not reminder_store.delete(reminder_id):
        raise HTTPException(status_code=404, detail="Reminder not found")
