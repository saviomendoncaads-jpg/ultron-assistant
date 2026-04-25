# -*- coding: utf-8 -*-
"""
web_automation.py — Navegação Inteligente com YouTube e controle de browser.

Responsabilidades:
  - Construir URLs corretas para busca/canal do YouTube
  - Resolver o nome do navegador para o executável real
  - Abrir via subprocess (processo independente do assistente)
  - Fallback automático para o browser padrão do sistema
"""
from __future__ import annotations

import re
from urllib.parse import quote_plus
from loguru import logger

# Reutiliza toda a lógica de descoberta de caminhos já testada
from .os_control import open_url, _BROWSER_EXE

# ── Mapeamento de nomes por voz → chave interna ───────────────────────────────
_VOICE_TO_BROWSER: dict[str, str] = {
    # Chrome
    "chrome": "chrome", "google chrome": "chrome", "crome": "chrome",
    # Firefox
    "firefox": "firefox", "mozilla": "firefox", "fire fox": "firefox",
    # Edge
    "edge": "edge", "microsoft edge": "edge",
    # Brave
    "brave": "brave", "brave browser": "brave",
    # Opera
    "opera": "opera", "opera gx": "opera", "operagx": "opera",
    # Outros
    "vivaldi": "vivaldi", "yandex": "yandex", "tor": "tor",
    "ie": "ie", "internet explorer": "ie",
}

# Nomes amigáveis para o feedback de voz
_DISPLAY_NAME: dict[str, str] = {
    "chrome":   "Google Chrome",
    "firefox":  "Mozilla Firefox",
    "edge":     "Microsoft Edge",
    "brave":    "Brave",
    "opera":    "Opera",
    "vivaldi":  "Vivaldi",
    "yandex":   "Yandex Browser",
    "tor":      "Tor Browser",
    "ie":       "Internet Explorer",
    "default":  "navegador padrão",
}


def _resolve_browser(raw: str) -> tuple[str, str]:
    """
    Recebe nome bruto (ex: 'brave', 'google chrome') e retorna
    (chave_interna, nome_exibição).
    """
    key = _VOICE_TO_BROWSER.get(raw.lower().strip(), raw.lower().strip())
    display = _DISPLAY_NAME.get(key, key.title())
    return key, display


def _build_youtube_url(query: str, mode: str = "search") -> str:
    """
    Constrói a URL correta do YouTube.

    mode="search"  → /results?search_query=termo+formatado
    mode="channel" → /results?search_query=canal+oficial  (YouTube não tem URL direta
                      de canal por nome, então busca pelo nome do canal)
    """
    query = query.strip()
    encoded = quote_plus(query)          # espaços → '+', caracteres especiais escapados

    if mode == "channel":
        # Pesquisa o canal pelo nome — YouTube redireciona automaticamente
        return f"https://www.youtube.com/results?search_query={encoded}&sp=EgIQAg%253D%253D"
    else:
        return f"https://www.youtube.com/results?search_query={encoded}"


def youtube_in_browser(query: str, browser: str = "default", mode: str = "search") -> str:
    """
    Abre uma busca do YouTube no navegador especificado.

    Args:
        query:   Termo de busca ou nome do canal
        browser: Nome do navegador (chrome, brave, firefox, edge, opera, default)
        mode:    'search' para busca normal, 'channel' para busca de canais

    Returns:
        Mensagem de feedback para o TTS do Ultron.
    """
    browser_key, browser_display = _resolve_browser(browser)
    url = _build_youtube_url(query, mode)

    logger.info(f"YouTube → browser={browser_key}, mode={mode}, query={query!r}")
    logger.debug(f"URL gerada: {url}")

    # open_url já tem toda a lógica de path discovery + fallback
    result = open_url(url, browser_key)
    logger.debug(f"open_url retornou: {result}")

    # Feedback de voz estruturado conforme requisito
    return (
        f"Acessando o YouTube via {browser_display}. "
        f"Localizando os dados solicitados, senhor."
    )
