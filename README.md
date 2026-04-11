# Task Garden 🌱

Task Garden is a lightweight Python CLI for managing todos with buckets, notes, tags, and reminder intervals.

It is designed to fit naturally into an OpenClaw workspace while staying simple enough to use on its own.

## Features

Current feature set:

- add todos
- list todos
- mark items done
- reopen completed items
- remove items
- move items between `unplanned` and `planned`
- append notes
- add tags
- set reminder intervals in hours
- list only items currently due for reminder
- list stale planned items by age in days
- touch reminder timestamps after a reminder is sent

Data model features:

- stable short item ids
- UTC timestamps
- `open` / `done` status
- `planned` / `unplanned` buckets
- optional notes
- optional tags
- optional reminder cadence
- compatibility with the existing workspace todo JSON format

## Data format and compatibility

Task Garden uses the OpenClaw workspace todo path by default.

Default path:

```bash
/root/.openclaw/workspace/state/todos.json
```

You can override the path with an environment variable:

```bash
export TASKGARDEN_DATA_PATH=/path/to/todos.json
```

## Installation

### Development install

```bash
git clone https://github.com/hargn111/taskgarden.git
cd taskgarden
python3 -m pip install -e .
```

For local development with tests:

```bash
python3 -m pip install -e .[dev]
```

If you do not want to install it yet, you can also run it directly from the repo:

```bash
PYTHONPATH=src python3 -m taskgarden.cli list
```

## Command overview

### Add a todo

```bash
taskgarden add "Create a basic git repo to test the Codex ACP flow"
```

With more metadata:

```bash
taskgarden add "Investigate MCP Bridge" \
  --bucket planned \
  --tag integration \
  --tag mcp \
  --note "Review options and rough architecture" \
  --remind-interval-hours 24
```

### List todos

List open items:

```bash
taskgarden list
```

List everything, including done items:

```bash
taskgarden list --all
```

List only planned items:

```bash
taskgarden list --bucket planned
```

List only items with a tag:

```bash
taskgarden list --tag automation
```

List only items due for reminder right now:

```bash
taskgarden list --due-reminders --bucket planned
```

List planned items that have gone stale and likely need review:

```bash
taskgarden list --stale-days 14
```

### Mark done or reopen

```bash
taskgarden done 01dd2b90
taskgarden reopen 01dd2b90
```

### Move between buckets

```bash
taskgarden set-bucket 01dd2b90 planned
taskgarden set-bucket 01dd2b90 unplanned
```

### Add a note

```bash
taskgarden note 01dd2b90 "Jordan said this can wait until after the GitHub PR flow is tested"
```

If a note already exists, Task Garden appends the new text as another line instead of replacing the old one.

### Edit a title

```bash
taskgarden set-title 01dd2b90 "Create Codex ACP validation repo"
```

### Set or clear reminders

Set a reminder cadence in hours:

```bash
taskgarden set-reminder 01dd2b90 6
```

Set a reminder and mark it as just reminded right now:

```bash
taskgarden set-reminder 01dd2b90 6 --touch-now
```

Clear a reminder:

```bash
taskgarden set-reminder 01dd2b90 --clear
```

Mark an item as having been reminded right now:

```bash
taskgarden touch-reminder 01dd2b90
```

## Reminder behavior

A reminder is considered due when all of these are true:

- the item is `open`
- the item has a `remind_interval_hours` value
- enough time has passed since `last_reminder_at`
- if `last_reminder_at` is missing, enough time has passed since `created_at`

Done items do not trigger reminders.

This makes it easy for cron jobs or agents to do deterministic checks before any heavier automation runs.

## Stale-task review behavior

An item is considered stale when all of these are true:

- the item is `open`
- the item is in the `planned` bucket
- it was created at least the requested number of days ago

This is meant to support lightweight review passes, especially for tasks that may be blocked, obsolete, or quietly drifting.

Example:

```bash
taskgarden list --stale-days 30
```

## Example workflow

1. Add tasks quickly as they come up
2. Keep rough ideas in `unplanned`
3. Move active work into `planned`
4. Add notes, tags, or reminders as needed
5. Use reminder and stale-task filters to review what needs attention
6. Mark tasks done when finished

## Output format

List output is intentionally compact and readable in terminals and chat logs:

```text
[open/planned] 01dd2b90  Create a basic git repo to test the Codex ACP flow
  created: 2026-04-09T00:37:49.704536+00:00
  note: Jordan mentioned this as a later validation task.
  tags: codex, git
  remind_interval_hours: 6.0
  last_reminder_at: 2026-04-09T08:29:22.972224+00:00
```

Mutation commands output JSON so other tools and scripts can consume them directly.

## Project layout

```text
taskgarden/
├── README.md
├── pyproject.toml
├── src/taskgarden/
│   ├── __init__.py
│   ├── cli.py
│   └── todos.py
└── tests/
    └── test_todos.py
```

## Testing and CI

Run the test suite locally with:

```bash
python3 -m pytest
```

GitHub Actions runs the test suite automatically on pushes and pull requests across Python 3.10, 3.11, 3.12, and 3.13.

## Roadmap

Near-term improvements:

- improve CLI help text further
- support structured export formats
- add richer filtering and search
- add review helpers for tasks that are still open but likely done, obsolete, or in need of reprioritization
- reach feature parity with the legacy todo flow before migrating automation fully
- keep notifications as a thin external wrapper around taskgarden rather than baking delivery logic into the core tool
- eventually expose this through MCP or other agent-facing interfaces

## Contributing

If you are a human collaborator:

- open an issue or PR
- keep changes small and reviewable
- prefer clarity over cleverness

If you are an AI assistant working on behalf of the maintainer:

- work in a branch
- explain the change clearly
- keep commits readable
- open a PR instead of silently mutating the default branch

## License

MIT
