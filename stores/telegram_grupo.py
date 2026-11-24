"""Adaptador de GRUPOS/CANAIS PRIVADOS do Telegram (via sua conta, MTProto).

Só leitura: não envia nada e não marca mensagens como lidas. Exige a conta
(pessoal ou secundária) já participar do grupo. Credenciais, via variáveis de
ambiente (secrets do GitHub Actions):

    TELEGRAM_API_ID, TELEGRAM_API_HASH   -> https://my.telegram.org (API development tools)
    TELEGRAM_SESSION                     -> gerado por gerar_sessao_telegram.py

ATENÇÃO: TELEGRAM_SESSION dá acesso total à conta. Trate como senha. Sem as três
variáveis, o adaptador é simplesmente ignorado.

Em urls_busca, use o @usuario, o link t.me do grupo ou o id numérico (-100...).
"""
import os
import re
from datetime import datetime, timedelta, timezone

from stores.telegram_msg import oferta_de_mensagem

HORAS_PADRAO = 3
LIMITE_PADRAO = 150


def _credenciais():
    api_id = os.environ.get("TELEGRAM_API_ID", "").strip()
    api_hash = os.environ.get("TELEGRAM_API_HASH", "").strip()
    sessao = os.environ.get("TELEGRAM_SESSION", "").strip()
    if not (api_id and api_hash and sessao):
        raise NotImplementedError(
            "TELEGRAM_API_ID/TELEGRAM_API_HASH/TELEGRAM_SESSION não definidos "
            "(grupos privados desativados)."
        )
    return int(api_id), api_hash, sessao


def _alvo(texto: str):
    texto = texto.strip()
    if re.fullmatch(r"-?\d+", texto):
        return int(texto)
    return texto


def scrape(grupo: str, horas: float = HORAS_PADRAO, limite: int = LIMITE_PADRAO, **_) -> list[dict]:
    api_id, api_hash, sessao = _credenciais()
    try:
        from telethon.sessions import StringSession
        from telethon.sync import TelegramClient
    except ImportError as exc:
        raise NotImplementedError("telethon não instalado (pip install telethon).") from exc

    corte = datetime.now(timezone.utc) - timedelta(hours=horas)
    ofertas = []
    client = TelegramClient(StringSession(sessao), api_id, api_hash)
    client.connect()
    try:
        if not client.is_user_authorized():
            raise RuntimeError("Sessão do Telegram inválida/expirada. Gere de novo com gerar_sessao_telegram.py.")
        entidade = client.get_entity(_alvo(grupo))
        usuario = getattr(entidade, "username", None)
        titulo = getattr(entidade, "title", None) or usuario or str(grupo)
        for msg in client.iter_messages(entidade, limit=limite):
            if msg.date < corte:
                break
            texto = msg.message or ""
            if not texto:
                continue
            links = [e.url for e, _t in (msg.get_entities_text() or []) if getattr(e, "url", None)]
            url_msg = (f"https://t.me/{usuario}/{msg.id}" if usuario
                       else f"https://t.me/c/{entidade.id}/{msg.id}")
            oferta = oferta_de_mensagem(
                texto, chave=f"tg:{entidade.id}/{msg.id}", url_mensagem=url_msg,
                origem=f"Telegram: {titulo}", links_extras=links,
            )
            if oferta:
                ofertas.append(oferta)
    finally:
        client.disconnect()
    return ofertas
