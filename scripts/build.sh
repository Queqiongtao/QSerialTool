#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="$ROOT/.venv/bin/python"

if [[ ! -x "$PYTHON" ]]; then
  echo "Virtual environment not found: $PYTHON" >&2
  exit 1
fi

cd "$ROOT"
"$PYTHON" scripts/check_docs_sync.py --working-tree
"$PYTHON" -m ruff format --check .
"$PYTHON" -m ruff check .
QT_QPA_PLATFORM=offscreen "$PYTHON" -m pytest
"$PYTHON" -m PyInstaller --clean --noconfirm packaging/qserialtool.spec

ARTIFACT="$ROOT/dist/QSerialTool"
if [[ ! -x "$ARTIFACT" ]]; then
  echo "Expected artifact was not produced: $ARTIFACT" >&2
  exit 1
fi

if command -v sha256sum >/dev/null 2>&1; then
  sha256sum "$ARTIFACT" | sed "s|$ARTIFACT|QSerialTool|" > "$ARTIFACT.sha256"
else
  shasum -a 256 "$ARTIFACT" | sed "s|$ARTIFACT|QSerialTool|" > "$ARTIFACT.sha256"
fi

echo "Built: $ARTIFACT"
cat "$ARTIFACT.sha256"