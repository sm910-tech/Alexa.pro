        if intent == "timer":
            seconds, label = self._extract_timer(message)
            if seconds:
                tool_results["timer_set"] = {"label": label, "seconds": seconds}
                m, s = divmod(seconds, 60)
                duration = f"{m} minute{'s' if m != 1 else ''}" if m else f"{s} second{'s' if s != 1 else ''}"
                return {
                    "reply":        f"Timer set for {duration}.",
                    "tool_results": tool_results,
                }

        # ── 2. Fall through to AI model for open-ended questions ──
        if not self.client:
            return {
                "reply":        "I can handle time, date, weather, reminders, timers, and calculations without the AI model. Add your ANTHROPIC_API_KEY to .env for open-ended conversation.",
                "tool_results": None,
            }

        reply = await self._ai_reply(message, history)
        return {"reply": reply, "tool_results": None}

    # ── Intent detection ──────────────────────────────────────────

    def _detect_intent(self, message: str) -> Optional[str]:
        for intent, pattern in _INTENT_PATTERNS.items():
            if pattern.search(message):
                return intent
        return None

    # ── Tool helpers ──────────────────────────────────────────────

    def _extract_math(self, message: str) -> str:
        """Pull the mathematical expression from the message."""
        # Handle "X% of Y" pattern
        pct = re.search(r"(\d+(?:\.\d+)?)\s*%\s*of\s*(\d+(?:\.\d+)?)", message, re.I)
        if pct:
            return f"{pct.group(1)}% of {pct.group(2)}"

        # Extract any expression with operators
        expr = re.search(r"[\d\.\+\-\*\/\^\(\)\s]+", message)
        return expr.group(0).strip() if expr else message

    def _extract_reminder_text(self, message: str) -> str:
        """Try to pull the actual reminder content from the message."""
        # "remind me to X" / "remember to X"
        m = re.search(r"remind(?:er)?\s+(?:me\s+)?to\s+(.+?)(?:\s+(?:at|on|by|in)\s+.+)?$", message, re.I)
        if m:
            return m.group(1).strip().rstrip(".")

        m = re.search(r"remember\s+to\s+(.+?)(?:\s+(?:at|on|by|in)\s+.+)?$", message, re.I)
        if m:
            return m.group(1).strip().rstrip(".")

        # Strip the trigger words and return what's left
        cleaned = re.sub(r"\b(remind me(?: to)?|add a reminder(?: (to|for))?|don't let me forget(?: to)?)\b", "", message, flags=re.I)
        return cleaned.strip().rstrip(".") or message

    def _extract_timer(self, message: str) -> tuple[Optional[int], str]:
        """Return (seconds, label) from a timer request."""
        # Match patterns like "5 minutes", "1 hour 30 minutes", "90 seconds"
        hours   = re.search(r"(\d+(?:\.\d+)?)\s*hours?", message, re.I)
        minutes = re.search(r"(\d+(?:\.\d+)?)\s*min(?:utes?)?", message, re.I)
        seconds = re.search(r"(\d+(?:\.\d+)?)\s*secs?(?:onds?)?", message, re.I)

        total = 0
        if hours:   total += int(float(hours.group(1))   * 3600)
        if minutes: total += int(float(minutes.group(1)) * 60)
        if seconds: total += int(float(seconds.group(1)))

        if total <= 0:
            return None, "Timer"

        # Try to extract a label like "pasta" from "set a 10-minute timer for pasta"
        label_match = re.search(r"timer\s+(?:for|called)\s+(.+?)$", message, re.I)
        label = label_match.group(1).strip().rstrip(".") if label_match else "Timer"

        return total, label

    # ── AI model call ─────────────────────────────────────────────

    async def _ai_reply(self, message: str, history: list[dict]) -> str:
        """Send the message + history to the Anthropic API and return the reply."""
        from datetime import datetime
        now = datetime.now().strftime("%A, %B %d %Y at %I:%M %p")

        messages = []

        # Inject conversation history (validated)
        for turn in history[-18:]:  # stay within context limits
            # ChatRequest validates history entries as Pydantic HistoryTurn objects.
            # Supporting dicts as well makes this helper safe for direct callers/tests.
            if isinstance(turn, dict):
                role = turn.get("role", "")
                content = turn.get("content", "")
            else:
                role = getattr(turn, "role", "")
                content = getattr(turn, "content", "")

            if role in ("user", "assistant") and isinstance(content, str):
                messages.append({"role": role, "content": content})

        # Make sure we don't end on an assistant turn before adding the new user message
        if messages and messages[-1]["role"] == "assistant":
            messages.append({"role": "user", "content": message})
        elif not messages or messages[-1]["role"] != "user":
            messages.append({"role": "user", "content": message})
        else:
            messages[-1]["content"] = message   # replace stale last user message

        response = self.client.messages.create(
            model="claude-opus-4-5",
            max_tokens=512,
            system=f"{SYSTEM_PROMPT}\n\nCurrent time: {now}",
            messages=messages,
        )

        return response.content[0].text.strip()
