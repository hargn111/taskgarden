"""Command-line interface for Task Garden."""

import argparse
import json
import sys
from typing import List, Optional

from .reminders import generate_reminder_message, load_reminder_config
from .todos import (
    TodoData,
    TodoItem,
    append_note,
    create_item,
    find_item,
    load_data,
    normalize_iso,
    reminder_due,
    save_data,
    set_title,
    stale_task_due,
    now_iso,
    parse_iso,
    VALID_BUCKETS,
)


def print_items(items: List[TodoItem], show_all: bool = False) -> None:
    """Pretty‑print a list of todo items."""
    filtered = items if show_all else [item for item in items if item["status"] == "open"]
    if not filtered:
        print("No todo items.")
        return

    for item in filtered:
        print(f"[{item['status']}/{item['bucket']}] {item['id']}  {item['title']}")
        print(f"  created: {item['created_at']}")
        if item.get("note"):
            print(f"  note: {item['note']}")
        tags = ", ".join(item.get("tags", []))
        if tags:
            print(f"  tags: {tags}")
        if item.get("remind_interval_hours") is not None:
            print(f"  remind_interval_hours: {item['remind_interval_hours']}")
        if item.get("last_reminder_at"):
            print(f"  last_reminder_at: {item['last_reminder_at']}")
        if item.get("completed_at"):
            print(f"  completed: {item['completed_at']}")
        print()


def cmd_add(args: argparse.Namespace) -> None:
    """Add a new todo item."""
    data = load_data()
    item = create_item(
        title=args.title,
        note=args.note or "",
        tags=args.tags,
        bucket=args.bucket,
        remind_interval_hours=args.remind_interval_hours,
    )
    data["items"].append(item)
    save_data(data)
    print_json(item)


def cmd_list(args: argparse.Namespace) -> None:
    """List todo items, optionally filtered."""
    data = load_data()
    items = data["items"]

    if args.stale_days is not None:
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        items = [item for item in items if stale_task_due(item, args.stale_days, now)]

    if args.tag:
        items = [item for item in items if args.tag in item.get("tags", [])]
    if args.bucket:
        items = [item for item in items if item.get("bucket") == args.bucket]
    if args.due_reminders:
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        items = [item for item in items if reminder_due(item, now)]

    print_items(items, show_all=args.all)


def cmd_done(args: argparse.Namespace) -> None:
    """Mark a todo item as done."""
    data = load_data()
    item = find_item(data, args.id)
    if not item:
        die(f"Todo not found: {args.id}")
    item["status"] = "done"
    item["completed_at"] = now_iso()
    save_data(data)
    print_json(item)


def cmd_reopen(args: argparse.Namespace) -> None:
    """Reopen a completed todo item."""
    data = load_data()
    item = find_item(data, args.id)
    if not item:
        die(f"Todo not found: {args.id}")
    item["status"] = "open"
    item["completed_at"] = None
    save_data(data)
    print_json(item)


def cmd_remove(args: argparse.Namespace) -> None:
    """Permanently remove a todo item."""
    data = load_data()
    before = len(data["items"])
    data["items"] = [item for item in data["items"] if item["id"] != args.id]
    if len(data["items"]) == before:
        die(f"Todo not found: {args.id}")
    save_data(data)
    print(f"Removed {args.id}")


def cmd_set_bucket(args: argparse.Namespace) -> None:
    """Move a todo item between unplanned and planned."""
    data = load_data()
    item = find_item(data, args.id)
    if not item:
        die(f"Todo not found: {args.id}")
    item["bucket"] = args.bucket
    save_data(data)
    print_json(item)


def cmd_note(args: argparse.Namespace) -> None:
    """Append a note to a todo item."""
    data = load_data()
    item = find_item(data, args.id)
    if not item:
        die(f"Todo not found: {args.id}")
    append_note(item, args.text)
    save_data(data)
    print_json(item)


def cmd_set_title(args: argparse.Namespace) -> None:
    """Update a todo item's title."""
    data = load_data()
    item = find_item(data, args.id)
    if not item:
        die(f"Todo not found: {args.id}")

    title = args.title.strip()
    if not title:
        die("Title cannot be empty")

    set_title(item, title)
    save_data(data)
    print_json(item)


def cmd_set_reminder(args: argparse.Namespace) -> None:
    """Set, update, or clear a reminder interval."""
    data = load_data()
    item = find_item(data, args.id)
    if not item:
        die(f"Todo not found: {args.id}")

    if args.clear:
        item["remind_interval_hours"] = None
        item["last_reminder_at"] = None
    else:
        if args.hours is None:
            die("Hours required unless --clear is used")
        item["remind_interval_hours"] = args.hours
        if args.touch_now:
            at_value = getattr(args, "at", None)
            item["last_reminder_at"] = normalize_iso(at_value) if at_value else now_iso()

    save_data(data)
    print_json(item)


def cmd_touch_reminder(args: argparse.Namespace) -> None:
    """Update the last reminder timestamp to now or a specified timestamp."""
    data = load_data()
    item = find_item(data, args.id)
    if not item:
        die(f"Todo not found: {args.id}")
    at_value = getattr(args, "at", None)
    item["last_reminder_at"] = normalize_iso(at_value) if at_value else now_iso()
    save_data(data)
    print_json(item)


def cmd_reminder_message(args: argparse.Namespace) -> None:
    """Generate reminder text for due items using config-driven fallback."""
    data = load_data()
    items = data["items"]

    if args.bucket:
        items = [item for item in items if item.get("bucket") == args.bucket]
    if args.due_reminders:
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        items = [item for item in items if reminder_due(item, now)]

    if not items:
        die("No todo items matched reminder-message selection")

    config = load_reminder_config()
    result = generate_reminder_message(items, config=config)
    print(json.dumps(result, indent=2, sort_keys=True))


def print_json(obj: TodoItem) -> None:
    """Print an item as formatted JSON."""
    import json

    print(json.dumps(obj, indent=2, sort_keys=True))


def die(message: str, code: int = 1) -> None:
    """Print error and exit."""
    print(message, file=sys.stderr)
    sys.exit(code)


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="Task Garden – a lightweight CLI for managing todos with reminders."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # add
    add_p = sub.add_parser("add", help="Add a todo item")
    add_p.add_argument("title")
    add_p.add_argument("--note")
    add_p.add_argument("--tag", dest="tags", action="append")
    add_p.add_argument("--bucket", choices=sorted(VALID_BUCKETS), default="unplanned")
    add_p.add_argument("--remind-interval-hours", type=float)
    add_p.set_defaults(func=cmd_add)

    # list
    list_p = sub.add_parser("list", help="List todo items")
    list_p.add_argument("--all", action="store_true")
    list_p.add_argument("--tag")
    list_p.add_argument("--bucket", choices=sorted(VALID_BUCKETS))
    list_p.add_argument("--due-reminders", action="store_true")
    list_p.add_argument(
        "--stale-days",
        type=float,
        help="Show open planned items that have been around at least this many days",
    )
    list_p.set_defaults(func=cmd_list)

    # done
    done_p = sub.add_parser("done", help="Mark a todo item done")
    done_p.add_argument("id")
    done_p.set_defaults(func=cmd_done)

    # reopen
    reopen_p = sub.add_parser("reopen", help="Reopen a completed item")
    reopen_p.add_argument("id")
    reopen_p.set_defaults(func=cmd_reopen)

    # remove
    remove_p = sub.add_parser("remove", help="Remove a todo item")
    remove_p.add_argument("id")
    remove_p.set_defaults(func=cmd_remove)

    # set‑bucket
    bucket_p = sub.add_parser("set-bucket", help="Move a todo item between unplanned and planned")
    bucket_p.add_argument("id")
    bucket_p.add_argument("bucket", choices=sorted(VALID_BUCKETS))
    bucket_p.set_defaults(func=cmd_set_bucket)

    # note
    note_p = sub.add_parser("note", help="Append a note to a todo item")
    note_p.add_argument("id")
    note_p.add_argument("text")
    note_p.set_defaults(func=cmd_note)

    # set-title
    title_p = sub.add_parser("set-title", help="Update a todo item's title")
    title_p.add_argument("id")
    title_p.add_argument("title")
    title_p.set_defaults(func=cmd_set_title)

    # set‑reminder
    remind_p = sub.add_parser(
        "set-reminder", help="Set, update, or clear reminder interval in hours"
    )
    remind_p.add_argument("id")
    remind_p.add_argument("hours", type=float, nargs="?")
    remind_p.add_argument("--touch-now", action="store_true")
    remind_p.add_argument("--at", help="ISO 8601 timestamp to use for last_reminder_at when touching")
    remind_p.add_argument("--clear", action="store_true")
    remind_p.set_defaults(func=cmd_set_reminder)

    # touch‑reminder
    touch_p = sub.add_parser("touch-reminder", help="Update last reminder time to now")
    touch_p.add_argument("id")
    touch_p.add_argument("--at", help="ISO 8601 timestamp to use for last_reminder_at")
    touch_p.set_defaults(func=cmd_touch_reminder)

    # reminder-message
    reminder_message_p = sub.add_parser(
        "reminder-message",
        help="Generate reminder text for selected items using config-driven model fallback",
    )
    reminder_message_p.add_argument("--bucket", choices=sorted(VALID_BUCKETS))
    reminder_message_p.add_argument(
        "--due-reminders",
        action="store_true",
        help="Restrict to items currently due for reminder",
    )
    reminder_message_p.set_defaults(func=cmd_reminder_message)

    return parser


def main() -> None:
    """Entry point for the CLI."""
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
