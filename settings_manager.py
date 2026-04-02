"""Settings persistence (config.json) and Settings GUI window."""

import json
import logging
import os

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSlider, QDoubleSpinBox,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, QGroupBox,
    QComboBox, QLineEdit, QMessageBox, QFileDialog,
)

import config

log = logging.getLogger("settings")

# ── Default settings ──────────────────────────────────────────────
_DEFAULTS = {
    "silence_timeout": config.DEFAULT_SILENCE_TIMEOUT,
    "wake_word_enabled": True,
    "wake_word_model": config.DEFAULT_WAKE_WORD,
    "custom_wake_word_path": "",        # absolute path to user's .onnx file
    "command_mappings": [],             # list of {"phrase": str, "shortcut": str}
}


def load_settings():
    """Load settings from config.json, returning defaults for missing keys."""
    settings = dict(_DEFAULTS)
    if os.path.isfile(config.CONFIG_JSON):
        try:
            with open(config.CONFIG_JSON, "r", encoding="utf-8") as f:
                saved = json.load(f)
            settings.update(saved)
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("Failed to load config.json: %s", exc)
    return settings


def save_settings(settings):
    """Save settings to config.json."""
    try:
        with open(config.CONFIG_JSON, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2)
        log.info("Settings saved to %s", config.CONFIG_JSON)
    except OSError as exc:
        log.error("Failed to save config.json: %s", exc)


class SettingsWindow(QWidget):
    """Settings GUI window — opened via right-click on tray icon."""

    settings_changed = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Voice Assistant Settings")
        self.setMinimumWidth(500)
        self.setMinimumHeight(400)
        self._settings = load_settings()
        self._build_ui()
        self._populate()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # ── Wake Word Selection ───────────────────────────────────
        ww_group = QGroupBox("Wake Word")
        ww_layout = QVBoxLayout(ww_group)

        combo_row = QHBoxLayout()
        combo_row.addWidget(QLabel("Wake word:"))
        self._ww_combo = QComboBox()
        for display_name, model_key in config.WAKE_WORD_MODELS.items():
            self._ww_combo.addItem(display_name, model_key)
        self._ww_combo.addItem("Custom (.onnx file)...", config.CUSTOM_WAKE_WORD_KEY)
        self._ww_combo.currentIndexChanged.connect(self._on_ww_combo_changed)
        combo_row.addWidget(self._ww_combo)
        ww_layout.addLayout(combo_row)

        # Custom model path row (hidden by default)
        self._custom_row = QWidget()
        custom_layout = QHBoxLayout(self._custom_row)
        custom_layout.setContentsMargins(0, 0, 0, 0)
        custom_layout.addWidget(QLabel("Model file:"))
        self._custom_path_edit = QLineEdit()
        self._custom_path_edit.setPlaceholderText("Select an .onnx wake word model...")
        self._custom_path_edit.setReadOnly(True)
        custom_layout.addWidget(self._custom_path_edit)
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse_custom_model)
        custom_layout.addWidget(browse_btn)
        self._custom_row.setVisible(False)
        ww_layout.addWidget(self._custom_row)

        layout.addWidget(ww_group)

        # ── Silence Timeout ───────────────────────────────────────
        timeout_group = QGroupBox("Voice-Triggered Dictation")
        timeout_layout = QHBoxLayout(timeout_group)

        timeout_layout.addWidget(QLabel("Silence timeout:"))
        self._timeout_spin = QDoubleSpinBox()
        self._timeout_spin.setRange(config.MIN_SILENCE_TIMEOUT,
                                     config.MAX_SILENCE_TIMEOUT)
        self._timeout_spin.setSingleStep(0.1)
        self._timeout_spin.setSuffix(" s")
        self._timeout_spin.setDecimals(1)
        timeout_layout.addWidget(self._timeout_spin)

        self._timeout_slider = QSlider(Qt.Orientation.Horizontal)
        self._timeout_slider.setRange(
            int(config.MIN_SILENCE_TIMEOUT * 10),
            int(config.MAX_SILENCE_TIMEOUT * 10),
        )
        timeout_layout.addWidget(self._timeout_slider)

        # Sync slider ↔ spinbox
        self._timeout_slider.valueChanged.connect(
            lambda v: self._timeout_spin.setValue(v / 10.0)
        )
        self._timeout_spin.valueChanged.connect(
            lambda v: self._timeout_slider.setValue(int(v * 10))
        )

        layout.addWidget(timeout_group)

        # ── Command Mappings ──────────────────────────────────────
        cmd_group = QGroupBox("Voice Command Mappings")
        cmd_layout = QVBoxLayout(cmd_group)

        self._table = QTableWidget(0, 2)
        self._table.setHorizontalHeaderLabels(["Voice Phrase", "Keyboard Shortcut"])
        self._table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self._table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        cmd_layout.addWidget(self._table)

        btn_layout = QHBoxLayout()
        add_btn = QPushButton("Add Row")
        add_btn.clicked.connect(self._add_row)
        btn_layout.addWidget(add_btn)

        remove_btn = QPushButton("Remove Selected")
        remove_btn.clicked.connect(self._remove_selected)
        btn_layout.addWidget(remove_btn)
        btn_layout.addStretch()
        cmd_layout.addLayout(btn_layout)

        layout.addWidget(cmd_group)

        # ── Save / Cancel ─────────────────────────────────────────
        bottom = QHBoxLayout()
        bottom.addStretch()
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self._save)
        bottom.addWidget(save_btn)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.close)
        bottom.addWidget(cancel_btn)
        layout.addLayout(bottom)

    def _on_ww_combo_changed(self, index):
        """Show/hide custom model path row based on combo selection."""
        is_custom = self._ww_combo.itemData(index) == config.CUSTOM_WAKE_WORD_KEY
        self._custom_row.setVisible(is_custom)

    def _browse_custom_model(self):
        """Open file dialog to select a custom .onnx wake word model."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Wake Word Model", "",
            "ONNX Models (*.onnx);;All Files (*)"
        )
        if path:
            self._custom_path_edit.setText(path)

    def _populate(self):
        """Fill UI from current settings."""
        # Wake word combo
        current_model = self._settings.get("wake_word_model", config.DEFAULT_WAKE_WORD)
        found = False
        for i in range(self._ww_combo.count()):
            if self._ww_combo.itemData(i) == current_model:
                self._ww_combo.setCurrentIndex(i)
                found = True
                break
        if not found:
            # Default to first item if saved model not found
            self._ww_combo.setCurrentIndex(0)

        # Custom model path
        custom_path = self._settings.get("custom_wake_word_path", "")
        self._custom_path_edit.setText(custom_path)
        self._custom_row.setVisible(current_model == config.CUSTOM_WAKE_WORD_KEY)

        self._timeout_spin.setValue(self._settings["silence_timeout"])

        mappings = self._settings.get("command_mappings", [])
        self._table.setRowCount(len(mappings))
        for i, mapping in enumerate(mappings):
            self._table.setItem(i, 0, QTableWidgetItem(mapping.get("phrase", "")))
            self._table.setItem(i, 1, QTableWidgetItem(mapping.get("shortcut", "")))

    def _add_row(self):
        row = self._table.rowCount()
        self._table.insertRow(row)
        self._table.setItem(row, 0, QTableWidgetItem(""))
        self._table.setItem(row, 1, QTableWidgetItem(""))

    def _remove_selected(self):
        rows = set(idx.row() for idx in self._table.selectedIndexes())
        for row in sorted(rows, reverse=True):
            self._table.removeRow(row)

    def _save(self):
        """Collect UI values, save to disk, emit signal."""
        mappings = []
        for row in range(self._table.rowCount()):
            phrase_item = self._table.item(row, 0)
            shortcut_item = self._table.item(row, 1)
            phrase = phrase_item.text().strip() if phrase_item else ""
            shortcut = shortcut_item.text().strip() if shortcut_item else ""
            if phrase and shortcut:
                mappings.append({"phrase": phrase, "shortcut": shortcut})

        self._settings["wake_word_model"] = self._ww_combo.currentData()
        self._settings["custom_wake_word_path"] = self._custom_path_edit.text()
        self._settings["silence_timeout"] = self._timeout_spin.value()
        self._settings["command_mappings"] = mappings

        save_settings(self._settings)
        self.settings_changed.emit(self._settings)
        self.close()

    def show_and_raise(self):
        """Show window and bring to front."""
        self._settings = load_settings()
        self._populate()
        self.show()
        self.raise_()
        self.activateWindow()
