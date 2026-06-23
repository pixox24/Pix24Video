#!/bin/bash
set -u

# macOS Finder shortcut for launching the Pixelle-Video Web UI.
cd "$(dirname "$0")"

export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

clear
echo "Starting Pixelle-Video Web UI..."
echo "Project folder: $(pwd)"
echo

if ! command -v uv >/dev/null 2>&1; then
  echo "[ERROR] uv was not found."
  echo "Install uv first: https://docs.astral.sh/uv/getting-started/installation/"
  echo
  read -r -p "Press Enter to close this window..."
  exit 1
fi

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "[WARN] ffmpeg was not found. The Web UI can start, but video generation may fail."
  echo "On macOS, install it with: brew install ffmpeg"
  echo
fi

echo "Opening http://localhost:8501 ..."
(sleep 3 && open "http://localhost:8501") >/dev/null 2>&1 &

uv run streamlit run web/app.py

status=$?
echo
echo "Pixelle-Video exited with status $status."
read -r -p "Press Enter to close this window..."
exit "$status"
