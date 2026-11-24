"""Envio de notificações via Telegram Bot API."""
import os
import html

import requests

from analise import chave as analise_chave

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


def _get_credentials():
    """Lê token e chat_id das variáveis de ambiente (secrets do GitHub Actions)."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        raise RuntimeError(
            "Faltam credenciais. Defina as variáveis de ambiente "
            "TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID "
            "(ou os secrets equivalentes no GitHub Actions)."
        )
    return token, chat_id


def send_message(text: str) -> None:
    """Envia uma mensagem de texto (formato HTML) para o chat configurado."""
    token, chat_id = _get_credentials()
    resp = requests.post(
        TELEGRAM_API.format(token=token),
        json={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
        },
        timeout=30,
    )
    resp.raise_for_status()


def _brl(valor: float) -> str:
    """Formata número como moeda brasileira: 7999.0 -> 7.999,00"""
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _linha_oferta(o: dict, novo: bool, preco_ideal: float | None = None) -> str:
    nome = html.escape(o["nome"][:70])
    loja = html.escape(o.get("loja", ""))
    url = html.escape(o["url"], quote=True)
    specs = o.get("specs", {})
    partes = []
    if specs.get("gpu"):
        vram = f" {specs['vram_gb']}GB" if specs.get("vram_gb") else ""
        partes.append(specs["gpu"].upper() + vram)
    if specs.get("cpu"):
        partes.append(specs["cpu"].upper() + (" HX" if specs.get("hx") else ""))
    if specs.get("ram_gb"):
        partes.append(f"{specs['ram_gb']}GB RAM")
    if specs.get("ssd_gb"):
        ssd = specs["ssd_gb"]
        partes.append(f"{ssd // 1024}TB" if ssd >= 1024 else f"{ssd}GB")
    if specs.get("hz"):
        partes.append(f"{specs['hz']}Hz")
    cfg = " · ".join(partes)
    cb = o.get("custo_beneficio")
    cb_txt = f" · R$ {cb:.0f}/ponto".replace(".", ",") if cb else ""
    tag = " 🆕" if novo else ""
    fogo = "🔥 " if preco_ideal and o["preco"] <= preco_ideal else ""
    cupom = f" · 🎟 <code>{html.escape(o['cupom'])}</code>" if o.get("cupom") else ""
    linhas = [
        f'🔗 <a href="{url}">{nome}</a>{tag}',
        f"   {loja} · {fogo}<b>{_brl(o['preco'])}</b>{cupom}",
        f"   ⚙ {cfg}",
        f"   📊 Desempenho: <b>{o.get('score', 0)}/100</b>{cb_txt}",
    ]
    if o.get("veredito"):
        linhas.append(f"   {html.escape(o['veredito'])}")
    if specs.get("sem_windows"):
        linhas.append("   ⚠ vem sem Windows (Linux): some o custo da licença")
    if not o.get("confirmado", True):
        linhas.append("   ⚠ RAM/SSD não confirmados no anúncio: confira antes de comprar")
    return "\n".join(linhas)


LIMITE_TELEGRAM = 4000  # o máximo da API é 4096 caracteres


def format_analise(ranking: dict, todos: list[dict], novos_chaves: set,
                   preco_ideal: float | None = None) -> str:
    """Monta a mensagem comparativa com destaques e ranking.

    ranking: dict com 'melhor_cb', 'mais_potente', 'mais_barato', 'ranking'.
    todos: lista de ofertas já analisadas.
    novos_chaves: chaves (analise.chave) das ofertas novas nesta verificação.
    preco_ideal: ofertas até este valor ganham 🔥.
    """
    novos = [o for o in todos if analise_chave(o) in novos_chaves]
    n_novos = len(novos)
    ideal = bool(preco_ideal) and any(o["preco"] <= preco_ideal for o in novos)
    if ideal:
        cab = f"🔥 <b>Oferta abaixo de {_brl(preco_ideal)}!</b>"
    elif n_novos == 1:
        cab = "🔔 <b>Notebook em oferta!</b>"
    else:
        cab = f"🔔 <b>{n_novos} notebooks na sua faixa!</b>"

    partes = [cab, ""]

    melhor = ranking.get("melhor_cb")
    potente = ranking.get("mais_potente")
    barato = ranking.get("mais_barato")

    def linha(o):
        return _linha_oferta(o, analise_chave(o) in novos_chaves, preco_ideal)

    if melhor:
        partes += ["🏆 <b>MELHOR CUSTO-BENEFÍCIO</b>", linha(melhor), ""]

    # Só mostra "mais potente" e "mais barato" se forem diferentes do melhor CB.
    if potente and analise_chave(potente) != analise_chave(melhor or {"url": ""}):
        partes += ["💪 <b>MAIS POTENTE</b>", linha(potente), ""]
    if barato and analise_chave(barato) not in {
        analise_chave(x) for x in (melhor, potente) if x
    }:
        partes += ["💵 <b>MAIS BARATO</b>", linha(barato), ""]

    destaque = {analise_chave(x) for x in (melhor, potente, barato) if x}
    resto = [o for o in ranking.get("ranking", []) if analise_chave(o) not in destaque]
    if resto:
        partes.append("📋 <b>Outras opções</b> (por custo-benefício):")
        for o in resto[:6]:
            cb = o.get("custo_beneficio")
            cb_txt = f" · R$ {cb:.0f}/pt".replace(".", ",") if cb else ""
            nome = html.escape(o["nome"][:48])
            fogo = "🔥" if preco_ideal and o["preco"] <= preco_ideal else "•"
            url = html.escape(o["url"], quote=True)
            partes.append(f'{fogo} <a href="{url}">{nome}</a> — {_brl(o["preco"])} · {o.get("score", 0)}/100{cb_txt}')
        partes.append("")

    partes.append("🆕 = novidade nesta verificação")
    partes.append("<i>Score é estimativa por tabela de specs, não benchmark real.</i>")
    msg = "\n".join(partes)
    if len(msg) > LIMITE_TELEGRAM:
        msg = msg[: LIMITE_TELEGRAM - 20].rsplit("\n", 1)[0] + "\n…(cortado)"
    return msg
