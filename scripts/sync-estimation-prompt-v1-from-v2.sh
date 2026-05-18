#!/usr/bin/env bash
# Sync estimation v1 prompt bundle from v2 (retrocompatible copy). Run after editing v2/.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="${ROOT}/app/prompts/estimation/v2"
DST="${ROOT}/app/prompts/estimation/v1"

if [[ ! -d "${SRC}" ]]; then
  echo "Missing source bundle: ${SRC}" >&2
  exit 1
fi

rsync -a --delete "${SRC}/" "${DST}/"
if [[ "$(uname)" == "Darwin" ]]; then
  sed -i '' 's/^version = "v2"/version = "v1"/' "${DST}/manifest.toml"
else
  sed -i 's/^version = "v2"/version = "v1"/' "${DST}/manifest.toml"
fi

echo "Synced ${SRC} -> ${DST} (manifest version=v1)"
