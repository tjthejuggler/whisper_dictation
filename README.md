# Whisper Dictation

A minimal KDE Plasma system tray application for voice dictation using [whisper.cpp](https://github.com/ggerganov/whisper.cpp) with Vulkan GPU acceleration (Intel Arc iGPU).

Click the tray icon to start recording. Click again to stop, transcribe, and type the result into the focused window.

## Requirements

- **Kubuntu / KDE Plasma on X11**
- **Python 3.8+**
- **PyQt5** — for the system tray icon
- **arecord** — for audio capture (`alsa-utils` package)
- **sox** — for silence trimming
- **xdotool** — for simulating keyboard paste into the active window
- **xsel** — for clipboard-based text injection (exits immediately, unlike xclip)
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

The pipeline has 5 stages:

1. **Record** — `arecord` captures 16kHz/16-bit/mono WAV audio from the microphone
2. **Stop** — `arecord` is terminated via SIGTERM, finalizing the WAV file
3. **Trim** — `sox` strips leading/trailing silence to prevent Whisper hallucinations
4. **Transcribe** — `whisper-cli` (Vulkan-accelerated on Intel Arc iGPU) processes the audio with:
   - Large V3 Turbo Q5 quantized model (RAM-efficient)
   - Vulkan GPU backend for fast encoder inference
   - 6 CPU threads (`-t 6`) pinned to P-cores only
   - Entropy threshold of 2.4 (anti-hallucination)
   - Lean context prompt for coding terminology
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

*Last updated: 2026-04-01T13:56 UTC-6*
