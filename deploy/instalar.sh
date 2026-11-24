#!/usr/bin/env bash
# Instala o monitor como serviço do usuário (systemd) e cria o atalho na área de trabalho.
set -eu
REPO="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"
UNITS="$HOME/.config/systemd/user"
DATA="$HOME/.local/share/notebook-price-alert"
DESK="$(xdg-user-dir DESKTOP)"
mkdir -p "$UNITS" "$DATA" "$HOME/.config/notebook-price-alert" "$DESK"
chmod +x "$REPO"/deploy/*.sh

for u in notebook-alert.service notebook-alert.timer notebook-alert-inhibit.service; do
  sed "s#@REPO@#$REPO#g" "$REPO/deploy/$u" > "$UNITS/$u"
done

# O estado (anti-spam) passa a viver fora do repositório; começa a partir do atual.
if [ ! -f "$DATA/state.json" ]; then
  cp "$REPO/state.json" "$DATA/state.json"
fi

ATALHO="$DESK/Monitor de Notebooks.desktop"
{
  echo "[Desktop Entry]"
  echo "Type=Application"
  echo "Name=Monitor de Notebooks (ligar/desligar)"
  echo "Comment=Liga ou desliga o monitor de ofertas de notebooks"
  echo "Exec=$REPO/deploy/alternar.sh"
  echo "Icon=preferences-system-time"
  echo "Terminal=true"
  echo "Categories=Utility;"
} > "$ATALHO"
chmod +x "$ATALHO"

systemctl --user daemon-reload
echo "Instalado. Atalho: $ATALHO"
