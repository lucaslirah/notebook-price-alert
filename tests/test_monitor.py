from datetime import datetime, timedelta, timezone

import pytest

import monitor

AGORA = datetime(2026, 11, 24, 12, 0, tzinfo=timezone.utc)
CONFIG = {
    "preco_maximo": 10000,
    "preco_ideal": 8000,
    "config_alvo": {"gpu": ["rtx 5060", "rtx 5070"], "cpu": ["i5", "i7", "ultra 7"],
                    "ram_min_gb": 16, "ssd_min_gb": 512, "exigir_ram_ssd": False},
    "lojas": [{"nome": "Fonte", "adaptador": "fake", "urls_busca": ["u"]}],
}


def prod(nome, preco, **extra):
    return {"nome": nome, "preco": preco, "url": f"https://x/{nome}", "config_texto": nome, **extra}


NB1 = "Notebook A i7-14650HX RTX 5060 16GB RAM 512GB SSD Windows 11 ANV16-I31-541M"
NB2 = "Notebook B Core Ultra 7 255HX RTX 5070 16GB RAM 1TB SSD Windows 11 PHN16-73-76TF"


@pytest.fixture
def ambiente(tmp_path, monkeypatch):
    monkeypatch.setattr(monitor, "STATE_PATH", str(tmp_path / "state.json"))
    enviadas = []
    monkeypatch.setattr(monitor.notifier, "send_message", enviadas.append)
    fonte = {"produtos": [], "erro": None}

    def fake_adapter(_nome):
        def scrape(_url, **_):
            if fonte["erro"]:
                raise RuntimeError(fonte["erro"])
            return [dict(p) for p in fonte["produtos"]]
        return scrape

    monkeypatch.setattr(monitor, "get_adapter", fake_adapter)
    return fonte, enviadas


# ------------------------------- anti-spam -------------------------------- #
def test_deve_notificar():
    estado = {"k": {"preco_notificado": 8000.0}}
    assert monitor.deve_notificar({}, "k", 8000, AGORA)
    assert not monitor.deve_notificar(estado, "k", 8000, AGORA)
    assert not monitor.deve_notificar(estado, "k", 9000, AGORA)       # subiu: não avisa
    assert not monitor.deve_notificar(estado, "k", 7980, AGORA)       # queda < R$ 30
    assert monitor.deve_notificar(estado, "k", 7900, AGORA)           # queda >= R$ 30


def test_realerta_depois_de_sumir():
    sumiu = (AGORA - timedelta(hours=13)).isoformat()
    recente = (AGORA - timedelta(hours=2)).isoformat()
    assert monitor.deve_notificar({"k": {"preco_notificado": 8000, "sumiu_em": sumiu}}, "k", 8000, AGORA)
    assert not monitor.deve_notificar({"k": {"preco_notificado": 8000, "sumiu_em": recente}}, "k", 8000, AGORA)


def test_referencia_so_desce_quando_notificado():
    estado = {}
    monitor.registrar_estado(estado, "k", 8000, "n", notificado=True)
    monitor.registrar_estado(estado, "k", 7990, "n", notificado=False)
    assert estado["k"]["preco_notificado"] == 8000 and estado["k"]["menor_preco"] == 7990
    monitor.registrar_estado(estado, "k", 8500, "n", notificado=False)
    assert estado["k"]["preco_notificado"] == 8500


def test_marcar_sumidos_e_limpar():
    estado = {"a": {"preco_notificado": 1}, "tg:velho": {"sumiu_em": (AGORA - timedelta(days=3)).isoformat()},
              "_saude": {}}
    monitor.marcar_sumidos(estado, set(), AGORA)
    assert "sumiu_em" in estado["a"] and "tg:velho" not in estado and "_saude" in estado


# ------------------------------- dedupe ----------------------------------- #
def test_codigos_modelo():
    assert "PHN167376TF" in monitor.codigos_modelo("Predator Helios Neo 16 AI PHN16-73-76TF Ultra 7")
    assert monitor.codigos_modelo("Notebook Windows 11 RTX 5060 i5-13450HX 16GB") == set()


def test_deduplicar_mantem_mais_barato():
    a = prod("Helios PHN16-73-76TF Kabum", 9989)
    b = prod("Acer Predator Helios Neo 16 AI PHN16-73-76TF", 9359)
    c = prod("Outro ANV16-I31-541M", 8000)
    saida = monitor.deduplicar_modelos([a, b, c])
    assert [o["preco"] for o in saida] == [8000, 9359]


# --------------------------------- veredito ------------------------------- #
def test_veredito_com_historico_da_fonte():
    h = {"min": 7000.0, "mediana": 8000.0, "dias": 120}
    assert "menor preço dos últimos 120 dias" in monitor.veredito_preco({}, "k", 7000, h)
    assert "já custou" in monitor.veredito_preco({}, "k", 7500, h)
    assert "abaixo da mediana" in monitor.veredito_preco({}, "k", 7000, h)


def test_veredito_com_estado_proprio():
    assert "primeira vez" in monitor.veredito_preco({}, "k", 1)
    assert "menor preço já visto" in monitor.veredito_preco({"k": {"menor_preco": 9}}, "k", 8)


# ------------------------------ fluxo completo ----------------------------- #
def test_fluxo_envia_uma_vez_e_de_novo_so_se_cair(ambiente):
    fonte, enviadas = ambiente
    fonte["produtos"] = [prod(NB1, 7900), prod("Notebook C i7 RTX 5060 8GB RAM 512GB SSD", 7000),
                         prod("Notebook D i7 RTX 5060 16GB RAM 512GB SSD", 11000)]

    r = monitor.rodar(CONFIG, agora=AGORA)
    assert len(r["novos"]) == 1 and len(enviadas) == 1       # C (8GB) e D (> teto) filtrados
    assert "🔥" in enviadas[0]

    monitor.rodar(CONFIG, agora=AGORA + timedelta(minutes=5))
    assert len(enviadas) == 1                                # nada novo

    fonte["produtos"] = [prod(NB1, 7850)]                    # queda de R$ 50
    monitor.rodar(CONFIG, agora=AGORA + timedelta(minutes=10))
    assert len(enviadas) == 2


def test_dry_run_nao_envia_nem_grava(ambiente, tmp_path):
    fonte, enviadas = ambiente
    fonte["produtos"] = [prod(NB1, 7900)]
    monitor.rodar(CONFIG, dry_run=True, agora=AGORA)
    assert enviadas == [] and not (tmp_path / "state.json").exists()


def test_falha_no_envio_mantem_oferta_pendente(ambiente, monkeypatch):
    fonte, enviadas = ambiente
    fonte["produtos"] = [prod(NB1, 7900)]

    def quebra(_msg):
        raise RuntimeError("telegram fora")

    monkeypatch.setattr(monitor.notifier, "send_message", quebra)
    r = monitor.rodar(CONFIG, agora=AGORA)
    assert r["erro_envio"]

    monkeypatch.setattr(monitor.notifier, "send_message", enviadas.append)
    r = monitor.rodar(CONFIG, agora=AGORA + timedelta(minutes=5))
    assert len(enviadas) == 1                                # reenviou, pois não foi registrada


def test_fonte_quebrada_alerta_na_terceira_falha(ambiente):
    fonte, enviadas = ambiente
    fonte["erro"] = "HTTP 503"
    for i in range(2):
        r = monitor.rodar(CONFIG, agora=AGORA + timedelta(minutes=5 * i))
        assert r["fontes_com_erro"] == 1
    assert enviadas == []
    monitor.rodar(CONFIG, agora=AGORA + timedelta(minutes=10))
    assert len(enviadas) == 1 and "falhou 3" in enviadas[0]
    monitor.rodar(CONFIG, agora=AGORA + timedelta(minutes=15))
    assert len(enviadas) == 1                                # não repete o aviso

    fonte["erro"] = None
    fonte["produtos"] = []
    monitor.rodar(CONFIG, agora=AGORA + timedelta(minutes=20))
    assert "_saude" not in monitor.carregar_estado()


def test_mensagem_destaca_os_dois_perfis(ambiente):
    fonte, enviadas = ambiente
    fonte["produtos"] = [prod(NB1, 7900, cupom="CUPOM1"), prod(NB2, 9400)]
    monitor.rodar(CONFIG, agora=AGORA)
    msg = enviadas[0]
    assert "MELHOR CUSTO-BENEFÍCIO" in msg and "MAIS POTENTE" in msg and "CUPOM1" in msg
    assert len(msg) <= 4000
