#!/usr/bin/env bash
# Toggle dictation on/off via IPC socket.
# Bind this script to a hotkey in KDE System Settings → Shortcuts.
# Sends "toggle" to the running Voice Assistant's IPC socket.
SOCKET="/tmp/voice_assistant_ipc.sock"

if [ ! -S "$SOCKET" ]; then
    echo "Error: Voice Assistant IPC socket not found at $SOCKET" >&2
    echo "Is the Voice Assistant running?" >&2
    exit 1
fi

echo -n "toggle" | socat - UNIX-CONNECT:"$SOCKET" 2>/dev/null

if [ $? -ne 0 ]; then
    echo "Error: Failed to connect to Voice Assistant IPC socket." >&2
    echo "Ensure 'socat' is installed (sudo apt install socat)." >&2
    exit 1
fi
