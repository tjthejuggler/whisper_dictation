#!/usr/bin/env python3
"""Whisper Dictation — KDE system tray app for voice dictation."""

import os
import shutil
import sys

from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QApplication, QSystemTrayIcon, QMenu, QAction

import config
from dictation import DictationManager, STATE_IDLE, STATE_RECORDING, STATE_PROCESSING


def check_dependencies():
    """Verify required external tools exist. Returns list of error messages."""
    errors = []
    if not os.path.isfile(config.WHISPER_CLI_BIN):
        errors.append(
            f"whisper-cli not found at:\n{config.WHISPER_CLI_BIN}\n"
            "Run ./setup_whisper.sh to build it."
        )
    if not os.path.isfile(config.WHISPER_MODEL):
        errors.append(
            f"Whisper model not found at:\n{config.WHISPER_MODEL}\n"
            "Run ./setup_whisper.sh to download it."
        )
    if shutil.which("arecord") is None:
        errors.append("arecord not found. Install: sudo apt install alsa-utils")
    if shutil.which("sox") is None:
        errors.append("sox not found. Install: sudo apt install sox")
    if shutil.which("xdotool") is None:
        errors.append("xdotool not found. Install: sudo apt install xdotool")
    return errors


class TrayApp:
    """System tray application for whisper dictation."""

    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)
        self.app.setApplicationName("Whisper Dictation")

        # Icons
        self.icon_on = QIcon(config.ICON_MIC_ON)
        self.icon_off = QIcon(config.ICON_MIC_OFF)

        # System tray icon
        self.tray = QSystemTrayIcon(self.icon_off, self.app)
        self.tray.setToolTip("Whisper Dictation — Ready")
        self.tray.activated.connect(self._on_tray_activated)

        # Context menu
        menu = QMenu()
        self.toggle_action = QAction("Start Recording", menu)
        self.toggle_action.triggered.connect(self._toggle)
        menu.addAction(self.toggle_action)
        menu.addSeparator()
        quit_action = QAction("Quit", menu)
        quit_action.triggered.connect(self._quit)
        menu.addAction(quit_action)
        self.tray.setContextMenu(menu)

        # Dictation manager
        self.dictation = DictationManager()
        self.dictation.state_changed.connect(self._on_state_changed)
        self.dictation.error_occurred.connect(self._on_error)

        self.tray.show()

    def _on_tray_activated(self, reason):
        """Handle tray icon clicks."""
        if reason == QSystemTrayIcon.Trigger:  # Left-click
            self._toggle()

    def _toggle(self):
        """Toggle dictation state."""
        self.dictation.toggle()

    def _on_state_changed(self, state):
        """Update tray icon and tooltip based on dictation state."""
        if state == STATE_RECORDING:
            self.tray.setIcon(self.icon_on)
            self.tray.setToolTip("Whisper Dictation — Recording...")
            self.toggle_action.setText("Stop & Transcribe")
        elif state == STATE_PROCESSING:
            self.tray.setIcon(self.icon_off)
            self.tray.setToolTip("Whisper Dictation — Transcribing...")
            self.toggle_action.setText("Processing...")
            self.toggle_action.setEnabled(False)
        else:  # STATE_IDLE
            self.tray.setIcon(self.icon_off)
            self.tray.setToolTip("Whisper Dictation — Ready")
            self.toggle_action.setText("Start Recording")
            self.toggle_action.setEnabled(True)

    def _on_error(self, message):
        """Show error as tray notification."""
        self.tray.showMessage("Whisper Dictation Error", message,
                              QSystemTrayIcon.Critical, 5000)

    def _quit(self):
        """Clean shutdown."""
        self.dictation.stop()
        self.tray.hide()
        self.app.quit()

    def run(self):
        """Start the application."""
        errors = check_dependencies()
        if errors:
            for err in errors:
                self.tray.showMessage("Whisper Dictation Error", err,
                                      QSystemTrayIcon.Critical, 5000)
        return self.app.exec_()


def main():
    app = TrayApp()
    sys.exit(app.run())


if __name__ == "__main__":
    main()
