import analise


def oferta(nome, preco):
    return {"nome": nome, "preco": preco, "url": "u:" + nome, "config_texto": nome}


def test_gpu_melhor_gera_score_maior():
    a = analise.analisar(oferta("i7 RTX 5070 16GB RAM 1TB SSD 165Hz", 10000))
    b = analise.analisar(oferta("i7 RTX 5060 16GB RAM 1TB SSD 165Hz", 10000))
    assert a["score"] > b["score"]


def test_hx_e_vram_aumentam_score():
    base = analise.analisar(oferta("Core Ultra 7 255H RTX 5070 16GB RAM 512GB SSD", 1))["score"]
    hx = analise.analisar(oferta("Core Ultra 7 255HX RTX 5070 16GB RAM 512GB SSD", 1))["score"]
    ti = analise.analisar(oferta("Core Ultra 7 255H RTX 5070 Ti 16GB RAM 512GB SSD", 1))["score"]
    assert hx > base and ti > base


def test_rankear_destaques():
    ofertas = [analise.analisar(oferta(n, p)) for n, p in [
        ("i5 RTX 5060 16GB RAM 512GB SSD", 7000),
        ("i9 RTX 5070 32GB RAM 1TB SSD 240Hz", 12000),
    ]]
    r = analise.rankear(ofertas)
    assert r["mais_barato"]["preco"] == 7000
    assert r["mais_potente"]["preco"] == 12000
    assert r["melhor_cb"]["custo_beneficio"] == min(o["custo_beneficio"] for o in ofertas)
