"""Envio de notificações via Telegram Bot API."""
import os
import html

import requests

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


def _get_credentials():
    """Lê token e chat_id das variáveis de ambiente (secrets do GitHub Actions)."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        raise RuntimeError(
            "Faltam credenciais. Defina as variáveis de ambiente "
            "TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID "
            "(ou os secrets equivalentes no GitHub Actions)."
        )
    return token, chat_id


def send_message(text: str) -> None:
    """Envia uma mensagem de texto (formato HTML) para o chat configurado."""
    token, chat_id = _get_credentials()
    resp = requests.post(
        TELEGRAM_API.format(token=token),
        json={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
        },
        timeout=30,
    )
    resp.raise_for_status()


def format_deal(produto: dict) -> str:
    """Monta a mensagem de um notebook que bateu os critérios."""
    nome = html.escape(produto["nome"])
    loja = html.escape(produto["loja"])
    preco = produto["preco"]
    url = html.escape(produto["url"], quote=True)
    config = html.escape(produto.get("config_texto", ""))

    linhas = [
        "🔔 <b>Notebook em oferta!</b>",
        "",
        f"🏷️ <b>{nome}</b>",
        f"🏬 Loja: {loja}",
        f"💰 Preço: <b>R$ {preco:,.2f}</b>".replace(",", "X").replace(".", ",").replace("X", "."),
    ]
    if config:
        linhas.append(f"⚙️ Config: {config}")
    linhas.append("")
    linhas.append(f'🔗 <a href="{url}">Ver oferta</a>')
    return "\n".join(linhas)
