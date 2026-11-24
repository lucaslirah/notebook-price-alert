from analise import extrair_specs
from filtros import bate_criterios, contem_algum
from texto import normalizar

ALVO = {
    "gpu": ["rtx 5060", "rtx 5070"],
    "cpu": ["i5", "i7", "ryzen 7", "ultra 7"],
    "ram_min_gb": 16,
    "ssd_min_gb": 512,
    "excluir_termos": ["pc gamer", "desktop"],
}


def test_normalizar_padroniza_specs():
    assert normalizar("RTX5060") == "rtx 5060"
    assert normalizar("16 GB") == "16gb"
    assert normalizar("Ryzen7 7735HS") == "ryzen 7 7735hs"
    assert normalizar("RTX 5070Ti") == "rtx 5070 ti"
    assert normalizar("Memória") == "memoria"


def test_termo_casa_palavra_inteira():
    assert contem_algum(normalizar("Core i5-13450HX"), ["i5"])
    assert not contem_algum(normalizar("modelo xi5x"), ["i5"])
    assert not contem_algum(normalizar("SSD 1512GB"), ["512gb"])
    assert contem_algum(normalizar("rtx 5070 ti 12gb"), ["rtx 5070"])


def test_criterios_basicos():
    ok = "Notebook Acer Core i7-14650HX RTX 5060 16GB RAM 512GB SSD Windows 11"
    assert bate_criterios(ok, ALVO)
    assert not bate_criterios(ok.replace("RTX 5060", "RTX 4060"), ALVO)
    assert not bate_criterios(ok.replace("i7-14650HX", "i3-1215U"), ALVO)
    assert not bate_criterios("PC Gamer " + ok, ALVO)


def test_ram_e_ssd_abaixo_do_minimo_sempre_reprova():
    base = "Core i7 RTX 5060 {ram} RAM {ssd} SSD"
    assert not bate_criterios(base.format(ram="8GB", ssd="512GB"), ALVO)
    assert not bate_criterios(base.format(ram="16GB", ssd="256GB"), ALVO)
    assert bate_criterios(base.format(ram="32GB", ssd="1TB"), ALVO)


def test_ram_ssd_ausentes_dependem_de_exigir():
    texto = "Notebook Core i7 RTX 5060"
    assert bate_criterios(texto, ALVO, exigir_ram_ssd=False)
    assert not bate_criterios(texto, ALVO, exigir_ram_ssd=True)


def test_specs_titulo_bench():
    s = extrair_specs("Notebook Lenovo LOQ 15IRX9 I5-13450HX RTX 4050 6GB 16GB RAM 512GB SSD Linux")
    assert (s["gpu"], s["vram_gb"], s["ram_gb"], s["ssd_gb"]) == ("rtx 4050", 6, 16, 512)
    assert s["hx"] and s["sem_windows"] and s["cpu"] == "i5"


def test_specs_estilo_qnc():
    s = extrair_specs("Acer Nitro Core 7 240H GeForce RTX 5060 RAM 16 GB SSD 512 GB 165 Hz Sistema windows 11")
    assert (s["gpu"], s["cpu"], s["ram_gb"], s["ssd_gb"], s["hz"]) == ("rtx 5060", "core 7", 16, 512, 165)
    assert not s["sem_windows"]


def test_vram_da_gpu_nao_vira_ram():
    s = extrair_specs("Notebook RTX 5070 Ti 12GB 1TB SSD")
    assert s["ram_gb"] == 0 and s["vram_gb"] == 12 and s["ssd_gb"] == 1024


def test_menor_variante_vence_em_pagina_com_varias_configs():
    s = extrair_specs("Essencial 16GB RAM SSD 512GB Recomenda 32GB RAM SSD 1TB")
    assert s["ram_gb"] == 16 and s["ssd_gb"] == 512
