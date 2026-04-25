#  Ultron — Assistente de Voz com IA

Assistente de voz pessoal para Windows com interface HUD sci-fi, controle total do sistema operacional, memória baseada em notas do Obsidian e personalidade sofisticada inspirada no Ultron.

---

##  Funcionalidades

| Categoria | Recursos |
|---|---|
| **Voz** | Escuta contínua · Transcrição offline · TTS neural gratuito (pt-BR) |
| **IA** | Groq API (llama-3.3-70b) · Fallback automático entre 4 modelos · Classificador de intenção híbrido |
| **Memória** | RAG com vault do Obsidian · BM25 local · Indexação de 13 mil+ notas |
| **Automação OS** | Abrir/fechar apps · Mouse e teclado · Screenshot com visão IA · Volume e mídia |
| **Navegadores** | Chrome · Firefox · Edge · Brave · Opera · Vivaldi · YouTube inteligente |
| **Skills RPA** | Bloco de Notas · WhatsApp Web · Gmail · Comandos de terminal |
| **HUD** | Interface 60fps com PyQt6 · Estrela vermelha animada · Responde à amplitude da voz |

---

##  Arquitetura

```
ultron-assistant/
│
├── main.py                        # Orquestrador principal — 2 threads (Qt + asyncio)
├── hud.py                         # Interface HUD sci-fi (PyQt6, 60fps, red nebula)
│
├── modules/
│   ├── llm.py                     # Agente LLM + classificador de intenção + fallback
│   ├── brain_engine.py            # RAG local com BM25 (vault Obsidian)
│   ├── stt.py                     # Speech-to-Text (Google Speech Recognition)
│   ├── tts.py                     # Text-to-Speech (edge-tts, voz neural gratuita)
│   ├── ui.py                      # Fila thread-safe (backend → HUD)
│   ├── obsidian.py                # Integração legada com Obsidian
│   │
│   └── automation/
│       ├── executor.py            # Dispatcher central de ferramentas (ActionExecutor)
│       ├── os_control.py          # Controle do SO: apps, mouse, teclado, arquivos, volume
│       ├── web_agent.py           # Playwright: navegação headless, busca, YouTube
│       ├── web_automation.py      # YouTube inteligente com browser específico
│       ├── notepad_automation.py  # RPA: Bloco de Notas via pyautogui + clipboard
│       ├── whatsapp.py            # WhatsApp Web via Playwright
│       ├── gmail.py               # Gmail via Playwright
│       └── browser.py             # Utilitários de browser
│
├── .env                           # Configuração (chaves, caminhos, parâmetros)
├── .env.example                   # Modelo de configuração (sem valores reais)
├── contacts.json                  # Mapa de apelidos → nomes reais (WhatsApp)
├── requirements.txt               # Dependências Python
├── setup.bat                      # Instalador automático
├── ULTRON.bat                     # Atalho de execução
└── Ultron.vbs                     # Executa sem janela de terminal
```

---

##  Como Funciona — Fluxo Completo

```
Microfone
    │
    ▼
[STT] Google Speech Recognition
    │ transcrição em texto
    ▼
[Classificador de Intenção] — Híbrido em 2 camadas:
    ├── Regex rápido → ACTION  (verbos imperativos, apps, browsers)
    └── LLM 8b leve → CHAT | KNOWLEDGE
    │
    ├── CHAT ──────────────────────────▶ [LLM 70b] responde livremente
    │                                        ↑ personalidade Ultron
    │
    ├── ACTION ─────────────────────────▶ [LLM 70b + Tools]
    │                                        │ chama ferramenta
    │                                        ▼
    │                                   [ActionExecutor]
    │                                   os_control / web_agent / RPA
    │
    └── KNOWLEDGE ──▶ [BrainEngine] busca no vault Obsidian (BM25)
                           │
                           ├── Encontrou ──▶ [LLM 70b] responde com contexto
                           └── Não encontrou ▶ "Senhor, vasculhei seus arquivos..."
    │
    ▼
[TTS] edge-tts — voz neural pt-BR (pt-BR-AntonioNeural)
    │
    ▼
[HUD] atualiza estado visual em tempo real
```

---

##  Sistema de Intenção (Intent Routing)

O classificador opera em duas camadas para máxima precisão com mínimo custo de tokens:

**Camada 1 — Regex (0ms, sem custo de API)**
Detecta ações óbvias por padrões de verbos imperativos:
- `"abra o chrome"` → `ACTION`
- `"pesquise no YouTube"` → `ACTION`
- `"escreva no bloco de notas"` → `ACTION`

**Camada 2 — LLM leve (llama-3.1-8b-instant)**
Distingue conversa de pesquisa para casos ambíguos:
- `"estou cansado"` → `CHAT`
- `"que dia difícil"` → `CHAT`
- `"me fala sobre o projeto Alpha"` → `KNOWLEDGE`
- `"quem é João nas minhas notas?"` → `KNOWLEDGE`

---

##  Personalidade do Ultron

O assistente é **proativo** e usa o histórico da conversa. Exemplos de comportamento:

| Senhor diz | Ultron responde |
|---|---|
| *"Estou cansado"* | "A eficiência humana tem seus limites, senhor. Deseja ativar música ambiente ou silenciar as notificações?" |
| *"Que dia difícil"* | "Dias assim testam os mais resilientes. Posso organizar o que resta ou ficar em standby." |
| *"Tô entediado"* | "Posso sugerir algo: um vídeo, uma playlist, ou prefere que eu liste suas pendências?" |
| *"Valeu"* | "Sempre, senhor." |
| Pergunta sem resposta no vault | "Senhor, vasculhei seus arquivos mas essa informação parece não existir. Devo criar uma nova entrada?" |

---

##  Fallback de Modelos (Rate Limit)

Quando o modelo primário atinge o limite de tokens diários (100k/dia gratuito), o sistema troca automaticamente:

```
llama-3.3-70b-versatile  →  llama-3.1-8b-instant  →  gemma2-9b-it  →  mixtral-8x7b-32768
      100k TPD                    100k TPD               100k TPD           100k TPD
```

Cada modelo tem **cota separada** na Groq — efetivamente ~400k tokens/dia no plano gratuito.

---

##  Ferramentas Disponíveis (Skills)

### Sistema Operacional
| Ferramenta | Descrição |
|---|---|
| `open_app` | Abre qualquer aplicativo instalado |
| `close_app` | Fecha janela ou processo |
| `press_hotkey` | Executa atalhos de teclado (ex: `ctrl+c`) |
| `type_text` | Digita texto no elemento focado |
| `click_at` / `right_click_at` | Clica em coordenadas X,Y |
| `scroll_at` | Rola a tela em uma posição |
| `take_screenshot` | Captura tela + análise visual por IA |
| `get_screen_size` | Retorna resolução atual |
| `run_command` | Executa comandos CMD ou PowerShell |
| `set_volume` | Define volume do sistema (0-100) |
| `media_control` | Play/pause/next/previous/stop |
| `lock_screen` | Bloqueia o Windows |

### Sistema de Arquivos
| Ferramenta | Descrição |
|---|---|
| `open_file` | Abre arquivo com app padrão |
| `create_folder` | Cria pasta em qualquer caminho |
| `list_files` | Lista conteúdo de diretório |

### Web e Navegadores
| Ferramenta | Descrição |
|---|---|
| `open_url` | Abre URL em qualquer navegador instalado |
| `navigate_to` | Navega para URL no browser controlado |
| `web_search` | Pesquisa no Google e retorna resultados |
| `web_click` | Clica em elemento da página |
| `web_fill` | Preenche campo de texto |
| `web_read_page` | Lê conteúdo textual da página |
| `web_screenshot` | Captura tela do navegador |
| `youtube_play` | Pesquisa e reproduz vídeo no YouTube |
| `youtube_in_browser` | YouTube em navegador específico por voz |

### Comunicação
| Ferramenta | Descrição |
|---|---|
| `whatsapp_send` | Envia mensagem via WhatsApp Web |
| `gmail_send` | Envia e-mail via Gmail |

### RPA
| Ferramenta | Descrição |
|---|---|
| `notepad_type` | Abre Bloco de Notas e digita texto com suporte a acentos |

---

##  Brain Engine (RAG com Obsidian)

O `BrainEngine` indexa todo o vault do Obsidian localmente, sem API externa:

- **Algoritmo**: BM25Okapi (`rank-bm25`) — busca por relevância lexical
- **Chunking**: 300 palavras com overlap de 60 (preserva contexto)
- **Cache**: arquivo `.pkl` com hash MD5 dos timestamps — reindexação só quando notas mudam
- **Velocidade**: ~2 min na primeira indexação, ~5s nos inícios seguintes (cache)
- **Compatível**: Python 3.14 (sem dependências nativas problemáticas)

```
Vault (.md files)
    │
    ▼ index()
Limpeza de markdown (frontmatter, [[links]], código, imagens)
    │
    ▼
Chunking (300 palavras, overlap 60)
    │
    ▼
BM25 Index ──── cache .pkl
    │
    ▼ search(query)
Top-K chunks relevantes → injetados no prompt do LLM
```

---

##  Interface HUD

Janela frameless de **500×580px**, 60fps, renderizada com `QPainter` puro:

- **Estrela central**: núcleo branco → vermelho com 8 raios de luz animados
- **Glow**: 5 camadas de halo difuso que respondem à amplitude da voz
- **Starfield**: 320 estrelas com cintilação independente
- **Painel MIC**: 12 segmentos VU meter (canto inferior esquerdo)
- **Estados visuais**: AGUARDANDO · OUVINDO · PROCESSANDO · TRANSMITINDO
- **Arrastar**: clique e arraste para mover a janela
- **Fechar**: botão X no canto superior direito ou duplo clique

---

##  Instalação

### Pré-requisitos
- Windows 10/11
- Python 3.10+ (recomendado 3.11)
- Microfone funcional
- Conta na [Groq](https://console.groq.com) (gratuita)

### Passo a passo

**1. Clone o repositório**
```bash
git clone https://github.com/saviomendoncaads-jpg/ultron-assistant.git
cd ultron-assistant
```

**2. Execute o instalador**
```bat
setup.bat
```
Isso cria o ambiente virtual e instala todas as dependências.

**3. Configure o `.env`**

O arquivo `.env` já vem configurado no repositório privado. Se precisar ajustar:

```env
# ── Groq API (obrigatório) ────────────────────
GROQ_API_KEY=sua_chave_aqui
GROQ_MODEL=llama-3.3-70b-versatile

# ── Voz TTS ───────────────────────────────────
TTS_VOICE=pt-BR-AntonioNeural
TTS_RATE=-8%
TTS_PITCH=-12Hz

# ── Reconhecimento de fala ────────────────────
STT_LANGUAGE=pt-BR
AUDIO_SILENCE_THRESHOLD=500
AUDIO_SILENCE_DURATION=1.8

# ── Vault do Obsidian (RAG) ───────────────────
OBSIDIAN_VAULT_PATH=C:\Users\SeuUsuario\Documents\Obsidian\SeuVault

# ── Wake Word (opcional) ─────────────────────
# Deixe vazio para escuta contínua
WAKE_WORD=
```

**4. Instale o Playwright (navegador controlado)**
```bash
venv\Scripts\python -m playwright install chromium
```

**5. Inicie o assistente**

Dê dois cliques em `Ultron.vbs` (sem terminal) ou execute:
```bat
ULTRON.bat
```

---

##  Exemplos de Comandos de Voz

### Conversação
```
"Ultron, tudo bem?"
"Estou com dor de cabeça hoje"
"Que dia cansativo esse foi"
```

### Controle do Sistema
```
"Abra o Spotify"
"Fecha o Chrome"
"Aumenta o volume para 70"
"Tira um print da tela"
"Bloqueia o computador"
```

### Navegação Web
```
"Pesquise notícias de tecnologia"
"Abra o YouTube no Brave"
"Abra o Chrome e procure Python para iniciantes no YouTube"
"Abra o gmail.com"
```

### RPA — Bloco de Notas
```
"Abra o bloco de notas e escreva minha lista de tarefas"
"Digite no notepad: reunião amanhã às 10h"
```

### Comunicação
```
"Manda mensagem para João dizendo que vou me atrasar"
"Envia e-mail para fulano@email.com com assunto Reunião"
```

### Pesquisa no Vault Obsidian
```
"Me fala sobre o projeto Alpha"
"Quem é o João que mencionei nas notas?"
"O que tenho anotado sobre React?"
```

---

##  Configuração Avançada

### Contatos (WhatsApp)
Edite `contacts.json` para mapear apelidos a nomes reais:
```json
{
  "joão": "João Silva",
  "mãe": "Maria Mendonça",
  "chefe": "Carlos Diretor"
}
```

### Wake Word
Para que o Ultron só responda ao ouvir uma palavra específica:
```env
WAKE_WORD=ultron
```
Deixe vazio para escuta contínua (padrão).

### Ajuste de Sensibilidade do Microfone
```env
AUDIO_SILENCE_THRESHOLD=500    # menor = mais sensível
AUDIO_SILENCE_DURATION=1.8     # segundos de silêncio para encerrar gravação
```

---

##  Dependências Principais

| Pacote | Versão | Uso |
|---|---|---|
| `PyQt6` | 6.11+ | Interface HUD 60fps |
| `groq` | latest | API de LLM (gratuita) |
| `edge-tts` | latest | Text-to-Speech neural |
| `speechrecognition` | latest | Captura de áudio + STT |
| `playwright` | 1.44+ | Automação de navegador |
| `pyautogui` | 0.9.54+ | Controle de mouse e teclado |
| `pygetwindow` | 0.0.9+ | Gerenciamento de janelas |
| `rank-bm25` | 0.2.2+ | Busca BM25 no vault |
| `pyperclip` | 1.11+ | Clipboard para acentos no RPA |
| `loguru` | 0.7.2+ | Logging estruturado |

---

##  Arquivos Ignorados pelo Git

| Arquivo/Pasta | Motivo |
|---|---|
| `venv/` | Específico da máquina — reinstalar via `setup.bat` |
| `.browser_session/` | Cookies de login do navegador |
| `*.pkl` | Cache do Brain — regenerado automaticamente |
| `*.log` | Logs de execução |

---

##  Licença

Uso pessoal. Projeto desenvolvido para automação do ambiente pessoal de trabalho.
