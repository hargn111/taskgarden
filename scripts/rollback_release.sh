#!/usr/bin/env bash
set -euo pipefail

INSTALL_ROOT="${TASKGARDEN_INSTALL_ROOT:-/opt/taskgarden}"
RELEASES_DIR="$INSTALL_ROOT/releases"
CURRENT_LINK="$INSTALL_ROOT/current"
TARGET="${1:-previous}"

if [[ ! -L "$CURRENT_LINK" ]]; then
  echo "Current link not found: $CURRENT_LINK" >&2
  exit 1
fi

current_target="$(readlink -f "$CURRENT_LINK")"
mapfile -t releases < <(find "$RELEASES_DIR" -mindepth 1 -maxdepth 1 -type d | sort)

if (( ${#releases[@]} == 0 )); then
  echo "No releases found in $RELEASES_DIR" >&2
  exit 1
fi

if [[ "$TARGET" == "previous" ]]; then
  previous=""
  for release in "${releases[@]}"; do
    if [[ "$release" == "$current_target" ]]; then
      break
    fi
    previous="$release"
  done
  if [[ -z "$previous" ]]; then
    echo "No previous release found before $current_target" >&2
    exit 1
  fi
  target_release="$previous"
else
  target_release="$RELEASES_DIR/$TARGET"
  if [[ ! -d "$target_release" ]]; then
    echo "Requested release not found: $target_release" >&2
    exit 1
  fi
fi

SMOKE_DATA="$(mktemp)"
cat > "$SMOKE_DATA" <<'EOF'
{
  "version": 2,
  "items": []
}
EOF
TASKGARDEN_DATA_PATH="$SMOKE_DATA" "$target_release/.venv/bin/python" -m taskgarden.cli list --all >/dev/null
rm -f "$SMOKE_DATA"

ln -sfn "$target_release" "$CURRENT_LINK"

echo "Rolled back current -> $(readlink -f "$CURRENT_LINK")"
