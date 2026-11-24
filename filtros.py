"""Filtros de critérios: decidem se um anúncio bate a configuração desejada."""
import re
from functools import lru_cache

from analise import extrair_specs
from texto import normalizar


@lru_cache(maxsize=512)
def _padrao(termo: str) -> re.Pattern:
    """Regex de palavra inteira: 'i5' casa 'i5-13450hx', mas não 'ci5x'."""
    return re.compile(r"(?<![a-z0-9])" + re.escape(normalizar(termo)) + r"(?![a-z0-9])")


def contem_algum(texto_norm: str, termos: list[str]) -> bool:
    """True se algum termo aparece como palavra inteira em texto_norm."""
    return any(_padrao(t).search(texto_norm) for t in termos)


def bate_criterios(texto: str, config_alvo: dict, exigir_ram_ssd: bool = False) -> bool:
    """Verifica GPU/CPU/termos e, numericamente, RAM e SSD mínimos.

    Se exigir_ram_ssd=False, RAM/SSD só reprovam quando são detectados e ficam
    abaixo do mínimo (valor não detectado passa). Se True, valor não detectado
    também reprova.
    """
    txt = normalizar(texto)

    for termo in config_alvo.get("exigir_termos") or []:
        if not _padrao(termo).search(txt):
            return False

    if contem_algum(txt, config_alvo.get("excluir_termos") or []):
        return False

    gpu = config_alvo.get("gpu") or []
    if gpu and not contem_algum(txt, gpu):
        return False

    cpu = config_alvo.get("cpu") or []
    if cpu and not contem_algum(txt, cpu):
        return False

    specs = extrair_specs(texto)
    for chave, minimo in (("ram_gb", config_alvo.get("ram_min_gb")),
                          ("ssd_gb", config_alvo.get("ssd_min_gb"))):
        if not minimo:
            continue
        valor = specs[chave]
        if valor == 0:
            if exigir_ram_ssd:
                return False
        elif valor < minimo:
            return False
    return True


def ram_ssd_confirmados(texto: str) -> bool:
    """True se RAM e SSD foram identificados no texto."""
    specs = extrair_specs(texto)
    return bool(specs["ram_gb"] and specs["ssd_gb"])
