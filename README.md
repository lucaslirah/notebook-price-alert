# 🔔 Monitor de preço de notebooks (alerta no Telegram)

Robô que varre agregadores de promoção (Bench Promos, Qual Notebook Comprar),
lojas e canais de Telegram, filtra os modelos com a **configuração que você quer**
e te avisa no **Telegram** quando algum estiver **abaixo do seu preço máximo**.
Roda sozinho no GitHub Actions, **a cada 5 minutos**.

Config-alvo padrão (editável em `config.yaml`):
**RTX 5060 ou melhor · CPU Ryzen/Core i5+/Ultra · mín. 16GB RAM e 512GB SSD ·
teto R$ 10.000 · faixa ideal 🔥 até R$ 8.000.**

---

## ⚠️ Primeiro: proteja seu token do Telegram

Se você já compartilhou o token do seu bot em algum lugar (chat, print, commit),
**revogue-o agora** e gere um novo:

1. No Telegram, abra o **@BotFather**.
2. `/mybots` → escolha seu bot → **API Token** → **Revoke current token**.
3. Guarde o novo token — ele vai como **secret** no GitHub (nunca no código).

---

## 1. Criar o bot e descobrir seu chat ID

**Criar o bot (se ainda não tem):**
1. Fale com o **@BotFather** → `/newbot` → siga as instruções → copie o **token**
   (algo como `123456789:AAxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`).

**Descobrir seu chat ID:**
1. Abra uma conversa com o **seu novo bot** e mande qualquer mensagem (ex: "oi").
2. No navegador, acesse (troque `<TOKEN>` pelo seu):
   ```
   https://api.telegram.org/bot<TOKEN>/getUpdates
   ```
3. Procure no JSON por `"chat":{"id":123456789,...}`. Esse número é o seu
   **chat ID**.

---

## 2. Publicar no GitHub e configurar os secrets

1. Crie um repositório no GitHub (pode ser **privado**) e suba estes arquivos.
2. No repositório: **Settings → Secrets and variables → Actions → New repository secret**.
   Crie dois secrets:
   | Nome | Valor |
   |------|-------|
   | `TELEGRAM_BOT_TOKEN` | o token do seu bot |
   | `TELEGRAM_CHAT_ID`   | o seu chat ID |
3. Vá na aba **Actions** e habilite os workflows se o GitHub pedir.

Pronto. O robô vai rodar a cada 5 minutos automaticamente.

> **Nota sobre o cron:** 5 minutos é o mínimo do GitHub Actions. O agendador é
> "melhor esforço": em horários de pico ele atrasa alguns minutos ou pula um
> ciclo. Cada execução leva ~20 s. Em repositório **público** o uso é ilimitado;
> em **privado** são 2.000 min/mês grátis, e rodar a cada 5 min gasta uns
> 290 min por dia (arredondando 1 min por execução), ou seja, acaba em ~7 dias.

**Testar na hora:** aba **Actions** → workflow *"Monitor de preço de notebooks"*
→ **Run workflow** (botão do `workflow_dispatch`).

---

## 3. Testar o Telegram isoladamente

No seu PC (com Python 3.10+):

```bash
pip install -r requirements-dev.txt
export TELEGRAM_BOT_TOKEN="seu_token"
export TELEGRAM_CHAT_ID="seu_chat_id"
python monitor.py --test-telegram   # deve chegar uma mensagem de teste no Telegram
```

Rodar o monitor sem enviar nada nem gravar estado (só ver o que ele acharia):

```bash
python monitor.py --dry-run
```

Rodar os testes: `python -m pytest -q`.

---

## 4. Ajustar o que é monitorado (`config.yaml`)

Você **não precisa mexer no código** — só no `config.yaml`:

```yaml
preco_maximo: 10000         # teto: nada acima disso gera alerta
preco_ideal: 8000           # até aqui: 🔥 e cabeçalho especial no alerta

config_alvo:
  gpu:  ["rtx 5060", "rtx 5070", "rtx 5080", "rtx 5090"]   # pelo menos uma
  cpu:  ["i5", "i7", "i9", "ryzen 7", "ultra 7", ...]       # pelo menos uma
  ram_min_gb: 16            # mínimos numéricos
  ssd_min_gb: 512
  exigir_ram_ssd: true      # confirma RAM/SSD (página do produto, quando dá)
  excluir_termos: ["pc gamer", "desktop", ...]

alertas:
  queda_minima_reais: 30    # só reavisa o mesmo item se cair pelo menos isso
  realertar_apos_horas: 12  # item que sumiu e voltou depois disso avisa de novo
```

- Os termos casam **palavra inteira**: `i5` casa `i5-13450HX`, mas não `ci5x`.
- RAM/SSD são comparados como **números**. Abaixo do mínimo sempre reprova. Se o
  anúncio não informa RAM/SSD, o alerta sai marcado com ⚠ "não confirmados".
- Quer o teto em R$ 8.500? `preco_maximo: 8500`.

---

## 5. Como funciona (resumo)

1. Para cada fonte habilitada, lê a **página de listagem/busca** (URL fixa que não
   muda), então produtos entram e saem naturalmente.
2. Filtra por **GPU + CPU + RAM/SSD mínimos + preço**.
3. Quando a fonte permite (Avell), abre a **página do produto** para confirmar
   RAM/SSD. Se a página falhar, o item segue marcado como "não confirmado".
4. Se o mesmo modelo aparece em várias fontes, fica só a **oferta mais barata**.
5. Envia alerta no Telegram e grava em `state.json` para **não repetir**: só avisa
   de novo se o preço **cair** (`queda_minima_reais`) ou se o item sumir e voltar.
   Aumento de preço não gera alerta.
6. Se uma fonte falha **3 execuções seguidas**, você recebe um aviso no Telegram.

## 5b. Análise de desempenho e custo-benefício

Além de avisar o preço, o bot **analisa e compara** os notebooks encontrados:

- **Score de desempenho (0–100):** estimativa a partir das specs (GPU, CPU, RAM,
  SSD, tela), com pesos ajustáveis em `config.yaml` (`pesos_analise`).
- **Custo-benefício (R$/ponto):** preço ÷ score. Menor = melhor. Responde "qual
  compensa mais", não só "qual é o mais barato".
- **Ranking comparativo:** quando há vários candidatos, destaca 🏆 melhor
  custo-benefício, 💪 mais potente e 💵 mais barato, e lista as demais opções.
- **Longevidade:** o score inclui a **VRAM** da GPU e dá bônus para CPUs **HX**
  (TDP alto). Alerta ⚠ quando o notebook vem **sem Windows** (custo da licença).
- **Veredito de preço:** nas ofertas do Qual Notebook Comprar usa o **histórico de
  ~4 meses** do site ("menor preço dos últimos 120 dias", "% abaixo da mediana").
  Nas demais, compara com o histórico que o próprio bot coletou.

> ⚠️ **O score é uma estimativa por tabela de specs, não um benchmark real**
> (Cinebench, FPS, etc.). Serve para comparar opções entre si de forma
> consistente, não como medição de laboratório. Isso vem escrito na própria
> mensagem do Telegram.

Exemplo de mensagem:

```
🔔 2 notebooks na sua faixa!

🏆 MELHOR CUSTO-BENEFÍCIO
Avell STORM 560  🆕
   Avell · R$ 7.999,00
   ⚙️ RTX 5060 · RYZEN 7 · 16GB · 512GB · 144Hz
   📊 Desempenho: 69/100 · R$ 116/ponto
   🆕 primeira vez que vejo este modelo

📋 Outras opções (por custo-benefício):
• Notebook Asus TUF F16 ... — R$ 8.414,15 · 58/100 · R$ 145/pt
```

Para valorizar mais uma peça, edite os pesos:

```yaml
pesos_analise:
  gpu: 0.40   # aumente para priorizar placa de vídeo
  cpu: 0.25
  ram: 0.15
  ssd: 0.12
  tela: 0.08
  vram: 0.10  # memória da GPU (longevidade)
```

---

## 6. Fontes

| Fonte | Adaptador | Status | Observação |
|-------|-----------|--------|------------|
| **Bench Promos** | `benchpromos` | ✅ | Lê o JSON embutido na página: todas as lojas, cupom e disponibilidade. ~280 notebooks. |
| **Qual Notebook Comprar** | `qnc` | ✅ | Specs estruturadas, cupom e **histórico de preço**. |
| **Avell** | `avell` | ✅ | Listagem + página do produto para RAM/SSD. |
| **Canais públicos do Telegram** | `telegram_canal` | ✅ | Sem login: lê `t.me/s/<canal>`. Só canais com @usuario. |
| **Grupos privados do Telegram** | `telegram_grupo` | ⚠️ | Usa sua conta (veja abaixo). **Não testado com conta real.** |
| **Kabum direta** | `kabum` | ⏸ desligada | Playwright; deixa cada execução ~1 min mais lenta. O Bench Promos já traz a Kabum. |
| Pichau / Terabyte | – | ❌ | HTTP 403 para robôs. |
| Amazon / Mercado Livre | – | ❌ | Bloqueiam scraping. Chegam via Bench Promos / QNC. |

### Telegram: canais e grupos

**Canais públicos** (têm `@usuario`): coloque em `urls_busca` do bloco
`telegram_canal` (`"@canal"` ou `"https://t.me/canal"`). Nada mais a configurar.
Limite: a prévia web mostra só as ~20 mensagens mais recentes.

**Grupos privados** (só entra com convite): o bot precisa ler com a **sua conta**.

1. Em <https://my.telegram.org> → *API development tools*, crie um app e anote
   `api_id` e `api_hash`.
2. No seu PC: `export TELEGRAM_API_ID=... TELEGRAM_API_HASH=...` e rode
   `python gerar_sessao_telegram.py` (pede telefone e código). Copie a string.
3. Crie os secrets `TELEGRAM_API_ID`, `TELEGRAM_API_HASH` e `TELEGRAM_SESSION`.
4. No `config.yaml`, ligue o bloco `telegram_grupo` e liste os grupos
   (`"@usuario"` ou id numérico `-100...`).

Riscos: a `TELEGRAM_SESSION` equivale à **senha da conta** (guarde só como secret,
nunca no repositório). O Telegram pode estranhar logins vindos de IPs de
datacenter e derrubar a sessão; nesse caso gere outra. Use uma conta
secundária se quiser reduzir o risco. O adaptador só **lê**: não envia nada.

**Para criar um adaptador novo:**

1. Crie `stores/minhaloja.py` com uma função:
   ```python
   def scrape(url_busca: str, **opcoes) -> list[dict]:
       # retorne uma lista de dicts:
       # {"nome": str, "preco": float, "url": str, "config_texto": str}
       # opcionais: "loja", "chave", "cupom", "historico"
       ...
   ```
   Opcionalmente, adicione `detalhes_produto(url) -> str` para confirmar RAM/SSD
   na página do produto (como faz `stores/avell.py`).
2. Registre em `stores/__init__.py`:
   ```python
   from stores import minhaloja
   ADAPTERS = { ..., "minhaloja": minhaloja.scrape }
   ```
3. Adicione a loja no `config.yaml` com `habilitado: true` e as `urls_busca`.

**Lojas que exigem JavaScript:** prefira achar o JSON embutido na página (como em
`stores/benchpromos.py`). Só use [Playwright](https://playwright.dev/python/)
(como em `stores/kabum.py`) se não houver alternativa.

---

## Estrutura do projeto

```
notebook-price-alert/
├── .github/workflows/monitor.yml  # agendamento no GitHub Actions (cron */5)
├── config.yaml                    # seus critérios (edite aqui)
├── monitor.py                     # núcleo: coleta, anti-spam, saúde das fontes
├── filtros.py                     # critérios (palavra inteira, RAM/SSD numéricos)
├── analise.py                     # score, custo-benefício, ranking
├── texto.py                       # normalização de texto
├── notifier.py                    # mensagem e envio Telegram
├── gerar_sessao_telegram.py       # gera TELEGRAM_SESSION (grupos privados)
├── requirements.txt / requirements-dev.txt
├── state.json                     # último preço notificado (anti-spam)
├── tests/                         # pytest
└── stores/                        # um adaptador por fonte
    ├── benchpromos.py  qnc.py  avell.py  kabum.py
    ├── telegram_canal.py  telegram_grupo.py  telegram_msg.py
    └── base.py  __init__.py
```
