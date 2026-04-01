"""Paths and constants for the whisper dictation tray app."""

import os

# ── whisper.cpp paths ──────────────────────────────────────────────
WHISPER_BASE = os.path.expanduser("~/.local/share/dictation-tool/whisper.cpp")
WHISPER_CLI_BIN = os.path.join(WHISPER_BASE, "build", "bin", "whisper-cli")
WHISPER_MODEL = os.path.join(WHISPER_BASE, "models", "ggml-large-v3-turbo-q5_0.bin")

# ── Temp file paths ───────────────────────────────────────────────
RAW_WAV = "/tmp/vibe_raw.wav"
TRIMMED_WAV = "/tmp/vibe_trimmed.wav"
OUTPUT_FILE = "/tmp/vibe_output"        # whisper-cli adds .txt extension
OUTPUT_TXT = "/tmp/vibe_output.txt"

# ── arecord command (16kHz, 16-bit, mono — required by Whisper) ───
ARECORD_CMD = ["arecord", "-D", "pulse", "-f", "S16_LE", "-c1", "-r16000", RAW_WAV]

# ── sox silence trimming command ──────────────────────────────────
# Reverse trick: chops trailing dead air without touching natural pauses
SOX_CMD = [
    "sox", RAW_WAV, TRIMMED_WAV,
    "reverse",
    "silence", "1", "0.1", "1%",
    "reverse",
]

# ── whisper-cli arguments ─────────────────────────────────────────
WHISPER_ARGS = [
    "-m", WHISPER_MODEL,
    "-f", TRIMMED_WAV,
    "-t", "6",                          # P-cores only (6P + 10E on Ultra 9 185H)
    "-nt",                              # No timestamps
    "-et", "2.4",                       # Entropy threshold (anti-hallucination)
    "-l", "en",                         # Force English
    "--prompt", "Roo Code, TypeScript, React, useEffect, camelCase",
    "-of", OUTPUT_FILE,                 # Output file base (whisper adds .txt)
    "-otxt",                            # Output format: plain text
]

# ── Icon paths (relative to this file's directory) ────────────────
_DIR = os.path.dirname(os.path.abspath(__file__))
ICON_MIC_ON = os.path.join(_DIR, "icons", "mic-on.svg")
ICON_MIC_OFF = os.path.join(_DIR, "icons", "mic-off.svg")
