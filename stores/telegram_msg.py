"""Converte mensagens de grupos/canais de promoção em ofertas.

Mensagens de promoção são texto livre. Extraímos: menor preço plausível de
notebook, primeiro link externo, cupom e um nome. O texto completo vira
config_texto, então o filtro/análise normal (GPU, CPU, RAM, SSD) se aplica.
"""
import re

from stores.base import parse_precos_brl

# Abaixo disso o "R$" quase certamente é parcela, cupom ou acessório.
PRECO_MINIMO_NOTEBOOK = 1500.0

_URL_RE = re.compile(r"https?://[^\s<>\"')\]]+")
_CUPOM_RE = re.compile(r"cupom[^\w\n]{0,6}([A-Z0-9]{4,25})\b", re.I)
_MARCAS = re.compile(
    r"notebook|acer|asus|lenovo|dell|samsung|\bhp\b|msi|gigabyte|avell|positivo|apple|macbook|predator|legion|loq|nitro|tuf|rog|alienware",
    re.I,
)


def extrair_preco(texto: str) -> float | None:
    """Menor preço >= PRECO_MINIMO_NOTEBOOK citado ('de X por Y' -> Y)."""
    validos = [p for p in parse_precos_brl(texto) if p >= PRECO_MINIMO_NOTEBOOK]
    return min(validos) if validos else None


def extrair_links(texto: str, extras: list[str] | None = None) -> list[str]:
    links = list(extras or []) + _URL_RE.findall(texto)
    vistos, saida = set(), []
    for link in links:
        link = link.rstrip(".,;")
        if link not in vistos:
            vistos.add(link)
            saida.append(link)
    return saida


def extrair_cupom(texto: str) -> str:
    for m in _CUPOM_RE.finditer(texto):
        codigo = m.group(1)
        if codigo.upper() == codigo and not codigo.isdigit():  # códigos vêm em maiúsculas
            return codigo
    return ""


def extrair_nome(texto: str) -> str:
    """Primeira linha que parece nome de produto (marca/'notebook'); senão a 1ª útil."""
    linhas = [re.sub(r"[=\-_*#]{3,}", " ", l).strip() for l in texto.splitlines()]
    linhas = [l for l in linhas if len(re.findall(r"[A-Za-z0-9]", l)) >= 8]
    for l in linhas:
        if _MARCAS.search(l):
            return l[:140]
    return linhas[0][:140] if linhas else texto.strip()[:140]


def oferta_de_mensagem(texto: str, chave: str, url_mensagem: str, origem: str,
                       links_extras: list[str] | None = None) -> dict | None:
    """Monta a oferta, ou None se a mensagem não tem um preço de notebook."""
    preco = extrair_preco(texto)
    if preco is None:
        return None
    externos = [l for l in extrair_links(texto, links_extras) if "t.me/" not in l and "?q=%23" not in l]
    return {
        "nome": extrair_nome(texto),
        "preco": preco,
        "url": externos[0] if externos else url_mensagem,
        "config_texto": texto,
        "loja": origem,
        "chave": chave,
        "cupom": extrair_cupom(texto),
        "origem_mensagem": url_mensagem,
    }
