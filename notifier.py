"""Envio de notificações via Telegram Bot API."""
import os
import html

import requests

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


def format_deal(produto: dict) -> str:
    """Monta a mensagem de um notebook que bateu os critérios."""
    nome = html.escape(produto["nome"])
    loja = html.escape(produto["loja"])
    preco = produto["preco"]
    url = html.escape(produto["url"], quote=True)
    config = html.escape(produto.get("config_texto", ""))

    linhas = [
        "🔔 <b>Notebook em oferta!</b>",
        "",
        f"🏷️ <b>{nome}</b>",
        f"🏬 Loja: {loja}",
        f"💰 Preço: <b>R$ {preco:,.2f}</b>".replace(",", "X").replace(".", ",").replace("X", "."),
    ]
    if config:
        linhas.append(f"⚙️ Config: {config}")
    linhas.append("")
    linhas.append(f'🔗 <a href="{url}">Ver oferta</a>')
    return "\n".join(linhas)


def _brl(valor: float) -> str:
    """Formata número como moeda brasileira: 7999.0 -> 7.999,00"""
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _linha_oferta(o: dict, novo: bool) -> str:
    nome = html.escape(o["nome"][:70])
    loja = html.escape(o.get("loja", ""))
    url = html.escape(o["url"], quote=True)
    specs = o.get("specs", {})
    partes = []
    if specs.get("gpu"):
        partes.append(specs["gpu"].upper())
    if specs.get("cpu"):
        partes.append(specs["cpu"].upper())
    if specs.get("ram_gb"):
        partes.append(f"{specs['ram_gb']}GB")
    if specs.get("ssd_gb"):
        ssd = specs["ssd_gb"]
        partes.append(f"{ssd // 1024}TB" if ssd >= 1024 else f"{ssd}GB")
    if specs.get("hz"):
        partes.append(f"{specs['hz']}Hz")
    cfg = " · ".join(partes)
    cb = o.get("custo_beneficio")
    cb_txt = f" · R$ {cb:.0f}/ponto".replace(".", ",") if cb else ""
    tag = " 🆕" if novo else ""
    linhas = [
        f'🔗 <a href="{url}">{nome}</a>{tag}',
        f"   {loja} · <b>{_brl(o['preco'])}</b>",
        f"   ⚙️ {cfg}",
        f"   📊 Desempenho: <b>{o.get('score', 0)}/100</b>{cb_txt}",
    ]
    if o.get("veredito"):
        linhas.append(f"   {html.escape(o['veredito'])}")
    return "\n".join(linhas)


def format_analise(ranking: dict, todos: list[dict], novos_urls: set) -> str:
    """Monta a mensagem comparativa com destaques e ranking.

    ranking: dict com 'melhor_cb', 'mais_potente', 'mais_barato', 'ranking'.
    todos: lista de ofertas já analisadas.
    novos_urls: set de URLs que são novidade (mudaram de preço/novos).
    """
    n_novos = len([o for o in todos if o["url"] in novos_urls])
    cab = "🔔 <b>Notebook em oferta!</b>" if n_novos == 1 else f"🔔 <b>{n_novos} notebooks na sua faixa!</b>"

    partes = [cab, ""]

    melhor = ranking.get("melhor_cb")
    potente = ranking.get("mais_potente")
    barato = ranking.get("mais_barato")

    if melhor:
        partes.append("🏆 <b>MELHOR CUSTO-BENEFÍCIO</b>")
        partes.append(_linha_oferta(melhor, melhor["url"] in novos_urls))
        partes.append("")

    # Só mostra "mais potente" e "mais barato" se forem diferentes do melhor CB.
    if potente and potente["url"] != (melhor or {}).get("url"):
        partes.append("💪 <b>MAIS POTENTE</b>")
        partes.append(_linha_oferta(potente, potente["url"] in novos_urls))
        partes.append("")
    if barato and barato["url"] not in {(melhor or {}).get("url"), (potente or {}).get("url")}:
        partes.append("💵 <b>MAIS BARATO</b>")
        partes.append(_linha_oferta(barato, barato["url"] in novos_urls))
        partes.append("")

    # Ranking completo (se houver mais de 1 candidato), resumido.
    rank = ranking.get("ranking", [])
    destaque_urls = {(melhor or {}).get("url"), (potente or {}).get("url"), (barato or {}).get("url")}
    resto = [o for o in rank if o["url"] not in destaque_urls]
    if resto:
        partes.append("📋 <b>Outras opções</b> (por custo-benefício):")
        for o in resto[:6]:
            cb = o.get("custo_beneficio")
            cb_txt = f" · R$ {cb:.0f}/pt".replace(".", ",") if cb else ""
            nome = html.escape(o["nome"][:48])
            partes.append(f"• {nome} — {_brl(o['preco'])} · {o.get('score',0)}/100{cb_txt}")
        partes.append("")

    partes.append("🆕 = novidade nesta verificação")
    partes.append("<i>Score é estimativa por tabela de specs, não benchmark real.</i>")
    return "\n".join(partes)
