#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 1 ]; then
  printf 'usage: %s /path/to/headroom-backup.tar.gz\n' "$0" >&2
  exit 2
fi

ARCHIVE="$1"
STATE_DIR="${HEADROOM_STATE_DIR:-/data/headroom}"
RESTORE_PARENT="$(dirname "${STATE_DIR}")"

if [ ! -f "${ARCHIVE}" ]; then
  printf 'backup archive not found: %s\n' "${ARCHIVE}" >&2
  exit 1
fi

mkdir -p "${RESTORE_PARENT}"

if [ -e "${STATE_DIR}" ]; then
  SAFETY_COPY="${STATE_DIR}.pre-restore.$(date -u +%Y%m%dT%H%M%SZ)"
  mv "${STATE_DIR}" "${SAFETY_COPY}"
  printf 'existing state moved to: %s\n' "${SAFETY_COPY}"
fi

tar -xzf "${ARCHIVE}" -C "${RESTORE_PARENT}"
printf 'restore complete: %s\n' "${STATE_DIR}"
