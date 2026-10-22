"""
tools/clock.py — Time and date queries

All responses are plain strings ready to be spoken by TTS.
No external dependencies required.
"""

from datetime import datetime
import zoneinfo


def get_time(tz: str | None = None) -> str:
    """Return a human-readable current time string.

    Args:
        tz: Optional IANA timezone name, e.g. 'America/New_York'.
            Defaults to the system local time.

    Returns:
        A natural language time string, e.g. "It's 3:42 PM."
    """
    now = _now(tz)
    t   = now.strftime("%-I:%M %p").lstrip("0") if hasattr(now, "strftime") else now.strftime("%I:%M %p").lstrip("0")
    tz_label = f" {now.strftime('%Z')}" if tz else ""
    return f"It's {t}{tz_label}."


def get_date(tz: str | None = None) -> str:
    """Return a human-readable current date string.

    Returns:
        e.g. "Today is Thursday, October 3rd, 2024."
    """
    now = _now(tz)
    day = now.day
    suffix = _ordinal_suffix(day)
    return now.strftime(f"Today is %A, %B {day}{suffix}, %Y.")


def get_datetime(tz: str | None = None) -> dict:
    """Return a structured dict with time components."""
    now = _now(tz)
    return {
        "iso":       now.isoformat(),
        "time":      now.strftime("%H:%M:%S"),
        "date":      now.strftime("%Y-%m-%d"),
        "weekday":   now.strftime("%A"),
        "month":     now.strftime("%B"),
        "day":       now.day,
        "year":      now.year,
        "timezone":  str(now.tzinfo) if now.tzinfo else "local",
    }


# ── Helpers ───────────────────────────────────────────────────────

def _now(tz: str | None) -> datetime:
    if tz:
        try:
            return datetime.now(zoneinfo.ZoneInfo(tz))
        except (zoneinfo.ZoneInfoNotFoundError, Exception):
            pass    # Fall through to local time
    return datetime.now()


def _ordinal_suffix(day: int) -> str:
    if 11 <= day <= 13:
        return "th"
    return {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
