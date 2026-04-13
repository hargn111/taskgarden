#!/usr/bin/env bash
set -euo pipefail

SOURCE_DIR="${1:-$(pwd)}"
RELEASE_ID="${TASKGARDEN_RELEASE_ID:-$(date -u +"%Y-%m-%dT%H-%M-%SZ")}"
INSTALL_ROOT="${TASKGARDEN_INSTALL_ROOT:-/opt/taskgarden}"
RELEASES_DIR="$INSTALL_ROOT/releases"
CURRENT_LINK="$INSTALL_ROOT/current"
KEEP_RELEASES="${TASKGARDEN_KEEP_RELEASES:-5}"
PYTHON_BIN="${TASKGARDEN_PYTHON_BIN:-python3}"

if [[ ! -f "$SOURCE_DIR/pyproject.toml" ]]; then
  echo "Expected a taskgarden source tree with pyproject.toml: $SOURCE_DIR" >&2
  exit 1
fi

RELEASE_DIR="$RELEASES_DIR/$RELEASE_ID"
mkdir -p "$RELEASES_DIR"

rsync -a --delete \
  --exclude '.git' \
  --exclude '.venv' \
  --exclude '__pycache__' \
  --exclude '.pytest_cache' \
  "$SOURCE_DIR/" "$RELEASE_DIR/"

"$PYTHON_BIN" -m venv "$RELEASE_DIR/.venv"
"$RELEASE_DIR/.venv/bin/python" -m pip install --upgrade pip setuptools wheel >/dev/null
"$RELEASE_DIR/.venv/bin/python" -m pip install "$RELEASE_DIR" >/dev/null

SMOKE_DATA="$(mktemp)"
cat > "$SMOKE_DATA" <<'EOF'
{
  "version": 2,
  "items": []
}
EOF
TASKGARDEN_DATA_PATH="$SMOKE_DATA" "$RELEASE_DIR/.venv/bin/python" -m taskgarden.cli list --all >/dev/null
rm -f "$SMOKE_DATA"

ln -sfn "$RELEASE_DIR" "$CURRENT_LINK"

if [[ "$KEEP_RELEASES" =~ ^[0-9]+$ ]] && (( KEEP_RELEASES > 0 )); then
  mapfile -t old_releases < <(find "$RELEASES_DIR" -mindepth 1 -maxdepth 1 -type d | sort)
  if (( ${#old_releases[@]} > KEEP_RELEASES )); then
    prune_count=$(( ${#old_releases[@]} - KEEP_RELEASES ))
    for ((i=0; i<prune_count; i++)); do
      rm -rf "${old_releases[$i]}"
    done
  fi
fi

echo "Release installed: $RELEASE_DIR"
echo "Current symlink: $CURRENT_LINK -> $(readlink -f "$CURRENT_LINK")"
