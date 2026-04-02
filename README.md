# Voice Assistant & Whisper Dictation

A locally-hosted voice assistant and dictation system tray application for KDE Plasma on X11. Uses [whisper.cpp](https://github.com/ggerganov/whisper.cpp) with Vulkan GPU acceleration (Intel Arc iGPU) for fast speech-to-text, [openwakeword](https://github.com/dscripka/openWakeWord) for hands-free wake word detection, and [webrtcvad](https://github.com/wiseman/py-webrtcvad) for voice activity detection.

## Features

- **Manual Dictation (Mode A):** Click tray icon to start/stop recording. Text is transcribed and pasted into the focused window.
- **Voice-Triggered Dictation (Mode B):** Say the wake word → say "Dictate" → speak freely → silence auto-stops and pastes text.
- **Voice Commands:** Say the wake word → speak a mapped phrase → executes a keyboard shortcut via `xdotool` or runs a script from the `scripts/` directory.
- **Wake Word Detection:** Always-on listening via `openwakeword` (runs locally, no cloud).
- **OSD Popup:** Old-timey silent-film style floating panel shows "Listening..." with 3x-scaled voice-reactive avatar image (brightens on speech, fades on silence) when wake word is detected.
- **Settings GUI:** Right-click tray icon → Settings to configure silence timeout and voice command mappings.
- **Unified Audio Engine:** Single PyAudio stream prevents ALSA/PipeWire device lockouts.

## Requirements

- **Kubuntu / KDE Plasma on X11**
- **Python 3.10+**
- **PyQt6** — for the system tray icon and GUI
- **PyAudio** — for unified microphone capture
- **openwakeword** — for wake word detection
- **webrtcvad** — for voice activity / silence detection
- **sox** — for silence trimming
- **xdotool** — for simulating keyboard shortcuts and paste
- **xsel** — for clipboard-based text injection
- **whisper.cpp** — compiled `whisper-cli` binary with Vulkan GPU support

## Quick Start

```bash
# 1. Clone and enter the project
cd /home/twain/Projects/whisper_dictation

# 2. Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# 3. Install Python dependencies
pip install -r requirements.txt

# 4. Install system dependencies
sudo apt install sox xdotool xsel xclip libportaudio2 portaudio19-dev

# 5. Build whisper.cpp with Vulkan and download the model
./setup_whisper.sh

# 6. Run the tray app
./run_dictation.sh
```

## Setup Details

### System Dependencies

```bash
sudo apt install sox xdotool xsel xclip libportaudio2 portaudio19-dev
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

> **Note:** Vulkan runs the quantized Q5_0 model directly on the Intel Arc iGPU. Uses 6 CPU threads (`-t 6`) pinned to the P-cores of the Intel Core Ultra 9 185H (6P + 10E hybrid architecture).

> **⚠️ glslc Limitation:** Ubuntu's `glslc` (shaderc 2025.2) does **not** support `GL_EXT_integer_dot_product`, which means the optimized DP4A quantized matmul shaders are compiled out. This causes ~5x slower Vulkan encode times (~17s vs ~3.7s). **Fix:** Install the [LunarG Vulkan SDK](https://vulkan.lunarg.com/sdk/home) to get a `glslc` that supports this extension, then rebuild whisper.cpp. See [Vulkan Performance Fix](#vulkan-performance-fix) below.

### Why Not OpenVINO?

OpenVINO was tested as an alternative encoder backend but proved **significantly slower** on this hardware:

| Backend | Encode Time (13s audio) | Notes |
|---------|------------------------|-------|
| **Vulkan GPU** | **3.7s** | Quantized Q5_0 model on iGPU |
| OpenVINO GPU (`-oved GPU`) | 13.7s | Full-precision FP32 IR model on iGPU |
| OpenVINO CPU (default) | 22.3s | Full-precision FP32 IR model on CPU |

The OpenVINO encoder uses a full-precision FP32 model (~2.5GB) converted from PyTorch, while Vulkan uses the quantized Q5_0 model (573MB) directly. The quantized model on Vulkan is both smaller and faster. OpenVINO's whisper encoder acceleration is better suited for systems without Vulkan GPU support.

### Vulkan Performance Fix

The system `glslc` (shaderc 2025.2 from Ubuntu repos) does not support `GL_EXT_integer_dot_product`. This causes whisper.cpp's Vulkan backend to compile without DP4A (integer dot product) optimized shaders, resulting in ~5x slower encode times on quantized models.

**Diagnosis** — run cmake and look for this line:
```
-- GL_EXT_integer_dot_product not supported by glslc
```

**Fix** — install the LunarG Vulkan SDK which includes a `glslc` with full extension support:

```bash
# 1. Download and install the LunarG Vulkan SDK
#    https://vulkan.lunarg.com/sdk/home → Linux → Latest
#    Extract to e.g. ~/vulkan-sdk/

# 2. Rebuild whisper.cpp using the SDK's glslc
cd ~/.local/share/dictation-tool/whisper.cpp
rm -rf build
export VULKAN_SDK=~/vulkan-sdk/x86_64
cmake -B build -DGGML_VULKAN=1 \
  -DVulkan_GLSLC_EXECUTABLE=$VULKAN_SDK/bin/glslc
cmake --build build --config Release -j$(nproc)

# 3. Verify the fix — cmake output should show:
#    -- GL_EXT_integer_dot_product supported by glslc
# And whisper-cli output should show:
#    int dot: 1
```

**Expected improvement:** encode time drops from ~17s to ~3.7s (5x faster) for a 13-second audio clip with the Q5_0 quantized model on Intel Arc iGPU.

## Install (Autostart)

Run the installer to add the voice assistant to your KDE autostart and application launcher:

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

### Manual Dictation (Mode A)

- **Left-click** the tray icon to **start recording** (icon turns green)
- **Left-click again** to **stop recording and transcribe** (icon shows processing state)
- Transcribed text is automatically pasted into the focused window via clipboard
- Silence does **not** stop recording — only a second click does

### Voice-Triggered Dictation (Mode B)

1. Say the **wake word** (e.g., "Hey Jarvis") — OSD popup shows "Listening..."
2. Say **"Dictate"** — OSD changes to "Dictating..."
3. **Speak freely** — audio is recorded
4. **Stop speaking** — after the configured silence timeout (default 2.5s), recording auto-stops
5. Text is transcribed and pasted into the focused window

### Voice Commands

1. Say the **wake word** — OSD popup shows "Listening..."
2. Say a **mapped phrase** (e.g., "Open Project Alpha")
3. The corresponding **keyboard shortcut** is executed via `xdotool`, or a **script** from `scripts/` is run

Configure voice commands in **Settings** (right-click tray icon → Settings).

### Voice Command Scripts

Voice commands can trigger shell scripts instead of keyboard shortcuts. Place executable scripts in the `scripts/` directory and reference them in command mappings with the `script:` prefix.

**Built-in example scripts:**

| Phrase | Action | OSD Label | Description |
|--------|--------|-----------|-------------|
| "talk" | `script:talk.sh` | Talking | Plays an MP3 from a random position, looping continuously via `mpv` |
| "stop" | `script:stop.sh` | Stopping | Stops the MP3 playback (kills `mpv`) |

**Adding your own scripts:**

1. Create an executable shell script in `scripts/` (e.g., `scripts/my-action.sh`)
2. In **Settings → Command Mappings**, add a row with your trigger phrase and `script:my-action.sh`
3. Scripts run detached in the background — they won't block the voice assistant

> **Note:** The `talk.sh` script requires `mpv`: `sudo apt install mpv`

### Settings

Right-click the tray icon → **Settings** to configure:
- **Wake Word:** Choose from 6 bundled models — Alexa, Hey Jarvis, Hey Marvin, Hey Mycroft, Timer, Weather (default: Hey Jarvis). Or select **"Custom (.onnx file)..."** to load your own openwakeword model via file browser.
- **Silence Timeout:** How long silence must last to auto-stop voice-triggered dictation (1.5s–5.0s)
- **Command Mappings:** Table of voice phrase → action (keyboard shortcut or `script:name.sh`) with optional OSD label

Settings are saved to `config.json` and persist between reboots. Wake word changes take effect immediately (model reloads in background).

### Custom Wake Words

To use a wake word not in the bundled list:

1. **Train your own model** using the [openwakeword training notebook](https://github.com/dscripka/openWakeWord#training-new-models) (Google Colab, ~30 min)
2. **Download a community model** `.onnx` file from the [openwakeword model repo](https://github.com/dscripka/openWakeWord/tree/main/openwakeword/resources/models)
3. In **Settings → Wake Word**, select **"Custom (.onnx file)..."** and browse to your `.onnx` file
4. Click **Save** — the model loads immediately

## Debugging / Profiling

Each dictation session writes detailed timing data to `/tmp/vibe_debug.log`. The log includes:

- **Audio processing time** — how long `sox` silence trimming takes
- **Whisper processing time** — full `whisper-cli` duration, plus its internal stderr metrics (model load, mel spectrogram, encode, decode times)
- **Typing/paste time** — how long `xsel` + `xdotool` clipboard paste takes
- **Total pipeline time** — end-to-end from stop-recording to text-injected

The log is truncated at the start of each new session. To inspect after a dictation:

```bash
cat /tmp/vibe_debug.log
```

## How It Works

### Audio Engine

A single continuous PyAudio microphone stream (16kHz, 16-bit, mono) is maintained at all times:
- **Idle:** Audio feeds into `openwakeword` for wake word detection
- **Recording:** Audio is written to a WAV file for whisper.cpp processing

This prevents Linux ALSA/PipeWire "Device Busy" lockouts that occur when multiple processes try to open the microphone.

### Transcription Pipeline

1. **Record** — PyAudio captures 16kHz/16-bit/mono WAV audio
2. **Stop** — Recording stops (manual click or silence timeout)
3. **Trim** — `sox` strips leading/trailing silence to prevent Whisper hallucinations
4. **Transcribe** — `whisper-cli` (Vulkan-accelerated on Intel Arc iGPU) processes the audio
5. **Inject** — `xsel` copies text to clipboard, then `xdotool` simulates Ctrl+V to paste

### Wake Word Flow

1. `openwakeword` continuously analyzes audio chunks from the PyAudio stream
2. When confidence exceeds threshold, the app enters "Listening" state
3. A short recording captures the voice command
4. `whisper-cli` transcribes the command
5. The command is matched against built-in commands ("Dictate") and user-defined mappings
6. Matched commands trigger dictation mode or keyboard shortcuts

## File Structure

```
whisper_dictation/
├── main.py              # Entry point — tray icon, app lifecycle, integration
├── audio_engine.py      # Unified PyAudio stream, wake word, VAD
├── dictation.py         # DictationManager — record/trim/transcribe/inject pipeline
├── voice_commands.py    # Command matching and xdotool shortcut execution
├── settings_manager.py  # JSON config persistence and Settings GUI window
├── osd_popup.py         # On-Screen Display popup (old-timey silent-film style)
├── config.py            # Paths, constants, and default settings
├── setup_whisper.sh     # Build whisper.cpp with Vulkan + download model
├── install.sh           # Installer — autostart and app launcher entries
├── run_dictation.sh     # Launcher script (activates venv + runs main.py)
├── config.json          # User settings (created on first save)
├── scripts/
│   ├── talk.sh          # Voice command script: play MP3 from random position, loop
│   └── stop.sh          # Voice command script: stop MP3 playback
├── icons/
│   ├── mic-on.svg       # Tray icon: recording active (green)
│   ├── mic-off.svg      # Tray icon: idle (gray)
│   └── alkelly-head.png # Avatar shown below "Listening..." text
├── requirements.txt
├── plans/
│   └── architecture.md
└── README.md
```

## Changelog

- **2026-04-01T21:30 UTC-6** — Fixed two OSD popup bugs: (1) Avatar image and label never reappearing after first fade — root cause was `_voice_anim` not being stopped in `show_message()` before setting opacity values, allowing the running animation to override them back to 0. Also added `isVisible()` guard to `_on_avatar_opacity_changed()` to prevent label fade when avatar is hidden. (2) OSD label (e.g., "Talking...", "Stopping...") never showing for voice commands — same root cause: label opacity was stuck at 0 from the previous fade animation. Fix: stop all animations at the top of `show_message()` before setting any opacity values.
- **2026-04-01T20:22 UTC-6** — Multiple improvements: (1) OSD label fade fix — text now restores instantly when speech resumes instead of lagging behind the avatar. (2) Reduced talk.sh startup lag by replacing ffprobe duration lookup with mpv percentage-based seeking (`--start=N%`). (3) System audio muting — `pactl` mutes default sink when wake word activates, unmutes after command completes. (4) Added 3rd "OSD Label" column to command mappings for gerund display (e.g., "Talking...", "Stopping..."). (5) Replaced mic SVG tray icons with alkelly-head.png avatar — red diagonal line when idle, clean image when recording.
- **2026-04-01T20:04 UTC-6** — Added voice command scripts support. Voice commands can now trigger shell scripts (prefixed with `script:`) in addition to keyboard shortcuts. Created `scripts/` directory with two example scripts: `talk.sh` (plays an MP3 from a random position via `mpv`, looping continuously) and `stop.sh` (kills `mpv` playback). Added `SCRIPTS_DIR` to `config.py`, `execute_script()` and `execute_action()` to `voice_commands.py`. Command mappings in `config.json` now support `script:name.sh` syntax.

- **2026-04-01T19:54 UTC-6** — OSD fade-to-zero: avatar now fades completely to 0% opacity during silence (was 25%). When avatar drops below 10%, "Listening..." text rapidly fades out (300ms) so text disappears just before the image. Both elements fully vanish when silence timeout is reached. Text opacity restores instantly when speech resumes. Implemented via `_label_wrapper` QWidget with its own `QGraphicsOpacityEffect` (needed because the label already uses `QGraphicsDropShadowEffect`), monitored through `opacityChanged` signal.
- **2026-04-01T19:47 UTC-6** — OSD popup aesthetic overhaul: old-timey silent-film style with large serif font (Georgia 28pt, warm ivory text on dark background, 3px letter-spacing). Added `alkelly-head.png` avatar image (scaled 3x to ~447×471) below "Listening..." text. Avatar is **voice-reactive**: starts at 25% opacity, boosts to 85% when speech detected (200ms fast response), fades to 0% during silence (1.5s gentle fade). VAD activity callback added to `AudioEngine.set_vad_activity_callback()`, bridged to OSD via `_vad_activity` Qt signal in `main.py`. Avatar only appears during "Listening..." state.
- **2026-04-01T16:13 UTC-6** — Added custom wake word support. Users can now load any `.onnx` openwakeword model via a file browser in Settings (select "Custom (.onnx file)..." from the wake word dropdown). Custom model path is persisted in `config.json`. Also includes the 6 bundled models (Alexa, Hey Jarvis, Hey Marvin, Hey Mycroft, Timer, Weather). Fixed openwakeword v0.4.0 API usage.
- **2026-04-01T15:38 UTC-6** — Major expansion: voice assistant features. Added wake word detection (`openwakeword`), voice-triggered dictation with silence auto-stop (`webrtcvad`), voice command mappings with keyboard shortcut execution, OSD popup, settings GUI, unified PyAudio audio engine. Migrated from PyQt5 to PyQt6. Replaced `arecord` subprocess with continuous PyAudio stream to prevent ALSA/PipeWire device lockouts. New modules: `audio_engine.py`, `osd_popup.py`, `voice_commands.py`, `settings_manager.py`. Existing dictation pipeline (sox → whisper-cli → xsel → xdotool) preserved intact.
- **2026-04-01T13:56 UTC-6** — Identified root cause of Vulkan performance regression: Ubuntu's `glslc` (shaderc 2025.2) does not support `GL_EXT_integer_dot_product`, so whisper.cpp's DP4A-optimized quantized matmul shaders are compiled out at build time. This causes the Vulkan backend to fall back to generic (non-DP4A) compute shaders, resulting in ~5x slower encode times (~17s vs ~3.7s). The regression was introduced by whisper.cpp commit `0810f025` (2025-03-31) which added DP4A MMQ shaders behind a compile-time feature gate. Fix requires installing the LunarG Vulkan SDK's `glslc` and rebuilding. Documented in README under "Vulkan Performance Fix".
- **2026-04-01T13:14 UTC-6** — Three Vulkan speed optimizations: (1) P-core thread pinning (`-t 6`) to avoid spilling into slower E-cores on the Intel Core Ultra 9 185H hybrid architecture; (2) aggressive silence trimming via sox reverse trick to chop trailing dead air without touching natural pauses; (3) shortened `--prompt` from 13 tokens to 5 to reduce token processing overhead. Also cleaned up ~5.1GB of OpenVINO artifacts (FP32 encoder model, Python venv, cache).
- **2026-04-01T12:57 UTC-6** — Reverted from OpenVINO back to Vulkan-only build after benchmarking showed OpenVINO is 3.7–6x slower. Root cause: the OpenVINO encoder uses a full-precision FP32 model (~2.5GB) while Vulkan uses the quantized Q5_0 model (573MB) directly on the GPU. Additionally, the previous OpenVINO build had accidentally dropped Vulkan support entirely (`-DGGML_VULKAN` was OFF), causing pure CPU fallback (22s encode). Rebuilt with `-DGGML_VULKAN=1 -DWHISPER_OPENVINO=OFF`. Restored `-t 4` threads (Vulkan original). Documented benchmark results in README.
- **2026-04-01T12:24 UTC-6** — Recompiled whisper.cpp with OpenVINO support (`-DWHISPER_OPENVINO=1`) for Intel Arc iGPU encoder acceleration. Generated OpenVINO IR encoder model for `large-v3-turbo`. Added `-t 12` CPU threads to feed the GPU encoder. Encode time expected to drop from ~4s (CPU/Vulkan fallback) to sub-second.
- **2026-04-01T10:30 UTC-6** — Added per-phase profiling to the transcription pipeline. Each session now logs precise timing breakdown (sox trim, whisper-cli, clipboard paste) and full whisper.cpp stderr metrics to `/tmp/vibe_debug.log`.
- **2026-04-01T10:23 UTC-6** — Fixed auto-paste: replaced `xclip` with `xsel --clipboard --input` for clipboard writes. `xclip` was hanging (5s timeout) in the background QThread because it forks to serve X11 selection requests. `xsel` writes and exits immediately. Also added `xdotool windowactivate --sync` to re-focus the target window before pasting.
- **2026-04-01T10:05 UTC-6** — Replaced `xdotool type --delay 2` with instant clipboard paste (`xsel` + `xdotool key ctrl+v`). Text injection is now effectively instant regardless of transcription length.
- **2026-04-01T14:38 UTC-6** — Major refactor: replaced real-time `whisper-stream` with batch `arecord` → `sox` → `whisper-cli` → `xdotool` pipeline. Added `setup_whisper.sh` for Vulkan compilation and Large V3 Turbo Q5 model download. New 3-state UI (idle/recording/processing).
- **2026-04-01T04:56 UTC** — Fixed `\r` partial transcriptions being injected as final text.

---

*Last updated: 2026-04-01T21:30 UTC-6*
