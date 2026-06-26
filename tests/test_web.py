"""Tests for the bundled Taskgarden web API."""

import json
from contextlib import contextmanager
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from typing import Iterator
from unittest.mock import patch

from taskgarden import config, todos
from taskgarden.web import TaskgardenRequestHandler


@contextmanager
def run_test_server(tmp_path: Path) -> Iterator[tuple[str, int]]:
    data_path = tmp_path / "todos.json"
    export_path = tmp_path / "export-todos.json"
    config_path = tmp_path / "ui-config.json"
    backup_dir = tmp_path / "crontab-backups"
    with patch("taskgarden.todos.DATA_PATH", data_path), patch(
        "taskgarden.todos.EXPORT_PATH", export_path
    ), patch("taskgarden.config.UI_CONFIG_PATH", config_path), patch(
        "taskgarden.config.CRONTAB_BACKUP_DIR", backup_dir
    ):
        todos.save_data({"version": 2, "items": []})
        server = ThreadingHTTPServer(("127.0.0.1", 0), TaskgardenRequestHandler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield "127.0.0.1", int(server.server_port)
        finally:
            server.shutdown()
            thread.join(timeout=5)
            server.server_close()


def request_json(
    address: tuple[str, int],
    method: str,
    path: str,
    body: dict | None = None,
) -> tuple[int, dict]:
    connection = HTTPConnection(*address, timeout=5)
    payload = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Content-Type": "application/json"} if body is not None else {}
    connection.request(method, path, body=payload, headers=headers)
    response = connection.getresponse()
    data = json.loads(response.read().decode("utf-8"))
    connection.close()
    return response.status, data


def test_web_api_create_update_touch_delete(tmp_path: Path) -> None:
    with run_test_server(tmp_path) as address:
        status, created = request_json(
            address,
            "POST",
            "/api/tasks",
            {
                "title": "Build the Taskgarden UI",
                "bucket": "planned",
                "tags": ["ui", "taskgarden"],
                "remind_interval_hours": 6,
            },
        )
        assert status == 201
        item_id = created["item"]["id"]
        assert created["item"]["bucket"] == "planned"

        status, updated = request_json(
            address,
            "PATCH",
            f"/api/tasks/{item_id}",
            {
                "title": "Build the full Taskgarden UI",
                "status": "done",
                "note": "Verified through the API.",
                "append_note": "Append still works.",
                "tags": "ui, verification",
                "remind_interval_hours": None,
            },
        )
        assert status == 200
        assert updated["item"]["title"] == "Build the full Taskgarden UI"
        assert updated["item"]["status"] == "done"
        assert updated["item"]["completed_at"] is not None
        assert updated["item"]["note"] == "Verified through the API.\n- Append still works."
        assert updated["item"]["tags"] == ["ui", "verification"]
        assert updated["item"]["remind_interval_hours"] is None

        status, touched = request_json(
            address,
            "POST",
            f"/api/tasks/{item_id}/touch-reminder",
            {"at": "2026-04-13T00:00:00Z"},
        )
        assert status == 200
        assert touched["item"]["last_reminder_at"] == "2026-04-13T00:00:00+00:00"

        status, listed = request_json(address, "GET", "/api/tasks?status=all")
        assert status == 200
        assert listed["counts"]["total"] == 1
        assert listed["items"][0]["id"] == item_id

        status, removed = request_json(address, "DELETE", f"/api/tasks/{item_id}")
        assert status == 200
        assert removed == {"ok": True, "removed": item_id}

        status, listed = request_json(address, "GET", "/api/tasks?status=all")
        assert status == 200
        assert listed["counts"]["total"] == 0


def test_web_serves_static_ui(tmp_path: Path) -> None:
    with run_test_server(tmp_path) as address:
        connection = HTTPConnection(*address, timeout=5)
        connection.request("GET", "/")
        response = connection.getresponse()
        body = response.read().decode("utf-8")
        connection.close()

    assert response.status == 200
    assert "Taskgarden" in body
    assert "/assets/app.js" in body
    assert "/assets/favicon.svg" in body


def test_web_config_api_saves_theme_and_applies_cron(tmp_path: Path) -> None:
    written_crontabs: list[str] = []

    existing_crontab = "# BEGIN FREYA_AUTOMATION\nPATH=/usr/bin:/bin\n# END FREYA_AUTOMATION\n"
    with patch("taskgarden.config.read_crontab", return_value=existing_crontab), patch(
        "taskgarden.config.write_crontab", side_effect=written_crontabs.append
    ):
        with run_test_server(tmp_path) as address:
            status, preview = request_json(
                address,
                "POST",
                "/api/config/cron/preview",
                {"startTimeEastern": "09:30", "intervalHours": 3, "runsPerDay": 4},
            )
            assert status == 200
            assert preview["cronExpression"] == "30 9,12,15,18 * * *"
            label = preview["cronPreview"][0]["label"]
            assert "ET" in label or "EDT" in label or "EST" in label

            status, saved = request_json(
                address,
                "PATCH",
                "/api/config",
                {
                    "refresh": {"enabled": True, "intervalSeconds": 60},
                    "theme": {"preset": "blueprint", "custom": {"accent": "#123456"}},
                    "cron": {
                        "enabled": True,
                        "startTimeEastern": "09:30",
                        "intervalHours": 3,
                        "runsPerDay": 4,
                        "jobPath": config.REMINDER_JOB_PATH,
                    },
                },
            )

    assert status == 200
    assert saved["config"]["refresh"] == {"enabled": True, "intervalSeconds": 60}
    assert saved["effectiveTheme"]["accent"] == "#123456"
    assert saved["cronUpdated"] is True
    assert written_crontabs
    assert "CRON_TZ=America/New_York" in written_crontabs[0]
    assert "30 9,12,15,18 * * *" in written_crontabs[0]
