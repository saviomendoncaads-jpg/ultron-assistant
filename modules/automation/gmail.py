"""
Automação do Gmail Web via Playwright.

Fluxo de envio:
  1. Abre Gmail (reutiliza sessão salva — sem login se já autenticado)
  2. Clica em "Escrever"
  3. Preenche destinatário, assunto e corpo
  4. Envia

Sessão persistida via BrowserSession (mesmo storage_state do WhatsApp, etc.)
"""
import asyncio
from loguru import logger
from playwright.async_api import Page, TimeoutError as PWTimeout
from .web_agent import WebAgent

GMAIL_URL = "https://mail.google.com/"
DEFAULT_TIMEOUT = 20_000


class GmailAutomation:
    """Usa a instância compartilhada do WebAgent para operar o Gmail."""

    def __init__(self):
        self._agent = WebAgent.get()

    async def send_email(self, to: str, subject: str, body: str) -> str:
        page = await self._get_gmail_page()

        # Abre compose
        await self._click_compose(page)

        # Preenche destinatário
        to_field = page.locator('textarea[name="to"], input[aria-label*="Para"]').first
        await to_field.wait_for(timeout=DEFAULT_TIMEOUT)
        await to_field.fill(to)
        await to_field.press("Tab")
        await asyncio.sleep(0.3)

        # Assunto
        subj_field = page.locator('input[name="subjectbox"], input[aria-label*="Assunto"]').first
        await subj_field.fill(subject)
        await subj_field.press("Tab")
        await asyncio.sleep(0.2)

        # Corpo
        body_field = page.locator('div[aria-label*="Corpo"], div[role="textbox"].Am').first
        try:
            await body_field.wait_for(timeout=5_000)
            await body_field.click()
            await body_field.type(body, delay=30)
        except PWTimeout:
            # Fallback: Tab para o campo e digita
            import pyautogui
            pyautogui.write(body, interval=0.03)

        await asyncio.sleep(0.3)

        # Envia (atalho Ctrl+Enter ou botão)
        try:
            send_btn = page.locator('div[aria-label*="Enviar"], div[aria-label*="Send"]').first
            await send_btn.wait_for(timeout=5_000)
            await send_btn.click()
        except PWTimeout:
            from playwright.async_api import Page as _Page
            await page.keyboard.press("Control+Return")

        await asyncio.sleep(1)
        logger.info(f"E-mail enviado para '{to}'.")
        return f"E-mail enviado para {to} com assunto '{subject}'."

    async def _get_gmail_page(self) -> Page:
        await self._agent._ensure_started()
        page = self._agent._page

        if "mail.google.com" not in page.url:
            await page.goto(GMAIL_URL, wait_until="domcontentloaded")

        # Aguarda inbox carregar
        try:
            await page.wait_for_selector(
                'div[gh="cm"], div[role="navigation"]',
                timeout=DEFAULT_TIMEOUT
            )
        except PWTimeout:
            raise RuntimeError(
                "Gmail não carregou ou não está autenticado. "
                "Abra gmail.com manualmente para fazer login."
            )
        return page

    async def _click_compose(self, page: Page) -> None:
        try:
            btn = page.locator('div[gh="cm"]').first   # botão "Escrever"
            await btn.wait_for(timeout=DEFAULT_TIMEOUT)
            await btn.click()
            await asyncio.sleep(0.8)
        except PWTimeout:
            # Fallback: atalho de teclado 'c' para compose
            await page.keyboard.press("c")
            await asyncio.sleep(0.8)
