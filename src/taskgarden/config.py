"""Persistent UI configuration and reminder-cron helpers for Taskgarden."""

from __future__ import annotations

import json
import os
import re
import subprocess
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

UI_CONFIG_PATH = Path(
    os.getenv("TASKGARDEN_UI_CONFIG_PATH", "/root/hermes-workspace/state/taskgarden-ui-config.json")
)
CRONTAB_BACKUP_DIR = Path(
    os.getenv(
        "TASKGARDEN_CRONTAB_BACKUP_DIR",
        "/root/hermes-workspace/state/automation/crontab-backups",
    )
)
REMINDER_JOB_PATH = "/root/hermes-workspace/scripts/jobs/planned_todo_reminder.sh"
EASTERN_TZ = ZoneInfo("America/New_York")
CRON_BEGIN = "# BEGIN TASKGARDEN_REMINDER_CRON"
CRON_END = "# END TASKGARDEN_REMINDER_CRON"
COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")

THEME_PRESETS: dict[str, dict[str, str]] = {
    "garden": {
        "label": "Garden ledger",
        "bg": "#ede8d8",
        "panel": "#f7f2e4",
        "panelStrong": "#fffaf0",
        "ink": "#171a13",
        "muted": "#66705b",
        "line": "#c8bea6",
        "lineStrong": "#8f9876",
        "accent": "#52692f",
        "accentStrong": "#304412",
        "warning": "#94681b",
        "danger": "#8c2f22",
    },
    "ink": {
        "label": "Ink and paper",
        "bg": "#f1eee6",
        "panel": "#fbf8ef",
        "panelStrong": "#fffdf7",
        "ink": "#111111",
        "muted": "#5f5d55",
        "line": "#c7c0b1",
        "lineStrong": "#2a2a2a",
        "accent": "#383838",
        "accentStrong": "#121212",
        "warning": "#9a6516",
        "danger": "#98281f",
    },
    "blueprint": {
        "label": "Blueprint",
        "bg": "#e9eef2",
        "panel": "#f8fbff",
        "panelStrong": "#ffffff",
        "ink": "#122033",
        "muted": "#53657d",
        "line": "#b6c2d1",
        "lineStrong": "#5d78a2",
        "accent": "#2d5f9a",
        "accentStrong": "#183b64",
        "warning": "#9b6b1f",
        "danger": "#9b2f35",
    },
    "ember": {
        "label": "Ember",
        "bg": "#241611",
        "panel": "#2f211b",
        "panelStrong": "#3b2a22",
        "ink": "#f5eadc",
        "muted": "#c5ad98",
        "line": "#5f4335",
        "lineStrong": "#d48a4a",
        "accent": "#e08b43",
        "accentStrong": "#ffbd6d",
        "warning": "#f1c35f",
        "danger": "#ff806e",
    },
    "terminal": {
        "label": "Terminal moss",
        "bg": "#071009",
        "panel": "#0e1a10",
        "panelStrong": "#142316",
        "ink": "#e7ffe6",
        "muted": "#9eb79b",
        "line": "#29412c",
        "lineStrong": "#4e7e52",
        "accent": "#7fd46c",
        "accentStrong": "#a8ff91",
        "warning": "#d6bd56",
        "danger": "#ff6f6f",
    },
}
THEME_COLOR_KEYS = [
    "bg",
    "panel",
    "panelStrong",
    "ink",
    "muted",
    "line",
    "lineStrong",
    "accent",
    "accentStrong",
    "warning",
    "danger",
]

DEFAULT_CONFIG: dict[str, Any] = {
    "version": 1,
    "refresh": {"enabled": False, "intervalSeconds": 30},
    "theme": {"preset": "garden", "custom": {}},
    "cron": {
        "enabled": True,
        "startTimeEastern": "10:00",
        "intervalHours": 2,
        "runsPerDay": 7,
        "jobPath": REMINDER_JOB_PATH,
    },
}


def load_ui_config(path: Path | None = None) -> dict[str, Any]:
    """Load and normalize UI config from disk."""
    config_path = path or UI_CONFIG_PATH
    if not config_path.exists():
        return deepcopy(DEFAULT_CONFIG)
    try:
        raw = json.loads(config_path.read_text())
    except json.JSONDecodeError:
        return deepcopy(DEFAULT_CONFIG)
    if not isinstance(raw, dict):
        return deepcopy(DEFAULT_CONFIG)
    return normalize_ui_config(raw)


def save_ui_config(config: dict[str, Any], path: Path | None = None) -> dict[str, Any]:
    """Normalize and atomically save UI config."""
    normalized = normalize_ui_config(config)
    config_path = path or UI_CONFIG_PATH
    config_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = config_path.with_name(f".{config_path.name}.tmp")
    temp_path.write_text(json.dumps(normalized, indent=2, sort_keys=True) + "\n")
    temp_path.replace(config_path)
    return normalized


def normalize_ui_config(raw: dict[str, Any]) -> dict[str, Any]:
    """Merge user config with defaults and discard invalid values."""
    merged = deepcopy(DEFAULT_CONFIG)
    if isinstance(raw.get("refresh"), dict):
        merged["refresh"] = normalize_refresh_config(raw["refresh"])
    if isinstance(raw.get("theme"), dict):
        merged["theme"] = normalize_theme_config(raw["theme"])
    if isinstance(raw.get("cron"), dict):
        merged["cron"] = normalize_cron_config(raw["cron"])
    merged["version"] = 1
    return merged


def normalize_refresh_config(raw: dict[str, Any]) -> dict[str, Any]:
    interval = raw.get("intervalSeconds", DEFAULT_CONFIG["refresh"]["intervalSeconds"])
    try:
        interval_seconds = int(interval)
    except (TypeError, ValueError):
        interval_seconds = DEFAULT_CONFIG["refresh"]["intervalSeconds"]
    interval_seconds = min(max(interval_seconds, 5), 3600)
    return {"enabled": bool(raw.get("enabled", False)), "intervalSeconds": interval_seconds}


def normalize_theme_config(raw: dict[str, Any]) -> dict[str, Any]:
    preset = raw.get("preset") if isinstance(raw.get("preset"), str) else "garden"
    if preset not in THEME_PRESETS and preset != "custom":
        preset = "garden"
    custom: dict[str, str] = {}
    raw_custom_value = raw.get("custom")
    raw_custom = raw_custom_value if isinstance(raw_custom_value, dict) else {}
    for key in THEME_COLOR_KEYS:
        value = raw_custom.get(key)
        if isinstance(value, str) and COLOR_RE.match(value):
            custom[key] = value.lower()
    return {"preset": preset, "custom": custom}


def normalize_cron_config(raw: dict[str, Any]) -> dict[str, Any]:
    start = raw.get("startTimeEastern", DEFAULT_CONFIG["cron"]["startTimeEastern"])
    if not isinstance(start, str) or not TIME_RE.match(start):
        start = DEFAULT_CONFIG["cron"]["startTimeEastern"]

    try:
        interval_hours = int(raw.get("intervalHours", DEFAULT_CONFIG["cron"]["intervalHours"]))
    except (TypeError, ValueError):
        interval_hours = DEFAULT_CONFIG["cron"]["intervalHours"]
    interval_hours = min(max(interval_hours, 1), 24)

    max_runs = max(1, 24 // interval_hours)
    try:
        runs_per_day = int(raw.get("runsPerDay", DEFAULT_CONFIG["cron"]["runsPerDay"]))
    except (TypeError, ValueError):
        runs_per_day = DEFAULT_CONFIG["cron"]["runsPerDay"]
    runs_per_day = min(max(runs_per_day, 1), max_runs)

    job_path_value = raw.get("jobPath")
    job_path = job_path_value if isinstance(job_path_value, str) else REMINDER_JOB_PATH
    if not job_path.strip():
        job_path = REMINDER_JOB_PATH

    return {
        "enabled": bool(raw.get("enabled", True)),
        "startTimeEastern": start,
        "intervalHours": interval_hours,
        "runsPerDay": runs_per_day,
        "jobPath": job_path,
    }


def effective_theme(theme_config: dict[str, Any]) -> dict[str, str]:
    """Return CSS color tokens for a normalized theme config."""
    theme = normalize_theme_config(theme_config)
    if theme["preset"] == "custom":
        colors = dict(THEME_PRESETS["garden"])
    else:
        colors = dict(THEME_PRESETS[theme["preset"]])
    colors.pop("label", None)
    colors.update(theme.get("custom", {}))
    return colors


def cron_slots(cron_config: dict[str, Any]) -> list[tuple[int, int]]:
    """Return sorted daily local-time cron slots as (hour, minute)."""
    config = normalize_cron_config(cron_config)
    hour, minute = parse_time(config["startTimeEastern"])
    interval = int(config["intervalHours"])
    runs = int(config["runsPerDay"])
    slots = {(hour + index * interval) % 24: minute for index in range(runs)}
    return sorted((slot_hour, slot_minute) for slot_hour, slot_minute in slots.items())


def cron_expression(cron_config: dict[str, Any]) -> str:
    """Build the cron expression for the configured Eastern-time schedule."""
    slots = cron_slots(cron_config)
    minutes = sorted({minute for _, minute in slots})
    if len(minutes) != 1:
        raise ValueError("Taskgarden reminder cron expects one minute value")
    hour_list = ",".join(str(hour) for hour, _ in slots)
    return f"{minutes[0]} {hour_list} * * *"


def preview_cron_runs(
    cron_config: dict[str, Any],
    count: int = 5,
    now: datetime | None = None,
) -> list[dict[str, str]]:
    """Preview the next reminder cron run times in US Eastern and UTC."""
    config = normalize_cron_config(cron_config)
    base = now or datetime.now(timezone.utc)
    if base.tzinfo is None:
        base = base.replace(tzinfo=timezone.utc)
    now_eastern = base.astimezone(EASTERN_TZ)
    slots = cron_slots(config)
    results: list[dict[str, str]] = []
    day = now_eastern.date()
    for day_offset in range(0, 370):
        candidate_day = day + timedelta(days=day_offset)
        for hour, minute in slots:
            candidate = datetime(
                candidate_day.year,
                candidate_day.month,
                candidate_day.day,
                hour,
                minute,
                tzinfo=EASTERN_TZ,
            )
            if candidate <= now_eastern:
                continue
            results.append(
                {
                    "eastern": candidate.isoformat(),
                    "utc": candidate.astimezone(timezone.utc).isoformat(),
                    "label": candidate.strftime("%a %b %d, %I:%M %p %Z"),
                }
            )
            if len(results) >= count:
                return results
    return results


def build_cron_block(cron_config: dict[str, Any]) -> list[str]:
    """Return managed crontab lines for the reminder job."""
    config = normalize_cron_config(cron_config)
    expression = cron_expression(config)
    job_path = config["jobPath"]
    summary = (
        f"# Planned todo reminder, every {config['intervalHours']}h starting "
        f"{config['startTimeEastern']} America/New_York for {config['runsPerDay']} run(s)"
    )
    lines = [CRON_BEGIN, summary]
    if config["enabled"]:
        lines.extend(["CRON_TZ=America/New_York", f"{expression} {job_path}", "CRON_TZ=UTC"])
    else:
        lines.extend(
            [
                "# Disabled by Taskgarden UI",
                "# CRON_TZ=America/New_York",
                f"# {expression} {job_path}",
                "# CRON_TZ=UTC",
            ]
        )
    lines.append(CRON_END)
    return lines


def apply_cron_config(cron_config: dict[str, Any]) -> str:
    """Install the managed reminder cron block in the current user's crontab."""
    current = read_crontab()
    updated = update_crontab_text(current, cron_config)
    backup_crontab(current)
    write_crontab(updated)
    return updated


def update_crontab_text(current: str, cron_config: dict[str, Any]) -> str:
    """Return crontab text with the Taskgarden reminder block installed."""
    cleaned = remove_existing_taskgarden_cron(current.splitlines())
    block = build_cron_block(cron_config)
    insert_at = insertion_index(cleaned)
    updated_lines = cleaned[:insert_at] + block + cleaned[insert_at:]
    return "\n".join(updated_lines).rstrip() + "\n"


def remove_existing_taskgarden_cron(lines: list[str]) -> list[str]:
    """Remove old managed blocks and legacy planned-reminder entries."""
    cleaned: list[str] = []
    in_managed_block = False
    skip_next_utc_reset = False
    for line in lines:
        stripped = line.strip()
        if stripped == CRON_BEGIN:
            in_managed_block = True
            continue
        if in_managed_block:
            if stripped == CRON_END:
                in_managed_block = False
            continue
        if skip_next_utc_reset and stripped == "CRON_TZ=UTC":
            skip_next_utc_reset = False
            continue
        skip_next_utc_reset = False
        if REMINDER_JOB_PATH in line or "planned_todo_reminder.sh" in line:
            while cleaned and (
                cleaned[-1].strip().startswith("# Planned todo reminder")
                or cleaned[-1].strip() == "CRON_TZ=America/New_York"
            ):
                cleaned.pop()
            skip_next_utc_reset = True
            continue
        cleaned.append(line)
    return cleaned


def insertion_index(lines: list[str]) -> int:
    """Insert after the leading crontab environment/header lines."""
    index = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            index = i + 1
            continue
        if re.match(r"^[A-Z_][A-Z0-9_]*=", stripped):
            index = i + 1
            continue
        if stripped == "# BEGIN FREYA_AUTOMATION":
            index = i + 1
            continue
        break
    return index


def read_crontab() -> str:
    """Return current crontab text, or empty text if no crontab exists."""
    result = subprocess.run(
        ["crontab", "-l"], capture_output=True, text=True, check=False
    )
    if result.returncode == 0:
        return result.stdout
    if "no crontab" in result.stderr.lower():
        return ""
    raise RuntimeError(result.stderr.strip() or "Unable to read crontab")


def write_crontab(text: str) -> None:
    """Replace current crontab with text."""
    subprocess.run(["crontab", "-"], input=text, text=True, check=True)


def backup_crontab(text: str) -> None:
    """Write a timestamped crontab backup before mutation."""
    CRONTAB_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    (CRONTAB_BACKUP_DIR / f"crontab-{stamp}.before-taskgarden-ui").write_text(text)


def parse_time(value: str) -> tuple[int, int]:
    match = TIME_RE.match(value)
    if not match:
        raise ValueError(f"Invalid HH:MM time: {value}")
    return int(match.group(1)), int(match.group(2))
