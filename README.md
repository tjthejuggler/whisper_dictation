# Whisper Dictation

A minimal KDE Plasma system tray application for voice dictation using [whisper.cpp](https://github.com/ggerganov/whisper.cpp) with Vulkan GPU acceleration.

Click the tray icon to start recording. Click again to stop, transcribe, and type the result into the focused window.

## Requirements

- **Kubuntu / KDE Plasma on X11**
- **Python 3.8+**
- **PyQt5** — for the system tray icon
- **arecord** — for audio capture (`alsa-utils` package)
- **sox** — for silence trimming
- **xdotool** — for simulating keyboard paste into the active window
- **xsel** — for clipboard-based text injection (exits immediately, unlike xclip)
- **whisper.cpp** — compiled `whisper-cli` binary with Vulkan support

## Quick Start

```bash
# 1. Clone and enter the project
cd /home/twain/Projects/whisper_dictation

# 2. Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# 3. Install Python dependencies
pip install -r requirements.txt

# 4. Build whisper.cpp with Vulkan and download the model
./setup_whisper.sh

# 5. Run the tray app
python main.py
```

## Setup Details

### System Dependencies

```bash
sudo apt install alsa-utils sox xdotool xsel
```

### whisper.cpp with Vulkan

Run the setup script to clone, compile, and download the model:

```bash
./setup_whisper.sh
```

This will:
- Install build dependencies (`cmake`, `libvulkan-dev`, etc.)
- Clone and compile `whisper.cpp` with `-DGGML_VULKAN=1`
- Download the **Large V3 Turbo Q5** quantized model (~1 GB)

Paths after setup:
```
~/.local/share/dictation-tool/whisper.cpp/build/bin/whisper-cli
~/.local/share/dictation-tool/whisper.cpp/models/ggml-large-v3-turbo-q5_0.bin
```

## Install (Autostart)

Run the installer to add Whisper Dictation to your KDE autostart and application launcher:

```bash
./install.sh
```

This creates:
- `~/.config/autostart/whisper-dictation.desktop` — starts the tray app on login
- `~/.local/share/applications/whisper-dictation.desktop` — shows in the app launcher

## Usage

Run from anywhere on your system using the launcher script:

```bash
/home/twain/Projects/whisper_dictation/run_dictation.sh
```

Or manually from the project directory:

```bash
source venv/bin/activate
python main.py
```

- **Left-click** the tray icon to **start recording** (icon turns green)
- **Left-click again** to **stop recording and transcribe** (icon shows processing state)
- Transcribed text is automatically pasted into the focused window via clipboard
- **Right-click** for context menu (Start/Stop, Quit)

## How It Works

The pipeline has 5 stages:

1. **Record** — `arecord` captures 16kHz/16-bit/mono WAV audio from the microphone
2. **Stop** — `arecord` is terminated via SIGTERM, finalizing the WAV file
3. **Trim** — `sox` strips leading/trailing silence to prevent Whisper hallucinations
4. **Transcribe** — `whisper-cli` (Vulkan-accelerated) processes the audio with:
   - Large V3 Turbo Q5 quantized model (RAM-efficient)
   - Entropy threshold of 2.4 (anti-hallucination)
   - Context prompt biased for coding terminology
   - English language forced
5. **Inject** — `xsel` copies text to clipboard, then `xdotool` simulates Ctrl+V to paste instantly

## File Structure

```
whisper_dictation/
├── main.py              # Entry point — tray icon and app lifecycle
├── dictation.py         # DictationManager — record/trim/transcribe/inject pipeline
├── config.py            # Paths and constants
├── setup_whisper.sh     # Build whisper.cpp with Vulkan + download model
├── install.sh           # Installer — autostart and app launcher entries
├── icons/
│   ├── mic-on.svg       # Tray icon: recording active (green)
│   └── mic-off.svg      # Tray icon: idle (gray)
├── requirements.txt
├── plans/
│   └── architecture.md
└── README.md
```

## Changelog

- **2026-04-01T10:23 UTC-6** — Fixed auto-paste: replaced `xclip` with `xsel --clipboard --input` for clipboard writes. `xclip` was hanging (5s timeout) in the background QThread because it forks to serve X11 selection requests. `xsel` writes and exits immediately. Also added `xdotool windowactivate --sync` to re-focus the target window before pasting.
- **2026-04-01T10:05 UTC-6** — Replaced `xdotool type --delay 2` with instant clipboard paste (`xsel` + `xdotool key ctrl+v`). Text injection is now effectively instant regardless of transcription length.
- **2026-04-01T14:38 UTC-6** — Major refactor: replaced real-time `whisper-stream` with batch `arecord` → `sox` → `whisper-cli` → `xdotool` pipeline. Added `setup_whisper.sh` for Vulkan compilation and Large V3 Turbo Q5 model download. New 3-state UI (idle/recording/processing).
- **2026-04-01T04:56 UTC** — Fixed `\r` partial transcriptions being injected as final text.

---

*Last updated: 2026-04-01T10:23 UTC-6*
