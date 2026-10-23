"""
Alexa Pro Assistant
Async AI integration through FreeLLMAPI.
Compatible with the existing main.py Assistant().respond() interface.
"""

import ast
import logging
import os
import re
import operator
from datetime import datetime
from typing import Optional

from dotenv import load_dotenv
from openai import (
    AsyncOpenAI,
    APIConnectionError,
    APIError,
    APITimeoutError,
)

load_dotenv()
logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """
You are Alexa Pro, a helpful, concise AI assistant.
Respond naturally and accurately.
Use the conversation history when relevant.
Do not claim to have performed actions you did not perform.
For current information you cannot access, explain the limitation.
"""


class Assistant:
    """Core Alexa Pro conversation and tool-handling logic."""

    def __init__(self):
        api_key = os.getenv("FREELLMAPI_API_KEY", "").strip()
        base_url = os.getenv(
            "FREELLMAPI_BASE_URL",
            "http://127.0.0.1:31415/v1",
        ).strip()
        self.model = os.getenv("FREELLMAPI_MODEL", "").strip()

        self.client = (
            AsyncOpenAI(
                api_key=api_key,
                base_url=base_url,
                timeout=90.0,
                max_retries=1,
            )
            if api_key
            else None
        )

    async def respond(
        self,
        message: str,
        history: Optional[list] = None,
    ) -> dict:
        """Process a message and return the backend response schema."""

        message = (message or "").strip()
        history = history or []
        tool_results = {}

        if not message:
            return {
                "reply": "Please enter a message.",
                "tool_results": None,
            }

        intent = self._detect_intent(message)

        # Local date and time require no API request.
        if intent == "time":
            now = datetime.now()
            return {
                "reply": f"The time is {now.strftime('%I:%M %p')}.",
                "tool_results": None,
            }

        if intent == "date":
            now = datetime.now()
            return {
                "reply": f"Today is {now.strftime('%A, %B %d, %Y')}.",
                "tool_results": None,
            }

        # Local timer handling.
        if intent == "timer":
            seconds, label = self._extract_timer(message)

            if seconds is not None and seconds > 0:
                tool_results["timer_set"] = {
                    "label": label,
                    "seconds": seconds,
                }

                if seconds >= 60 and seconds % 60 == 0:
                    minutes = seconds // 60
                    duration = (
                        f"{minutes} minute"
                        f"{'s' if minutes != 1 else ''}"
                    )
                else:
                    duration = (
                        f"{seconds} second"
                        f"{'s' if seconds != 1 else ''}"
                    )

                return {
                    "reply": f"Timer set for {duration}.",
                    "tool_results": tool_results,
                }

            return {
                "reply": (
                    "Please specify a duration, such as "
                    "'set a timer for 5 minutes'."
                ),
                "tool_results": None,
            }

        # FIX 3: Safe arithmetic evaluation without eval().
        # Falls through to AI when the expression can't be parsed locally,
        # but returns a clear error when no AI client is configured.
        if intent == "math":
            expression = self._extract_math(message)
            result = self._calculate(expression)

            if result is not None:
                return {
                    "reply": f"The answer is {result}.",
                    "tool_results": None,
                }

            # Fall through to AI when configured, so natural-language
            # expressions can still be interpreted.
            if not self.client or not self.model:
                return {
                    "reply": (
                        "I couldn't calculate that expression. "
                        "Try a format like '10% of 50' or '25 * 4'."
                    ),
                    "tool_results": None,
                }

        # Preserve a useful offline fallback.
        if not self.client:
            return {
                "reply": (
                    "AI is not configured. Set "
                    "FREELLMAPI_API_KEY in the backend environment."
                ),
                "tool_results": None,
            }

        if not self.model:
            return {
                "reply": (
                    "AI configuration error: "
                    "FREELLMAPI_MODEL is not configured."
                ),
                "tool_results": None,
            }

        reply = await self._ai_reply(message, history)
        return {
            "reply": reply,
            "tool_results": None,
        }

    # FIX 1: Timer detection takes priority; common time/date phrasings covered.
    def _detect_intent(self, message: str) -> Optional[str]:
        text = message.lower().strip()

        if re.search(r"\b(timer|countdown)\b", text):
            return "timer"

        if re.search(
            r"\b(what time is it|what's the time|"
            r"what is the time|current time|time please|"
            r"tell me the time|what's the current time)\b",
            text,
        ):
            return "time"

        if re.search(
            r"\b(today'?s date|what date is it|"
            r"what is the date|what's the date|"
            r"what's the date today|current date|"
            r"what day is it)\b",
            text,
        ):
            return "date"

        if re.search(
            r"\b(calculate|compute|solve)\b",
            text,
        ) or re.search(
            r"\b(what is|what's)\b.*\d.*(?:%|[+\-*/])",
            text,
        ):
            return "math"

        return None

    def _extract_timer(
        self,
        message: str,
    ) -> tuple[Optional[int], str]:
        """Extract a duration and optional timer label."""

        text = message.lower()

        units = {
            "hours": 3600,
            "hour": 3600,
            "hrs": 3600,
            "hr": 3600,
            "minutes": 60,
            "minute": 60,
            "mins": 60,
            "min": 60,
            "seconds": 1,
            "second": 1,
            "secs": 1,
            "sec": 1,
        }

        pattern = (
            r"\b(\d+(?:\.\d+)?)\s*"
            r"(hours?|hrs?|minutes?|mins?|seconds?|secs?)\b"
        )

        total = 0.0

        for match in re.finditer(pattern, text):
            amount = float(match.group(1))
            unit = match.group(2)
            total += amount * units[unit]

        if total <= 0:
            # Handle "set a timer for 90" as 90 seconds.
            bare = re.search(
                r"\btimer\s+(?:for\s+)?(\d+)\s*$",
                text,
            )
            if bare:
                total = float(bare.group(1))

        if total <= 0 or total > 365 * 24 * 3600:
            logger.debug("Timer extraction failed: total=%s", total)
            return None, "Timer"

        seconds = int(total)

        # FIX 4: Strip duration phrases before extracting the timer label
        # so the digit doesn't get captured as the label name.
        label_text = re.sub(
            r"\b\d+(?:\.\d+)?\s*"
            r"(?:hours?|hrs?|minutes?|mins?|seconds?|secs?)\b",
            " ",
            message,
            flags=re.I,
        )
        label_match = re.search(
            r"\btimer\s+(?:called|named)\s+(.+?)(?:\s+for\b|$)",
            label_text,
            re.I,
        )
        label = (
            label_match.group(1).strip(" .")
            if label_match
            else "Timer"
        )

        return seconds, label or "Timer"

    # FIX 2: Handle percentages before ordinary arithmetic, support Unicode
    # whitespace, avoid treating "X% of Y" expressions as modulo.
    def _extract_math(self, message: str) -> str:
        """Extract a supported arithmetic expression."""

        text = message.strip()

        percent = re.search(
            r"(\d+(?:\.\d+)?)\s*%\s*of\s*"
            r"(\d+(?:\.\d+)?)",
            text,
            re.I,
        )

        if percent:
            return (
                f"({percent.group(1)} / 100) * "
                f"{percent.group(2)}"
            )

        text = re.sub(
            r"^(?:please\s+)?(?:calculate|compute|solve|"
            r"what is|what's)\s+",
            "",
            text,
            flags=re.I,
        ).strip()

        # Allow only arithmetic characters and whitespace.
        if not re.fullmatch(r"[\d\s.+\-*/()%]+", text):
            return ""

        return text

    def _calculate(self, expression: str):
        """Evaluate basic arithmetic through a restricted AST."""

        if not expression or len(expression) > 150:
            return None

        allowed_operators = {
            ast.Add: operator.add,
            ast.Sub: operator.sub,
            ast.Mult: operator.mul,
            ast.Div: operator.truediv,
            ast.Mod: operator.mod,
            ast.USub: operator.neg,
            ast.UAdd: operator.pos,
        }

        def evaluate(node):
            if isinstance(node, ast.Expression):
                return evaluate(node.body)

            if isinstance(node, ast.Constant) and type(node.value) in (
                int,
                float,
            ):
                return node.value

            if isinstance(node, ast.BinOp):
                op = allowed_operators.get(type(node.op))
                if op is None:
                    raise ValueError("Unsupported operator")
                left = evaluate(node.left)
                right = evaluate(node.right)

                if abs(left) > 1e100 or abs(right) > 1e100:
                    raise ValueError("Number too large")

                result = op(left, right)
                if abs(result) > 1e100:
                    raise ValueError("Result too large")
                return result

            if isinstance(node, ast.UnaryOp):
                op = allowed_operators.get(type(node.op))
                if op is None:
                    raise ValueError("Unsupported operator")
                return op(evaluate(node.operand))

            raise ValueError("Unsupported expression")

        try:
            tree = ast.parse(expression, mode="eval")
            result = evaluate(tree)

            if isinstance(result, float) and not (
                float("-inf") < result < float("inf")
            ):
                return None

            if isinstance(result, float) and result.is_integer():
                return int(result)

            return round(result, 10) if isinstance(result, float) else result

        except (ValueError, TypeError, SyntaxError, ZeroDivisionError,
                OverflowError):
            return None

    async def _ai_reply(
        self,
        message: str,
        history: list,
    ) -> str:
        """Send validated conversation history to FreeLLMAPI."""

        now = datetime.now().strftime(
            "%A, %B %d %Y at %I:%M %p"
        )

        messages = []

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
            ):
                messages.append({
                    "role": role,
                    "content": content,
                })

        # FIX 5: Only append the current message when it isn't already
        # the last entry in history, preventing both silent overwrites
        # and duplicate user turns.
        if not (
            messages
            and messages[-1]["role"] == "user"
            and messages[-1]["content"].strip() == message.strip()
        ):
            messages.append({
                "role": "user",
                "content": message,
            })

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            f"{SYSTEM_PROMPT}\n\n"
                            f"Current local time: {now}"
                        ),
                    },
                    *messages,
                ],
                # FIX 6: Configurable token limit via environment variable.
                max_tokens=int(os.getenv("FREELLMAPI_MAX_TOKENS", "1024")),
                timeout=90.0,
            )

            if not response.choices:
                return "The AI provider returned an empty response."

            content = response.choices[0].message.content

            if isinstance(content, str) and content.strip():
                return content.strip()

            return "The AI provider returned an empty response."

        except APITimeoutError:
            logger.warning("FreeLLMAPI request timed out")
            return (
                "The AI service timed out. "
                "Please try again shortly."
            )

        except APIConnectionError:
            logger.warning("Cannot connect to FreeLLMAPI")
            return (
                "Cannot connect to the AI service. "
                "Check that FreeLLMAPI is running and reachable."
            )

        except APIError as exc:
            logger.error(
                "FreeLLMAPI returned an API error: %s",
                type(exc).__name__,
            )
            return (
                "The AI provider returned an error. "
                "Please try again later."
            )

        except Exception:
            logger.exception("Unexpected assistant error")
            return (
                "An unexpected AI error occurred. "
                "Please try again later."
            )
