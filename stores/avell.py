"""Adaptador de scraping da Avell (avell.com.br).

A página de listagem (ex: /notebooks) já traz nome, GPU, CPU, tela e preço de
cada modelo. RAM e SSD NÃO aparecem na listagem — só na página do produto — por
isso o núcleo abre a página do produto quando precisa confirmar RAM/SSD.
"""
from urllib.parse import urljoin

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
    """Baixa a página do produto e devolve o texto (com RAM/SSD) para o filtro."""
    html = fetch_html(url_produto)
    soup = BeautifulSoup(html, "html.parser")
    return soup.get_text(" ", strip=True)
