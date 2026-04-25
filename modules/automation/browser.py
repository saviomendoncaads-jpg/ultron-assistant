"""
Gerenciador base do Playwright com persistência de sessão.
Salva cookies e localStorage em disco para não exigir login a cada execução.
"""
import os
import json
from pathlib import Path
from playwright.async_api import async_playwright, BrowserContext, Browser, Playwright
from loguru import logger

SESSION_PATH = Path(os.getenv("BROWSER_SESSION_PATH", ".browser_session"))
CHROME_EXEC = os.getenv("CHROME_EXECUTABLE_PATH", "")


class BrowserSession:
    """Context manager que fornece um BrowserContext com sessão persistente."""

    def __init__(self, headless: bool = False):
        self.headless = headless
        self._pw: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None

    async def __aenter__(self) -> BrowserContext:
        SESSION_PATH.mkdir(parents=True, exist_ok=True)
        state_file = SESSION_PATH / "state.json"

        self._pw = await async_playwright().start()

        launch_kwargs: dict = {
            "headless": self.headless,
            "args": [
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
            ],
        }

        if CHROME_EXEC:
            launch_kwargs["executable_path"] = CHROME_EXEC
            self._browser = await self._pw.chromium.launch(**launch_kwargs)
        else:
            self._browser = await self._pw.chromium.launch(**launch_kwargs)

        context_kwargs: dict = {
            "viewport": {"width": 1280, "height": 800},
            "user_agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        }

        if state_file.exists():
            logger.info("Carregando sessão salva do navegador.")
            context_kwargs["storage_state"] = str(state_file)

        self._context = await self._browser.new_context(**context_kwargs)
        return self._context

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._context:
            state_file = SESSION_PATH / "state.json"
            try:
                await self._context.storage_state(path=str(state_file))
                logger.info("Sessão do navegador salva com sucesso.")
            except Exception as exc:
                logger.warning(f"Não foi possível salvar a sessão: {exc}")
            await self._context.close()

        if self._browser:
            await self._browser.close()

        if self._pw:
            await self._pw.stop()
