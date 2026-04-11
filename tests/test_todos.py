"""Unit tests for Task Garden."""

from pathlib import Path
from unittest.mock import patch

from taskgarden.todos import (
    TodoData,
    TodoItem,
    append_note,
    create_item,
    find_item,
    load_data,
    normalize_item,
    now_iso,
    parse_iso,
    reminder_due,
    save_data,
    set_title,
    stale_task_due,
)


def test_normalize_item() -> None:
    """Test that missing fields are added and invalid values corrected."""
    raw = {"id": "abc123", "title": "test"}
    item = normalize_item(raw)
    assert item["id"] == "abc123"
    assert item["title"] == "test"
    assert item["note"] == ""
    assert item["tags"] == []
    assert item["status"] == "open"
    assert item["bucket"] == "unplanned"
    assert item["completed_at"] is None
    assert item["remind_interval_hours"] is None
    assert item["last_reminder_at"] is None

    # Invalid status/bucket are corrected
    raw2 = {"id": "x", "title": "y", "status": "invalid", "bucket": "invalid"}
    item2 = normalize_item(raw2)
    assert item2["status"] == "open"
    assert item2["bucket"] == "unplanned"

    # Tags deduplicated and sorted
    raw3 = {"id": "x", "title": "y", "tags": ["b", "a", "b"]}
    item3 = normalize_item(raw3)
    assert item3["tags"] == ["a", "b"]


def test_create_item() -> None:
    """Test item creation with default and custom fields."""
    with patch("taskgarden.todos.uuid.uuid4") as mock_uuid:
        mock_uuid.return_value.hex = "deadbeef12345678"
        item = create_item("Write tests", tags=["test", "python"], bucket="planned")
        assert item["id"] == "deadbeef"
        assert item["title"] == "Write tests"
        assert item["tags"] == ["python", "test"]
        assert item["bucket"] == "planned"
        assert item["status"] == "open"
        assert item["created_at"]  # present
        assert item["remind_interval_hours"] is None


def test_load_save_data(tmp_path: Path) -> None:
    """Test loading and saving data with a temporary file."""
    data_path = tmp_path / "todos.json"
    with patch("taskgarden.todos.DATA_PATH", data_path):
        # Load empty file
        data = load_data()
        assert data["version"] == 2
        assert data["items"] == []

        # Add an item and save
        item = create_item("Test todo")
        data["items"].append(item)
        save_data(data)

        # Reload and verify
        data2 = load_data()
        assert len(data2["items"]) == 1
        assert data2["items"][0]["id"] == item["id"]
        assert data2["items"][0]["title"] == "Test todo"


def test_find_item() -> None:
    """Test finding an item by ID."""
    data: TodoData = {
        "version": 2,
        "items": [
            {"id": "aaa", "title": "First"},
            {"id": "bbb", "title": "Second"},
        ],
    }
    found = find_item(data, "bbb")
    assert found is not None
    assert found["title"] == "Second"

    missing = find_item(data, "ccc")
    assert missing is None


def test_reminder_due() -> None:
    """Test reminder due logic."""
    now = parse_iso("2026-01-01T12:00:00+00:00")

    # No interval → not due
    item: TodoItem = {
        "id": "x",
        "title": "test",
        "status": "open",
        "bucket": "unplanned",
        "created_at": "2026-01-01T06:00:00+00:00",
        "note": "",
        "tags": [],
        "completed_at": None,
        "remind_interval_hours": None,
        "last_reminder_at": None,
    }
    assert not reminder_due(item, now)

    # Interval set, never reminded → due
    item["remind_interval_hours"] = 6.0
    assert reminder_due(item, now)  # created 6h ago, exactly interval

    # Last reminded recently → not due
    item["last_reminder_at"] = "2026-01-01T10:00:00+00:00"
    assert not reminder_due(item, now)  # only 2h elapsed

    # Done item → never due
    item["status"] = "done"
    assert not reminder_due(item, now)


def test_stale_task_due() -> None:
    """Test stale planned task review logic."""
    now = parse_iso("2026-01-15T12:00:00+00:00")

    item: TodoItem = {
        "id": "x",
        "title": "review me",
        "status": "open",
        "bucket": "planned",
        "created_at": "2026-01-01T12:00:00+00:00",
        "note": "",
        "tags": [],
        "completed_at": None,
        "remind_interval_hours": None,
        "last_reminder_at": None,
    }

    assert stale_task_due(item, 14, now)
    assert not stale_task_due(item, 15, now)

    item["bucket"] = "unplanned"
    assert not stale_task_due(item, 14, now)

    item["bucket"] = "planned"
    item["status"] = "done"
    assert not stale_task_due(item, 14, now)


def test_append_note() -> None:
    """Test appending notes."""
    item: TodoItem = {
        "id": "x",
        "title": "test",
        "status": "open",
        "bucket": "unplanned",
        "created_at": now_iso(),
        "note": "",
        "tags": [],
        "completed_at": None,
        "remind_interval_hours": None,
        "last_reminder_at": None,
    }
    # First note
    append_note(item, "First note")
    assert item["note"] == "First note"

    # Append second note
    append_note(item, "Second note")
    assert item["note"] == "First note\n- Second note"

    # Empty note does nothing
    append_note(item, "   ")
    assert item["note"] == "First note\n- Second note"


def test_set_title() -> None:
    """Test updating a title."""
    item: TodoItem = {
        "id": "x",
        "title": "old title",
        "status": "open",
        "bucket": "unplanned",
        "created_at": now_iso(),
        "note": "",
        "tags": [],
        "completed_at": None,
        "remind_interval_hours": None,
        "last_reminder_at": None,
    }

    set_title(item, "  new title  ")
    assert item["title"] == "new title"
