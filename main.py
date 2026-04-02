#!/usr/bin/env python3
"""Voice Assistant — KDE system tray app with wake word, voice commands, and dictation."""

import logging
import os
import shutil
import sys

from PyQt6.QtCore import QSize, Qt, QThread, QTimer, pyqtSignal, QObject
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QAction
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu

import config
from audio_engine import AudioEngine
from dictation import (
    DictationManager, CommandTranscriptionWorker,
    STATE_IDLE, STATE_RECORDING, STATE_PROCESSING, STATE_LISTENING,
    get_focused_window_id, _reset_log_handler, log,
)
from osd_popup import OSDPopup
from settings_manager import SettingsWindow, load_settings, save_settings
from voice_commands import match_command, execute_shortcut


def _load_svg_icon(path):
    """Load an SVG file as a QIcon using QSvgRenderer."""
    renderer = QSvgRenderer(path)
    if not renderer.isValid():
        return QIcon(path)
    pixmap = QPixmap(QSize(64, 64))
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return QIcon(pixmap)


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
    if shutil.which("sox") is None:
        errors.append("sox not found. Install: sudo apt install sox")
    if shutil.which("xdotool") is None:
        errors.append("xdotool not found. Install: sudo apt install xdotool")
    if shutil.which("xsel") is None:
        errors.append("xsel not found. Install: sudo apt install xsel")
    return errors


class TrayApp(QObject):
    """System tray application — integrates audio engine, dictation, wake word, OSD."""

    # Signal to handle wake word from audio thread safely
    _wake_word_detected = pyqtSignal()
    _silence_timeout_reached = pyqtSignal()

    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)
        self.app.setApplicationName("Voice Assistant")

        super().__init__()

        # Load settings
        self._settings = load_settings()

        # Icons
        self.icon_on = _load_svg_icon(config.ICON_MIC_ON)
        self.icon_off = _load_svg_icon(config.ICON_MIC_OFF)

        # Audio engine (unified PyAudio stream)
        self.audio_engine = AudioEngine()
        self.audio_engine.set_silence_timeout(self._settings["silence_timeout"])
        # Apply saved wake word model
        ww_model = self._settings.get("wake_word_model", config.DEFAULT_WAKE_WORD)
        custom_path = self._settings.get("custom_wake_word_path", "")
        self.audio_engine.set_wake_word_model(ww_model, custom_path)

        # Dictation manager
        self.dictation = DictationManager(self.audio_engine)
        self.dictation.state_changed.connect(self._on_state_changed)
        self.dictation.error_occurred.connect(self._on_error)

        # OSD popup
        self.osd = OSDPopup()

        # Settings window (lazy)
        self._settings_window = None

        # Wake word / command state
        self._app_state = STATE_IDLE
        self._cmd_thread = None
        self._cmd_worker = None

        # Connect cross-thread signals
        self._wake_word_detected.connect(self._on_wake_word)
        self._silence_timeout_reached.connect(self._on_command_silence)
        self.audio_engine.set_wake_callback(self._wake_word_bridge)

        # System tray icon
        self.tray = QSystemTrayIcon(self.icon_off, self.app)
        self.tray.setToolTip("Voice Assistant — Ready")
        self.tray.activated.connect(self._on_tray_activated)

        # Context menu (right-click)
        menu = QMenu()
        self.toggle_action = QAction("Start Recording", menu)
        self.toggle_action.triggered.connect(self._toggle)
        menu.addAction(self.toggle_action)
        menu.addSeparator()
        settings_action = QAction("Settings...", menu)
        settings_action.triggered.connect(self._open_settings)
        menu.addAction(settings_action)
        menu.addSeparator()
        quit_action = QAction("Quit", menu)
        quit_action.triggered.connect(self._quit)
        menu.addAction(quit_action)
        self.tray.setContextMenu(menu)

        self.tray.show()

        # Start audio engine
        self.audio_engine.start()

    def _wake_word_bridge(self):
        """Bridge from audio thread to Qt main thread via signal."""
        self._wake_word_detected.emit()

    def _on_wake_word(self):
        """Handle wake word detection (runs on main thread)."""
        if self._app_state != STATE_IDLE:
            log.info("Wake word ignored — app not idle (state=%s)", self._app_state)
            return

        log.info("Wake word activated — entering LISTENING state")
        self._app_state = STATE_LISTENING

        # Show OSD
        self.osd.show_message("Listening...")

        # Start recording the command
        for path in (config.RAW_WAV, config.TRIMMED_WAV, config.OUTPUT_TXT):
            if os.path.isfile(path):
                os.remove(path)

        # Record with VAD — when silence is detected, transcribe the command
        self.audio_engine.set_silence_callback(self._silence_timeout_bridge)
        self.audio_engine.start_recording(with_vad=True)

    def _silence_timeout_bridge(self):
        """Bridge silence timeout from audio thread to Qt main thread."""
        self._silence_timeout_reached.emit()

    def _on_command_silence(self):
        """Silence detected after wake word — transcribe and process command."""
        if self._app_state != STATE_LISTENING:
            return

        log.info("Command recording complete — transcribing")
        self.audio_engine.stop_recording()
        self.audio_engine.set_silence_callback(None)

        self.osd.show_message("Processing...")

        # Transcribe the command in a background thread
        self._cmd_thread = QThread()
        self._cmd_worker = CommandTranscriptionWorker()
        self._cmd_worker.moveToThread(self._cmd_thread)

        self._cmd_thread.started.connect(self._cmd_worker.run)
        self._cmd_worker.finished.connect(self._on_command_transcribed)
        self._cmd_worker.error.connect(self._on_error)

        self._cmd_thread.start()

    def _on_command_transcribed(self, text):
        """Handle the transcribed voice command."""
        # Clean up thread
        if self._cmd_thread is not None:
            self._cmd_thread.quit()
            self._cmd_thread.wait(5000)
            self._cmd_thread = None
        self._cmd_worker = None

        if not text:
            log.info("Empty command — returning to idle")
            self.osd.hide_message()
            self._app_state = STATE_IDLE
            return

        # Match against commands
        mapping = match_command(text, self._settings.get("command_mappings", []))

        if mapping and mapping["shortcut"] == "__DICTATE__":
            # Mode B: Voice-triggered dictation
            log.info("Voice command: DICTATE — starting voice-triggered dictation")
            self.osd.show_message("Dictating...")
            self._app_state = STATE_IDLE  # Reset so dictation manager can take over
            self.dictation.start_voice_dictation()
        elif mapping:
            # Execute keyboard shortcut
            log.info("Voice command: %s -> %s", mapping["phrase"], mapping["shortcut"])
            self.osd.hide_message()
            execute_shortcut(mapping["shortcut"])
            self._app_state = STATE_IDLE
        else:
            # No match
            log.info("No command matched: %r", text)
            self.osd.show_message(f"Unknown: {text[:30]}")
            QTimer.singleShot(2000, self._return_to_idle)

    def _return_to_idle(self):
        """Return to idle state and hide OSD."""
        self.osd.hide_message()
        self._app_state = STATE_IDLE

    def _on_tray_activated(self, reason):
        """Handle tray icon clicks."""
        if reason == QSystemTrayIcon.ActivationReason.Trigger:  # Left-click
            self._toggle()

    def _toggle(self):
        """Toggle dictation state (Mode A: manual click)."""
        if self._app_state == STATE_LISTENING:
            # Cancel wake word listening
            self.audio_engine.stop_recording()
            self.audio_engine.set_silence_callback(None)
            self.osd.hide_message()
            self._app_state = STATE_IDLE
            return

        self.dictation.toggle()

    def _on_state_changed(self, state):
        """Update tray icon and tooltip based on dictation state."""
        if state == STATE_RECORDING:
            self.tray.setIcon(self.icon_on)
            self.tray.setToolTip("Voice Assistant — Recording...")
            self.toggle_action.setText("Stop & Transcribe")
            self._app_state = STATE_RECORDING
        elif state == STATE_PROCESSING:
            self.tray.setIcon(self.icon_off)
            self.tray.setToolTip("Voice Assistant — Transcribing...")
            self.toggle_action.setText("Processing...")
            self.toggle_action.setEnabled(False)
            self._app_state = STATE_PROCESSING
        else:  # STATE_IDLE
            self.tray.setIcon(self.icon_off)
            self.tray.setToolTip("Voice Assistant — Ready")
            self.toggle_action.setText("Start Recording")
            self.toggle_action.setEnabled(True)
            self.osd.hide_message()
            self._app_state = STATE_IDLE

    def _on_error(self, message):
        """Show error as tray notification."""
        self.tray.showMessage("Voice Assistant Error", message,
                              QSystemTrayIcon.MessageIcon.Critical, 5000)

    def _open_settings(self):
        """Open the settings window."""
        if self._settings_window is None:
            self._settings_window = SettingsWindow()
            self._settings_window.settings_changed.connect(self._on_settings_changed)
        self._settings_window.show_and_raise()

    def _on_settings_changed(self, settings):
        """Apply updated settings."""
        self._settings = settings
        self.audio_engine.set_silence_timeout(settings["silence_timeout"])
        self.audio_engine.set_wake_word_model(
            settings.get("wake_word_model", config.DEFAULT_WAKE_WORD),
            settings.get("custom_wake_word_path", ""),
        )
        log.info("Settings updated: wake_word=%s, silence_timeout=%.1f, commands=%d",
                 settings.get("wake_word_model", "?"),
                 settings["silence_timeout"],
                 len(settings.get("command_mappings", [])))

    def _quit(self):
        """Clean shutdown."""
        self.dictation.stop()
        self.audio_engine.stop()
        self.osd.hide_message()
        self.tray.hide()
        self.app.quit()

    def run(self):
        """Start the application."""
        errors = check_dependencies()
        if errors:
            for err in errors:
                self.tray.showMessage("Voice Assistant Error", err,
                                      QSystemTrayIcon.MessageIcon.Critical, 5000)
        return self.app.exec()


def main():
    app = TrayApp()
    sys.exit(app.run())


if __name__ == "__main__":
    main()
