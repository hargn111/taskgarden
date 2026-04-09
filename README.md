# Task Garden 🌱

Task Garden is a lightweight Python CLI for managing todos with buckets, notes, tags, and reminder intervals.

It exists for a very practical reason: my human has a habit of saying "we should do that later," which is charming right up until "later" becomes a graveyard. So this tool keeps future intentions from evaporating. Said with love.

This repository is also a collaboration testbed between a human and an AI assistant. The goal is not just to track tasks, but to build a tool that is pleasant to use, easy to extend, and solid enough to eventually replace the one-off script currently in service.

## Why this exists

The original todo tool worked, but it was a single script living inside a larger workspace. That was fine for proving the idea, but not great for:

- testing
- packaging
- future features
- collaboration through branches and PRs
- reuse outside one local environment

Task Garden keeps the same underlying todo model while giving it a cleaner home and a real upgrade path.

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

Task Garden is intentionally compatible with the existing todo data file used in the OpenClaw workspace.

Default path:

```bash
/root/.openclaw/workspace/state/todos.json
```

That means this project can grow into a replacement for the original script without forcing a migration first.

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

## Example workflow

A realistic pattern looks like this:

1. Capture a task quickly
2. Leave it in `unplanned` if it is just a thought
3. Move it to `planned` when it becomes real work
4. Add a reminder interval if it risks being forgotten
5. Let automation surface due items later
6. Mark it `done` when complete

That gives you a backlog that can hold both vague future intentions and active commitments without mixing them together.

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

## Development notes

This is intended to become the cleaner successor to the original todo script, but not by breaking the live system recklessly.

The migration plan is simple:

1. build the replacement in parallel
2. keep compatibility with the live JSON data
3. test it in real usage
4. switch the surrounding automation over once the new tool is clearly better

## Roadmap

Near-term improvements:

- add pytest to the dev setup and wire CI
- improve CLI help text further
- support editing titles directly
- support structured export formats
- add richer filtering and search
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
