# ADR: IPC Socket for External Toggle + Send Buttons in Settings

## Date: 2026-05-13

## Status: Accepted

## Context
Two features were requested:
1. A "Send" button in the Settings GUI for each command mapping row, so users can execute commands directly from settings without voice input.
2. A hotkey-toggle mechanism so users can start/stop dictation via a keyboard shortcut, with the tray icon updating just like a manual click.

## Decision
- **Send buttons**: Added a 4th column ("Send") to the command mappings QTableWidget in `settings_manager.py`. Each row gets a QPushButton that calls `execute_action()` from `voice_commands.py` directly.
- **IPC socket**: Added a Unix domain socket (`/tmp/voice_assistant_ipc.sock`) in `TrayApp.__init__()` using `socket.AF_UNIX, socket.SOCK_STREAM`. A `QSocketNotifier` watches for incoming connections on the main thread. When data arrives, it's parsed as a command string (`toggle`, `start`, `stop`). The `_toggle()` method is invoked via `QTimer.singleShot(0, ...)` to ensure thread safety with Qt's main event loop.
- **Toggle script**: Created `scripts/toggle_dictation.sh` which sends `"toggle"` to the IPC socket via `socat`. This script can be bound to any KDE keyboard shortcut.

## Consequences
- External scripts can now control the app via the IPC socket (toggle/start/stop).
- The tray icon and menu state update correctly because `_toggle()` runs on the Qt main thread.
- `socat` is now a required system dependency for the hotkey toggle feature.
- The IPC socket is cleaned up on app quit via `_cleanup_ipc()`.
