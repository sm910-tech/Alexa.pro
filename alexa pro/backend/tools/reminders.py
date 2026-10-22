"""
tools/reminders.py — Create, list, update and delete reminders

Storage: JSON file (reminders.json) in the backend directory.
Falls back to in-memory if the file can't be written (e.g. read-only FS).
"""

import json
import uuid
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

STORAGE_PATH = Path(__file__).parent.parent / "reminders.json"


class ReminderStore:
    def __init__(self):
        self._reminders: list[dict] = self._load()

    # ── Public API ────────────────────────────────────────────────

    def create(self, text: str, due_at: Optional[str] = None) -> dict:
        """Create and persist a new reminder."""
        reminder = {
            "id":         str(uuid.uuid4()),
            "text":       text.strip(),
            "due_at":     due_at,
            "done":       False,
            "created_at": datetime.now().isoformat(),
        }
        self._reminders.append(reminder)
        self._save()
        log.info("Reminder created: %s", text[:60])
        return reminder

    def list_all(self) -> list[dict]:
        """Return all reminders, newest first."""
        return list(reversed(self._reminders))

    def list_pending(self) -> list[dict]:
        """Return only incomplete reminders."""
        return [r for r in self._reminders if not r["done"]]

    def update(
        self,
        reminder_id: str,
        done: Optional[bool] = None,
        text: Optional[str] = None,
    ) -> Optional[dict]:
        """Update a reminder's done state and/or text. Returns None if not found."""
        for r in self._reminders:
            if r["id"] == reminder_id:
                if done is not None:
                    r["done"] = done
                if text is not None:
                    r["text"] = text.strip()
                r["updated_at"] = datetime.now().isoformat()
                self._save()
                return r
        return None

    def delete(self, reminder_id: str) -> bool:
        """Delete a reminder. Returns True on success, False if not found."""
        before = len(self._reminders)
        self._reminders = [r for r in self._reminders if r["id"] != reminder_id]
        if len(self._reminders) < before:
            self._save()
            return True
        return False

    def complete_all(self) -> int:
        """Mark all pending reminders done. Returns count changed."""
        count = 0
        for r in self._reminders:
            if not r["done"]:
                r["done"] = True
                count += 1
        if count:
            self._save()
        return count

    # ── Persistence ───────────────────────────────────────────────

    def _load(self) -> list[dict]:
        try:
            if STORAGE_PATH.exists():
                data = json.loads(STORAGE_PATH.read_text())
                if isinstance(data, list):
                    return data
        except Exception as exc:
            log.warning("Could not load reminders file: %s", exc)
        return []

    def _save(self) -> None:
        try:
            STORAGE_PATH.write_text(json.dumps(self._reminders, indent=2))
        except Exception as exc:
            log.warning("Could not save reminders file: %s", exc)
