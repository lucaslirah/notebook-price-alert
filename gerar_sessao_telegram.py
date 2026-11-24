"""Gera a TELEGRAM_SESSION (string) para ler grupos privados. Rode UMA vez, local.

    pip install telethon
    export TELEGRAM_API_ID=... TELEGRAM_API_HASH=...
    python gerar_sessao_telegram.py

Vai pedir seu telefone e o código que o Telegram enviar. Copie a string impressa
para o secret TELEGRAM_SESSION do GitHub. NÃO commite nem compartilhe: ela
equivale à senha da conta.
"""
import os

from telethon.sessions import StringSession
from telethon.sync import TelegramClient

api_id = int(os.environ["TELEGRAM_API_ID"])
api_hash = os.environ["TELEGRAM_API_HASH"]

with TelegramClient(StringSession(), api_id, api_hash) as client:
    print("\nTELEGRAM_SESSION =")
    print(client.session.save())
