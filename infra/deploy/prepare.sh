#!/usr/bin/env bash
set -euo pipefail

DATAFORGE_PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$DATAFORGE_PROJECT_ROOT"

command -v uv >/dev/null 2>&1 || { echo "uv is required" >&2; exit 1; }
command -v npm >/dev/null 2>&1 || { echo "npm is required" >&2; exit 1; }

uv sync --frozen --extra dataflow --extra web --extra studio --extra indexing
npm ci --prefix frontend
npm run build --prefix frontend

if [[ -f third_party/dataflow_webui/frontend/package-lock.json ]]; then
  npm ci --prefix third_party/dataflow_webui/frontend
  npm run build --prefix third_party/dataflow_webui/frontend
fi

uv run --extra dataflow --extra web --extra studio --extra indexing dataforge doctor
