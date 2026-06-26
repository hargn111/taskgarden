"""Tests for Taskgarden UI configuration helpers."""

from datetime import datetime
from zoneinfo import ZoneInfo

from taskgarden.config import (
    REMINDER_JOB_PATH,
    cron_expression,
    preview_cron_runs,
    update_crontab_text,
)


def test_cron_preview_uses_us_eastern_time() -> None:
    preview = preview_cron_runs(
        {
            "enabled": True,
            "startTimeEastern": "09:30",
            "intervalHours": 3,
            "runsPerDay": 4,
            "jobPath": REMINDER_JOB_PATH,
        },
        count=4,
        now=datetime(2026, 6, 26, 8, 0, tzinfo=ZoneInfo("America/New_York")),
    )

    assert [item["label"] for item in preview] == [
        "Fri Jun 26, 09:30 AM EDT",
        "Fri Jun 26, 12:30 PM EDT",
        "Fri Jun 26, 03:30 PM EDT",
        "Fri Jun 26, 06:30 PM EDT",
    ]
    assert preview[0]["utc"].startswith("2026-06-26T13:30:00")


def test_cron_expression_and_crontab_update() -> None:
    cron = {
        "enabled": True,
        "startTimeEastern": "10:00",
        "intervalHours": 2,
        "runsPerDay": 7,
        "jobPath": REMINDER_JOB_PATH,
    }

    assert cron_expression(cron) == "0 10,12,14,16,18,20,22 * * *"

    existing = """# BEGIN FREYA_AUTOMATION
SHELL=/bin/bash
PATH=/usr/bin:/bin
# Planned todo reminder, every 2 hours during 14:00-22:00 UTC plus 00:00 and 02:00 UTC
0 14,16,18,20,22,0,2 * * * /root/hermes-workspace/scripts/jobs/planned_todo_reminder.sh
# Weekly cleanup review, Sundays at 17:00 UTC
0 17 * * 0 /root/hermes-workspace/scripts/jobs/weekly_cleanup_review.sh
# END FREYA_AUTOMATION
"""

    updated = update_crontab_text(existing, cron)

    assert "0 14,16,18,20,22,0,2" not in updated
    assert "# BEGIN TASKGARDEN_REMINDER_CRON" in updated
    assert "CRON_TZ=America/New_York" in updated
    assert f"0 10,12,14,16,18,20,22 * * * {REMINDER_JOB_PATH}" in updated
    assert "# Weekly cleanup review" in updated
