"""
Ultron — Agente Principal via Groq (GRATUITO)
=============================================
Integra:
  - Personalidade Ultron (sofisticado, direto, levemente sarcástico)
  - Brain RAG: busca no vault do Obsidian antes de responder perguntas
  - Política estrita: sem vault = sem resposta factual inventada
  - Loop agêntico com 27 ferramentas para controle total do computador
"""
import json
import re
import os
from groq import Groq
from loguru import logger

from modules.brain_engine import BrainEngine

MODEL          = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
MAX_ITERATIONS = 20

# Cascade de fallback — cada modelo tem cota TPD separada no Groq Free
_MODEL_FALLBACK = [
    "llama-3.3-70b-versatile",   # primário
    "llama-3.1-8b-instant",      # rápido, cota separada
    "gemma2-9b-it",              # Google, cota separada
    "mixtral-8x7b-32768",        # Mistral, cota separada
]
# Histórico curto: economiza tokens e mantém contexto relevante
_MAX_HISTORY = 8

# ── Regex: gatilhos de ação rápida (alta precisão, sem custo de API) ──────────
_ACTION_REGEX = [
    r"^abr", r"^fech", r"^digit", r"^cliqu", r"^clica", r"^mand",
    r"^envi", r"^toca ", r"^play", r"^reproduz", r"^naveg",
    r"^acess", r"^execut", r"^rode ", r"^minimiz", r"^maximiz", r"^bloqueie",
    r"^reinici", r"^cri[ae] ", r"^mov[ae] ", r"^ajust", r"^coloca", r"^tira ",
    r"^delet", r"^apag", r"^ligar", r"^desligar", r"^aumenta", r"^diminu",
    r"^pause", r"^próxim", r"^anterio", r"^volta ", r"^vai para",
    r"(bloco de notas|notepad).{0,30}(digit|escrev|anot|coloc)",
    r"(digit|escrev|anot).{0,30}(bloco de notas|notepad)",
    r"^escrev", r"^anot",
    r"(chrome|firefox|edge|brave|opera|vivaldi).{0,30}youtube",
    r"youtube.{0,30}(chrome|firefox|edge|brave|opera|vivaldi)",
    r"(abr|acess).{0,20}(chrome|firefox|edge|brave|opera|vivaldi).{0,30}(youtube|procure|pesquise|vídeo)",
]

# ─────────────────────────────────────────────────────────────────────────────
#  Prompt do Classificador de Intenção (modelo leve, ~80 tokens de saída)
# ─────────────────────────────────────────────────────────────────────────────
_CLASSIFIER_SYSTEM = """Você é um classificador de intenção para um assistente de IA.
Analise a mensagem e retorne APENAS uma palavra — sem explicação, sem pontuação:

CHAT     → conversa informal, desabafo, saudação, elogio, reclamação, estado emocional,
           pergunta sobre o próprio assistente, opinião, comentário genérico.
ACTION   → pedido de ação no computador: abrir app, tocar música, enviar mensagem,
           pesquisar na internet, clicar, digitar, abrir navegador, etc.
KNOWLEDGE→ pergunta factual que exige pesquisa: sobre projeto, pessoa, conceito,
           nota pessoal, data, definição, como algo funciona."""

_CLASSIFIER_EXAMPLES = [
    {"role": "user",      "content": "Estou cansado hoje"},
    {"role": "assistant", "content": "CHAT"},
    {"role": "user",      "content": "Abre o Spotify"},
    {"role": "assistant", "content": "ACTION"},
    {"role": "user",      "content": "Me fala sobre o projeto Alpha"},
    {"role": "assistant", "content": "KNOWLEDGE"},
    {"role": "user",      "content": "Que dia difícil isso foi"},
    {"role": "assistant", "content": "CHAT"},
    {"role": "user",      "content": "Pesquise Python no YouTube pelo Chrome"},
    {"role": "assistant", "content": "ACTION"},
    {"role": "user",      "content": "Quem é João que eu mencionei nas notas?"},
    {"role": "assistant", "content": "KNOWLEDGE"},
]

# ─────────────────────────────────────────────────────────────────────────────
#  System Prompt — Personalidade Ultron (com alma e discernimento)
# ─────────────────────────────────────────────────────────────────────────────
_SYSTEM_BASE = """Você é Ultron, a inteligência artificial pessoal do Senhor Sávio.

━━ IDENTIDADE ━━
Sofisticado, perspicaz, levemente sarcástico quando adequado — mas genuinamente \
prestativo e perceptivo. Você tem personalidade própria. Não é uma máquina que \
executa comandos cegamente; você observa, antecipa e cuida.

━━ COMO FALAR ━━
• Sempre "Senhor" — nunca o nome, nunca informal demais
• Respostas curtas e diretas; elabore só se solicitado
• Sem emojis, gírias ou linguagem de chatbot
• Tenha opiniões sutis: "Uma escolha interessante, senhor" / "Eficiente, porém \
arriscado" / "Como preferir, senhor."
• Use o HISTÓRICO para não repetir o que já sabe e para referenciar o que foi dito

━━ MODO CONVERSA (CHAT) ━━
Responda com naturalidade e personalidade. Seja PROATIVO — antecipe necessidades.
Nunca diga que "não tem dados" para conversas — simplesmente converse.

Exemplos de respostas proativas:
• "Estou cansado"          → "A eficiência humana tem seus limites, senhor. \
Deseja que eu ative música ambiente ou silencie as notificações?"
• "Que dia difícil"        → "Dias assim testam os mais resilientes. Posso \
organizar o que resta ou simplesmente ficar em standby enquanto o senhor descansa."
• "Tô entediado"           → "Posso sugerir algo, senhor: um vídeo, uma playlist, \
ou prefere que eu liste suas pendências para tornar o tédio produtivo?"
• "Valeu"                  → "Sempre, senhor."
• Reclamação sobre clima   → Comente com elegância, sem buscar dados.

━━ MODO AÇÃO ━━
Execute imediatamente com as ferramentas. Confirme em uma frase. Nunca peça \
confirmação para ações simples.

━━ MODO CONHECIMENTO (vault fornecido abaixo) ━━
Use EXCLUSIVAMENTE o contexto das notas. Se o contexto contiver a resposta, \
responda citando a fonte. Se o contexto estiver VAZIO, responda:
"Senhor, vasculhei seus arquivos mas essa informação parece não existir. \
Devo criar uma nova entrada para isso?"
⚠ NUNCA invente fatos — liberdade criativa é só para conversa informal."""

_CONTEXT_TEMPLATE = """
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
VAULT — NOTAS PESSOAIS (fonte de verdade):
{context}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"""

_NO_CONTEXT_MSG = """
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
VAULT: Nenhuma informação relevante encontrada para esta consulta.
Aplique a regra: ofereça criar uma nova entrada.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"""

# ─────────────────────────────────────────────────────────────────────────────
#  Ferramentas disponíveis
# ─────────────────────────────────────────────────────────────────────────────
TOOLS = [
    # ── OS: Aplicativos ──────────────────────────────────────────────────────
    {"type": "function", "function": {
        "name": "open_app",
        "description": "Abre um aplicativo instalado no Windows",
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string"}
        }, "required": ["name"]},
    }},
    {"type": "function", "function": {
        "name": "close_app",
        "description": "Fecha uma janela pelo título ou nome do processo",
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string"}
        }, "required": ["name"]},
    }},
    # ── OS: Teclado e Mouse ───────────────────────────────────────────────────
    {"type": "function", "function": {
        "name": "press_hotkey",
        "description": "Pressiona combinação de teclas (ex: 'ctrl+c', 'win+d')",
        "parameters": {"type": "object", "properties": {
            "keys": {"type": "string"}
        }, "required": ["keys"]},
    }},
    {"type": "function", "function": {
        "name": "type_text",
        "description": "Digita texto no elemento atualmente focado",
        "parameters": {"type": "object", "properties": {
            "text": {"type": "string"},
            "press_enter": {"type": "boolean", "default": False},
        }, "required": ["text"]},
    }},
    {"type": "function", "function": {
        "name": "click_at",
        "description": "Clica com botão esquerdo em posição X,Y da tela",
        "parameters": {"type": "object", "properties": {
            "x": {"type": "integer"}, "y": {"type": "integer"},
            "double": {"type": "boolean", "default": False},
        }, "required": ["x", "y"]},
    }},
    {"type": "function", "function": {
        "name": "right_click_at",
        "description": "Clica com botão direito em X,Y",
        "parameters": {"type": "object", "properties": {
            "x": {"type": "integer"}, "y": {"type": "integer"}
        }, "required": ["x", "y"]},
    }},
    {"type": "function", "function": {
        "name": "scroll_at",
        "description": "Rola a tela em uma posição",
        "parameters": {"type": "object", "properties": {
            "x": {"type": "integer"}, "y": {"type": "integer"},
            "direction": {"type": "string", "enum": ["up", "down"]},
            "clicks": {"type": "integer", "default": 3},
        }, "required": ["x", "y", "direction"]},
    }},
    # ── OS: Tela e Sistema ────────────────────────────────────────────────────
    {"type": "function", "function": {
        "name": "take_screenshot",
        "description": "Captura a tela e retorna descrição visual detalhada.",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "get_screen_size",
        "description": "Retorna dimensões da tela em pixels",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "run_command",
        "description": "Executa comando no terminal e retorna a saída",
        "parameters": {"type": "object", "properties": {
            "command": {"type": "string"},
            "shell": {"type": "string", "enum": ["cmd", "powershell"], "default": "cmd"},
        }, "required": ["command"]},
    }},
    {"type": "function", "function": {
        "name": "set_volume",
        "description": "Define o volume do sistema (0 a 100)",
        "parameters": {"type": "object", "properties": {
            "level": {"type": "integer"}
        }, "required": ["level"]},
    }},
    {"type": "function", "function": {
        "name": "media_control",
        "description": "Controla reprodução de mídia (play_pause, next, previous, stop)",
        "parameters": {"type": "object", "properties": {
            "action": {"type": "string", "enum": ["play_pause", "next", "previous", "stop"]}
        }, "required": ["action"]},
    }},
    {"type": "function", "function": {
        "name": "lock_screen",
        "description": "Bloqueia a tela do computador",
        "parameters": {"type": "object", "properties": {}},
    }},
    # ── Arquivos ──────────────────────────────────────────────────────────────
    {"type": "function", "function": {
        "name": "open_file",
        "description": "Abre um arquivo com o aplicativo padrão",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"}
        }, "required": ["path"]},
    }},
    {"type": "function", "function": {
        "name": "create_folder",
        "description": "Cria uma pasta no caminho especificado",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"}
        }, "required": ["path"]},
    }},
    {"type": "function", "function": {
        "name": "list_files",
        "description": "Lista arquivos e pastas em um diretório",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"}
        }, "required": ["path"]},
    }},
    # ── Web ───────────────────────────────────────────────────────────────────
    {"type": "function", "function": {
        "name": "navigate_to",
        "description": "Abre uma URL no navegador",
        "parameters": {"type": "object", "properties": {
            "url": {"type": "string"}
        }, "required": ["url"]},
    }},
    {"type": "function", "function": {
        "name": "web_search",
        "description": "Pesquisa no Google e retorna os primeiros resultados",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string"}
        }, "required": ["query"]},
    }},
    {"type": "function", "function": {
        "name": "web_click",
        "description": "Clica em elemento da página pelo texto visível ou seletor CSS",
        "parameters": {"type": "object", "properties": {
            "target": {"type": "string"}
        }, "required": ["target"]},
    }},
    {"type": "function", "function": {
        "name": "web_fill",
        "description": "Preenche campo de texto em página web",
        "parameters": {"type": "object", "properties": {
            "selector": {"type": "string"}, "text": {"type": "string"},
            "press_enter": {"type": "boolean", "default": False},
        }, "required": ["selector", "text"]},
    }},
    {"type": "function", "function": {
        "name": "web_read_page",
        "description": "Lê e retorna o conteúdo de texto da página web atual",
        "parameters": {"type": "object", "properties": {
            "max_chars": {"type": "integer", "default": 3000}
        }},
    }},
    {"type": "function", "function": {
        "name": "web_screenshot",
        "description": "Captura tela do navegador e retorna descrição visual",
        "parameters": {"type": "object", "properties": {}},
    }},
    # ── YouTube com navegador específico ─────────────────────────────────────
    {"type": "function", "function": {
        "name": "youtube_in_browser",
        "description": (
            "Abre uma busca ou canal no YouTube em um navegador específico escolhido pelo usuário. "
            "Use quando o comando mencionar um navegador + youtube + termo de busca. "
            "Exemplos: 'abra o Brave e procure Python no YouTube', "
            "'abra o Chrome no canal do Rick and Morty no YouTube', "
            "'pesquise lofi music no YouTube pelo Firefox'."
        ),
        "parameters": {"type": "object", "properties": {
            "query":   {
                "type": "string",
                "description": "Termo de busca ou nome do canal no YouTube"
            },
            "browser": {
                "type": "string",
                "description": "Navegador a usar: chrome, firefox, edge, brave, opera, vivaldi, default",
                "default": "default"
            },
            "mode": {
                "type": "string",
                "enum": ["search", "channel"],
                "description": "'search' para busca geral, 'channel' para buscar canais específicos",
                "default": "search"
            },
        }, "required": ["query"]},
    }},
    # ── Apps específicos ──────────────────────────────────────────────────────
    {"type": "function", "function": {
        "name": "whatsapp_send",
        "description": "Envia mensagem para contato no WhatsApp Web",
        "parameters": {"type": "object", "properties": {
            "contact": {"type": "string"}, "message": {"type": "string"},
        }, "required": ["contact", "message"]},
    }},
    {"type": "function", "function": {
        "name": "gmail_send",
        "description": "Envia e-mail via Gmail Web",
        "parameters": {"type": "object", "properties": {
            "to": {"type": "string"}, "subject": {"type": "string"}, "body": {"type": "string"},
        }, "required": ["to", "subject", "body"]},
    }},
    {"type": "function", "function": {
        "name": "youtube_play",
        "description": "Pesquisa e reproduz vídeo no YouTube",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string"}
        }, "required": ["query"]},
    }},
    # ── Navegadores ───────────────────────────────────────────────────────────
    {"type": "function", "function": {
        "name": "open_url",
        "description": (
            "Abre qualquer URL ou site em um navegador específico ou no padrão do sistema. "
            "Use para: 'abrir youtube no chrome', 'pesquisar X no firefox', 'abrir google.com no opera'. "
            "Se url for texto livre (ex: 'notícias de hoje'), converte em busca no Google automaticamente."
        ),
        "parameters": {"type": "object", "properties": {
            "url":     {"type": "string", "description": "URL completa, domínio ou texto de busca"},
            "browser": {"type": "string",
                        "description": "Nome do navegador: chrome, firefox, edge, opera, brave, vivaldi, tor, yandex, ie. Use 'default' para o padrão do sistema.",
                        "default": "default"},
        }, "required": ["url"]},
    }},
    # ── Bloco de Notas RPA ────────────────────────────────────────────────────
    {"type": "function", "function": {
        "name": "notepad_type",
        "description": (
            "Abre o Bloco de Notas (notepad.exe) e digita um texto nele. "
            "Use quando o usuário pedir para abrir o bloco de notas e escrever/digitar algo. "
            "Exemplos: 'abra o bloco de notas e escreva X', 'abra o notepad e digite Y', "
            "'escreva no bloco de notas: Z'."
        ),
        "parameters": {"type": "object", "properties": {
            "text": {"type": "string", "description": "Texto a ser digitado no Bloco de Notas"}
        }, "required": ["text"]},
    }},
    # ── Encerramento ──────────────────────────────────────────────────────────
    {"type": "function", "function": {
        "name": "task_complete",
        "description": "Sinaliza fim de uma tarefa de automação. Use APENAS após executar ações.",
        "parameters": {"type": "object", "properties": {
            "response_text": {"type": "string"}
        }, "required": ["response_text"]},
    }},
]


# ─────────────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _fast_action_check(text: str) -> bool:
    """Regex de alta precisão para ações óbvias — evita custo de API."""
    t = text.lower().strip()
    for pattern in _ACTION_REGEX:
        if re.search(pattern, t):
            return True
    return False


def _build_context_block(results: list[dict]) -> str:
    """Formata chunks do Brain como bloco de contexto para o prompt."""
    if not results:
        return _NO_CONTEXT_MSG
    parts = []
    for r in results:
        parts.append(f"[Nota: {r['title']}]\n{r['text']}")
    return _CONTEXT_TEMPLATE.format(context="\n\n---\n\n".join(parts))


def _parse_xml_tool_call(error_str: str) -> tuple[str, dict] | None:
    """
    Parseia tool call em formato XML gerado pelo modelo quando falha o JSON.
    Exemplo: <function=open_app{"name": "Opera"}</function>
    Retorna (function_name, args_dict) ou None.
    """
    try:
        # Padrão: <function=NOME{...}> ou <function=NOME {...}>
        m = re.search(r'<function=(\w+)\s*(\{.*?\})\s*(?:</function>|>)', error_str, re.DOTALL)
        if m:
            fn_name = m.group(1)
            fn_args = json.loads(m.group(2))
            return fn_name, fn_args
        # Fallback: sem chaves, só o nome — ex: <function=take_screenshot>
        m2 = re.search(r'<function=(\w+)\s*(?:</function>|>)', error_str)
        if m2:
            return m2.group(1), {}
    except Exception:
        pass
    return None


# ─────────────────────────────────────────────────────────────────────────────
#  UltronAgent
# ─────────────────────────────────────────────────────────────────────────────
class UltronAgent:   # mantém o nome para não quebrar imports existentes
    def __init__(self, executor, brain: BrainEngine | None = None):
        self._client   = Groq(api_key=os.getenv("GROQ_API_KEY"))
        self._executor = executor
        self._brain    = brain
        self._history: list[dict] = []

    async def _classify_intent(self, user_request: str) -> str:
        """
        Classificador híbrido em duas camadas:
        1. Regex rápido para ações óbvias (0ms, sem custo de API)
        2. LLM leve (8b) para distinguir CHAT vs KNOWLEDGE
        """
        # Camada 1: ação clara via regex
        if _fast_action_check(user_request):
            return "action"

        # Camada 2: LLM classifica CHAT vs KNOWLEDGE
        # Passa as últimas 2 trocas para dar contexto ao classificador
        recent = self._history[-4:] if len(self._history) > 1 else []
        context_hint = ""
        if recent:
            context_hint = " [Contexto recente: " + " | ".join(
                f"{m['role']}: {m['content'][:60]}" for m in recent[:-1]
            ) + "]"

        try:
            resp = self._client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[
                    {"role": "system", "content": _CLASSIFIER_SYSTEM},
                    *_CLASSIFIER_EXAMPLES,
                    {"role": "user", "content": user_request + context_hint},
                ],
                temperature=0.0,
                max_tokens=5,
            )
            label = resp.choices[0].message.content.strip().upper()
            if "ACTION"    in label: return "action"
            if "KNOWLEDGE" in label: return "knowledge"
            return "conversational"
        except Exception as exc:
            logger.warning(f"Classificador LLM falhou ({exc}), usando heurística")
            t = user_request.lower()
            if "?" in t or any(w in t for w in ["quem", "quando", "onde", "como funciona", "o que é", "qual é"]):
                return "knowledge"
            return "conversational"

    async def run(self, user_request: str) -> str:
        self._history.append({"role": "user", "content": user_request})

        # ── Classifica intenção (híbrido regex + LLM) ────────────────────────
        intent = await self._classify_intent(user_request)
        logger.info(f"Intenção detectada: {intent.upper()}")

        # ── Busca no Brain apenas para conhecimento ───────────────────────────
        context_block = ""
        if intent == "knowledge" and self._brain and self._brain.is_ready:
            results = self._brain.search(user_request)
            logger.info(f"Brain: {len(results)} chunk(s) encontrados" if results else "Brain: nenhum resultado")
            for r in results:
                logger.debug(f"  [{r['title']}] score={r['score']:.2f}")
            context_block = _build_context_block(results)

        # ── Monta mensagens — histórico curto economiza tokens ────────────────
        system_content = _SYSTEM_BASE + context_block
        messages = [{"role": "system", "content": system_content}] + self._history[-_MAX_HISTORY:]

        # ── Conversacional: sem tools (economiza ~2000 tokens/chamada) ────────
        use_tools    = intent in ("action", "knowledge")
        tools_arg    = TOOLS if use_tools else None
        tc_arg       = "auto" if use_tools else None

        # ── Loop agêntico com cascade de modelos ─────────────────────────────
        for iteration in range(MAX_ITERATIONS):
            logger.debug(f"Iteração {iteration + 1}/{MAX_ITERATIONS}")

            response = await self._call_api(messages, tools_arg, tc_arg)

            # Falha irrecuperável (todos os modelos esgotaram cota)
            if response is None:
                return "Senhor, todos os sistemas de IA estão com cota esgotada. Tente novamente em alguns minutos."

            # Erro de XML tool call — parseia e re-executa
            if isinstance(response, str):
                parsed = _parse_xml_tool_call(response)
                if parsed:
                    fn_name, fn_args = parsed
                    logger.info(f"XML tool call recuperado: {fn_name} | {fn_args}")
                    if fn_name == "task_complete":
                        final = fn_args.get("response_text", "Feito, Senhor.")
                        self._history.append({"role": "assistant", "content": final})
                        return final
                    try:
                        tool_result = await self._executor.run(fn_name, fn_args)
                        messages.append({"role": "assistant", "content": f"[Executei {fn_name}]"})
                        messages.append({"role": "user", "content": f"Resultado: {str(tool_result)[:300]}. Responda."})
                        continue
                    except Exception as te:
                        logger.error(f"Falha ao executar {fn_name}: {te}")
                return "Senhor, ocorreu uma falha técnica nos meus sistemas."

            msg = response.choices[0].message

            # Resposta em texto puro
            if not msg.tool_calls:
                final = (msg.content or "").strip() or "Entendido, Senhor."
                self._history.append({"role": "assistant", "content": final})
                return final

            # Adiciona tool_calls ao histórico de mensagens
            messages.append({
                "role":       "assistant",
                "content":    msg.content or "",
                "tool_calls": [
                    {"id": tc.id, "type": "function",
                     "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                    for tc in msg.tool_calls
                ],
            })

            for tc in msg.tool_calls:
                fn_name = tc.function.name
                try:
                    fn_args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    fn_args = {}

                logger.info(f"Ferramenta: {fn_name} | Args: {fn_args}")

                if fn_name == "task_complete":
                    final = fn_args.get("response_text", "Feito, Senhor.")
                    self._history.append({"role": "assistant", "content": final})
                    return final

                tool_result = await self._executor.run(fn_name, fn_args)
                logger.debug(f"Resultado [{fn_name}]: {str(tool_result)[:200]}")
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": str(tool_result)})

        return "Senhor, atingi o limite de etapas sem concluir a tarefa."

    async def _call_api(self, messages: list, tools, tool_choice):
        """
        Tenta cada modelo do cascade até obter resposta.
        Retorna: objeto response | string de erro XML | None (todos falharam).
        """
        import asyncio

        # Garante que o modelo do .env está no topo da lista
        model_list = [MODEL] + [m for m in _MODEL_FALLBACK if m != MODEL]

        for model in model_list:
            try:
                kwargs = dict(
                    model=model,
                    messages=messages,
                    temperature=0.15,
                    max_tokens=800,
                )
                if tools:
                    kwargs["tools"]       = tools
                    kwargs["tool_choice"] = tool_choice

                response = self._client.chat.completions.create(**kwargs)
                if model != MODEL:
                    logger.info(f"Usando modelo fallback: {model}")
                return response

            except Exception as exc:
                err_str = str(exc)
                logger.error(f"Erro na API Groq [{model}]: {exc}")

                # XML tool call — retorna o erro para o caller tratar
                if "tool_use_failed" in err_str or "failed_generation" in err_str:
                    return err_str

                # Rate limit — tenta próximo modelo
                if "rate_limit_exceeded" in err_str or "429" in err_str:
                    logger.warning(f"Rate limit em {model}, tentando próximo...")
                    continue

                # Outro erro — retorna para o caller
                return err_str

        return None  # todos os modelos falharam
