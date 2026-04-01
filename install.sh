#!/usr/bin/env bash
# install.sh — Install Whisper Dictation autostart and app launcher entries
set -euo pipefail

DESKTOP_CONTENT='[Desktop Entry]
Name=Whisper Dictation
Comment=Voice dictation using whisper.cpp with Vulkan acceleration
Exec=/home/twain/Projects/whisper_dictation/venv/bin/python /home/twain/Projects/whisper_dictation/main.py
Icon=/home/twain/Projects/whisper_dictation/icons/mic-off.svg
Terminal=false
Type=Application
Categories=Utility;Accessibility;
StartupNotify=false
X-KDE-autostart-after=panel'

AUTOSTART_DIR="$HOME/.config/autostart"
APPLICATIONS_DIR="$HOME/.local/share/applications"

# Create directories if needed
mkdir -p "$AUTOSTART_DIR"
mkdir -p "$APPLICATIONS_DIR"

# Write autostart entry (starts on login)
echo "$DESKTOP_CONTENT" > "$AUTOSTART_DIR/whisper-dictation.desktop"
echo "✓ Created autostart entry: $AUTOSTART_DIR/whisper-dictation.desktop"

# Write application launcher entry (shows in app menu)
echo "$DESKTOP_CONTENT" > "$APPLICATIONS_DIR/whisper-dictation.desktop"
echo "✓ Created app launcher entry: $APPLICATIONS_DIR/whisper-dictation.desktop"

echo ""
echo "Whisper Dictation installed successfully!"
echo "  • The tray icon will appear automatically on next login."
echo "  • You can also find it in your application launcher."
