"""Registro de adaptadores de loja.

Cada adaptador é uma função que recebe uma URL de busca e retorna uma lista de
dicionários de produto no formato:

    {
        "nome": str,          # título do notebook
        "preco": float,       # preço em reais
        "url": str,           # link do produto
        "config_texto": str,  # texto bruto com specs (gpu/cpu/tela...) para filtro
    }

Para adicionar uma loja nova: crie stores/<nome>.py com uma função scrape(url) e
registre-a em ADAPTERS abaixo.
"""
from stores import avell, kabum

ADAPTERS = {
    "avell": avell.scrape,
    "kabum": kabum.scrape,
}


def get_adapter(nome: str):
    adapter = ADAPTERS.get(nome)
    if adapter is None:
        raise KeyError(f"Adaptador de loja desconhecido: {nome!r}")
    return adapter
