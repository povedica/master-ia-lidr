#!/bin/sh
set -e
/app
uv sync --frozen --no-cache
exec "$@"
