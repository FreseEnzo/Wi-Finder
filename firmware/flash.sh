#!/bin/sh
# Compila e grava o firmware no ESP32. Uso: firmware/flash.sh [porta]
# Requer: arduino-cli com o core esp32 e as bibliotecas TinyGPSPlus e U8g2
#   arduino-cli core install esp32:esp32
#   arduino-cli lib install TinyGPSPlus U8g2
set -e
cd "$(dirname "$0")"
PORT=${1:-/dev/ttyUSB0}
FQBN=esp32:esp32:esp32:PartitionScheme=no_ota   # 2 MB de app + 2 MB para os logs
arduino-cli compile --fqbn "$FQBN" wifinder
arduino-cli upload --fqbn "$FQBN" -p "$PORT" wifinder
echo "Gravado. Para ver a serial: arduino-cli monitor -p $PORT -c baudrate=115200"
