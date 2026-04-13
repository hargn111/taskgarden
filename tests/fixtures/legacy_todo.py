#!/usr/bin/env python3
import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

DATA_PATH = Path('/root/.openclaw/workspace/state/todos.json')
VALID_BUCKETS = {"unplanned", "planned"}
VALID_STATUS = {"open", "done"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_iso(value: str) -> datetime:
    if value.endswith('Z'):
        value = value[:-1] + '+00:00'
    return datetime.fromisoformat(value)


def normalize_item(item: dict) -> dict:
    item.setdefault("note", "")
    item.setdefault("tags", [])
    item.setdefault("status", "open")
    item.setdefault("bucket", "unplanned")
    item.setdefault("completed_at", None)
    item.setdefault("remind_interval_hours", None)
    item.setdefault("last_reminder_at", None)
    item["tags"] = sorted(set(item.get("tags", [])))
    if item["status"] not in VALID_STATUS:
        item["status"] = "open"
    if item["bucket"] not in VALID_BUCKETS:
        item["bucket"] = "unplanned"
    return item


def load_data() -> dict:
    if not DATA_PATH.exists():
        return {"version": 2, "items": []}
    data = json.loads(DATA_PATH.read_text())
    data.setdefault("version", 1)
    data.setdefault("items", [])
    data["items"] = [normalize_item(item) for item in data["items"]]
    if data["version"] < 2:
        data["version"] = 2
        save_data(data)
    return data


def save_data(data: dict) -> None:
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    data["version"] = 2
    data["items"] = [normalize_item(item) for item in data["items"]]
    DATA_PATH.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def find_item(data: dict, item_id: str) -> dict | None:
    for item in data["items"]:
        if item["id"] == item_id:
            return item
    return None


def append_note(item: dict, note: str) -> None:
    note = note.strip()
    if not note:
        return
    if item.get("note"):
        item["note"] = item["note"].rstrip() + "\n- " + note
    else:
        item["note"] = note


def reminder_due(item: dict, now: datetime) -> bool:
    if item.get("status") != "open":
        return False
    interval = item.get("remind_interval_hours")
    if interval is None:
        return False
    last = item.get("last_reminder_at") or item.get("created_at")
    if not last:
        return True
    last_dt = parse_iso(last)
    elapsed_hours = (now - last_dt).total_seconds() / 3600
    return elapsed_hours >= float(interval)


def print_items(items: list[dict], show_all: bool = False) -> None:
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


def cmd_add(args):
    data = load_data()
    item = normalize_item({
        "id": uuid.uuid4().hex[:8],
        "title": args.title.strip(),
        "note": (args.note or "").strip(),
        "tags": sorted(set(args.tags or [])),
        "status": "open",
        "bucket": args.bucket,
        "created_at": now_iso(),
        "completed_at": None,
        "remind_interval_hours": args.remind_interval_hours,
        "last_reminder_at": None,
    })
    data["items"].append(item)
    save_data(data)
    print(json.dumps(item, indent=2, sort_keys=True))


def cmd_list(args):
    data = load_data()
    items = data["items"]
    if args.tag:
        items = [item for item in items if args.tag in item.get("tags", [])]
    if args.bucket:
        items = [item for item in items if item.get("bucket") == args.bucket]
    if args.due_reminders:
        now = datetime.now(timezone.utc)
        items = [item for item in items if reminder_due(item, now)]
    print_items(items, show_all=args.all)


def cmd_done(args):
    data = load_data()
    item = find_item(data, args.id)
    if not item:
        print(f"Todo not found: {args.id}", file=sys.stderr)
        sys.exit(1)
    item["status"] = "done"
    item["completed_at"] = now_iso()
    save_data(data)
    print(json.dumps(item, indent=2, sort_keys=True))


def cmd_reopen(args):
    data = load_data()
    item = find_item(data, args.id)
    if not item:
        print(f"Todo not found: {args.id}", file=sys.stderr)
        sys.exit(1)
    item["status"] = "open"
    item["completed_at"] = None
    save_data(data)
    print(json.dumps(item, indent=2, sort_keys=True))


def cmd_remove(args):
    data = load_data()
    before = len(data["items"])
    data["items"] = [item for item in data["items"] if item["id"] != args.id]
    if len(data["items"]) == before:
        print(f"Todo not found: {args.id}", file=sys.stderr)
        sys.exit(1)
    save_data(data)
    print(f"Removed {args.id}")


def cmd_set_bucket(args):
    data = load_data()
    item = find_item(data, args.id)
    if not item:
        print(f"Todo not found: {args.id}", file=sys.stderr)
        sys.exit(1)
    item["bucket"] = args.bucket
    save_data(data)
    print(json.dumps(item, indent=2, sort_keys=True))


def cmd_note(args):
    data = load_data()
    item = find_item(data, args.id)
    if not item:
        print(f"Todo not found: {args.id}", file=sys.stderr)
        sys.exit(1)
    append_note(item, args.text)
    save_data(data)
    print(json.dumps(item, indent=2, sort_keys=True))


def cmd_set_reminder(args):
    data = load_data()
    item = find_item(data, args.id)
    if not item:
        print(f"Todo not found: {args.id}", file=sys.stderr)
        sys.exit(1)
    if args.clear:
        item["remind_interval_hours"] = None
        item["last_reminder_at"] = None
    else:
        item["remind_interval_hours"] = args.hours
        if args.touch_now:
            item["last_reminder_at"] = now_iso()
    save_data(data)
    print(json.dumps(item, indent=2, sort_keys=True))


def cmd_touch_reminder(args):
    data = load_data()
    item = find_item(data, args.id)
    if not item:
        print(f"Todo not found: {args.id}", file=sys.stderr)
        sys.exit(1)
    item["last_reminder_at"] = now_iso()
    save_data(data)
    print(json.dumps(item, indent=2, sort_keys=True))


def build_parser():
    parser = argparse.ArgumentParser(description="Small persistent todo tracker")
    sub = parser.add_subparsers(dest="command", required=True)

    add_p = sub.add_parser("add", help="Add a todo item")
    add_p.add_argument("title")
    add_p.add_argument("--note")
    add_p.add_argument("--tag", dest="tags", action="append")
    add_p.add_argument("--bucket", choices=sorted(VALID_BUCKETS), default="unplanned")
    add_p.add_argument("--remind-interval-hours", type=float)
    add_p.set_defaults(func=cmd_add)

    list_p = sub.add_parser("list", help="List todo items")
    list_p.add_argument("--all", action="store_true")
    list_p.add_argument("--tag")
    list_p.add_argument("--bucket", choices=sorted(VALID_BUCKETS))
    list_p.add_argument("--due-reminders", action="store_true")
    list_p.set_defaults(func=cmd_list)

    done_p = sub.add_parser("done", help="Mark a todo item done")
    done_p.add_argument("id")
    done_p.set_defaults(func=cmd_done)

    reopen_p = sub.add_parser("reopen", help="Reopen a completed item")
    reopen_p.add_argument("id")
    reopen_p.set_defaults(func=cmd_reopen)

    remove_p = sub.add_parser("remove", help="Remove a todo item")
    remove_p.add_argument("id")
    remove_p.set_defaults(func=cmd_remove)

    bucket_p = sub.add_parser("set-bucket", help="Move a todo item between unplanned and planned")
    bucket_p.add_argument("id")
    bucket_p.add_argument("bucket", choices=sorted(VALID_BUCKETS))
    bucket_p.set_defaults(func=cmd_set_bucket)

    note_p = sub.add_parser("note", help="Append a note to a todo item")
    note_p.add_argument("id")
    note_p.add_argument("text")
    note_p.set_defaults(func=cmd_note)

    remind_p = sub.add_parser("set-reminder", help="Set, update, or clear reminder interval in hours")
    remind_p.add_argument("id")
    remind_p.add_argument("hours", type=float, nargs="?")
    remind_p.add_argument("--touch-now", action="store_true")
    remind_p.add_argument("--clear", action="store_true")
    remind_p.set_defaults(func=cmd_set_reminder)

    touch_p = sub.add_parser("touch-reminder", help="Update last reminder time to now")
    touch_p.add_argument("id")
    touch_p.set_defaults(func=cmd_touch_reminder)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
