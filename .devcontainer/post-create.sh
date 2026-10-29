#!/usr/bin/env bash
set -euo pipefail

# Installs dependencies for whichever parts of the app already exist.
# Safe to run before backend/frontend scaffolding is added — each step
# no-ops if its manifest isn't present yet.

if ! command -v uv >/dev/null 2>&1; then
  echo "Installing uv..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
export PATH="$HOME/.local/bin:$PATH"

if [ -f backend/pyproject.toml ]; then
  echo "Installing backend (Python) dependencies with uv..."
  (cd backend && uv sync)
fi

if [ -f frontend/package.json ]; then
  echo "Installing frontend (Node) dependencies with npm..."
  npm --prefix frontend install
fi
