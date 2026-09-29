"""Utilidades compartilhadas entre adaptadores de loja."""
import re
import time

import requests

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
}

_PRICE_RE = re.compile(r"R\$\s*([\d.]+,\d{2})")


def fetch_html(url: str, timeout: int = 30) -> str:
    """Baixa o HTML de uma URL com retry simples."""
    last_exc = None
    for tentativa in range(3):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=timeout)
            resp.raise_for_status()
            return resp.text
        except requests.RequestException as exc:
            last_exc = exc
            time.sleep(2 * (tentativa + 1))
    raise RuntimeError(f"Falha ao baixar {url}: {last_exc}")


def parse_preco_brl(texto: str):
    """Extrai o primeiro preço no formato brasileiro (R$ 7.999,00) como float.

    Retorna None se não encontrar.
    """
    m = _PRICE_RE.search(texto)
    if not m:
        return None
    valor = m.group(1).replace(".", "").replace(",", ".")
    try:
        return float(valor)
    except ValueError:
        return None
