# 🔔 Monitor de preço de notebooks (alerta no Telegram)

Robô que varre lojas de notebook, filtra pelos modelos com a **configuração que
você quer** e te avisa no **Telegram** quando algum estiver **abaixo do seu preço
máximo**. Roda sozinho **24/7 no GitHub Actions** — de graça.

Config-alvo padrão (editável em `config.yaml`):
**RTX 5060 · Ryzen 7 ou Core i7 · 16GB RAM · 512GB ou 1TB SSD · até R$ 8.000.**

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

Pronto. O robô vai rodar a cada 30 minutos automaticamente.

> **Nota sobre o cron:** o agendador do GitHub Actions é "melhor esforço" — em
> horários de pico ele pode atrasar alguns minutos ou pular um ciclo. Para
> monitorar preço até a Black Friday isso é irrelevante.

**Testar na hora:** aba **Actions** → workflow *"Monitor de preço de notebooks"*
→ **Run workflow** (botão do `workflow_dispatch`).

---

## 3. Testar o Telegram isoladamente

No seu PC (com Python 3.10+):

```bash
pip install -r requirements.txt
python -m playwright install chromium   # navegador headless (para a Kabum)
export TELEGRAM_BOT_TOKEN="seu_token"
export TELEGRAM_CHAT_ID="seu_chat_id"
python monitor.py --test-telegram   # deve chegar uma mensagem de teste no Telegram
```

Rodar o monitor sem enviar nada (só ver o que ele acharia):

```bash
python monitor.py --dry-run
```

---

## 4. Ajustar o que é monitorado (`config.yaml`)

Você **não precisa mexer no código** — só no `config.yaml`:

```yaml
preco_maximo: 8000          # alerta se preço <= este valor

config_alvo:
  gpu:  ["rtx 5060"]        # GPU obrigatória
  cpu:  ["ryzen 7", "i7"]   # pelo menos uma destas CPUs
  ram:  ["16gb"]            # RAM desejada (confirmada na página do produto)
  ssd:  ["512gb", "1tb"]    # armazenamento desejado
  exigir_ram_ssd: true      # true = confirma RAM/SSD abrindo a página do produto
  excluir_termos:           # descarta itens com estes termos (ex.: desktops)
    - "pc gamer"
    - "desktop"
  exigir_termos: []         # termos obrigatórios (vazio = não exige)
```

- Quer aceitar **32GB** também? `ram: ["16gb", "32gb"]`.
- Quer alertar qualquer RTX 5060 sem se importar com RAM/SSD? `exigir_ram_ssd: false`.
- Quer subir o teto para R$ 8.500? `preco_maximo: 8500`.
- **`excluir_termos`**: a busca de algumas lojas (ex.: Kabum) mistura **desktops/PC
  Gamer** com a mesma config (Ryzen 7 + RTX 5060). Esses termos removem o que não
  é notebook. Ajuste se precisar.

---

## 5. Como funciona (resumo)

1. Para cada loja habilitada, lê a **página de listagem/busca** (URL fixa que não
   muda), então produtos entram e saem naturalmente — não é preciso fixar links
   de produtos individuais.
2. Filtra por **GPU + CPU + preço** na listagem (rápido).
3. Para os candidatos, abre a **página do produto** e confirma **RAM/SSD** (quando
   `exigir_ram_ssd: true`).
4. Envia alerta no Telegram e grava o preço em `state.json` para **não repetir** o
   mesmo alerta (só avisa de novo se o preço mudar).

---

## 6. Adicionar mais lojas

O projeto usa um **adaptador por loja** em `stores/`. Nem toda loja é fácil de ler:

| Loja | Status | Observação |
|------|--------|------------|
| **Avell** | ✅ Funcionando | A listagem já traz preço e specs no HTML. |
| **Kabum** | ✅ Funcionando | Via Playwright (navegador headless), pois a busca é renderizada por JavaScript. |
| **Pichau / Terabyte** | ❌ Bloqueiam | Retornam HTTP 403 para robôs. |
| **Amazon** | ❌ Difícil | Detecta e bloqueia scraping, ainda mais de IP de datacenter (Actions). |
| **Mercado Livre** | ❌ Fechado | O ML desativou a busca pública da API (403 mesmo com token válido). |

**Para criar um adaptador novo:**

1. Crie `stores/minhaloja.py` com uma função:
   ```python
   def scrape(url_busca: str) -> list[dict]:
       # retorne uma lista de dicts:
       # {"nome": str, "preco": float, "url": str, "config_texto": str}
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

**Lojas que exigem JavaScript** (ex: Kabum): a forma robusta é usar
[Playwright](https://playwright.dev/python/) para renderizar a página, ou achar a
API/JSON interna da loja (às vezes em `__NEXT_DATA__` no HTML). Isso é mais
trabalhoso e foge do escopo do esqueleto atual — por isso a Kabum vem desligada.

---

## Estrutura do projeto

```
notebook-price-alert/
├── .github/workflows/monitor.yml  # agendamento no GitHub Actions (cron */30)
├── config.yaml                    # seus critérios (edite aqui)
├── monitor.py                     # núcleo: filtro, preço, anti-spam
├── notifier.py                    # envio Telegram
├── requirements.txt
├── state.json                     # último preço notificado (anti-spam)
└── stores/                        # um adaptador por loja
    ├── __init__.py                # registro dos adaptadores
    ├── base.py                    # download + parse de preço
    ├── avell.py                   # ✅ funcionando
    └── kabum.py                   # ⚠️ esqueleto (JS)
```
