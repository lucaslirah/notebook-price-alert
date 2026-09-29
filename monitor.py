"""Monitor de preço de notebooks.

Lê config.yaml, varre as lojas habilitadas, filtra pelos critérios de configuração
e preço, e envia alerta no Telegram para os notebooks que baterem. Guarda o último
preço notificado por produto para não repetir alertas (anti-spam).

Uso:
    python monitor.py                 # execução normal
    python monitor.py --dry-run       # não envia Telegram, só imprime
    python monitor.py --test-telegram # envia uma mensagem de teste e sai
"""
import argparse
import json
import os
import re
import sys
import unicodedata

import yaml

import notifier
from stores import get_adapter

CONFIG_PATH = os.environ.get("CONFIG_PATH", "config.yaml")
STATE_PATH = os.environ.get("STATE_PATH", "state.json")


# --------------------------------------------------------------------------- #
# Normalização e filtro de config
# --------------------------------------------------------------------------- #
def normalizar(texto: str) -> str:
    """minúsculas + sem acento, para comparar termos de forma robusta."""
    texto = texto.lower()
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return texto


def contem_algum(texto_norm: str, termos: list[str]) -> bool:
    return any(normalizar(t) in texto_norm for t in termos)


def resumir_specs(texto: str) -> str:
    """Extrai um resumo curto (CPU / GPU / RAM / SSD) do texto de specs para a mensagem."""
    partes = []
    padroes = [
        (r"(ryzen\s*\d+\s*\w*|core\s*i\d[\w\- ]*|ultra\s*\d[\w\- ]*|intel\s*core[\w\- ]*)", "CPU"),
        (r"(rtx\s*\d{4}\s*ti|rtx\s*\d{4})", "GPU"),
        (r"(\d+\s*gb)\s*(?:mem[óo]ria|ddr)", "RAM"),
        (r"ssd[\w\.\s]*?(\d+\s*(?:gb|tb))", "SSD"),
    ]
    txt = normalizar(texto)
    for padrao, _rotulo in padroes:
        m = re.search(padrao, txt)
        if m:
            valor = m.group(1).strip()
            valor = re.sub(r"\s+", " ", valor)
            partes.append(valor.upper())
    return " · ".join(dict.fromkeys(partes)) if partes else ""


def bate_criterios(texto: str, config_alvo: dict) -> bool:
    """Verifica se o texto de specs bate os critérios de gpu/cpu (e ram/ssd)."""
    txt = normalizar(texto)

    # Termos que DEVEM aparecer (ex.: "notebook") — evita casar com desktop/PC Gamer.
    exigir = config_alvo.get("exigir_termos") or []
    for termo in exigir:
        if normalizar(termo) not in txt:
            return False

    # Termos que, se aparecerem, DESCARTAM o item (ex.: "pc gamer", "desktop").
    excluir = config_alvo.get("excluir_termos") or []
    for termo in excluir:
        if normalizar(termo) in txt:
            return False

    gpu = config_alvo.get("gpu") or []
    if gpu and not contem_algum(txt, gpu):
        return False

    cpu = config_alvo.get("cpu") or []
    if cpu and not contem_algum(txt, cpu):
        return False

    if config_alvo.get("exigir_ram_ssd"):
        ram = config_alvo.get("ram") or []
        if ram and not contem_algum(txt, ram):
            return False
        ssd = config_alvo.get("ssd") or []
        if ssd and not contem_algum(txt, ssd):
            return False

    return True


# --------------------------------------------------------------------------- #
# Estado (anti-spam)
# --------------------------------------------------------------------------- #
def carregar_estado() -> dict:
    if os.path.exists(STATE_PATH):
        try:
            with open(STATE_PATH, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def salvar_estado(estado: dict) -> None:
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(estado, f, ensure_ascii=False, indent=2)


def deve_notificar(estado: dict, url: str, preco: float) -> bool:
    """Notifica se nunca notificou este produto OU se o preço mudou desde então."""
    anterior = estado.get(url, {}).get("preco_notificado")
    return anterior is None or abs(anterior - preco) >= 0.01


# --------------------------------------------------------------------------- #
# Núcleo
# --------------------------------------------------------------------------- #
def coletar_produtos(loja: dict) -> list[dict]:
    """Roda o adaptador da loja sobre todas as urls_busca configuradas."""
    scrape = get_adapter(loja["adaptador"])
    produtos = []
    for url in loja.get("urls_busca", []):
        try:
            encontrados = scrape(url)
        except NotImplementedError as exc:
            print(f"  [ignorado] {loja['nome']}: {exc}", file=sys.stderr)
            continue
        except Exception as exc:  # noqa: BLE001 - queremos continuar nas outras lojas
            print(f"  [ERRO] {loja['nome']} ({url}): {exc}", file=sys.stderr)
            continue
        for p in encontrados:
            p["loja"] = loja["nome"]
            p["adaptador"] = loja["adaptador"]
        produtos.extend(encontrados)
    return produtos


def confirmar_config_detalhada(produto: dict, config_alvo: dict) -> bool:
    """Abre a página do produto para confirmar RAM/SSD, quando o adaptador suportar.

    Só é chamado quando exigir_ram_ssd=True e o produto já passou no filtro de
    listagem (gpu+cpu+preço), evitando abrir páginas desnecessárias.
    """
    adaptador = produto.get("adaptador")
    mod = sys.modules.get(f"stores.{adaptador}")
    detalhes = getattr(mod, "detalhes_produto", None)
    if detalhes is None:
        # Adaptador não sabe abrir a página; confia no texto da listagem.
        return bate_criterios(produto["config_texto"], config_alvo)
    try:
        texto = detalhes(produto["url"])
    except Exception as exc:  # noqa: BLE001
        print(f"  [aviso] não confirmei config de {produto['url']}: {exc}", file=sys.stderr)
        return False
    produto["config_texto"] = texto
    return bate_criterios(texto, config_alvo)


def rodar(config: dict, dry_run: bool = False) -> list[dict]:
    preco_max = float(config["preco_maximo"])
    config_alvo = config["config_alvo"]
    estado = carregar_estado()

    ofertas_enviadas = []

    for loja in config.get("lojas", []):
        if not loja.get("habilitado", True):
            continue
        print(f"Varrendo {loja['nome']}...")
        # Na listagem só há GPU/CPU (não há RAM/SSD), então o filtro barato
        # nunca exige RAM/SSD — isso é confirmado depois na página do produto.
        criterios_listagem = {**config_alvo, "exigir_ram_ssd": False}
        for produto in coletar_produtos(loja):
            # 1) filtro barato na listagem: gpu + cpu
            if not bate_criterios(produto["config_texto"], criterios_listagem):
                continue
            # 2) preço
            if produto["preco"] > preco_max:
                continue
            # 3) confirmação de RAM/SSD (abre página do produto se exigido)
            if config_alvo.get("exigir_ram_ssd"):
                if not confirmar_config_detalhada(produto, config_alvo):
                    continue

            # anti-spam
            if not deve_notificar(estado, produto["url"], produto["preco"]):
                print(f"  = já notificado: {produto['nome']} (R$ {produto['preco']:.2f})")
                continue

            # resumo curto das specs para a mensagem (evita despejar a página toda)
            produto["config_texto"] = resumir_specs(produto["config_texto"])
            msg = notifier.format_deal(produto)
            print(f"  ★ OFERTA: {produto['nome']} — R$ {produto['preco']:.2f}")
            if dry_run:
                print("    [dry-run] mensagem que seria enviada:")
                print("    " + msg.replace("\n", "\n    "))
            else:
                notifier.send_message(msg)

            estado[produto["url"]] = {
                "preco_notificado": produto["preco"],
                "nome": produto["nome"],
            }
            ofertas_enviadas.append(produto)

    if not dry_run:
        salvar_estado(estado)
    return ofertas_enviadas


def carregar_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def main() -> int:
    parser = argparse.ArgumentParser(description="Monitor de preço de notebooks")
    parser.add_argument("--dry-run", action="store_true",
                        help="não envia Telegram, apenas imprime as ofertas")
    parser.add_argument("--test-telegram", action="store_true",
                        help="envia uma mensagem de teste e sai")
    args = parser.parse_args()

    if args.test_telegram:
        notifier.send_message("✅ Teste do monitor de notebooks: o bot está funcionando!")
        print("Mensagem de teste enviada.")
        return 0

    config = carregar_config()
    ofertas = rodar(config, dry_run=args.dry_run)
    print(f"\nConcluído. {len(ofertas)} oferta(s) {'detectada(s)' if args.dry_run else 'enviada(s)'}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
