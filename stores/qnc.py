"""Adaptador do Qual Notebook Comprar (quenotebookcomprar.com.br/ofertas).

A listagem de ofertas já traz as specs estruturadas (CPU, GPU, RAM, SSD, Hz), as
lojas com preço/cupom e o histórico de preços de ~4 meses. Usamos o histórico
para dizer se o preço atual é de fato bom (e não só um "desconto" de vitrine).

A paginação do filtro usa ?sf_paged=N.
"""
import json
import re
import statistics
import sys
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from stores.base import fetch_html, parse_precos_brl

MAX_PAGINAS_PADRAO = 8


def _preco(el) -> float | None:
    precos = parse_precos_brl(el.get_text(" ", strip=True)) if el else []
    return precos[0] if precos else None


def _historico(card) -> dict | None:
    el = card.select_one("[name=priceHistory]")
    if not el or not el.get("data-history"):
        return None
    try:
        pontos = json.loads(el["data-history"])
    except json.JSONDecodeError:
        return None
    valores = [p["y"] for p in pontos if p.get("y")]
    if len(valores) < 7:  # histórico curto demais para dizer algo
        return None
    return {"min": float(min(valores)), "mediana": float(statistics.median(valores)),
            "dias": len(valores)}


def parse_cards(html: str, base_url: str) -> list[dict]:
    """Converte o HTML de uma página de listagem em ofertas."""
    soup = BeautifulSoup(html, "html.parser")
    ofertas = []
    for card in soup.select(".products_list .list_item"):
        link = card.select_one(".infos h4 a[href]")
        if not link:
            continue
        nome = " ".join(link.get_text(" ", strip=True).split())
        url = urljoin(base_url, link["href"])

        # Melhor loja: menor preço entre as lojas listadas no modal "Onde comprar".
        melhor = None
        for item in card.select(".all-prices-item"):
            preco = _preco(item.select_one(".lowest-price"))
            if preco is None:
                continue
            if melhor is None or preco < melhor[0]:
                loja_el = item.select_one(".store")
                loja = next((c for c in (loja_el.get("class") or []) if c != "store"), "") if loja_el else ""
                cupom_el = item.select_one(".coupon-code")
                melhor = (preco, loja.replace("-", " ").title(),
                          cupom_el.get_text(strip=True) if cupom_el else "")
        historico = _historico(card)

        # Cartões sem lojas detalhadas: usa o preço de destaque do cartão.
        if melhor is None:
            preco = _preco(card.select_one(".price-infos .lowest-price"))
            if preco is None:
                continue
            melhor = (preco, "", "")

        for modal in card.select(".overlay-qnc"):
            modal.extract()
        specs = " ".join(s.get_text(" ", strip=True) for s in card.select(".spec_stamps.mobile .spec_mobile"))
        so_el = card.select_one(".spec_stamp.operating_system")
        so = next((c for c in (so_el.get("class") or [])
                   if c not in ("spec_stamp", "operating_system")), "") if so_el else ""
        if so:
            specs += f" Sistema {so.replace('_', ' ')}"
        texto_card = card.get_text(" ", strip=True)
        m = re.search(r"pre[çc]o justo fica entre R\$\s*([\d.]+) e R\$\s*([\d.]+)", texto_card, re.I)
        if m and historico is not None:
            historico["justo_min"] = float(m.group(1).replace(".", ""))
            historico["justo_max"] = float(m.group(2).replace(".", ""))

        preco, loja, cupom = melhor
        ofertas.append({
            "nome": nome,
            "preco": preco,
            "url": url,
            "config_texto": f"{nome} {specs}",
            "loja": loja or "QNC",
            "cupom": cupom,
            "historico": historico,
        })
    return ofertas


def _total_paginas(html: str) -> int:
    m = re.search(r"P[áa]gina\s+\d+\s+de\s+(\d+)", html)
    return int(m.group(1)) if m else 1


def scrape(url_busca: str, max_paginas: int = MAX_PAGINAS_PADRAO, **_) -> list[dict]:
    """Lê todas as páginas da listagem de ofertas (até max_paginas)."""
    html1 = fetch_html(url_busca)
    primeiros = parse_cards(html1, url_busca)
    if not primeiros:
        raise RuntimeError("QNC: nenhuma oferta na página 1 (layout mudou?)")

    total = min(_total_paginas(html1), max_paginas)
    sep = "&" if "?" in url_busca else "?"

    def baixar(n: int) -> list[dict]:
        try:
            return parse_cards(fetch_html(f"{url_busca}{sep}sf_paged={n}"), url_busca)
        except RuntimeError as exc:
            print(f"  [aviso] QNC página {n}: {exc}", file=sys.stderr)
            return []

    ofertas = list(primeiros)
    if total > 1:
        with ThreadPoolExecutor(max_workers=3) as pool:
            for lote in pool.map(baixar, range(2, total + 1)):
                ofertas.extend(lote)

    vistos, unicas = set(), []
    for o in ofertas:
        if o["url"] not in vistos:
            vistos.add(o["url"])
            unicas.append(o)
    return unicas
