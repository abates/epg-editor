#!/usr/bin/env bash
set -euo pipefail

# Installs dependencies for whichever parts of the app already exist.
# Safe to run before backend/frontend scaffolding is added — each step
# no-ops if its manifest isn't present yet.

if [ -f backend/pyproject.toml ]; then
  echo "Installing backend (Python) dependencies..."
  pip install --upgrade pip
  pip install -e "./backend[dev]"
elif [ -f backend/requirements.txt ]; then
  echo "Installing backend (Python) dependencies..."
  pip install --upgrade pip
  pip install -r backend/requirements.txt
fi

if [ -f frontend/package.json ]; then
  echo "Installing frontend (Node) dependencies..."
  npm --prefix frontend install
fi
