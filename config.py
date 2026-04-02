"""Paths and constants for the whisper dictation + voice assistant app."""

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

# ── Audio settings (PyAudio) ──────────────────────────────────────
AUDIO_RATE = 16000                      # 16kHz — required by Whisper
AUDIO_CHANNELS = 1                      # Mono
AUDIO_FORMAT_WIDTH = 2                  # 16-bit (2 bytes per sample)
AUDIO_CHUNK = 1280                      # 80ms at 16kHz (must be 10/20/30ms for webrtcvad)

# ── Wake word settings ────────────────────────────────────────────
WAKE_WORD_THRESHOLD = 0.5              # Detection confidence threshold (0.0-1.0)
DEFAULT_WAKE_WORD = "hey_jarvis_v0.1"  # Default wake word model name (filename stem)
CUSTOM_WAKE_WORD_KEY = "__custom__"    # Sentinel value for user-provided .onnx file

# Available bundled wake word models (display name → onnx filename stem)
WAKE_WORD_MODELS = {
    "Alexa":       "alexa_v0.1",
    "Hey Jarvis":  "hey_jarvis_v0.1",
    "Hey Marvin":  "hey_marvin_v0.1",
    "Hey Mycroft": "hey_mycroft_v0.1",
    "Timer":       "timer_v0.1",
    "Weather":     "weather_v0.1",
}

# ── Voice-triggered dictation defaults ────────────────────────────
DEFAULT_SILENCE_TIMEOUT = 2.5           # Seconds of silence to auto-stop dictation
MIN_SILENCE_TIMEOUT = 1.5
MAX_SILENCE_TIMEOUT = 5.0

# ── Settings persistence ──────────────────────────────────────────
_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_JSON = os.path.join(_DIR, "config.json")

# ── Icon paths (relative to this file's directory) ────────────────
ICON_MIC_ON = os.path.join(_DIR, "icons", "mic-on.svg")
ICON_MIC_OFF = os.path.join(_DIR, "icons", "mic-off.svg")

# ── Legacy arecord command (kept for reference, replaced by PyAudio) ─
ARECORD_CMD = ["arecord", "-D", "pulse", "-f", "S16_LE", "-c1", "-r16000", RAW_WAV]
