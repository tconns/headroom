#!/usr/bin/env bash
set -euo pipefail

STATE_DIR="${HEADROOM_STATE_DIR:-/data/headroom}"
BACKUP_DIR="${HEADROOM_BACKUP_DIR:-/data/headroom/backups}"
RETENTION_DAYS="${HEADROOM_BACKUP_RETENTION_DAYS:-7}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
ARCHIVE="${BACKUP_DIR}/headroom-${STAMP}.tar.gz"

mkdir -p "${BACKUP_DIR}"

tar \
  --exclude="${BACKUP_DIR}" \
  -czf "${ARCHIVE}" \
  -C "$(dirname "${STATE_DIR}")" \
  "$(basename "${STATE_DIR}")"

find "${BACKUP_DIR}" -type f -name 'headroom-*.tar.gz' -mtime "+${RETENTION_DAYS}" -delete

printf 'backup created: %s\n' "${ARCHIVE}"
