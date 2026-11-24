"""Monitor de preço de notebooks.

Lê config.yaml, varre as fontes habilitadas (lojas, agregadores de promoção e
canais de Telegram), filtra pelos critérios de configuração e preço, e envia
alerta no Telegram para os notebooks que baterem. Guarda o último preço
notificado por oferta para não repetir alertas (anti-spam).

Uso:
    python monitor.py                 # execução normal
    python monitor.py --dry-run       # não envia Telegram, só imprime
    python monitor.py --test-telegram # envia uma mensagem de teste e sai
"""
import argparse
import copy
import html
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

import yaml

import analise
import notifier
from analise import chave
from filtros import bate_criterios, ram_ssd_confirmados
from stores import get_adapter

CONFIG_PATH = os.environ.get("CONFIG_PATH", "config.yaml")
STATE_PATH = os.environ.get("STATE_PATH", "state.json")

QUEDA_MINIMA_PADRAO = 30.0        # R$ de queda para renotificar o mesmo item
REALERTAR_HORAS_PADRAO = 12       # item sumiu por tanto tempo e voltou -> avisa de novo
FALHAS_PARA_ALERTAR = 3           # execuções seguidas com a fonte quebrada
RETENCAO_DIAS = {"padrao": 90, "tg:": 2}

_MODELO_RE = re.compile(r"^(?:[A-Z]{2,5}\d{2}|\d{2}[A-Z]{3})[A-Z0-9]{3,}$")


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


def _agora_iso(agora: datetime) -> str:
    return agora.replace(microsecond=0).isoformat()


def deve_notificar(estado: dict, chave_oferta: str, preco: float, agora: datetime,
                   queda_minima: float = QUEDA_MINIMA_PADRAO,
                   realertar_horas: float = REALERTAR_HORAS_PADRAO) -> bool:
    """Notifica se é inédito, se o preço caiu o suficiente, ou se voltou após sumir.

    Aumento de preço NÃO notifica (só vira a nova referência de preço).
    """
    hist = estado.get(chave_oferta)
    if not hist or hist.get("preco_notificado") is None:
        return True
    if preco <= hist["preco_notificado"] - queda_minima:
        return True
    sumiu = hist.get("sumiu_em")
    if sumiu:
        try:
            if agora - datetime.fromisoformat(sumiu) >= timedelta(hours=realertar_horas):
                return True
        except ValueError:
            return True
    return False


def _fmt_brl(valor: float) -> str:
    """R$ no padrão brasileiro: 7999.0 -> R$ 7.999,00"""
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def veredito_preco(estado: dict, chave_oferta: str, preco: float, historico: dict | None = None) -> str:
    """Diz se o preço é bom, usando histórico da fonte (QNC) ou o do próprio bot."""
    if historico and historico.get("min"):
        dias, minimo, mediana = historico["dias"], historico["min"], historico["mediana"]
        if preco <= minimo + 0.5:
            texto = f"✅ menor preço dos últimos {dias} dias"
        else:
            texto = f"⚠ já custou {_fmt_brl(minimo)} nos últimos {dias} dias"
        pct = (mediana - preco) / mediana * 100 if mediana else 0
        if pct >= 3:
            texto += f" · {pct:.0f}% abaixo da mediana"
        return texto

    menor = estado.get(chave_oferta, {}).get("menor_preco")
    if menor is None:
        return "🆕 primeira vez que vejo este modelo"
    if preco < menor - 0.01:
        return f"✅ menor preço já visto! (antes: {_fmt_brl(menor)})"
    if abs(preco - menor) <= 0.01:
        return "✅ empatado com o menor preço já visto"
    return f"⚠ já esteve mais barato: {_fmt_brl(menor)} (agora {_fmt_brl(preco - menor)} acima)"


def registrar_estado(estado: dict, chave_oferta: str, preco: float, nome: str,
                     notificado: bool) -> None:
    """Atualiza a referência de preço e o menor preço já visto.

    A referência (preco_notificado) só desce quando houve notificação; sobe
    sempre que o preço sobe. Assim quedas pequenas e graduais não se perdem.
    """
    hist = estado.get(chave_oferta, {})
    anterior = hist.get("preco_notificado")
    menor = hist.get("menor_preco")
    referencia = preco if (notificado or anterior is None or preco > anterior) else anterior
    estado[chave_oferta] = {
        "preco_notificado": referencia,
        "nome": nome,
        "menor_preco": preco if menor is None else min(menor, preco),
    }


def marcar_sumidos(estado: dict, chaves_ativas: set, agora: datetime) -> None:
    """Marca quando um item deixou de ser candidato e limpa registros antigos."""
    for k in list(estado):
        if k.startswith("_"):
            continue
        h = estado[k]
        if k in chaves_ativas:
            continue
        if "sumiu_em" not in h:
            h["sumiu_em"] = _agora_iso(agora)
            continue
        try:
            sumiu = datetime.fromisoformat(h["sumiu_em"])
        except ValueError:
            continue
        dias = next((d for pref, d in RETENCAO_DIAS.items() if pref != "padrao" and k.startswith(pref)),
                    RETENCAO_DIAS["padrao"])
        if agora - sumiu > timedelta(days=dias):
            del estado[k]


# --------------------------------------------------------------------------- #
# Coleta e filtro
# --------------------------------------------------------------------------- #
def codigos_modelo(nome: str) -> set[str]:
    """Códigos de modelo (ex.: PHN16-73-76TF -> PHN167376TF) citados no texto."""
    codigos = set()
    for palavra in re.split(r"[\s,;()]+", nome.upper()):
        palavra = palavra.replace("-", "")
        if len(palavra) >= 8 and _MODELO_RE.match(palavra) and re.search(r"\d", palavra):
            codigos.add(palavra)
    return codigos


def deduplicar_modelos(ofertas: list[dict]) -> list[dict]:
    """Mantém só a oferta mais barata quando várias fontes citam o mesmo modelo."""
    mantidas, codigos_vistos = [], []
    for o in sorted(ofertas, key=lambda x: x["preco"]):
        cods = codigos_modelo(o["nome"]) | codigos_modelo(o.get("config_texto", ""))
        if cods and any(cods & v for v in codigos_vistos):
            continue
        mantidas.append(o)
        codigos_vistos.append(cods)
    return mantidas


def coletar_produtos(loja: dict) -> tuple[list[dict], list[str]]:
    """Roda o adaptador sobre todas as urls_busca. Retorna (produtos, erros)."""
    scrape = get_adapter(loja["adaptador"])
    opcoes = loja.get("opcoes") or {}
    produtos, erros = [], []
    for url in loja.get("urls_busca", []):
        try:
            encontrados = scrape(url, **opcoes)
        except NotImplementedError as exc:
            print(f"  [ignorado] {loja['nome']}: {exc}", file=sys.stderr)
            continue
        except Exception as exc:  # noqa: BLE001 - queremos continuar nas outras fontes
            print(f"  [ERRO] {loja['nome']} ({url}): {exc}", file=sys.stderr)
            erros.append(f"{url}: {exc}")
            continue
        for p in encontrados:
            p.setdefault("loja", loja["nome"])
            p["fonte"] = loja["nome"]
            p["adaptador"] = loja["adaptador"]
        print(f"  {loja['nome']}: {len(encontrados)} produto(s) em '{url}'")
        produtos.extend(encontrados)
    return produtos, erros


def confirmar_config_detalhada(produto: dict, config_alvo: dict) -> bool:
    """Confirma RAM/SSD. Define produto['confirmado'] e devolve se o item segue.

    - Adaptador com detalhes_produto(): abre a página do produto. Se a página
      falhar (rede), o item segue como NÃO confirmado em vez de ser descartado.
    - Sem detalhes: usa o texto do anúncio; RAM/SSD abaixo do mínimo reprovam,
      RAM/SSD ausentes seguem como NÃO confirmados.
    """
    mod = sys.modules.get(f"stores.{produto.get('adaptador')}")
    detalhes = getattr(mod, "detalhes_produto", None)
    if detalhes is None:
        produto["confirmado"] = ram_ssd_confirmados(produto["config_texto"])
        return True
    try:
        texto = detalhes(produto["url"])
    except Exception as exc:  # noqa: BLE001
        print(f"  [aviso] não confirmei config de {produto['url']}: {exc}", file=sys.stderr)
        produto["confirmado"] = False
        return True
    produto["config_texto"] = texto
    produto["confirmado"] = True
    return bate_criterios(texto, config_alvo, exigir_ram_ssd=True)


def atualizar_saude(estado: dict, fonte: str, erros: list[str], produtos: list) -> bool:
    """Conta falhas seguidas por fonte. True quando é hora de alertar."""
    saude = estado.setdefault("_saude", {})
    if erros and not produtos:
        n = saude.get(fonte, {}).get("falhas", 0) + 1
        saude[fonte] = {"falhas": n, "erro": erros[0][:200]}
        return n == FALHAS_PARA_ALERTAR
    saude.pop(fonte, None)
    if not saude:
        estado.pop("_saude", None)
    return False


def rodar(config: dict, dry_run: bool = False, agora: datetime | None = None) -> dict:
    """Executa uma varredura. Retorna {'novos', 'candidatos', 'fontes', 'fontes_com_erro', 'erro_envio'}."""
    agora = agora or datetime.now(timezone.utc)
    preco_max = float(config["preco_maximo"])
    preco_ideal = float(config["preco_ideal"]) if config.get("preco_ideal") else None
    config_alvo = config["config_alvo"]
    pesos = config.get("pesos_analise")
    alertas = config.get("alertas") or {}
    queda_min = float(alertas.get("queda_minima_reais", QUEDA_MINIMA_PADRAO))
    realertar = float(alertas.get("realertar_apos_horas", REALERTAR_HORAS_PADRAO))
    estado = carregar_estado()
    estado_inicial = copy.deepcopy(estado)

    resultado = {"novos": [], "candidatos": [], "fontes": 0, "fontes_com_erro": 0, "erro_envio": False}
    avisos = []

    # 1) Coletar todas as ofertas qualificadas (config + preço) de todas as fontes.
    candidatos = []
    for loja in config.get("lojas", []):
        if not loja.get("habilitado", True):
            continue
        print(f"Varrendo {loja['nome']}...")
        resultado["fontes"] += 1
        produtos, erros = coletar_produtos(loja)
        if erros and not produtos:
            resultado["fontes_com_erro"] += 1
        if atualizar_saude(estado, loja["nome"], erros, produtos):
            avisos.append(f"⚠ Fonte <b>{html.escape(loja['nome'])}</b> falhou {FALHAS_PARA_ALERTAR} "
                          f"execuções seguidas: {html.escape(erros[0][:200])}")

        for produto in produtos:
            if produto["preco"] > preco_max:
                continue
            if not bate_criterios(produto["config_texto"], config_alvo, exigir_ram_ssd=False):
                continue
            produto["confirmado"] = True
            if config_alvo.get("exigir_ram_ssd") and not confirmar_config_detalhada(produto, config_alvo):
                continue
            candidatos.append(produto)

    candidatos = deduplicar_modelos(candidatos)
    resultado["candidatos"] = candidatos

    # 2) Anti-spam.
    novos = [p for p in candidatos
             if deve_notificar(estado, chave(p), p["preco"], agora, queda_min, realertar)]
    novos_chaves = {chave(p) for p in novos}
    for p in candidatos:
        if chave(p) not in novos_chaves:
            print(f"  = já notificado: {p['nome'][:70]} (R$ {p['preco']:.2f})")

    # 3) Analisar (score + custo-benefício) e rankear; enviar se há novidade.
    enviado = False
    if novos:
        analisados = [analise.analisar(p, pesos) for p in candidatos]
        for o in analisados:
            o["veredito"] = veredito_preco(estado, chave(o), o["preco"], o.get("historico"))
        ranking = analise.rankear(analisados)
        msg = notifier.format_analise(ranking, analisados, novos_chaves, preco_ideal)
        print(f"  ★ {len(novos)} oferta(s) nova(s); {len(analisados)} candidato(s) na análise.")
        if dry_run:
            print("    [dry-run] mensagem que seria enviada:")
            print("    " + msg.replace("\n", "\n    "))
        else:
            try:
                notifier.send_message(msg)
                enviado = True
            except Exception as exc:  # noqa: BLE001
                print(f"  [ERRO] envio ao Telegram falhou: {exc}", file=sys.stderr)
                resultado["erro_envio"] = True
        resultado["novos"] = novos
    else:
        print("Nenhuma oferta nova.")

    if dry_run:
        return resultado

    # 4) Atualiza o estado (se o envio falhou, os novos ficam pendentes p/ próxima rodada).
    for p in candidatos:
        k = chave(p)
        if k in novos_chaves and not enviado:
            continue
        registrar_estado(estado, k, p["preco"], p["nome"], notificado=k in novos_chaves)
    marcar_sumidos(estado, {chave(p) for p in candidatos}, agora)

    for aviso in avisos:
        try:
            notifier.send_message(aviso)
        except Exception as exc:  # noqa: BLE001
            print(f"  [aviso] não consegui enviar alerta de fonte: {exc}", file=sys.stderr)

    if estado != estado_inicial:
        salvar_estado(estado)
    return resultado


def carregar_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def main() -> int:
    parser = argparse.ArgumentParser(description="Monitor de preço de notebooks")
    parser.add_argument("--dry-run", action="store_true",
                        help="não envia Telegram nem grava estado, apenas imprime as ofertas")
    parser.add_argument("--test-telegram", action="store_true",
                        help="envia uma mensagem de teste e sai")
    args = parser.parse_args()

    if args.test_telegram:
        notifier.send_message("✅ Teste do monitor de notebooks: o bot está funcionando!")
        print("Mensagem de teste enviada.")
        return 0

    resultado = rodar(carregar_config(), dry_run=args.dry_run)
    print(f"\nConcluído. {len(resultado['novos'])} oferta(s) "
          f"{'detectada(s)' if args.dry_run else 'nova(s)'}.")
    if resultado["erro_envio"]:
        return 1
    if resultado["fontes"] and resultado["fontes_com_erro"] == resultado["fontes"]:
        print("Todas as fontes falharam.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
