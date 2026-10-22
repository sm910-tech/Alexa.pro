
"""
assistant.py — AI conversation logic

Handles:
  • System prompt construction
  • Tool selection from the user's message
  • Calling the real tool implementations
  • Falling back to the AI model for open-ended answers
  • Returning a structured response to the frontend
"""

import os
import logging
import re
from typing import Optional

import anthropic

from tools.clock import get_time, get_date
from tools.reminders import ReminderStore
from tools.calculator import safe_calculate
from tools.weather import get_weather

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are Alexa Pro, a helpful, warm, and efficient personal AI assistant.
You respond conversationally and concisely — one or two sentences where possible.
When you perform an action (set a timer, add a reminder, calculate something), confirm it briefly.
You never make up facts. If you don't know something, say so and suggest where to find it.
Today's date and time are provided at the start of each conversation turn.
"""

# Intent patterns — simple keyword matching before calling the AI model.
_INTENT_PATTERNS = {
    "time": re.compile(
        r"\b(what(?:'s| is) (the )?time|current time|time (is it|now))\b",
        re.I,
    ),
    "date": re.compile(
        r"\b(what(?:'s| is) (the )?date|today(?:'s date)?|what day)\b",
        re.I,
    ),
    "reminder": re.compile(
        r"\b(remind(er)?|don't (let me )?forget|remember to)\b",
        re.I,
    ),
    "timer": re.compile(
        r"\b(set (a )?timer|timer for|countdown)\b",
        re.I,
    ),
    "calculate": re.compile(
        r"\b(calculate|compute|what(?:'s| is) \d|math|percent(age)?|\bof\b)\b",
        re.I,
    ),
    "weather": re.compile(
        r"\b(weather|temperature|forecast|raining|sunny|outside today)\b",
        re.I,
    ),
}


class Assistant:
    def __init__(self):
        api_key = os.getenv("ANTHROPIC_API_KEY")

        if not api_key:
            log.warning(
                "ANTHROPIC_API_KEY not set — AI responses will be unavailable"
            )

        self.client = (
            anthropic.Anthropic(api_key=api_key)
            if api_key
            else None
        )

        self.reminder_store = ReminderStore()

    async def respond(
        self,
        message: str,
        history: list[dict],
    ) -> dict:
        """
        Main entry point.

        Returns:
            {
                "reply": str,
                "tool_results": dict | None
            }
        """
        tool_results: dict = {}

        # 1. Handle built-in tools before calling the AI model.
        intent = self._detect_intent(message)

        if intent == "time":
            return {
                "reply": get_time(),
                "tool_results": None,
            }

        if intent == "date":
            return {
                "reply": get_date(),
                "tool_results": None,
            }

        if intent == "calculate":
            expr = self._extract_math(message)
            result = safe_calculate(expr)

            reply = (
                f"{expr} = {result}"
                if result is not None
                else (
                    "I couldn't parse that calculation. "
                    "Try something like '15% of 240'."
                )
            )

            return {
                "reply": reply,
                "tool_results": None,
            }

        if intent == "weather":
            data = await get_weather()

            reply = (
                f"Currently {data['description']} in "
                f"{data['location']} — {data['temp']}. "
                f"{data.get('extra', '')}"
            ).strip()

            return {
                "reply": reply.strip(" ."),
                "tool_results": None,
            }

        if intent == "reminder":
            text = self._extract_reminder_text(message)
            created = self.reminder_store.create(text)

            tool_results["reminders_updated"] = True
            tool_results["reminders"] = (
                self.reminder_store.list_all()
            )

            return {
                "reply": (
                    f"Got it — I've added a reminder: "
                    f"\"{created['text']}\"."
                ),
                "tool_results": tool_results,
            }

        if intent == "timer":
            seconds, label = self._extract_timer(message)

            if seconds:
                tool_results["timer_set"] = {
                    "label": label,
                    "seconds": seconds,
                }

                minutes, remaining_seconds = divmod(seconds, 60)

                if minutes:
                    duration = (
                        f"{minutes} minute"
                        f"{'s' if minutes != 1 else ''}"
                    )
                    if remaining_seconds:
                        duration += (
                            f" and {remaining_seconds} second"
                            f"{'s' if remaining_seconds != 1 else ''}"
                        )
                else:
                    duration = (
                        f"{remaining_seconds} second"
                        f"{'s' if remaining_seconds != 1 else ''}"
                    )

                return {
                    "reply": f"Timer set for {duration}.",
                    "tool_results": tool_results,
                }

        # 2. Use a fallback if the AI API key is missing.
        if not self.client:
            return {
                "reply": (
                    "I can handle time, date, weather, reminders, "
                    "timers, and calculations without the AI model. "
                    "Configure ANTHROPIC_API_KEY in your backend "
                    "environment to enable open-ended conversation."
                ),
                "tool_results": None,
            }

        # 3. Handle open-ended conversation with the AI model.
        reply = await self._ai_reply(message, history)

        return {
            "reply": reply,
            "tool_results": None,
        }

    # Intent detection

    def _detect_intent(
        self,
        message: str,
    ) -> Optional[str]:
        for intent, pattern in _INTENT_PATTERNS.items():
            if pattern.search(message):
                return intent

        return None

    # Tool helpers

    def _extract_math(self, message: str) -> str:
        """Extract a mathematical expression from the message."""

        percentage = re.search(
            r"(\d+(?:\.\d+)?)\s*%\s*of\s*(\d+(?:\.\d+)?)",
            message,
            re.I,
        )

        if percentage:
            return (
                f"{percentage.group(1)}% of "
                f"{percentage.group(2)}"
            )

        expression = re.search(
            r"[\d\.\+\-\*\/\^\(\)\s]+",
            message,
        )

        return (
            expression.group(0).strip()
            if expression
            else message
        )

    def _extract_reminder_text(self, message: str) -> str:
        """Extract the reminder content from the message."""

        match = re.search(
            r"remind(?:er)?\s+(?:me\s+)?to\s+"
            r"(.+?)(?:\s+(?:at|on|by|in)\s+.+)?$",
            message,
            re.I,
        )

        if match:
            return match.group(1).strip().rstrip(".")

        match = re.search(
            r"remember\s+to\s+"
            r"(.+?)(?:\s+(?:at|on|by|in)\s+.+)?$",
            message,
            re.I,
        )

        if match:
            return match.group(1).strip().rstrip(".")

        cleaned = re.sub(
            r"\b(remind me(?: to)?|"
            r"add a reminder(?: (to|for))?|"
            r"don't let me forget(?: to)?)\b",
            "",
            message,
            flags=re.I,
        )

        return cleaned.strip().rstrip(".") or message

    def _extract_timer(
        self,
        message: str,
    ) -> tuple[Optional[int], str]:
        """Return (duration in seconds, timer label)."""

        hours = re.search(
            r"(\d+(?:\.\d+)?)\s*hours?",
            message,
            re.I,
        )

        minutes = re.search(
            r"(\d+(?:\.\d+)?)\s*min(?:utes?)?",
            message,
            re.I,
        )

        seconds_match = re.search(
            r"(\d+(?:\.\d+)?)\s*secs?(?:onds?)?",
            message,
            re.I,
        )

        total = 0

        if hours:
            total += int(float(hours.group(1)) * 3600)

        if minutes:
            total += int(float(minutes.group(1)) * 60)

        if seconds_match:
            total += int(float(seconds_match.group(1)))

        if total <= 0:
            return None, "Timer"

        label_match = re.search(
            r"timer\s+(?:for|called)\s+(.+?)$",
            message,
            re.I,
        )

        label = (
            label_match.group(1).strip().rstrip(".")
            if label_match
            else "Timer"
        )

        return total, label

    # AI model call

    async def _ai_reply(
        self,
        message: str,
        history: list[dict],
    ) -> str:
        """Send conversation history to Anthropic and return its reply."""

        from datetime import datetime

        now = datetime.now().strftime(
            "%A, %B %d %Y at %I:%M %p"
        )

        messages = []

        # Support dictionaries and Pydantic HistoryTurn objects.
        for turn in history[-18:]:
            if isinstance(turn, dict):
                role = turn.get("role", "")
                content = turn.get("content", "")
            else:
                role = getattr(turn, "role", "")
                content = getattr(turn, "content", "")

            if (
                role in ("user", "assistant")
                and isinstance(content, str)
                and content.strip()
            ):
                messages.append({
                    "role": role,
                    "content": content,
                })

        # The Anthropic API expects conversation messages to begin
        # with a user turn. Remove leading assistant turns if present.
        while messages and messages[0]["role"] == "assistant":
            messages.pop(0)

        # Replace a stale final user message or append the new one.
        if messages and messages[-1]["role"] == "user":
            messages[-1]["content"] = message
        else:
            messages.append({
                "role": "user",
                "content": message,
            })

        try:
            response = self.client.messages.create(
                model="claude-opus-4-5",
                max_tokens=512,
                system=(
                    f"{SYSTEM_PROMPT}\n\n"
                    f"Current time: {now}"
                ),
                messages=messages,
            )

            for block in response.content:
                if getattr(block, "type", None) == "text":
                    return block.text.strip()

            return "I couldn't generate a text response. Please try again."

        except anthropic.APIError:
            log.exception("Anthropic API request failed")
            raise
