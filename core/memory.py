"""
Memory System
Agent's long-term and short-term memory.
Stores context, decisions, events, user notes.
"""

import json
import os
from datetime import datetime
from typing import Optional

MEMORY_PATH = "data/memory.json"


def _load() -> dict:
    os.makedirs("data", exist_ok=True)
    if not os.path.exists(MEMORY_PATH):
        return {"short_term": [], "long_term": {}, "agent_notes": []}
    with open(MEMORY_PATH) as f:
        return json.load(f)


def _save(db: dict):
    with open(MEMORY_PATH, "w") as f:
        json.dump(db, f, indent=2, ensure_ascii=False)


class Memory:
    MAX_SHORT_TERM = 100

    def __init__(self):
        self.db = _load()

    def remember(self, key: str, value):
        """Store a long-term fact."""
        self.db["long_term"][key] = {
            "value": value,
            "updated_at": datetime.utcnow().isoformat()
        }
        _save(self.db)

    def recall(self, key: str):
        """Retrieve a long-term fact."""
        entry = self.db["long_term"].get(key)
        return entry["value"] if entry else None

    def log_event(self, event_type: str, content: str, metadata: dict = None):
        """Add to short-term event log."""
        entry = {
            "type": event_type,
            "content": content,
            "metadata": metadata or {},
            "timestamp": datetime.utcnow().isoformat()
        }
        self.db["short_term"].append(entry)
        # Trim to max
        if len(self.db["short_term"]) > self.MAX_SHORT_TERM:
            self.db["short_term"] = self.db["short_term"][-self.MAX_SHORT_TERM:]
        _save(self.db)

    def get_recent_events(self, n: int = 20) -> list:
        return self.db["short_term"][-n:]

    def add_note(self, note: str, tags: list = None):
        """Agent adds a note to itself."""
        self.db["agent_notes"].append({
            "note": note,
            "tags": tags or [],
            "timestamp": datetime.utcnow().isoformat()
        })
        _save(self.db)

    def get_notes(self, tag: str = None) -> list:
        notes = self.db["agent_notes"]
        if tag:
            notes = [n for n in notes if tag in n.get("tags", [])]
        return notes

    def get_context_summary(self) -> str:
        """Returns a brief text summary of recent memory for AI context."""
        recent = self.get_recent_events(10)
        if not recent:
            return "No recent events."
        lines = []
        for e in recent:
            lines.append(f"[{e['type']}] {e['content'][:100]}")
        return "\n".join(lines)
