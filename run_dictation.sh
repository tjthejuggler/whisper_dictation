#!/usr/bin/env bash
# Run whisper_dictation from anywhere
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/venv/bin/activate"
python3 "$SCRIPT_DIR/main.py" "$@"
