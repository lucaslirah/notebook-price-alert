"""Adaptador da Kabum via Playwright (navegador headless).

A busca da Kabum é renderizada por JavaScript, então usamos o Chromium headless
do Playwright para carregar a página e extrair os cards de produto. Cada card é
um <a href*="/produto/"> que contém, no próprio texto, o título completo (com
CPU/RAM/GPU/SSD) e o preço.

Requer:
    pip install playwright
    playwright install chromium
"""
import re

from stores.base import parse_preco_brl

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

# JS que roda no contexto da página e devolve a lista de produtos.
_EXTRACT_JS = r"""
() => {
  const out = [];
  const seen = new Set();
  const cards = document.querySelectorAll("a[href*='/produto/']");
  for (const a of cards) {
    const txt = a.innerText || "";
    if (!/R\$/.test(txt)) continue;               // só cards com preço próprio
    const href = a.href.split("?")[0];
    if (seen.has(href)) continue;
    const precos = [...txt.matchAll(/R\$\s*([\d.]+,\d{2})/g)].map(m => m[1]);
    if (!precos.length) continue;
    let title = txt.replace(/\n/g, " ")
                   .replace(/Frete grátis\*?/ig, "")
                   .replace(/Patrocinado/ig, "")
                   .replace(/SELO:[^]*?(Notebook)/i, "$1")
                   .replace(/Avaliação[^]*?(Notebook)/i, "$1")
                   .replace(/R\$\s*[\d.]+,\d{2}.*$/, "")
                   .replace(/\s+/g, " ")
                   .trim();
    seen.add(href);
    out.push({ href: href, title: title.slice(0, 160), preco: precos[0] });
  }
  return out;
}
"""


def scrape(url_busca: str) -> list[dict]:
    """Carrega a busca da Kabum com Playwright e retorna os produtos."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # noqa: F841
        raise NotImplementedError(
            "Playwright não instalado. Rode: pip install playwright && "
            "playwright install chromium"
        )

    produtos = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page(user_agent=USER_AGENT)
            page.goto(url_busca, wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(3000)  # dá tempo para os cards renderizarem
            itens = page.evaluate(_EXTRACT_JS)
        finally:
            browser.close()

    for it in itens:
        preco = parse_preco_brl("R$ " + it["preco"])
        if preco is None:
            continue
        produtos.append(
            {
                "nome": it["title"],
                "preco": preco,
                "url": it["href"],
                # O título da Kabum já traz CPU/RAM/GPU/SSD -> serve de config_texto.
                "config_texto": it["title"],
            }
        )
    return produtos


# NÃO definimos detalhes_produto() de propósito: o título da listagem da Kabum já
# contém RAM/SSD, então o núcleo confirma a config em cima do config_texto sem
# precisar abrir a página do produto (que também é JS e custosa).
