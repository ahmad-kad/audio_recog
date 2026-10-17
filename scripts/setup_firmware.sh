#!/usr/bin/env bash
# Toolchain for firmware/xiao_mic_bridge, pinned to the versions it was tested with.
set -euo pipefail
ESP32_CORE="esp32:esp32@3.3.12"
AUDIO_TOOLS="https://github.com/pschatzmann/arduino-audio-tools.git#v1.2.6"

if ! command -v arduino-cli >/dev/null; then
  if [[ "$(uname)" == "Darwin" ]]; then
    brew install arduino-cli
  else
    echo "Install arduino-cli 1.5.1 first: https://arduino.github.io/arduino-cli/latest/installation/" >&2
    exit 1
  fi
fi
arduino-cli config init >/dev/null 2>&1 || true  # keeps an existing config
arduino-cli config add board_manager.additional_urls \
  https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json
arduino-cli core update-index
arduino-cli core install "$ESP32_CORE"
arduino-cli config set library.enable_unsafe_install true
arduino-cli lib install --git-url "$AUDIO_TOOLS"
echo "Firmware toolchain ready. Flash the XIAO with: scripts/flash_bridge"
