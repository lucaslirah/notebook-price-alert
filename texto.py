"""Normalização de texto compartilhada por filtros, análise e adaptadores."""
import re
import unicodedata


def normalizar(texto: str) -> str:
    """Minúsculas, sem acento e com grafias de specs padronizadas.

    Exemplos: "RTX5060" -> "rtx 5060"; "16 GB" -> "16gb"; "Ryzen7" -> "ryzen 7";
    "5070Ti" -> "5070 ti". Isso permite comparar termos por palavra inteira.
    """
    t = unicodedata.normalize("NFKD", (texto or "").lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = t.replace("™", " ").replace("®", " ")
    t = re.sub(r"(rtx|gtx)\s*-?\s*(\d)", r"\1 \2", t)
    t = re.sub(r"(\d{4})\s*ti\b", r"\1 ti", t)
    t = re.sub(r"ryzen\s*(\d)", r"ryzen \1", t)
    t = re.sub(r"(\d)\s+(gb|tb|hz)\b", r"\1\2", t)
    return re.sub(r"\s+", " ", t).strip()
