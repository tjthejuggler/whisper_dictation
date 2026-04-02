#!/usr/bin/env bash
# talk.sh — Play an MP3 from a random position, looping continuously.
# Triggered by the voice command "talk".
#
# Requires: mpv

MP3_FILE="/home/twain/Downloads/Al_Kelly_Talks.mp3"

# ── Validate ──────────────────────────────────────────────────────
if [[ ! -f "$MP3_FILE" ]]; then
    echo "ERROR: MP3 file not found: $MP3_FILE" >&2
    exit 1
fi

if ! command -v mpv &>/dev/null; then
    echo "ERROR: mpv not found. Install: sudo apt install mpv" >&2
    exit 1
fi

# ── Pick a random start percentage (0-99%) ────────────────────────
START_PCT=$(( RANDOM % 100 ))

echo "Playing $MP3_FILE from ${START_PCT}%, looping..."

# ── Play from random position, loop forever ───────────────────────
# --start=N%       → start at N% of the file (no ffprobe needed)
# --loop-file=inf  → loop the file indefinitely
# --no-video       → audio only (no window)
# --really-quiet   → suppress mpv output
exec mpv --no-video --really-quiet --loop-file=inf --start="${START_PCT}%" "$MP3_FILE"
