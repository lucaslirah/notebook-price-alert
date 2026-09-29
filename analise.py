"""Análise de desempenho e custo-benefício dos notebooks encontrados.

IMPORTANTE: o score de desempenho é uma ESTIMATIVA baseada em uma tabela de pesos
(não é benchmark real). Serve para COMPARAR opções entre si, não como medição
absoluta de laboratório. Os pesos são configuráveis em config.yaml (chave
'pesos_analise'); se ausentes, usamos os padrões abaixo.
"""
import re
import unicodedata

# --------------------------------------------------------------------------- #
# Tabelas de pontuação (0..1 relativo dentro de cada categoria)
# --------------------------------------------------------------------------- #
# GPU — a peça que mais importa em notebook gamer. Ordem crescente de potência.
GPU_SCORE = {
    "rtx 5090": 1.00, "rtx 5080": 0.92, "rtx 5070 ti": 0.85, "rtx 5070": 0.78,
    "rtx 5060": 0.62, "rtx 5050": 0.50,
    "rtx 4090": 0.95, "rtx 4080": 0.88, "rtx 4070": 0.74, "rtx 4060": 0.60,
    "rtx 4050": 0.46, "rtx 3060": 0.48, "rtx 3050": 0.36,
}

# CPU — famílias comuns em notebook. Aproximação por classe.
CPU_SCORE = {
    "ultra 9": 1.00, "i9": 0.95, "ryzen 9": 0.95,
    "ultra 7": 0.82, "i7": 0.80, "ryzen 7": 0.80,
    "ultra 5": 0.62, "i5": 0.60, "ryzen 5": 0.60,
    "i3": 0.35, "ryzen 3": 0.35,
}

# Pesos de cada categoria no score final (somam 1.0). Padrão: GPU manda.
PESOS_PADRAO = {
    "gpu": 0.40,
    "cpu": 0.25,
    "ram": 0.15,
    "ssd": 0.12,
    "tela": 0.08,
}


def _norm(texto: str) -> str:
    texto = (texto or "").lower()
    texto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in texto if not unicodedata.combining(c))


def _match_maior(txt: str, tabela: dict) -> float:
    """Retorna o maior score cujo termo aparece no texto (0 se nenhum)."""
    melhor = 0.0
    for termo, valor in tabela.items():
        if termo in txt and valor > melhor:
            melhor = valor
    return melhor


def extrair_specs(texto: str) -> dict:
    """Extrai specs estruturadas do título/descrição de um anúncio."""
    txt = _norm(texto)

    # GPU
    mgpu = re.search(r"rtx\s*\d{4}\s*ti|rtx\s*\d{4}|gtx\s*\d{3,4}", txt)
    gpu = re.sub(r"\s+", " ", mgpu.group(0)).strip() if mgpu else ""

    # CPU (classe)
    cpu = ""
    for termo in CPU_SCORE:
        if termo in txt:
            cpu = termo
            break

    # RAM (GB) — pega o MENOR valor plausível listado, pois o preço "a partir de"
    # corresponde à configuração base (páginas listam variantes maiores também).
    rams = [int(x) for x in re.findall(r"(\d+)\s*gb\s*(?:de\s*)?(?:ram|memoria|ddr)", txt)]
    if not rams:
        rams = [int(x) for x in re.findall(r"(\d+)\s*gb", txt) if 4 <= int(x) <= 128]
    ram_gb = min(rams) if rams else 0

    # SSD (em GB; 1tb -> 1024) — idem: menor variante listada = config base.
    ssds = []
    for x in re.findall(r"(\d+)\s*tb", txt):
        ssds.append(int(x) * 1024)
    for m in re.finditer(r"ssd[\w\.\s]*?(\d+)\s*gb|(\d+)\s*gb\s*ssd", txt):
        ssds.append(int(m.group(1) or m.group(2)))
    ssd_gb = min(ssds) if ssds else 0

    # Tela (Hz)
    mhz = re.search(r"(\d{2,3})\s*hz", txt)
    hz = int(mhz.group(1)) if mhz else 0

    return {"gpu": gpu, "cpu": cpu, "ram_gb": ram_gb, "ssd_gb": ssd_gb, "hz": hz}


def _score_ram(gb: int) -> float:
    if gb >= 32: return 1.0
    if gb >= 16: return 0.75
    if gb >= 8:  return 0.45
    return 0.2 if gb else 0.0


def _score_ssd(gb: int) -> float:
    if gb >= 2048: return 1.0
    if gb >= 1024: return 0.8
    if gb >= 512:  return 0.6
    if gb >= 256:  return 0.4
    return 0.0


def _score_tela(hz: int) -> float:
    if hz >= 240: return 1.0
    if hz >= 165: return 0.85
    if hz >= 144: return 0.7
    if hz >= 120: return 0.55
    if hz >= 60:  return 0.35
    return 0.0


def calcular_score(texto: str, pesos: dict | None = None) -> tuple[int, dict]:
    """Calcula um score 0..100 e devolve (score, specs).

    O score é a média ponderada das categorias normalizadas.
    """
    pesos = {**PESOS_PADRAO, **(pesos or {})}
    specs = extrair_specs(texto)
    txt = _norm(texto)

    s_gpu = _match_maior(txt, GPU_SCORE)
    s_cpu = CPU_SCORE.get(specs["cpu"], 0.0) if specs["cpu"] else _match_maior(txt, CPU_SCORE)
    s_ram = _score_ram(specs["ram_gb"])
    s_ssd = _score_ssd(specs["ssd_gb"])
    s_tela = _score_tela(specs["hz"])

    total = (
        pesos["gpu"] * s_gpu
        + pesos["cpu"] * s_cpu
        + pesos["ram"] * s_ram
        + pesos["ssd"] * s_ssd
        + pesos["tela"] * s_tela
    )
    soma_pesos = sum(pesos[k] for k in ("gpu", "cpu", "ram", "ssd", "tela"))
    score = round(100 * total / soma_pesos) if soma_pesos else 0
    return score, specs


def custo_beneficio(preco: float, score: int) -> float | None:
    """R$ por ponto de desempenho. Menor = melhor. None se score 0."""
    if not score:
        return None
    return round(preco / score, 2)


def analisar(oferta: dict, pesos: dict | None = None) -> dict:
    """Enriquece uma oferta com score, specs e custo-benefício."""
    score, specs = calcular_score(oferta.get("config_texto") or oferta.get("nome", ""), pesos)
    cb = custo_beneficio(oferta["preco"], score)
    return {**oferta, "score": score, "specs": specs, "custo_beneficio": cb}


def rankear(ofertas: list[dict]) -> dict:
    """Ordena e identifica destaques entre as ofertas analisadas.

    Retorna dict com: 'ranking' (por custo-benefício), e os destaques
    'melhor_cb', 'mais_potente', 'mais_barato'.
    """
    com_cb = [o for o in ofertas if o.get("custo_beneficio") is not None]
    ranking = sorted(com_cb, key=lambda o: o["custo_beneficio"])  # menor R$/ponto primeiro
    resultado = {"ranking": ranking or ofertas}
    if ofertas:
        resultado["mais_barato"] = min(ofertas, key=lambda o: o["preco"])
        resultado["mais_potente"] = max(ofertas, key=lambda o: o.get("score", 0))
        resultado["melhor_cb"] = ranking[0] if ranking else resultado["mais_barato"]
    return resultado
