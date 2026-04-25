"""
Automação do WhatsApp Web via Playwright.

Fluxo:
  1. Abre/reutiliza aba com web.whatsapp.com
  2. Se sessão salva: já aparece logado (sem QR Code)
  3. Se não: aguarda o usuário escanear o QR Code (timeout de 60s)
  4. Busca o contato pelo nome
  5. Digita e envia a mensagem
  6. Salva a sessão para o próximo uso
"""
import asyncio
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type
from playwright.async_api import BrowserContext, Page, TimeoutError as PWTimeout
from loguru import logger
from .browser import BrowserSession

WA_URL = "https://web.whatsapp.com"
DEFAULT_TIMEOUT = 30_000   # ms
QR_TIMEOUT = 90_000        # ms — tempo para escanear o QR Code na primeira vez


class WhatsAppAutomation:
    """Encapsula operações no WhatsApp Web."""

    def __init__(self):
        self._session = BrowserSession(headless=False)
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    async def __aenter__(self) -> "WhatsAppAutomation":
        self._context = await self._session.__aenter__()
        return self

    async def __aexit__(self, *args):
        await self._session.__aexit__(*args)

    # ──────────────────────────────────────────────────────────────────────────
    # API pública
    # ──────────────────────────────────────────────────────────────────────────

    async def send_message(self, contact_name: str, message: str) -> str:
        """
        Envia mensagem para o contato e retorna texto de confirmação.
        Raises RuntimeError se o contato não for encontrado.
        """
        logger.info(f"WhatsApp: enviando para '{contact_name}': {message!r}")
        await self._open_whatsapp()
        await self._search_contact(contact_name)
        await self._type_and_send(message)
        return f"Tarefa concluída. Mensagem enviada para {contact_name}."

    # ──────────────────────────────────────────────────────────────────────────
    # Passos internos
    # ──────────────────────────────────────────────────────────────────────────

    async def _open_whatsapp(self) -> None:
        """Abre o WhatsApp Web e aguarda o carregamento (com ou sem QR Code)."""
        pages = self._context.pages
        self._page = pages[0] if pages else await self._context.new_page()

        current_url = self._page.url
        if "web.whatsapp.com" not in current_url:
            logger.info("Navegando para o WhatsApp Web...")
            await self._page.goto(WA_URL, wait_until="domcontentloaded")

        # Espera pela caixa de pesquisa (já logado) OU pelo QR Code
        try:
            await self._page.wait_for_selector(
                'div[data-testid="chat-list-search"]',
                timeout=DEFAULT_TIMEOUT,
            )
            logger.info("WhatsApp Web carregado e autenticado.")
        except PWTimeout:
            logger.warning("Caixa de pesquisa não encontrada. Verificando QR Code...")
            await self._handle_qr_code()

    async def _handle_qr_code(self) -> None:
        """Aguarda o usuário escanear o QR Code."""
        try:
            await self._page.wait_for_selector('canvas[aria-label="Scan me!"]',
                                                timeout=5_000)
            logger.warning(
                "QR Code detectado. Por favor, escaneie com seu celular. "
                f"Aguardando {QR_TIMEOUT // 1000}s..."
            )
            # Aguarda até estar autenticado (QR Code some e aparece a lista de chats)
            await self._page.wait_for_selector(
                'div[data-testid="chat-list-search"]',
                timeout=QR_TIMEOUT,
            )
            logger.info("Autenticação via QR Code concluída.")
        except PWTimeout as exc:
            raise RuntimeError(
                "Tempo esgotado aguardando o QR Code. "
                "Abra o WhatsApp Web manualmente para autenticar."
            ) from exc

    @retry(
        retry=retry_if_exception_type(RuntimeError),
        stop=stop_after_attempt(2),
        wait=wait_fixed(2),
    )
    async def _search_contact(self, contact_name: str) -> None:
        """Localiza o contato pelo nome usando a barra de pesquisa."""
        search_box = self._page.locator('div[data-testid="chat-list-search"]')
        await search_box.click()
        await search_box.fill("")
        await search_box.type(contact_name, delay=60)

        # Aguarda resultados aparecerem
        await asyncio.sleep(1.5)

        # Tenta clicar no primeiro resultado que contenha o nome
        contact_selector = (
            f'span[title="{contact_name}"], '
            f'span[data-testid="cell-frame-title"]:has-text("{contact_name}")'
        )
        try:
            contact = self._page.locator(contact_selector).first
            await contact.wait_for(timeout=DEFAULT_TIMEOUT)
            await contact.click()
            logger.info(f"Contato '{contact_name}' selecionado.")
        except PWTimeout:
            raise RuntimeError(
                f"Contato '{contact_name}' não encontrado no WhatsApp Web. "
                "Verifique o nome exato em contacts.json."
            )

    async def _type_and_send(self, message: str) -> None:
        """Digita a mensagem no campo de texto e pressiona Enter."""
        msg_box = self._page.locator(
            'div[data-testid="conversation-compose-box-input"]'
        )
        try:
            await msg_box.wait_for(timeout=DEFAULT_TIMEOUT)
        except PWTimeout as exc:
            raise RuntimeError("Campo de mensagem não encontrado.") from exc

        await msg_box.click()
        await msg_box.fill("")
        await msg_box.type(message, delay=40)

        # Aguarda brevemente e envia
        await asyncio.sleep(0.3)
        await msg_box.press("Enter")
        await asyncio.sleep(0.8)   # aguarda confirmação de envio

        logger.info("Mensagem enviada com sucesso.")
