#!/usr/bin/env bash
# Mirror Second Brain project notes into the repo (canonical source: Obsidian vault).
# Run from anywhere; uses git repo root. Requires a valid learnings/second-brain-master-ia symlink.
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || {
  echo "error: not inside a git repository" >&2
  exit 1
}

LINK="${ROOT}/learnings/second-brain-master-ia"
SRC="${LINK}/proyectos/estimador-cag/"
DST="${ROOT}/docs/"

if [[ ! -e "${LINK}" ]]; then
  echo "error: missing ${LINK} (create the learnings/second-brain-master-ia symlink; see repo README)" >&2
  exit 1
fi

if [[ ! -d "${SRC}" ]]; then
  echo "error: source directory not found: ${SRC}" >&2
  echo "hint: fix or recreate the symlink; vault path should contain proyectos/estimador-cag/" >&2
  exit 1
fi

mkdir -p "${DST}"

# Main replica under docs/ (learning-oriented subtrees go under learnings/)
rsync -a --delete \
  --exclude='.obsidian/' \
  --exclude='.trash/' \
  --exclude='sesiones/' \
  --exclude='aprendizajes/' \
  --exclude='retrospectivas/' \
  "${SRC}" "${DST}"

mirror_subtree() {
  local rel="$1"
  local dest="$2"
  if [[ -d "${SRC}${rel}" ]]; then
    mkdir -p "${dest}"
    rsync -a --delete \
      --exclude='.obsidian/' \
      --exclude='.trash/' \
      "${SRC}${rel}/" "${dest}/"
    echo "synced: ${SRC}${rel}/ -> ${dest}/"
  fi
}

mirror_subtree "sesiones" "${ROOT}/learnings/docs/sesiones"
mirror_subtree "aprendizajes" "${ROOT}/learnings/aprendizajes"
mirror_subtree "retrospectivas" "${ROOT}/learnings/retrospectiva"

echo "synced: ${SRC} -> ${DST} (with learnings/ mirrors for sesiones, aprendizajes, retrospectivas)"
