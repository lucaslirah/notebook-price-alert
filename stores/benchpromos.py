"""Adaptador do Bench Promos (benchpromos.com.br).

A página /notebooks é renderizada pelo Next.js e embute a lista de produtos como
JSON (com todas as lojas, preços em centavos, cupom e disponibilidade). Lemos
esse JSON em vez de depender do HTML. São ~20 produtos por página, via ?page=N.

Por produto, devolvemos a oferta disponível MAIS BARATA entre as lojas.
"""
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor

from stores.base import fetch_html

BASE_URL = "https://benchpromos.com.br"
MAX_PAGINAS_PADRAO = 14

_PUSH_RE = re.compile(r'self\.__next_f\.push\(\[1,(".*?")\]\)</script>', re.S)


def extrair_produtos(html: str) -> list[dict]:
    """Extrai a lista de produtos (JSON) embutida no HTML do Next.js."""
    blob = ""
    for pedaco in _PUSH_RE.findall(html):
        try:
            blob += json.loads(pedaco)
        except json.JSONDecodeError:
            continue
    decoder = json.JSONDecoder()
    for m in re.finditer(r'"products":\[', blob):
        try:
            lista, _ = decoder.raw_decode(blob[m.end() - 1:])
        except json.JSONDecodeError:
            continue
        if lista and isinstance(lista[0], dict) and "deals" in lista[0]:
            return lista
    return []


def produto_para_oferta(produto: dict) -> dict | None:
    """Converte um produto do Bench na oferta disponível mais barata (ou None)."""
    deals = [
        d for d in produto.get("deals", [])
        if d.get("availability") and (d.get("price") or 0) > 0
    ]
    if not deals:
        return None
    melhor = min(deals, key=lambda d: d["price"])
    cupom = melhor.get("coupon") or {}
    cupom_codigo = (cupom.get("code") or "").strip() if cupom.get("availability", True) else ""
    url = f"{BASE_URL}/notebooks/{produto['slug']}"
    outras = sorted(
        {(d["retailer"]["name"], d["price"] / 100) for d in deals if d is not melhor},
        key=lambda x: x[1],
    )
    return {
        "nome": produto["name"],
        "preco": melhor["price"] / 100,
        "url": url,
        "config_texto": produto["name"],
        "loja": melhor["retailer"]["name"],
        "cupom": cupom_codigo,
        "outras_lojas": outras[:3],
    }


def scrape(url_busca: str, max_paginas: int = MAX_PAGINAS_PADRAO, **_) -> list[dict]:
    """Lê as páginas de /notebooks e devolve a melhor oferta de cada produto."""

    def baixar(n: int):
        try:
            return n, extrair_produtos(fetch_html(url_busca, params={"page": n}))
        except RuntimeError as exc:
            if n == 1:
                raise
            print(f"  [aviso] Bench Promos página {n}: {exc}", file=sys.stderr)
            return n, []

    with ThreadPoolExecutor(max_workers=4) as pool:
        paginas = sorted(pool.map(baixar, range(1, max_paginas + 1)))

    if not paginas[0][1]:
        raise RuntimeError("Bench Promos: nenhum produto na página 1 (layout mudou?)")

    ofertas, vistos = [], set()
    for _n, produtos in paginas:
        for p in produtos:
            if p.get("id") in vistos:
                continue
            vistos.add(p.get("id"))
            oferta = produto_para_oferta(p)
            if oferta:
                ofertas.append(oferta)
    return ofertas
