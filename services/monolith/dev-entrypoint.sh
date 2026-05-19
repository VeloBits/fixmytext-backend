#!/bin/sh
# Dev container entrypoint — keeps /app/.venv in sync with requirements.txt
# on every container start. The first build installs the venv; subsequent
# starts compare the file hash and only re-install if requirements.txt has
# actually changed since the last sync. Idempotent and fast (<100ms) when
# nothing changed.
#
# Why this exists: the dev compose mounts a *named* volume at /app/.venv so
# the venv survives restarts. But that means a `requirements.txt` edit on the
# host wouldn't reach the container without a manual `--renew-anon-volumes`.
# This script removes that footgun.
set -eu

VENV=/app/.venv
HASH_FILE="$VENV/.requirements.hash"
REQS=/app/requirements.txt

if [ ! -d "$VENV" ]; then
  # First boot on a fresh named volume — recreate the venv inside it.
  echo "[dev-entrypoint] creating venv at $VENV..."
  python -m venv "$VENV"
  "$VENV/bin/pip" install --upgrade pip --quiet
fi

NEW_HASH=$(sha256sum "$REQS" | awk '{print $1}')
OLD_HASH=$(cat "$HASH_FILE" 2>/dev/null || true)

if [ "$NEW_HASH" != "$OLD_HASH" ]; then
  echo "[dev-entrypoint] requirements.txt changed — syncing dependencies..."
  "$VENV/bin/pip" install --no-cache-dir -r "$REQS"
  echo "$NEW_HASH" > "$HASH_FILE"
  echo "[dev-entrypoint] dependency sync complete."
else
  echo "[dev-entrypoint] requirements.txt unchanged — skipping pip install."
fi

exec "$@"
