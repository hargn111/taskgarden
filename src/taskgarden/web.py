"""Small web UI and JSON API for Task Garden.

The server intentionally uses only the Python standard library. Taskgarden is a
local personal tool; avoiding a frontend/backend dependency stack keeps deploys
simple and makes the UI easy to run from the same release as the CLI.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import sys
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Literal, cast
from urllib.parse import parse_qs, unquote, urlparse

from . import config as ui_config
from . import todos

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
MAX_BODY_BYTES = 1024 * 1024
STALE_DAYS_DEFAULT = 14.0
STATIC_DIR = Path(__file__).with_name("static")


class ApiError(ValueError):
    """Expected request error that should be returned as a JSON 400/404."""

    def __init__(self, message: str, status: HTTPStatus = HTTPStatus.BAD_REQUEST):
        super().__init__(message)
        self.status = status


class TaskgardenRequestHandler(BaseHTTPRequestHandler):
    """HTTP handler for the Taskgarden UI and API."""

    server_version = "TaskgardenUI/0.1"

    def do_OPTIONS(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_common_headers()
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        try:
            parsed = urlparse(self.path)
            if parsed.path in {"/", "/tasks"}:
                self.send_static_file("index.html")
                return
            if parsed.path.startswith("/assets/"):
                self.send_static_file(parsed.path.removeprefix("/assets/"))
                return
            if parsed.path == "/api/healthz":
                self.send_json(HTTPStatus.OK, health_payload())
                return
            if parsed.path == "/api/meta":
                self.send_json(HTTPStatus.OK, meta_payload())
                return
            if parsed.path == "/api/config":
                self.send_json(HTTPStatus.OK, config_payload())
                return
            if parsed.path == "/api/tasks":
                self.send_json(HTTPStatus.OK, list_tasks(parse_qs(parsed.query)))
                return
            if parsed.path.startswith("/api/tasks/"):
                item_id = api_tail(parsed.path, "/api/tasks/")
                item = require_item(item_id)
                self.send_json(HTTPStatus.OK, {"item": serialize_item(item)})
                return
            self.send_error_response(HTTPStatus.NOT_FOUND, "Not found")
        except ApiError as exc:
            self.send_error_response(exc.status, str(exc))
        except Exception as exc:  # pragma: no cover - safety net for live service
            self.send_error_response(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        try:
            parsed = urlparse(self.path)
            body = self.read_json_body()
            if parsed.path == "/api/config/cron/preview":
                self.send_json(HTTPStatus.OK, preview_cron_payload(body))
                return
            if parsed.path == "/api/tasks":
                self.send_json(HTTPStatus.CREATED, {"item": create_task(body)})
                return
            if parsed.path.startswith("/api/tasks/") and parsed.path.endswith(
                "/touch-reminder"
            ):
                item_id = api_tail(parsed.path, "/api/tasks/").removesuffix(
                    "/touch-reminder"
                )
                self.send_json(
                    HTTPStatus.OK,
                    {"item": touch_task_reminder(item_id, body)},
                )
                return
            self.send_error_response(HTTPStatus.NOT_FOUND, "Not found")
        except ApiError as exc:
            self.send_error_response(exc.status, str(exc))
        except Exception as exc:  # pragma: no cover - safety net for live service
            self.send_error_response(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))

    def do_PATCH(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        try:
            parsed = urlparse(self.path)
            if parsed.path == "/api/config":
                body = self.read_json_body()
                self.send_json(HTTPStatus.OK, update_config_payload(body))
                return
            if parsed.path.startswith("/api/tasks/"):
                item_id = api_tail(parsed.path, "/api/tasks/")
                body = self.read_json_body()
                self.send_json(HTTPStatus.OK, {"item": update_task(item_id, body)})
                return
            self.send_error_response(HTTPStatus.NOT_FOUND, "Not found")
        except ApiError as exc:
            self.send_error_response(exc.status, str(exc))
        except Exception as exc:  # pragma: no cover - safety net for live service
            self.send_error_response(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))

    def do_DELETE(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        try:
            parsed = urlparse(self.path)
            if parsed.path.startswith("/api/tasks/"):
                item_id = api_tail(parsed.path, "/api/tasks/")
                remove_task(item_id)
                self.send_json(HTTPStatus.OK, {"ok": True, "removed": item_id})
                return
            self.send_error_response(HTTPStatus.NOT_FOUND, "Not found")
        except ApiError as exc:
            self.send_error_response(exc.status, str(exc))
        except Exception as exc:  # pragma: no cover - safety net for live service
            self.send_error_response(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))

    def read_json_body(self) -> dict[str, Any]:
        length_raw = self.headers.get("Content-Length") or "0"
        try:
            length = int(length_raw)
        except ValueError as exc:
            raise ApiError("Invalid Content-Length") from exc
        if length > MAX_BODY_BYTES:
            raise ApiError("Request body too large", HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ApiError("Invalid JSON body") from exc
        if not isinstance(payload, dict):
            raise ApiError("JSON body must be an object")
        return payload

    def send_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_common_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_error_response(self, status: HTTPStatus, message: str) -> None:
        self.send_json(status, {"ok": False, "error": message})

    def send_static_file(self, relative_path: str) -> None:
        candidate = (STATIC_DIR / unquote(relative_path)).resolve()
        if not candidate.is_relative_to(STATIC_DIR.resolve()) or not candidate.is_file():
            self.send_error_response(HTTPStatus.NOT_FOUND, "Static file not found")
            return
        body = candidate.read_bytes()
        content_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
        if candidate.suffix == ".js":
            content_type = "text/javascript"
        self.send_response(HTTPStatus.OK)
        self.send_common_headers()
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_common_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:",
        )

    def log_message(self, format: str, *args: object) -> None:
        print(f"{self.address_string()} - {format % args}", file=sys.stderr)


def api_tail(path: str, prefix: str) -> str:
    tail = unquote(path.removeprefix(prefix)).strip("/")
    if not tail:
        raise ApiError("Missing task id", HTTPStatus.NOT_FOUND)
    return tail


def health_payload() -> dict[str, Any]:
    return {
        "ok": True,
        "service": "taskgarden-ui",
        "dataPath": str(todos.DATA_PATH),
        "dataExists": todos.DATA_PATH.exists(),
        "updatedAt": todos.now_iso(),
    }


def meta_payload() -> dict[str, Any]:
    data = todos.load_data()
    counts = build_counts(data["items"])
    return {
        "updatedAt": todos.now_iso(),
        "version": data["version"],
        "dataPath": str(todos.DATA_PATH),
        "exportPath": str(todos.EXPORT_PATH) if todos.EXPORT_PATH else None,
        "counts": counts,
    }


def config_payload() -> dict[str, Any]:
    """Return UI config, theme presets, and cron preview."""
    config = ui_config.load_ui_config()
    cron = config["cron"]
    return {
        "updatedAt": todos.now_iso(),
        "config": config,
        "effectiveTheme": ui_config.effective_theme(config["theme"]),
        "themePresets": ui_config.THEME_PRESETS,
        "cronExpression": ui_config.cron_expression(cron),
        "cronPreview": ui_config.preview_cron_runs(cron),
    }


def update_config_payload(input_data: dict[str, Any]) -> dict[str, Any]:
    """Persist UI config and apply reminder cron when cron settings are supplied."""
    current = ui_config.load_ui_config()
    merged = dict(current)
    for section in ("refresh", "theme", "cron"):
        if section in input_data:
            merged[section] = input_data[section]
    config = ui_config.save_ui_config(merged)
    cron_updated = False
    if "cron" in input_data or input_data.get("applyCron") is True:
        ui_config.apply_cron_config(config["cron"])
        cron_updated = True
    return {
        "ok": True,
        "cronUpdated": cron_updated,
        **config_payload(),
    }


def preview_cron_payload(input_data: dict[str, Any]) -> dict[str, Any]:
    """Return a schedule preview for supplied unsaved cron settings."""
    current = ui_config.load_ui_config()["cron"]
    cron = dict(current)
    cron.update(input_data.get("cron", input_data))
    normalized = ui_config.normalize_cron_config(cron)
    return {
        "cron": normalized,
        "cronExpression": ui_config.cron_expression(normalized),
        "cronPreview": ui_config.preview_cron_runs(normalized),
    }


def list_tasks(query: dict[str, list[str]]) -> dict[str, Any]:
    data = todos.load_data()
    source_items = data["items"]
    filtered = list(source_items)
    now = datetime.now(timezone.utc)

    status = single_query(query, "status")
    if status and status != "all":
        validate_choice(status, todos.VALID_STATUS, "status")
        filtered = [item for item in filtered if item.get("status") == status]

    bucket = single_query(query, "bucket")
    if bucket and bucket != "all":
        validate_choice(bucket, todos.VALID_BUCKETS, "bucket")
        filtered = [item for item in filtered if item.get("bucket") == bucket]

    tag = single_query(query, "tag")
    if tag and tag != "all":
        filtered = [item for item in filtered if tag in item.get("tags", [])]

    search = (single_query(query, "q") or "").strip().casefold()
    if search:
        filtered = [item for item in filtered if item_matches_search(item, search)]

    if trueish(single_query(query, "due_reminders")):
        filtered = [item for item in filtered if todos.reminder_due(item, now)]

    stale_days = single_query(query, "stale_days")
    if stale_days:
        days = coerce_float(stale_days, "stale_days")
        filtered = [item for item in filtered if todos.stale_task_due(item, days, now)]

    filtered = sorted(
        filtered,
        key=lambda item: (
            0 if item.get("status") == "open" else 1,
            item.get("bucket") != "planned",
            item.get("created_at") or "",
        ),
        reverse=False,
    )

    return {
        "updatedAt": todos.now_iso(),
        "version": data["version"],
        "items": [serialize_item(item) for item in filtered],
        "counts": build_counts(source_items),
        "tags": build_tag_counts(source_items),
    }


def single_query(query: dict[str, list[str]], key: str) -> str | None:
    values = query.get(key)
    return values[0] if values else None


def item_matches_search(item: todos.TodoItem, search: str) -> bool:
    haystack = " ".join(
        [
            item.get("id", ""),
            item.get("title", ""),
            item.get("note", ""),
            " ".join(item.get("tags", [])),
        ]
    ).casefold()
    return search in haystack


def build_counts(items: list[todos.TodoItem]) -> dict[str, int]:
    now = datetime.now(timezone.utc)
    return {
        "total": len(items),
        "open": sum(1 for item in items if item.get("status") == "open"),
        "done": sum(1 for item in items if item.get("status") == "done"),
        "planned": sum(
            1
            for item in items
            if item.get("status") == "open" and item.get("bucket") == "planned"
        ),
        "unplanned": sum(
            1
            for item in items
            if item.get("status") == "open" and item.get("bucket") == "unplanned"
        ),
        "withReminders": sum(
            1
            for item in items
            if item.get("status") == "open"
            and item.get("remind_interval_hours") is not None
        ),
        "dueReminders": sum(1 for item in items if todos.reminder_due(item, now)),
        "stalePlanned": sum(
            1 for item in items if todos.stale_task_due(item, STALE_DAYS_DEFAULT, now)
        ),
    }


def build_tag_counts(items: list[todos.TodoItem]) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for item in items:
        for tag in item.get("tags", []):
            counts[tag] = counts.get(tag, 0) + 1
    return [
        {"tag": tag, "count": count}
        for tag, count in sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))
    ]


def create_task(input_data: dict[str, Any]) -> dict[str, Any]:
    title = clean_title(input_data.get("title"))
    bucket = clean_bucket(input_data.get("bucket", "unplanned"))
    note = clean_note(input_data.get("note", ""))
    tags = clean_tags(input_data.get("tags", []))
    remind_hours = clean_optional_hours(
        input_data.get("remind_interval_hours", input_data.get("remindIntervalHours"))
    )

    data = todos.load_data()
    item = todos.create_item(
        title=title,
        note=note,
        tags=tags,
        bucket=bucket,
        remind_interval_hours=remind_hours,
    )
    data["items"].append(item)
    todos.save_data(data)
    return serialize_item(item)


def update_task(item_id: str, input_data: dict[str, Any]) -> dict[str, Any]:
    data = todos.load_data()
    item = todos.find_item(data, item_id)
    if not item:
        raise ApiError(f"Task not found: {item_id}", HTTPStatus.NOT_FOUND)

    if "title" in input_data:
        todos.set_title(item, clean_title(input_data["title"]))
    if "bucket" in input_data:
        item["bucket"] = clean_bucket(input_data["bucket"])
    if "status" in input_data:
        status = clean_status(input_data["status"])
        if status != item.get("status"):
            item["completed_at"] = todos.now_iso() if status == "done" else None
        elif status == "done" and not item.get("completed_at"):
            item["completed_at"] = todos.now_iso()
        item["status"] = status
    if "note" in input_data:
        item["note"] = clean_note(input_data["note"])
    append_value = input_data.get("append_note", input_data.get("appendNote"))
    if append_value:
        todos.append_note(item, str(append_value))
    if "tags" in input_data:
        item["tags"] = clean_tags(input_data["tags"])
    if "remind_interval_hours" in input_data or "remindIntervalHours" in input_data:
        item["remind_interval_hours"] = clean_optional_hours(
            input_data.get("remind_interval_hours", input_data.get("remindIntervalHours"))
        )
        if item["remind_interval_hours"] is None:
            item["last_reminder_at"] = None
    if "last_reminder_at" in input_data or "lastReminderAt" in input_data:
        value = input_data.get("last_reminder_at", input_data.get("lastReminderAt"))
        item["last_reminder_at"] = clean_optional_iso(value)

    todos.save_data(data)
    return serialize_item(item)


def touch_task_reminder(item_id: str, input_data: dict[str, Any]) -> dict[str, Any]:
    data = todos.load_data()
    item = todos.find_item(data, item_id)
    if not item:
        raise ApiError(f"Task not found: {item_id}", HTTPStatus.NOT_FOUND)
    at_value = input_data.get("at")
    item["last_reminder_at"] = clean_optional_iso(at_value) if at_value else todos.now_iso()
    todos.save_data(data)
    return serialize_item(item)


def remove_task(item_id: str) -> None:
    data = todos.load_data()
    before = len(data["items"])
    data["items"] = [item for item in data["items"] if item.get("id") != item_id]
    if len(data["items"]) == before:
        raise ApiError(f"Task not found: {item_id}", HTTPStatus.NOT_FOUND)
    todos.save_data(data)


def require_item(item_id: str) -> todos.TodoItem:
    data = todos.load_data()
    item = todos.find_item(data, item_id)
    if not item:
        raise ApiError(f"Task not found: {item_id}", HTTPStatus.NOT_FOUND)
    return item


def serialize_item(item: todos.TodoItem) -> dict[str, Any]:
    return dict(todos.normalize_item(dict(item)))


def clean_title(value: Any) -> str:
    if not isinstance(value, str):
        raise ApiError("Title is required")
    title = value.strip()
    if not title:
        raise ApiError("Title cannot be empty")
    return title


def clean_note(value: Any) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ApiError("Note must be a string")
    return value.strip()


def clean_tags(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, str):
        raw_tags = value.replace("\n", ",").split(",")
    elif isinstance(value, list):
        raw_tags = value
    else:
        raise ApiError("Tags must be a list or comma-separated string")
    return sorted(
        {
            str(tag).strip().lstrip("#")
            for tag in raw_tags
            if str(tag).strip().lstrip("#")
        }
    )


def clean_bucket(value: Any) -> Literal["planned", "unplanned"]:
    if not isinstance(value, str):
        raise ApiError("Bucket must be a string")
    return cast(
        Literal["planned", "unplanned"],
        validate_choice(value, todos.VALID_BUCKETS, "bucket"),
    )


def clean_status(value: Any) -> Literal["open", "done"]:
    if not isinstance(value, str):
        raise ApiError("Status must be a string")
    return cast(
        Literal["open", "done"], validate_choice(value, todos.VALID_STATUS, "status")
    )


def validate_choice(value: str, choices: set[str], field_name: str) -> str:
    if value not in choices:
        options = ", ".join(sorted(choices))
        raise ApiError(f"Invalid {field_name}: {value}. Expected one of: {options}")
    return value


def clean_optional_hours(value: Any) -> float | None:
    if value in (None, ""):
        return None
    hours = coerce_float(value, "reminder hours")
    if hours <= 0:
        raise ApiError("Reminder hours must be greater than 0")
    return hours


def coerce_float(value: Any, field_name: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ApiError(f"Invalid {field_name}: {value}") from exc


def clean_optional_iso(value: Any) -> str | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise ApiError("Timestamp must be an ISO 8601 string")
    try:
        return todos.normalize_iso(value)
    except ValueError as exc:
        raise ApiError(f"Invalid timestamp: {value}") from exc


def trueish(value: str | None) -> bool:
    return str(value or "").casefold() in {"1", "true", "yes", "on"}


def serve(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
    server = ThreadingHTTPServer((host, port), TaskgardenRequestHandler)
    url_host = "127.0.0.1" if host in {"", "0.0.0.0"} else host
    print(f"Taskgarden UI listening on http://{url_host}:{port}", flush=True)
    server.serve_forever()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Taskgarden web UI.")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Bind host")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Bind port")
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        serve(host=args.host, port=args.port)
    except KeyboardInterrupt:
        print("Taskgarden UI stopped.", file=sys.stderr)


if __name__ == "__main__":
    main()
