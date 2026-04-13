# Taskgarden migration plan

This document describes how to migrate the workspace todo system from the legacy `scripts/todo.py` driver to `taskgarden` with low risk.

## Goal

Make `taskgarden` the canonical driver for todo operations and reminder automation while preserving current behavior, validating parity with deterministic tests, and keeping rollback fast.

## Current state

- Both tools operate on the same data file: `/root/.openclaw/workspace/state/todos.json`.
- `taskgarden` already covers the main legacy operations:
  - add
  - list
  - done / reopen
  - set bucket
  - note append
  - set reminder / clear reminder
  - touch reminder
  - stale planned-task review
  - title editing
- Current known gaps or risks:
  - no rolling `.bak` backup behavior yet for todo mutations
  - scheduled callers still invoke the legacy script path
  - current file writes are plain writes with no locking, so concurrent writes can briefly corrupt or race the JSON file

## Migration principles

1. Prefer compatibility over schema churn.
2. Keep the data file path unchanged during migration.
3. Migrate wrappers and scheduled jobs only after parity tests pass.
4. Keep the legacy script available as a rollback path until the new flow has survived a soak period.
5. Avoid multi-writer races during rollout.

## Proposed implementation phases

### Phase 1: Fill behavior gaps in taskgarden

1. Add rolling `.bak` backups for todo mutations.
   - create a backup before replacing the live file
   - keep the newest 4 to 5 backups
   - prune older backups deterministically
2. Harden storage writes:
   - write to a temp file in the same directory
   - fsync if practical
   - atomic rename into place
   - optional simple lock file if concurrent scheduled mutation is expected
3. Leave `canceled` as a later roadmap item, outside the parity gate for migration.

### Phase 2: Build parity tests against the legacy flow

Create deterministic fixtures and compare old vs new behavior on the same todo dataset.
Only test overlapping legacy behavior here. Do not include future `canceled` status work in the parity gate.

#### Core parity tests

1. Load existing version-2 `todos.json` without modification.
2. List open items.
3. List with `--all`.
4. Filter by bucket.
5. Filter by tag.
6. Detect due reminders.
7. Mark item done.
8. Reopen item.
9. Move bucket planned ↔ unplanned.
10. Append note.
11. Set reminder interval.
12. Clear reminder interval.
13. Touch reminder timestamp.

#### Taskgarden-specific acceptance tests

1. Stale planned-task review works as documented.
2. Title editing works.
3. CLI output remains readable and machine-safe where expected.
4. Rolling `.bak` backups are created and pruned correctly on mutation.

#### Regression and compatibility tests

1. Legacy JSON fixtures round-trip without losing fields.
2. Unknown or older-version data is normalized safely.
3. Done items never trigger reminder checks.
4. Unplanned items never appear in stale planned-task review.
5. Reminder calculations match exact boundary behavior from the legacy script.

#### Concurrency / durability tests

1. Two rapid sequential mutations do not leave invalid JSON behind.
2. Interrupted write simulation leaves either the old valid file or the new valid file, never an empty or partial file.
3. Scheduled reminder touch plus manual edit does not corrupt storage.

## Phase 3: Introduce a migration harness

Before changing cron wrappers, add a small verification script that:

1. snapshots `state/todos.json`
2. runs a fixed set of `todo.py` operations on a fixture copy
3. runs the equivalent `taskgarden` operations on another fixture copy
4. diffs the resulting JSON structures
5. fails loudly on divergence

This should become the preflight gate for cutover.

## Phase 4: Cut over automation in small steps

1. Update one deterministic wrapper at a time.
   - first: planned todo reminder wrapper
   - second: weekly cleanup helpers that inspect todo state
2. After each cutover, run the wrapper manually on a fixture and then on live data.
3. Observe for a soak period before removing legacy references.
4. Only after stable soak, decide whether `scripts/todo.py` should:
   - remain as a thin compatibility shim to `taskgarden`, or
   - stay frozen but unused, or
   - be removed later in a separate cleanup.

## Recommended tests to validate migration

### Unit tests

Add tests for:
- current legacy-compatible status normalization
- reminder semantics for `open` and `done`
- stale review semantics for `planned`, `unplanned`, and `done`
- atomic save behavior
- rolling `.bak` backup behavior
- load/save compatibility with current workspace fixtures

### CLI integration tests

Using temporary fixture files, test exact commands such as:
- `taskgarden list --due-reminders --bucket planned`
- `taskgarden done <id>`
- `taskgarden set-bucket <id> unplanned`
- `taskgarden set-reminder <id> --clear`
- `taskgarden note <id> "..."`

### Wrapper tests

For each installed automation wrapper:
- confirm no-op behavior when nothing is due
- confirm only due planned items are selected
- confirm only reminded ids have `last_reminder_at` updated
- confirm output remains short and suitable for chat delivery

### Acceptance test checklist for live cutover

1. Back up the live todo file.
2. Run `taskgarden list` and compare against current expected open items.
3. Run due-reminder detection and compare against the current script.
4. Perform one harmless mutation on a non-critical test item.
5. Confirm automation wrappers still produce the same user-visible reminder text.
6. Confirm no JSON corruption after repeated quick mutations.

## Backout plan

If any migration test fails or live behavior diverges:

1. Stop the cutover immediately.
2. Point wrappers back to `scripts/todo.py`.
3. Restore the most recent backup of `state/todos.json` if schema or state changed unexpectedly.
4. Keep `taskgarden` changes isolated in git until the failing case is understood.
5. Add a regression test for the failure before retrying cutover.

## Operational rollback details

Before each live cutover step:
- copy `state/todos.json` to `state/backups/todos-<timestamp>.json`
- record which wrapper or cron entry was switched
- keep the old command line in comments or adjacent notes so reverting is one edit

A rollback should require only:
- restoring the previous wrapper command
- optionally restoring the last known-good JSON snapshot
- rerunning the deterministic verification harness

## Recommended immediate next steps

1. Add rolling `.bak` backup behavior for mutations.
2. Add atomic-write protection.
3. Add fixture-based CLI integration tests.
4. Create and run the parity harness comparing `todo.py` and `taskgarden` on the same fixture data.
5. If parity holds, cut over the planned reminder wrapper first, because it is deterministic and easy to validate.
