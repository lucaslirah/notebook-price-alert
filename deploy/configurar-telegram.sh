#!/usr/bin/env bash
# Guarda token e chat ID do Telegram em um arquivo só seu (modo 600), fora do repositório.
set -eu
DIR="$HOME/.config/notebook-price-alert"
ENVF="$DIR/env"
REPO="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"
mkdir -p "$DIR" "$HOME/.local/share/notebook-price-alert"

echo "Cole os dados do seu bot (o token não aparece na tela)."
read -r -s -p "TELEGRAM_BOT_TOKEN: " TOKEN
echo
read -r -p "TELEGRAM_CHAT_ID: " CHAT
if [ -z "$TOKEN" ] || [ -z "$CHAT" ]; then
  echo "Token e chat ID são obrigatórios."
  exit 1
fi

umask 077
{
  echo "TELEGRAM_BOT_TOKEN=$TOKEN"
  echo "TELEGRAM_CHAT_ID=$CHAT"
  echo "STATE_PATH=$HOME/.local/share/notebook-price-alert/state.json"
  echo "CONFIG_PATH=$REPO/config.yaml"
} > "$ENVF"
chmod 600 "$ENVF"
echo "Salvo em $ENVF"

echo "Enviando mensagem de teste..."
set -a
. "$ENVF"
set +a
cd "$REPO"
.venv/bin/python monitor.py --test-telegram
