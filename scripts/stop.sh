#!/usr/bin/env bash
# stop.sh — Stop MP3 playback started by talk.sh.
# Triggered by the voice command "stop".
#
# Kills any mpv processes started by the scripts/ directory.

# Kill all mpv processes (graceful SIGTERM first)
if pkill -x mpv 2>/dev/null; then
    echo "Stopped mpv playback."
else
    echo "No mpv process found."
fi
