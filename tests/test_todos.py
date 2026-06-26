"""Unit tests for Task Garden."""

import json
from pathlib import Path
from unittest.mock import patch
import subprocess

from argparse import Namespace

import taskgarden.cli as tg_cli
from taskgarden.reminders import generate_reminder_message, load_reminder_config
from taskgarden.todos import (
    TodoData,
    TodoItem,
    append_note,
    backup_path,
    create_item,
    find_item,
    load_data,
    normalize_iso,
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
        assert not backup_path(data_path, 1).exists()


def test_save_data_creates_rolling_backups(tmp_path: Path) -> None:
    """Test that repeated saves create numbered rolling backups."""
    data_path = tmp_path / "todos.json"
    with patch("taskgarden.todos.DATA_PATH", data_path):
        for index in range(7):
            save_data(
                {
                    "version": 2,
                    "items": [
                        {
                            "id": f"id{index}",
                            "title": f"title-{index}",
                        }
                    ],
                }
            )

        current = load_data()
        assert current["items"][0]["id"] == "id6"
        assert backup_path(data_path, 1).exists()
        assert backup_path(data_path, 2).exists()
        assert backup_path(data_path, 3).exists()
        assert backup_path(data_path, 4).exists()
        assert backup_path(data_path, 5).exists()
        assert not backup_path(data_path, 6).exists()

        newest_backup = normalize_item(json_load(backup_path(data_path, 1))["items"][0])
        oldest_backup = normalize_item(json_load(backup_path(data_path, 5))["items"][0])
        assert newest_backup["id"] == "id5"
        assert oldest_backup["id"] == "id1"


def test_save_data_leaves_no_temp_files(tmp_path: Path) -> None:
    """Test that atomic save does not leave temp files behind."""
    data_path = tmp_path / "todos.json"
    with patch("taskgarden.todos.DATA_PATH", data_path):
        save_data({"version": 2, "items": [{"id": "a", "title": "alpha"}]})
        leftovers = list(tmp_path.glob(".todos.json.*.tmp"))
        assert leftovers == []
        assert load_data()["items"][0]["id"] == "a"


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


def json_load(path: Path) -> dict:
    return json.loads(path.read_text())


def test_normalize_iso() -> None:
    assert normalize_iso("2026-04-13T00:00:00Z") == "2026-04-13T00:00:00+00:00"


def test_touch_reminder_at_timestamp(tmp_path: Path) -> None:
    data_path = tmp_path / "todos.json"
    with patch("taskgarden.todos.DATA_PATH", data_path), patch("taskgarden.cli.load_data", side_effect=tg_cli.load_data), patch("taskgarden.cli.save_data", side_effect=tg_cli.save_data):
        save_data({"version": 2, "items": [{"id": "x", "title": "alpha"}]})
        tg_cli.cmd_touch_reminder(Namespace(id="x", at="2026-04-13T00:00:00Z"))
        data = load_data()
        assert data["items"][0]["last_reminder_at"] == "2026-04-13T00:00:00+00:00"


def test_set_reminder_touch_now_at_timestamp(tmp_path: Path) -> None:
    data_path = tmp_path / "todos.json"
    with patch("taskgarden.todos.DATA_PATH", data_path), patch("taskgarden.cli.load_data", side_effect=tg_cli.load_data), patch("taskgarden.cli.save_data", side_effect=tg_cli.save_data):
        save_data({"version": 2, "items": [{"id": "x", "title": "alpha"}]})
        tg_cli.cmd_set_reminder(
            Namespace(id="x", hours=6.0, touch_now=True, at="2026-04-13T00:00:00Z", clear=False)
        )
        data = load_data()
        assert data["items"][0]["remind_interval_hours"] == 6.0
        assert data["items"][0]["last_reminder_at"] == "2026-04-13T00:00:00+00:00"


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


def test_load_reminder_config_defaults(tmp_path: Path) -> None:
    config_path = tmp_path / "missing-reminder-config.json"
    config = load_reminder_config(config_path)
    assert config["primaryModel"] == "plain"
    assert config["fallbackModels"] == []
    assert config["timeoutSeconds"] == 90


def test_generate_reminder_message_uses_model_then_returns_text() -> None:
    items = [
        {
            "id": "x",
            "title": "Look up batteries",
            "status": "open",
            "bucket": "planned",
            "created_at": "2026-01-01T00:00:00+00:00",
            "note": "",
            "tags": [],
            "completed_at": None,
            "remind_interval_hours": 2.0,
            "last_reminder_at": None,
        }
    ]
    config = {
        "primaryModel": "google/gemini-3.1-flash-lite-preview",
        "fallbackModels": ["plain"],
        "timeoutSeconds": 30,
        "stylePrompt": "Brief and useful.",
    }

    def fake_runner(*args, **kwargs):
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=0,
            stdout=json.dumps(
                {
                    "provider": "google",
                    "model": "gemini-3.1-flash-lite-preview",
                    "outputs": [{"text": "Don't forget to look up batteries."}],
                }
            ),
            stderr="",
        )

    result = generate_reminder_message(items, config=config, runner=fake_runner)
    assert result["mode"] == "model"
    assert result["provider"] == "google"
    assert result["model"] == "gemini-3.1-flash-lite-preview"
    assert result["text"] == "Don't forget to look up batteries."
    assert result["attempts"] == [{"model": "google/gemini-3.1-flash-lite-preview", "ok": True}]


def test_generate_reminder_message_falls_back_to_plain() -> None:
    items = [
        {
            "id": "x",
            "title": "Fallback test reminder",
            "status": "open",
            "bucket": "planned",
            "created_at": "2026-01-01T00:00:00+00:00",
            "note": "",
            "tags": [],
            "completed_at": None,
            "remind_interval_hours": 2.0,
            "last_reminder_at": None,
        }
    ]
    config = {
        "primaryModel": "google/not-a-real-model",
        "fallbackModels": ["plain"],
        "timeoutSeconds": 5,
        "stylePrompt": "Brief and useful.",
    }

    def fake_runner(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args[0], timeout=5)

    result = generate_reminder_message(items, config=config, runner=fake_runner)
    assert result["mode"] == "plain"
    assert result["model"] == "plain"
    assert result["text"] == "Reminder: Fallback test reminder"
    assert result["attempts"][0]["model"] == "google/not-a-real-model"
    assert result["attempts"][0]["ok"] is False


def test_cmd_reminder_message_due_reminders(tmp_path: Path, capsys) -> None:
    data_path = tmp_path / "todos.json"
    config_path = tmp_path / "reminder-config.json"
    config_path.write_text(
        json.dumps(
            {
                "messageGeneration": {
                    "primaryModel": "plain",
                    "fallbackModels": [],
                    "timeoutSeconds": 30,
                }
            }
        )
    )

    with patch("taskgarden.todos.DATA_PATH", data_path), patch(
        "taskgarden.reminders.DEFAULT_REMINDER_CONFIG_PATH", config_path
    ):
        save_data(
            {
                "version": 2,
                "items": [
                    {
                        "id": "due1",
                        "title": "Due reminder",
                        "bucket": "planned",
                        "status": "open",
                        "created_at": "2026-01-01T00:00:00+00:00",
                        "completed_at": None,
                        "last_reminder_at": None,
                        "remind_interval_hours": 1.0,
                        "note": "",
                        "tags": [],
                    },
                    {
                        "id": "later1",
                        "title": "Not due yet",
                        "bucket": "planned",
                        "status": "open",
                        "created_at": now_iso(),
                        "completed_at": None,
                        "last_reminder_at": None,
                        "remind_interval_hours": 24.0,
                        "note": "",
                        "tags": [],
                    },
                ],
            }
        )
        tg_cli.cmd_reminder_message(Namespace(bucket="planned", due_reminders=True))
        output = json.loads(capsys.readouterr().out)
        assert output["mode"] == "plain"
        assert output["text"] == "Reminder: Due reminder"
