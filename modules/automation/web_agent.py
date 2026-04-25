"""
Agente de automação web geral via Playwright.
Mantém uma única aba/contexto compartilhado por toda a sessão.

Operações:
- navigate_to(url)
- web_search(query)       → Google → retorna lista de resultados
- web_click(target)       → por texto visível ou seletor CSS
- web_fill(selector, text)
- web_read_page()         → extrai texto limpo da página
- web_screenshot()        → GPT-4o Vision na página atual
- youtube_play(query)     → pesquisa e abre o primeiro vídeo
"""
import asyncio
import base64
import io
import os
import re

from loguru import logger
from groq import Groq
from playwright.async_api import (
    BrowserContext,
    Page,
    TimeoutError as PWTimeout,
    async_playwright,
)

from .browser import BrowserSession

_groq = Groq(api_key=os.getenv("GROQ_API_KEY"))
DEFAULT_TIMEOUT = 20_000   # ms


class WebAgent:
    """Singleton que mantém uma aba aberta durante a sessão."""

    _instance: "WebAgent | None" = None

    def __init__(self):
        self._session = BrowserSession(headless=False)
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._started = False

    @classmethod
    def get(cls) -> "WebAgent":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ── Ciclo de vida ────────────────────────────────────────────────────────

    async def _ensure_started(self):
        if not self._started:
            self._context = await self._session.__aenter__()
            pages = self._context.pages
            self._page = pages[0] if pages else await self._context.new_page()
            self._started = True

    async def close(self):
        if self._started:
            await self._session.__aexit__(None, None, None)
            self._started = False
            WebAgent._instance = None

    # ── Navegação ────────────────────────────────────────────────────────────

    async def navigate_to(self, url: str) -> str:
        await self._ensure_started()
        try:
            await self._page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            title = await self._page.title()
            return f"Página aberta: '{title}' — {self._page.url}"
        except PWTimeout:
            return f"Timeout ao carregar '{url}'. A página pode estar lenta."
        except Exception as exc:
            return f"Erro ao navegar para '{url}': {exc}"

    # ── Pesquisa Google ───────────────────────────────────────────────────────

    async def web_search(self, query: str) -> str:
        await self._ensure_started()
        search_url = f"https://www.google.com/search?q={query.replace(' ', '+')}&hl=pt-BR"
        try:
            await self._page.goto(search_url, wait_until="domcontentloaded")
            await asyncio.sleep(1)

            # Extrai resultados orgânicos
            results = await self._page.evaluate("""() => {
                const items = [];
                document.querySelectorAll('div.g').forEach((el, i) => {
                    if (i >= 5) return;
                    const title = el.querySelector('h3')?.innerText || '';
                    const url   = el.querySelector('a')?.href || '';
                    const desc  = el.querySelector('[data-sncf], .VwiC3b')?.innerText || '';
                    if (title) items.push({ title, url, desc });
                });
                return items;
            }""")

            if not results:
                return "Nenhum resultado encontrado."

            lines = []
            for i, r in enumerate(results, 1):
                lines.append(f"{i}. {r['title']}\n   {r['url']}\n   {r['desc'][:150]}")
            return "\n\n".join(lines)
        except Exception as exc:
            return f"Erro na pesquisa: {exc}"

    # ── Interação com a página ────────────────────────────────────────────────

    async def web_click(self, target: str) -> str:
        await self._ensure_started()
        try:
            # Tenta por texto visível primeiro
            locator = self._page.get_by_text(target, exact=False).first
            await locator.wait_for(timeout=5_000)
            await locator.click()
            return f"Clicou em elemento com texto '{target}'."
        except PWTimeout:
            pass

        try:
            # Fallback: trata como seletor CSS/role
            await self._page.click(target, timeout=DEFAULT_TIMEOUT)
            return f"Clicou no seletor '{target}'."
        except Exception as exc:
            return f"Não encontrei o elemento '{target}': {exc}"

    async def web_fill(self, selector: str, text: str, press_enter: bool = False) -> str:
        await self._ensure_started()
        try:
            # Tenta pelo placeholder/label primeiro
            loc = self._page.get_by_placeholder(selector)
            count = await loc.count()
            if count == 0:
                loc = self._page.locator(selector)

            await loc.first.fill(text)
            if press_enter:
                await loc.first.press("Enter")
            return f"Campo preenchido com '{text}'."
        except Exception as exc:
            return f"Erro ao preencher campo '{selector}': {exc}"

    # ── Leitura ───────────────────────────────────────────────────────────────

    async def web_read_page(self, max_chars: int = 3000) -> str:
        await self._ensure_started()
        try:
            text = await self._page.evaluate("""() => {
                const el = document.body;
                return el ? el.innerText : '';
            }""")
            text = re.sub(r'\n{3,}', '\n\n', text).strip()
            return text[:max_chars] if len(text) > max_chars else text
        except Exception as exc:
            return f"Erro ao ler página: {exc}"

    async def web_screenshot(self) -> str:
        await self._ensure_started()
        try:
            png_bytes = await self._page.screenshot(full_page=False)
            b64 = base64.b64encode(png_bytes).decode()

            response = _groq.chat.completions.create(
                model="meta-llama/llama-4-scout-17b-16e-instruct",
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "Descreva detalhadamente o que está sendo exibido nesta captura de tela do navegador. "
                                "Inclua: URL/título da página, elementos interativos visíveis (botões, campos, links), "
                                "conteúdo principal e posição aproximada de elementos relevantes. "
                                "Seja técnico e específico para auxiliar automação."
                            )
                        },
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                    ],
                }],
                max_tokens=1000,
            )
            return response.choices[0].message.content
        except Exception as exc:
            return f"Erro ao capturar tela do navegador: {exc}"

    # ── YouTube ───────────────────────────────────────────────────────────────

    async def youtube_play(self, query: str) -> str:
        await self._ensure_started()
        search_url = f"https://www.youtube.com/results?search_query={query.replace(' ', '+')}"
        try:
            await self._page.goto(search_url, wait_until="domcontentloaded")
            await asyncio.sleep(2)

            # Clica no primeiro resultado de vídeo
            first_video = self._page.locator("ytd-video-renderer a#video-title").first
            await first_video.wait_for(timeout=DEFAULT_TIMEOUT)
            title = await first_video.get_attribute("title") or "vídeo"
            await first_video.click()
            await asyncio.sleep(1)
            return f"Reproduzindo: '{title}' no YouTube."
        except Exception as exc:
            return f"Erro ao reproduzir '{query}' no YouTube: {exc}"
