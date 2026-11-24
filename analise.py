"""Análise de desempenho e custo-benefício dos notebooks encontrados.

IMPORTANTE: o score de desempenho é uma ESTIMATIVA baseada em uma tabela de pesos
(não é benchmark real). Serve para COMPARAR opções entre si, não como medição
absoluta de laboratório. Os pesos são configuráveis em config.yaml (chave
'pesos_analise'); se ausentes, usamos os padrões abaixo.
"""
import re

from texto import normalizar

# --------------------------------------------------------------------------- #
# Tabelas de pontuação (0..1 relativo dentro de cada categoria)
# --------------------------------------------------------------------------- #
# GPU: a peça que mais importa em notebook gamer.
GPU_SCORE = {
    "rtx 5090": 1.00, "rtx 5080": 0.92, "rtx 5070 ti": 0.85, "rtx 5070": 0.78,
    "rtx 5060": 0.62, "rtx 5050": 0.50,
    "rtx 4090": 0.95, "rtx 4080": 0.88, "rtx 4070": 0.74, "rtx 4060": 0.60,
    "rtx 4050": 0.46, "rtx 3060": 0.48, "rtx 3050": 0.36,
}

# VRAM (GB) das GPUs mobile. Pesa na longevidade: jogos novos pedem cada vez mais.
GPU_VRAM_GB = {
    "rtx 5090": 24, "rtx 5080": 16, "rtx 5070 ti": 12, "rtx 5070": 8,
    "rtx 5060": 8, "rtx 5050": 8,
    "rtx 4090": 16, "rtx 4080": 12, "rtx 4070": 8, "rtx 4060": 8, "rtx 4050": 6,
    "rtx 3060": 6, "rtx 3050": 4,
}

# CPU: famílias comuns em notebook. Aproximação por classe.
CPU_SCORE = {
    "ultra 9": 1.00, "i9": 0.95, "ryzen 9": 0.95, "ryzen ai 9": 0.95,
    "ultra 7": 0.82, "i7": 0.80, "ryzen 7": 0.80, "ryzen ai 7": 0.82, "core 7": 0.72,
    "ultra 5": 0.62, "i5": 0.60, "ryzen 5": 0.60, "core 5": 0.55,
    "i3": 0.35, "ryzen 3": 0.35,
}

# Pesos de cada categoria no score final (normalizados pela soma).
PESOS_PADRAO = {
    "gpu": 0.40,
    "cpu": 0.25,
    "ram": 0.15,
    "ssd": 0.12,
    "tela": 0.08,
    "vram": 0.10,
}


def chave(oferta: dict) -> str:
    """Identificador estável da oferta (anti-spam): 'chave' se houver, senão a URL."""
    return oferta.get("chave") or oferta["url"]


def _tem_termo(txt: str, termo: str) -> bool:
    return re.search(r"(?<![a-z0-9])" + re.escape(termo) + r"(?![a-z0-9])", txt) is not None


def _match_maior(txt: str, tabela: dict) -> float:
    """Retorna o maior score cujo termo aparece no texto (0 se nenhum)."""
    melhor = 0.0
    for termo, valor in tabela.items():
        if valor > melhor and _tem_termo(txt, termo):
            melhor = valor
    return melhor


def _extrair_ram(txt: str) -> int:
    """Menor RAM (GB) plausível citada: o preço 'a partir de' é da config base."""
    rams = [int(x) for x in re.findall(r"(\d+)gb\s*(?:de\s*)?(?:ram|memoria|(?<![a-z])ddr)", txt)]
    rams += [int(x) for x in re.findall(r"(?:ram|memoria)(?:\s*ddr\d)?\s*(?:de\s*)?(\d+)gb", txt)]
    rams = [r for r in rams if 4 <= r <= 192]
    if rams:
        return min(rams)
    # Último recurso: "NNgb" avulso, ignorando VRAM da GPU e armazenamento.
    sem_gpu = re.sub(r"(?:rtx|gtx) \d{3,4}(?: ti)?\s*\d+gb", " ", txt)
    cand = [int(x) for x in re.findall(r"(?<![\d.])(\d+)gb(?!\s*(?:ssd|hdd|nvme|m\.?2))", sem_gpu)]
    cand = [c for c in cand if c in (8, 12, 16, 24, 32, 48, 64, 96, 128)]
    return min(cand) if cand else 0


def _extrair_ssd(txt: str) -> int:
    """Menor SSD (GB) citado; 1tb = 1024."""
    def gb(n, un):
        return int(n) * (1024 if un == "tb" else 1)

    achados = [gb(n, u) for n, u in re.findall(r"ssd[a-z0-9\.\s\-]{0,30}?(\d+)\s*(gb|tb)", txt)]
    achados += [gb(n, u) for n, u in re.findall(r"(\d+)(gb|tb)\s*(?:nvme\s*)?(?:m\.?2\s*)?(?:pcie\s*)?ssd", txt)]
    achados = [a for a in achados if a >= 64]
    if achados:
        return min(achados)
    tbs = [int(x) * 1024 for x in re.findall(r"(?<![\d.])(\d)tb", txt)]
    if tbs:
        return min(tbs)
    avulsos = [int(x) for x in re.findall(r"(?<![\d.])(256|512)gb", txt)]
    return min(avulsos) if avulsos else 0


def extrair_specs(texto: str) -> dict:
    """Extrai specs estruturadas do título/descrição de um anúncio."""
    txt = normalizar(texto)

    mgpu = re.search(r"rtx \d{4}(?: ti| super)?|gtx \d{3,4}", txt)
    gpu = mgpu.group(0) if mgpu else ""

    cpu = ""
    for termo in CPU_SCORE:
        if _tem_termo(txt, termo):
            cpu = termo
            break

    mhz = re.search(r"(\d{2,3})hz", txt)
    vram = GPU_VRAM_GB.get(gpu, 0)
    if not vram and gpu:
        vram = GPU_VRAM_GB.get(re.sub(r" (ti|super)$", "", gpu), 0)

    return {
        "gpu": gpu,
        "cpu": cpu,
        "ram_gb": _extrair_ram(txt),
        "ssd_gb": _extrair_ssd(txt),
        "hz": int(mhz.group(1)) if mhz else 0,
        "vram_gb": vram,
        # CPUs "HX" têm TDP alto e rendem bem mais que as "H" da mesma geração.
        "hx": bool(re.search(r"\d{3,5}hx", txt)),
        # Sem Windows: a licença é custo extra (e o item costuma parecer mais barato).
        "sem_windows": bool(re.search(r"(?<![a-z])(linux|freedos|sem sistema)", txt))
                       and "windows" not in txt,
    }


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


def _score_vram(gb: int) -> float:
    if gb >= 16: return 1.0
    if gb >= 12: return 0.85
    if gb >= 8:  return 0.6
    if gb >= 6:  return 0.4
    return 0.2 if gb else 0.0


def calcular_score(texto: str, pesos: dict | None = None) -> tuple[int, dict]:
    """Calcula um score 0..100 e devolve (score, specs).

    O score é a média ponderada das categorias normalizadas.
    """
    pesos = {**PESOS_PADRAO, **(pesos or {})}
    specs = extrair_specs(texto)
    txt = normalizar(texto)

    s_gpu = GPU_SCORE.get(specs["gpu"]) or _match_maior(txt, GPU_SCORE)
    s_cpu = CPU_SCORE.get(specs["cpu"], 0.0)
    if specs["hx"]:
        s_cpu = min(1.0, s_cpu + 0.10)
    componentes = {
        "gpu": s_gpu,
        "cpu": s_cpu,
        "ram": _score_ram(specs["ram_gb"]),
        "ssd": _score_ssd(specs["ssd_gb"]),
        "tela": _score_tela(specs["hz"]),
        "vram": _score_vram(specs["vram_gb"]),
    }
    soma_pesos = sum(pesos[k] for k in componentes)
    total = sum(pesos[k] * v for k, v in componentes.items())
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
        resultado["mais_potente"] = max(ofertas, key=lambda o: (o.get("score", 0), -o["preco"]))
        resultado["melhor_cb"] = ranking[0] if ranking else resultado["mais_barato"]
    return resultado
