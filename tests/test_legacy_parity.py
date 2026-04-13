"""Parity tests between the legacy todo script and Task Garden.

These tests intentionally cover only the overlapping feature set.
They do not assert future roadmap features such as a canceled status.
"""

from __future__ import annotations

import importlib.util
import io
import json
from argparse import Namespace
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import taskgarden.cli as tg_cli
import taskgarden.todos as tg_todos

LEGACY_TODO_PATH = Path(__file__).parent / "fixtures" / "legacy_todo.py"


spec = importlib.util.spec_from_file_location("legacy_todo", LEGACY_TODO_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Could not load legacy todo script from {LEGACY_TODO_PATH}")
legacy_todo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(legacy_todo)


FIXED_NOW = "2026-04-12T21:15:00+00:00"
FIXED_ID_HEX = "abc12345deadbeef"


def sample_data() -> dict:
    return {
        "version": 2,
        "items": [
            {
                "id": "plan001",
                "title": "Planned due item",
                "note": "first line",
                "tags": ["b", "a", "b"],
                "status": "open",
                "bucket": "planned",
                "created_at": "2026-04-10T00:00:00+00:00",
                "completed_at": None,
                "remind_interval_hours": 12.0,
                "last_reminder_at": "2026-04-11T00:00:00+00:00",
            },
            {
                "id": "unplan01",
                "title": "Unplanned item",
                "note": "",
                "tags": ["solo"],
                "status": "open",
                "bucket": "unplanned",
                "created_at": "2026-04-12T18:00:00+00:00",
                "completed_at": None,
                "remind_interval_hours": None,
                "last_reminder_at": None,
            },
            {
                "id": "done0001",
                "title": "Done item",
                "note": "",
                "tags": [],
                "status": "done",
                "bucket": "planned",
                "created_at": "2026-04-01T00:00:00+00:00",
                "completed_at": "2026-04-02T00:00:00+00:00",
                "remind_interval_hours": 6.0,
                "last_reminder_at": "2026-04-02T00:00:00+00:00",
            },
        ],
    }


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text())


def run_legacy(func_name: str, data_path: Path, **kwargs) -> tuple[str, dict]:
    write_json(data_path, sample_data())
    buffer = io.StringIO()
    func = getattr(legacy_todo, func_name)
    with patch.object(legacy_todo, "DATA_PATH", data_path):
        with patch.object(legacy_todo, "now_iso", return_value=FIXED_NOW):
            with patch.object(legacy_todo.uuid, "uuid4") as mock_uuid:
                mock_uuid.return_value.hex = FIXED_ID_HEX
                with redirect_stdout(buffer):
                    func(Namespace(**kwargs))
    return buffer.getvalue(), read_json(data_path)


def run_taskgarden(func_name: str, data_path: Path, **kwargs) -> tuple[str, dict]:
    write_json(data_path, sample_data())
    buffer = io.StringIO()
    func = getattr(tg_cli, func_name)
    with patch.object(tg_todos, "DATA_PATH", data_path):
        with patch.object(tg_todos, "now_iso", return_value=FIXED_NOW):
            with patch.object(tg_cli, "now_iso", return_value=FIXED_NOW):
                with patch.object(tg_todos.uuid, "uuid4") as mock_uuid:
                    mock_uuid.return_value.hex = FIXED_ID_HEX
                    with redirect_stdout(buffer):
                        func(Namespace(**kwargs))
    return buffer.getvalue(), read_json(data_path)


def test_normalize_item_parity() -> None:
    raw = {"id": "x", "title": "test", "tags": ["b", "a", "b"], "status": "bad"}
    assert legacy_todo.normalize_item(dict(raw)) == tg_todos.normalize_item(dict(raw))


def test_reminder_due_parity() -> None:
    item = sample_data()["items"][0]
    now = legacy_todo.parse_iso(FIXED_NOW)
    assert legacy_todo.reminder_due(dict(item), now) == tg_todos.reminder_due(dict(item), now)


def test_list_open_output_parity(tmp_path: Path) -> None:
    legacy_out, _ = run_legacy(
        "cmd_list",
        tmp_path / "legacy.json",
        all=False,
        tag=None,
        bucket=None,
        due_reminders=False,
    )
    taskgarden_out, _ = run_taskgarden(
        "cmd_list",
        tmp_path / "taskgarden.json",
        all=False,
        tag=None,
        bucket=None,
        due_reminders=False,
        stale_days=None,
    )
    assert legacy_out == taskgarden_out


def test_list_all_output_parity(tmp_path: Path) -> None:
    legacy_out, _ = run_legacy(
        "cmd_list",
        tmp_path / "legacy.json",
        all=True,
        tag=None,
        bucket=None,
        due_reminders=False,
    )
    taskgarden_out, _ = run_taskgarden(
        "cmd_list",
        tmp_path / "taskgarden.json",
        all=True,
        tag=None,
        bucket=None,
        due_reminders=False,
        stale_days=None,
    )
    assert legacy_out == taskgarden_out


def test_list_bucket_filter_parity(tmp_path: Path) -> None:
    legacy_out, _ = run_legacy(
        "cmd_list",
        tmp_path / "legacy.json",
        all=False,
        tag=None,
        bucket="planned",
        due_reminders=False,
    )
    taskgarden_out, _ = run_taskgarden(
        "cmd_list",
        tmp_path / "taskgarden.json",
        all=False,
        tag=None,
        bucket="planned",
        due_reminders=False,
        stale_days=None,
    )
    assert legacy_out == taskgarden_out


def test_list_tag_filter_parity(tmp_path: Path) -> None:
    legacy_out, _ = run_legacy(
        "cmd_list",
        tmp_path / "legacy.json",
        all=False,
        tag="solo",
        bucket=None,
        due_reminders=False,
    )
    taskgarden_out, _ = run_taskgarden(
        "cmd_list",
        tmp_path / "taskgarden.json",
        all=False,
        tag="solo",
        bucket=None,
        due_reminders=False,
        stale_days=None,
    )
    assert legacy_out == taskgarden_out


def test_list_due_reminders_parity(tmp_path: Path) -> None:
    legacy_out, _ = run_legacy(
        "cmd_list",
        tmp_path / "legacy.json",
        all=False,
        tag=None,
        bucket="planned",
        due_reminders=True,
    )
    taskgarden_out, _ = run_taskgarden(
        "cmd_list",
        tmp_path / "taskgarden.json",
        all=False,
        tag=None,
        bucket="planned",
        due_reminders=True,
        stale_days=None,
    )
    assert legacy_out == taskgarden_out


def test_add_parity(tmp_path: Path) -> None:
    legacy_out, legacy_json = run_legacy(
        "cmd_add",
        tmp_path / "legacy.json",
        title="Added item",
        note="hello",
        tags=["z", "a"],
        bucket="planned",
        remind_interval_hours=6.0,
    )
    taskgarden_out, taskgarden_json = run_taskgarden(
        "cmd_add",
        tmp_path / "taskgarden.json",
        title="Added item",
        note="hello",
        tags=["z", "a"],
        bucket="planned",
        remind_interval_hours=6.0,
    )
    assert json.loads(legacy_out) == json.loads(taskgarden_out)
    assert legacy_json == taskgarden_json


def test_done_parity(tmp_path: Path) -> None:
    _, legacy_json = run_legacy("cmd_done", tmp_path / "legacy.json", id="plan001")
    _, taskgarden_json = run_taskgarden("cmd_done", tmp_path / "taskgarden.json", id="plan001")
    assert legacy_json == taskgarden_json


def test_reopen_parity(tmp_path: Path) -> None:
    _, legacy_json = run_legacy("cmd_reopen", tmp_path / "legacy.json", id="done0001")
    _, taskgarden_json = run_taskgarden("cmd_reopen", tmp_path / "taskgarden.json", id="done0001")
    assert legacy_json == taskgarden_json


def test_remove_parity(tmp_path: Path) -> None:
    legacy_out, legacy_json = run_legacy("cmd_remove", tmp_path / "legacy.json", id="unplan01")
    taskgarden_out, taskgarden_json = run_taskgarden("cmd_remove", tmp_path / "taskgarden.json", id="unplan01")
    assert legacy_out == taskgarden_out
    assert legacy_json == taskgarden_json


def test_set_bucket_parity(tmp_path: Path) -> None:
    _, legacy_json = run_legacy(
        "cmd_set_bucket", tmp_path / "legacy.json", id="unplan01", bucket="planned"
    )
    _, taskgarden_json = run_taskgarden(
        "cmd_set_bucket", tmp_path / "taskgarden.json", id="unplan01", bucket="planned"
    )
    assert legacy_json == taskgarden_json


def test_note_append_parity(tmp_path: Path) -> None:
    _, legacy_json = run_legacy(
        "cmd_note", tmp_path / "legacy.json", id="plan001", text="follow-up"
    )
    _, taskgarden_json = run_taskgarden(
        "cmd_note", tmp_path / "taskgarden.json", id="plan001", text="follow-up"
    )
    assert legacy_json == taskgarden_json


def test_set_reminder_parity(tmp_path: Path) -> None:
    _, legacy_json = run_legacy(
        "cmd_set_reminder",
        tmp_path / "legacy.json",
        id="unplan01",
        hours=4.0,
        clear=False,
        touch_now=True,
    )
    _, taskgarden_json = run_taskgarden(
        "cmd_set_reminder",
        tmp_path / "taskgarden.json",
        id="unplan01",
        hours=4.0,
        clear=False,
        touch_now=True,
    )
    assert legacy_json == taskgarden_json


def test_clear_reminder_parity(tmp_path: Path) -> None:
    _, legacy_json = run_legacy(
        "cmd_set_reminder",
        tmp_path / "legacy.json",
        id="plan001",
        hours=None,
        clear=True,
        touch_now=False,
    )
    _, taskgarden_json = run_taskgarden(
        "cmd_set_reminder",
        tmp_path / "taskgarden.json",
        id="plan001",
        hours=None,
        clear=True,
        touch_now=False,
    )
    assert legacy_json == taskgarden_json


def test_touch_reminder_parity(tmp_path: Path) -> None:
    _, legacy_json = run_legacy(
        "cmd_touch_reminder", tmp_path / "legacy.json", id="unplan01"
    )
    _, taskgarden_json = run_taskgarden(
        "cmd_touch_reminder", tmp_path / "taskgarden.json", id="unplan01"
    )
    assert legacy_json == taskgarden_json
