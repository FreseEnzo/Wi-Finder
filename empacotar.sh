#!/bin/sh
# Gera o executável do WiFinder para Linux (um arquivo só, sem precisar de
# Python instalado em quem for usar). Resultado: ./WiFinder
#
#   ./empacotar.sh            gera o executável
#   ./empacotar.sh --atalho   gera e põe o WiFinder no menu de aplicativos
set -e
cd "$(dirname "$0")"

VENV=build/venv
if [ ! -x "$VENV/bin/pyinstaller" ]; then
    python3 -m venv "$VENV"
    "$VENV/bin/pip" install --quiet --upgrade pip
    "$VENV/bin/pip" install --quiet pyinstaller numpy pyserial matplotlib pillow
fi

printf 'from wifinder.__main__ import main\nmain()\n' > build/wifinder_app.py
"$VENV/bin/pyinstaller" --onefile --name WiFinder --noconfirm --log-level WARN \
    --distpath build/dist --workpath build/work --specpath build \
    --paths . \
    --exclude-module tkinter --exclude-module pytest \
    build/wifinder_app.py
mv build/dist/WiFinder ./WiFinder
echo "Pronto: $(pwd)/WiFinder ($(du -h WiFinder | cut -f1))"

if [ "$1" = "--atalho" ]; then
    APPS="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
    mkdir -p "$APPS"
    cat > "$APPS/wifinder.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=WiFinder
Comment=Baixa os voos do ESP32 e mostra as redes WiFi no mapa
Exec="$(pwd)/WiFinder"
Path=$(pwd)
Icon=network-wireless
Terminal=false
Categories=Utility;Network;
EOF
    echo "Atalho criado: $APPS/wifinder.desktop (procure por WiFinder no menu)"
fi
