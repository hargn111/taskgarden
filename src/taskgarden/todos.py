"""Core data model and storage for Task Garden."""

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, TypedDict, Union

# Default data path (same as the old script)
DEFAULT_DATA_PATH = Path("/root/.openclaw/workspace/state/todos.json")
DATA_PATH = Path(os.getenv("TASKGARDEN_DATA_PATH", DEFAULT_DATA_PATH))

VALID_BUCKETS = {"unplanned", "planned"}
VALID_STATUS = {"open", "done"}


class TodoItem(TypedDict, total=False):
    """Schema of a todo item."""

    id: str
    title: str
    note: str
    tags: List[str]
    status: Literal["open", "done"]
    bucket: Literal["unplanned", "planned"]
    created_at: str
    completed_at: Optional[str]
    remind_interval_hours: Optional[float]
    last_reminder_at: Optional[str]


class TodoData(TypedDict):
    """Schema of the whole storage file."""

    version: int
    items: List[TodoItem]


def now_iso() -> str:
    """Return current UTC time as ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def parse_iso(value: str) -> datetime:
    """Parse ISO 8601 string to datetime (supports Z suffix)."""
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)


def normalize_item(item: Dict[str, Any]) -> TodoItem:
    """Ensure an item has all required fields and valid values."""
    item.setdefault("note", "")
    item.setdefault("tags", [])
    item.setdefault("status", "open")
    item.setdefault("bucket", "unplanned")
    item.setdefault("completed_at", None)
    item.setdefault("remind_interval_hours", None)
    item.setdefault("last_reminder_at", None)

    # Deduplicate and sort tags
    if "tags" in item:
        item["tags"] = sorted(set(item["tags"]))

    if item["status"] not in VALID_STATUS:
        item["status"] = "open"
    if item["bucket"] not in VALID_BUCKETS:
        item["bucket"] = "unplanned"

    return item  # type: ignore


def load_data() -> TodoData:
    """Load and normalize todo data from JSON file."""
    if not DATA_PATH.exists():
        return {"version": 2, "items": []}

    content = DATA_PATH.read_text()
    data: Dict[str, Any] = json.loads(content)
    data.setdefault("version", 1)
    data.setdefault("items", [])
    data["items"] = [normalize_item(item) for item in data["items"]]

    # Upgrade version if needed
    if data["version"] < 2:
        data["version"] = 2
        save_data(data)

    return data  # type: ignore


def save_data(data: TodoData) -> None:
    """Save todo data to JSON file."""
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    data["version"] = 2
    data["items"] = [normalize_item(item) for item in data["items"]]
    DATA_PATH.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def find_item(data: TodoData, item_id: str) -> Optional[TodoItem]:
    """Find an item by ID, returning None if not found."""
    for item in data["items"]:
        if item["id"] == item_id:
            return item
    return None


def append_note(item: TodoItem, note: str) -> None:
    """Append a line to the item's note field."""
    note = note.strip()
    if not note:
        return
    if item.get("note"):
        item["note"] = item["note"].rstrip() + "\n- " + note
    else:
        item["note"] = note


def reminder_due(item: TodoItem, now: Optional[datetime] = None) -> bool:
    """Return True if the item is due for a reminder."""
    if item.get("status") != "open":
        return False
    interval = item.get("remind_interval_hours")
    if interval is None:
        return False

    last = item.get("last_reminder_at") or item.get("created_at")
    if not last:
        return True

    last_dt = parse_iso(last)
    now_dt = now or datetime.now(timezone.utc)
    elapsed_hours = (now_dt - last_dt).total_seconds() / 3600
    return elapsed_hours >= float(interval)


def create_item(
    title: str,
    note: str = "",
    tags: Optional[List[str]] = None,
    bucket: str = "unplanned",
    remind_interval_hours: Optional[float] = None,
) -> TodoItem:
    """Create a new todo item with a generated ID."""
    return normalize_item(
        {
            "id": uuid.uuid4().hex[:8],
            "title": title.strip(),
            "note": note.strip(),
            "tags": sorted(set(tags or [])),
            "status": "open",
            "bucket": bucket,
            "created_at": now_iso(),
            "completed_at": None,
            "remind_interval_hours": remind_interval_hours,
            "last_reminder_at": None,
        }
    )
