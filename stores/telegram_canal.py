"""Adaptador de CANAIS PÚBLICOS do Telegram, sem login e sem conta.

Todo canal público tem uma prévia web em https://t.me/s/<canal> com as ~20
mensagens mais recentes. Lemos essa página como as outras lojas. Funciona só
para canais públicos (com @usuario). Para grupos privados, use telegram_grupo.

Em urls_busca, aceita: "https://t.me/s/canal", "https://t.me/canal" ou "@canal".
"""
import re
from datetime import datetime, timedelta, timezone

from bs4 import BeautifulSoup

from stores.base import fetch_html
from stores.telegram_msg import oferta_de_mensagem

HORAS_PADRAO = 3


def nome_canal(url_busca: str) -> str:
    m = re.search(r"(?:t\.me/(?:s/)?|@)?([A-Za-z0-9_]{4,})/?$", url_busca.strip())
    if not m:
        raise ValueError(f"Canal do Telegram inválido: {url_busca!r}")
    return m.group(1)


def parse_mensagens(html: str, canal: str, horas: float, agora: datetime | None = None) -> list[dict]:
    """Converte a prévia web do canal em ofertas (apenas mensagens recentes)."""
    agora = agora or datetime.now(timezone.utc)
    corte = agora - timedelta(hours=horas)
    soup = BeautifulSoup(html, "html.parser")
    ofertas = []
    for msg in soup.select(".tgme_widget_message"):
        post = msg.get("data-post")  # "canal/12345"
        texto_el = msg.select_one(".tgme_widget_message_text")
        tempo_el = msg.select_one("time[datetime]")
        if not post or not texto_el:
            continue
        if tempo_el:
            quando = datetime.fromisoformat(tempo_el["datetime"])
            if quando < corte:
                continue
        texto = texto_el.get_text("\n", strip=True)
        links = [a["href"] for a in texto_el.find_all("a", href=True) if a["href"].startswith("http")]
        oferta = oferta_de_mensagem(
            texto, chave=f"tg:{post}", url_mensagem=f"https://t.me/{post}",
            origem=f"Telegram @{canal}", links_extras=links,
        )
        if oferta:
            ofertas.append(oferta)
    return ofertas


def scrape(url_busca: str, horas: float = HORAS_PADRAO, **_) -> list[dict]:
    canal = nome_canal(url_busca)
    html = fetch_html(f"https://t.me/s/{canal}")
    if "tgme_widget_message" not in html:
        raise RuntimeError(
            f"@{canal}: sem mensagens na prévia web. O canal é público? "
            "Grupos privados precisam do adaptador telegram_grupo."
        )
    return parse_mensagens(html, canal, horas)
