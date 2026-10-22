"""
schemas.py — Pydantic data models for request and response validation

Keeping schemas in a separate file:
  • Makes them importable without pulling in all of main.py
  • Makes it easy to add OpenAPI documentation strings
  • Keeps main.py and assistant.py free of model definitions
"""

from __future__ import annotations
from typing import Any, Optional
from pydantic import BaseModel, Field, field_validator


# ── Chat ──────────────────────────────────────────────────────────

class HistoryTurn(BaseModel):
    role:    str = Field(..., pattern="^(user|assistant)$")
    content: str = Field(..., min_length=0, max_length=16_000)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4_000, description="The user's current message")
    history: list[HistoryTurn] = Field(
        default_factory=list,
        max_length=40,
        description="Recent conversation turns, newest last (max 40 entries = 20 turns)",
    )

    @field_validator("message")
    @classmethod
    def strip_message(cls, v: str) -> str:
        return v.strip()


class ChatResponse(BaseModel):
    reply:        str       = Field(..., description="The assistant's reply text (also sent to TTS)")
    tool_results: Optional[dict[str, Any]] = Field(
        default=None,
        description="Optional side-effects the frontend should act on",
    )


# ── Reminders ─────────────────────────────────────────────────────

class ReminderCreate(BaseModel):
    text:   str            = Field(..., min_length=1, max_length=500)
    due_at: Optional[str]  = Field(default=None, description="ISO 8601 datetime string")

    @field_validator("text")
    @classmethod
    def strip_text(cls, v: str) -> str:
        return v.strip()


class ReminderUpdate(BaseModel):
    done: Optional[bool]  = None
    text: Optional[str]   = Field(default=None, min_length=1, max_length=500)


# ── Weather (response) ────────────────────────────────────────────

class WeatherResponse(BaseModel):
    icon:        str = "⛅"
    temp:        str = "--°"
    description: str = "Unknown"
    location:    str = ""
    extra:       str = ""
    demo:        bool = False    # True when returning labelled demo data
