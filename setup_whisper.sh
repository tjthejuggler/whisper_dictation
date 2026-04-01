#!/usr/bin/env bash
# setup_whisper.sh — Install whisper.cpp with Vulkan support and download the quantized turbo model.
# Idempotent: safe to run multiple times.
set -euo pipefail

# ── Colors ───────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color
check="${GREEN}✔${NC}"
cross="${RED}✘${NC}"
arrow="${YELLOW}➜${NC}"

WHISPER_DIR="$HOME/.local/share/dictation-tool/whisper.cpp"
BINARY="$WHISPER_DIR/build/bin/whisper-cli"
MODEL_NAME="ggml-large-v3-turbo-q5_0.bin"
MODEL_PATH="$WHISPER_DIR/models/$MODEL_NAME"
MODEL_URL="https://huggingface.co/ggerganov/whisper.cpp/resolve/main/$MODEL_NAME"

# ── 1. System dependencies ──────────────────────────────────────────────────
echo -e "\n${arrow} Installing system dependencies …"
sudo apt install -y build-essential cmake libvulkan-dev vulkan-tools sox alsa-utils xdotool xclip
echo -e "${check} System dependencies installed.\n"

# ── 2. Clone & build whisper.cpp ─────────────────────────────────────────────
if [ -f "$BINARY" ]; then
    echo -e "${check} whisper-cli already built at ${BINARY} — skipping clone & build."
else
    echo -e "${arrow} Building whisper.cpp with Vulkan support …"

    if [ ! -d "$WHISPER_DIR" ]; then
        mkdir -p "$(dirname "$WHISPER_DIR")"
        git clone https://github.com/ggerganov/whisper.cpp.git "$WHISPER_DIR"
    else
        echo -e "${arrow} Directory exists but binary missing — rebuilding …"
    fi

    cd "$WHISPER_DIR"
    cmake -B build -DGGML_VULKAN=1
    cmake --build build --config Release -j"$(nproc)"

    if [ -f "$BINARY" ]; then
        echo -e "${check} whisper-cli built successfully."
    else
        echo -e "${cross} Build finished but whisper-cli binary not found at ${BINARY}."
        exit 1
    fi
fi

# ── 3. Download quantized turbo model ────────────────────────────────────────
if [ -f "$MODEL_PATH" ]; then
    echo -e "${check} Model already downloaded at ${MODEL_PATH} — skipping."
else
    echo -e "${arrow} Downloading ${MODEL_NAME} …"
    mkdir -p "$WHISPER_DIR/models"
    wget -O "$MODEL_PATH" "$MODEL_URL"
    echo -e "${check} Model downloaded."
fi

# ── 4. Summary ───────────────────────────────────────────────────────────────
echo ""
echo "=============================="
echo "  Setup complete"
echo "=============================="
echo -e "  Binary : ${GREEN}${BINARY}${NC}"
echo -e "  Model  : ${GREEN}${MODEL_PATH}${NC}"
echo ""
