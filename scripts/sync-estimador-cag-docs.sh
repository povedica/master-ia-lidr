#!/usr/bin/env bash
# Mirror Second Brain project notes into the repo (canonical source: Obsidian vault).
# Run from anywhere; uses git repo root. Requires a valid second-brain-master-ia symlink.
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || {
  echo "error: not inside a git repository" >&2
  exit 1
}

LINK="${ROOT}/second-brain-master-ia"
SRC="${LINK}/proyectos/estimador-cag/"
DST="${ROOT}/proyectos/estimador-cag/docs/"

if [[ ! -e "${LINK}" ]]; then
  echo "error: missing ${LINK} (create the second-brain-master-ia symlink; see repo README)" >&2
  exit 1
fi

if [[ ! -d "${SRC}" ]]; then
  echo "error: source directory not found: ${SRC}" >&2
  echo "hint: fix or recreate the symlink; vault path should contain proyectos/estimador-cag/" >&2
  exit 1
fi

mkdir -p "${DST}"

# --delete: replica; files removed in the vault are removed from docs/
# Excludes: Obsidian metadata and trash only (adjust if new noise appears)
rsync -a --delete \
  --exclude='.obsidian/' \
  --exclude='.trash/' \
  "${SRC}" "${DST}"

echo "synced: ${SRC} -> ${DST}"
