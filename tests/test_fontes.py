import json
from datetime import datetime, timezone

from stores import benchpromos, qnc, telegram_canal
from stores.telegram_msg import extrair_cupom, extrair_nome, extrair_preco, oferta_de_mensagem


# ----------------------------- Bench Promos ------------------------------- #
def _html_bench(produtos):
    carga = '6:["$","div",null,{"products":' + json.dumps(produtos) + "}]\n"
    return f"<script>self.__next_f.push([1,{json.dumps(carga)}])</script>"


def _deal(preco, loja, ok=True, cupom=None):
    return {"price": int(preco * 100), "availability": ok, "retailer": {"name": loja}, "coupon": cupom}


def test_bench_escolhe_menor_preco_disponivel():
    prod = {"id": "1", "name": "Notebook X i7 RTX 5060 16GB RAM 512GB SSD", "slug": "nb-x", "deals": [
        _deal(9000, "Amazon"),
        _deal(8000, "Kabum", cupom={"code": "BF10", "availability": True}),
        _deal(5000, "ML", ok=False),
    ]}
    ofertas = [benchpromos.produto_para_oferta(p) for p in benchpromos.extrair_produtos(_html_bench([prod]))]
    assert len(ofertas) == 1
    o = ofertas[0]
    assert o["preco"] == 8000 and o["loja"] == "Kabum" and o["cupom"] == "BF10"
    assert o["url"].endswith("/notebooks/nb-x")
    assert o["outras_lojas"] == [("Amazon", 9000.0)]


def test_bench_sem_oferta_disponivel():
    prod = {"id": "1", "name": "X", "slug": "x", "deals": [_deal(100, "A", ok=False)]}
    assert benchpromos.produto_para_oferta(prod) is None


def test_bench_html_sem_produtos():
    assert benchpromos.extrair_produtos("<html></html>") == []


# --------------------------------- QNC ------------------------------------ #
HISTORICO = json.dumps([{"x": i, "y": v} for i, v in enumerate([8000] * 10 + [7000, 7000, 7500])])
HTML_QNC = f"""
<div class="products_list"><div class="list_item laptop">
  <div class="thumbnail"><span class="spec_stamp operating_system linux"></span></div>
  <div class="infos"><h4><a href="../acer-nitro-x">Acer Nitro <b>X1</b></a></h4>
    <div class="spec_stamps mobile">
      <span class="spec_mobile">Core 7 240H</span><span class="spec_mobile">GeForce RTX 5060</span>
      <span class="spec_mobile">RAM 16 GB</span><span class="spec_mobile">SSD 512 GB</span>
    </div></div>
  <div class="overlay-qnc"><div name="priceHistory" data-history='{HISTORICO}'></div>
    <div class="all-prices-item"><div class="store acer"></div>
      <div class="price-infos"><div class="lowest-price"><p><b><small>R$</small>7.199</b></p></div></div>
      <p class="coupon-code copy">ACERBF</p></div>
    <div class="all-prices-item"><div class="store amazon"></div>
      <div class="price-infos"><div class="lowest-price"><p><b><small>R$</small>7.902</b></p></div></div></div>
  </div>
  <p>O preço justo fica entre R$ 7.218 e R$ 7.820</p>
</div></div>
<div class="pagination"><span class="pages">Página 1 de 5</span></div>
"""


def test_qnc_parse_card():
    (o,) = qnc.parse_cards(HTML_QNC, "https://quenotebookcomprar.com.br/ofertas?x=1")
    assert o["nome"] == "Acer Nitro X1"
    assert o["url"] == "https://quenotebookcomprar.com.br/acer-nitro-x"
    assert o["preco"] == 7199 and o["loja"] == "Acer" and o["cupom"] == "ACERBF"
    assert "RAM 16 GB" in o["config_texto"] and "Sistema linux" in o["config_texto"]
    assert o["historico"]["min"] == 7000 and o["historico"]["dias"] == 13
    assert o["historico"]["justo_max"] == 7820
    assert qnc._total_paginas(HTML_QNC) == 5


# ------------------------------- Telegram --------------------------------- #
MSG = """PARCELADO 10x SEM JUROS
==========
💻
Acer Aspire Nitro V16 ANV16-I31-541M
==========
Core 5-210H | GeForce RTX 5060
RAM 16 GB | SSD 512 GB | Windows 11
✅
De R$ 9.999 por R$ 7799
Até 12x de R$ 649 SEM JUROS
Cupom: ACERBF
https://loja.exemplo/p/123"""


def test_telegram_extracao():
    assert extrair_preco(MSG) == 7799
    assert extrair_preco("10x de R$ 899,90") is None
    assert extrair_cupom(MSG) == "ACERBF"
    assert extrair_cupom("cupom desconto aplicado") == ""
    assert extrair_nome(MSG).startswith("Acer Aspire Nitro V16")


def test_telegram_oferta_de_mensagem():
    o = oferta_de_mensagem(MSG, "tg:c/1", "https://t.me/c/1", "Telegram @c")
    assert o["preco"] == 7799 and o["url"] == "https://loja.exemplo/p/123" and o["chave"] == "tg:c/1"
    assert oferta_de_mensagem("bom dia pessoal", "k", "u", "o") is None


def _html_canal(quando):
    return f"""<div class="tgme_widget_message" data-post="canal/10">
      <div class="tgme_widget_message_text">{MSG.replace(chr(10), '<br>')}
        <a href="https://qual.not.br/abc">ver</a></div>
      <time datetime="{quando}"></time></div>"""


def test_telegram_canal_respeita_janela_de_horas():
    agora = datetime(2026, 11, 24, 12, 0, tzinfo=timezone.utc)
    recente = telegram_canal.parse_mensagens(_html_canal("2026-11-24T11:00:00+00:00"), "canal", 3, agora)
    antigo = telegram_canal.parse_mensagens(_html_canal("2026-11-24T05:00:00+00:00"), "canal", 3, agora)
    assert len(recente) == 1 and recente[0]["chave"] == "tg:canal/10"
    assert antigo == []


def test_nome_canal():
    for entrada in ("https://t.me/s/qualnotebook", "https://t.me/qualnotebook", "@qualnotebook", "qualnotebook"):
        assert telegram_canal.nome_canal(entrada) == "qualnotebook"
