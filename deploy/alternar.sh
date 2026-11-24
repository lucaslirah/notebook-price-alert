#!/usr/bin/env bash
# Liga/desliga o monitor de notebooks (timer de 5 em 5 minutos).
UNIT=notebook-alert
ENVF="$HOME/.config/notebook-price-alert/env"
REPO="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"

avisar() { notify-send -i dialog-information "Monitor de notebooks" "$1" 2>/dev/null; }

if systemctl --user is-active --quiet "$UNIT.timer"; then
  systemctl --user disable --now "$UNIT.timer" >/dev/null 2>&1
  systemctl --user stop notebook-alert-inhibit.service >/dev/null 2>&1
  echo "⏸  DESATIVADO. O notebook volta a poder suspender."
  avisar "⏸ Desativado"
else
  if ! grep -q '^TELEGRAM_BOT_TOKEN=.\+' "$ENVF" 2>/dev/null; then
    echo "Primeiro uso: falta configurar o Telegram."
    if ! "$REPO/deploy/configurar-telegram.sh"; then
      echo "Não ativei."
      read -r -p "Enter para fechar"
      exit 1
    fi
  fi
  systemctl --user daemon-reload
  systemctl --user enable --now "$UNIT.timer"
  echo "▶  ATIVADO. Varredura a cada 5 minutos; suspensão bloqueada."
  avisar "▶ Ativado (a cada 5 min)"
  echo "Aguardando a primeira varredura..."
  sleep 25
fi

echo
echo "--- Próxima execução ---"
systemctl --user list-timers "$UNIT.timer" --no-pager 2>/dev/null | head -3
echo
echo "--- Último resultado ---"
journalctl --user -u "$UNIT.service" -n 8 --no-pager -o cat 2>/dev/null
echo
read -r -t 15 -p "Fechando em 15 s (Enter para fechar agora)..." || true
