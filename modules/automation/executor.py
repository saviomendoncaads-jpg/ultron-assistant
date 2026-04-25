"""
Dispatcher central de ferramentas.

Recebe (fn_name, fn_args) do agente LLM e roteia para o módulo correto.
Para adicionar nova ferramenta: implemente a função no módulo adequado
e adicione uma entrada em _DISPATCH abaixo.
"""
import json
from pathlib import Path
from loguru import logger

from . import os_control as os_ctrl
from .web_agent import WebAgent
from .whatsapp import WhatsAppAutomation
from .gmail import GmailAutomation
from .notepad_automation import open_notepad_and_type
from .web_automation import youtube_in_browser
from modules.obsidian import ObsidianBrain


def _load_contacts() -> dict:
    path = Path(__file__).parent.parent.parent / "contacts.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


class ActionExecutor:
    """Singleton que despacha chamadas de ferramenta para os módulos corretos."""

    def __init__(self):
        self._contacts = _load_contacts()
        self._web = WebAgent.get()
        self._obsidian = ObsidianBrain.get()

    def _resolve_contact(self, alias: str) -> str:
        return self._contacts.get(alias.lower().strip(), alias)

    async def run(self, fn_name: str, args: dict) -> str:
        logger.debug(f"Executor → {fn_name}({args})")
        try:
            return await self._dispatch(fn_name, args)
        except Exception as exc:
            logger.exception(f"Erro ao executar '{fn_name}': {exc}")
            return f"Erro ao executar '{fn_name}': {exc}"

    async def _dispatch(self, fn: str, a: dict) -> str:
        # ── OS: Aplicativos ─────────────────────────────────────────────────
        if fn == "open_app":
            return os_ctrl.open_app(a["name"])

        if fn == "close_app":
            return os_ctrl.close_app(a["name"])

        # ── OS: Teclado e Mouse ──────────────────────────────────────────────
        if fn == "press_hotkey":
            return os_ctrl.press_hotkey(a["keys"])

        if fn == "type_text":
            return os_ctrl.type_text(a["text"], a.get("press_enter", False))

        if fn == "click_at":
            return os_ctrl.click_at(a["x"], a["y"], a.get("double", False))

        if fn == "right_click_at":
            return os_ctrl.right_click_at(a["x"], a["y"])

        if fn == "scroll_at":
            return os_ctrl.scroll_at(a["x"], a["y"], a["direction"], a.get("clicks", 3))

        # ── OS: Tela e Sistema ───────────────────────────────────────────────
        if fn == "take_screenshot":
            return await os_ctrl.take_screenshot()

        if fn == "get_screen_size":
            return os_ctrl.get_screen_size()

        if fn == "run_command":
            return os_ctrl.run_command(a["command"], a.get("shell", "cmd"))

        if fn == "set_volume":
            return os_ctrl.set_volume(a["level"])

        if fn == "media_control":
            return os_ctrl.media_control(a["action"])

        if fn == "lock_screen":
            return os_ctrl.lock_screen()

        # ── OS: Sistema de Arquivos ──────────────────────────────────────────
        if fn == "open_file":
            return os_ctrl.open_file(a["path"])

        if fn == "create_folder":
            return os_ctrl.create_folder(a["path"])

        if fn == "list_files":
            return os_ctrl.list_files(a["path"])

        # ── Navegadores: abrir URL em qualquer browser ───────────────────────
        if fn == "open_url":
            return os_ctrl.open_url(a["url"], a.get("browser", "default"))

        # ── Web: Navegação geral ─────────────────────────────────────────────
        if fn == "navigate_to":
            return await self._web.navigate_to(a["url"])

        if fn == "web_search":
            return await self._web.web_search(a["query"])

        if fn == "web_click":
            return await self._web.web_click(a["target"])

        if fn == "web_fill":
            return await self._web.web_fill(
                a["selector"], a["text"], a.get("press_enter", False)
            )

        if fn == "web_read_page":
            return await self._web.web_read_page(a.get("max_chars", 3000))

        if fn == "web_screenshot":
            return await self._web.web_screenshot()

        # ── Apps específicos ─────────────────────────────────────────────────
        if fn == "whatsapp_send":
            contact_alias = a["contact"]
            contact_name = self._resolve_contact(contact_alias)
            async with WhatsAppAutomation() as wa:
                return await wa.send_message(
                    contact_name=contact_name,
                    message=a["message"],
                )

        if fn == "gmail_send":
            gmail = GmailAutomation()
            return await gmail.send_email(
                to=a["to"],
                subject=a["subject"],
                body=a["body"],
            )

        if fn == "youtube_play":
            return await self._web.youtube_play(a["query"])

        if fn == "youtube_in_browser":
            return youtube_in_browser(
                query   = a["query"],
                browser = a.get("browser", "default"),
                mode    = a.get("mode", "search"),
            )

        # ── Obsidian Brain ───────────────────────────────────────────────────
        if fn == "consultar_obsidian":
            return self._obsidian.search(a["query"])

        if fn == "salvar_obsidian":
            return self._obsidian.salvar_nota(a["titulo"], a["conteudo"])

        # ── Bloco de Notas RPA ───────────────────────────────────────────────
        if fn == "notepad_type":
            return open_notepad_and_type(a["text"])

        return f"Ferramenta '{fn}' não implementada."

    async def cleanup(self):
        """Fecha o navegador ao encerrar o programa."""
        try:
            await self._web.close()
        except Exception:
            pass
