#!/bin/sh
set -e
cd /app
uv sync --frozen --no-cache
exec "$@"
