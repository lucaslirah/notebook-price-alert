"""Adaptador de scraping da Avell (avell.com.br).

A página de listagem (ex: /notebooks) já traz nome, GPU, CPU, tela e preço de
cada modelo. RAM e SSD NÃO aparecem na listagem — só na página do produto — por
isso o núcleo abre a página do produto quando precisa confirmar RAM/SSD.
"""
from urllib.parse import urljoin

import re

from bs4 import BeautifulSoup

from stores.base import fetch_html, parse_preco_brl

BASE_URL = "https://avell.com.br"


def scrape(url_busca: str) -> list[dict]:
    """Lê uma página de listagem e retorna os produtos encontrados."""
    html = fetch_html(url_busca)
    soup = BeautifulSoup(html, "html.parser")

    produtos = []
    for card in soup.select(".product-card"):
        link_el = card.select_one("a[href]")
        nome_el = card.select_one("h2")
        if not link_el or not nome_el:
            continue

        href = link_el.get("href", "")
        url_produto = urljoin(BASE_URL, href)
        nome = nome_el.get_text(strip=True)

        texto_card = card.get_text(" ", strip=True)
        preco = parse_preco_brl(texto_card)
        if preco is None:
            continue

        produtos.append(
            {
                "nome": nome,
                "preco": preco,
                "url": url_produto,
                # Na listagem só há GPU/CPU/tela. RAM/SSD são confirmados depois.
                "config_texto": texto_card,
            }
        )
    return produtos


def detalhes_produto(url_produto: str) -> str:
    """Baixa a página do produto e devolve o texto da CONFIGURAÇÃO BASE.

    A página lista várias variantes (Essencial / Avell Recomenda / Pro) com RAM e
    SSD diferentes. O preço capturado é o "A partir de" (= variante base
    "Essencial"), então retornamos apenas esse bloco para o filtro/análise não
    confundir com as opções maiores. Se não achar o bloco, cai no texto completo.
    """
    html = fetch_html(url_produto)
    soup = BeautifulSoup(html, "html.parser")
    texto = soup.get_text(" ", strip=True)

    low = texto.lower()
    ini = low.find("essencial")
    if ini != -1:
        # vai até o início da próxima variante ("Avell Recomenda") ou +260 chars
        fim = low.find("avell recomenda", ini)
        if fim == -1 or fim - ini > 400:
            fim = ini + 260
        base = texto[ini:fim]
        # Garante que CPU/GPU (que ficam no topo/ficha técnica) entrem no texto,
        # senão o bloco "Essencial" sozinho não tem o processador.
        extras = []
        for termo in ("Ryzen", "Core i9", "Core i7", "Core i5", "Ultra 9",
                      "Ultra 7", "Ultra 5", "RTX", "GTX"):
            m = re.search(re.escape(termo) + r"[\w™®\s\-]{0,20}", texto)
            if m:
                extras.append(m.group(0).strip())
        mhz = re.search(r"\d{2,3}\s*hz", texto, re.IGNORECASE)
        if mhz:
            extras.append(mhz.group(0))
        return " ".join(extras) + " " + base
    return texto
