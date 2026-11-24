"""Registro de adaptadores de loja.

Cada adaptador é uma função scrape(url_busca, **opcoes) que retorna uma lista de
dicionários de produto no formato:

    {
        "nome": str,          # título do notebook
        "preco": float,       # preço em reais
        "url": str,           # link do produto
        "config_texto": str,  # texto bruto com specs (gpu/cpu/ram/ssd...) para filtro
    }

Campos opcionais: "loja" (loja real, quando a fonte é um agregador), "chave"
(identificador estável para o anti-spam; padrão = url), "cupom", "historico"
({min, mediana, dias, ...}) e "outras_lojas".

"opcoes" vem de 'opcoes:' da loja no config.yaml (ex.: max_paginas, horas).

Para adicionar uma fonte nova: crie stores/<nome>.py com scrape() e registre-a
em ADAPTERS abaixo.
"""
from stores import avell, benchpromos, kabum, qnc, telegram_canal, telegram_grupo

ADAPTERS = {
    "avell": avell.scrape,
    "kabum": kabum.scrape,
    "benchpromos": benchpromos.scrape,
    "qnc": qnc.scrape,
    "telegram_canal": telegram_canal.scrape,
    "telegram_grupo": telegram_grupo.scrape,
}


def get_adapter(nome: str):
    adapter = ADAPTERS.get(nome)
    if adapter is None:
        raise KeyError(f"Adaptador de loja desconhecido: {nome!r}")
    return adapter
