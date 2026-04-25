"""
Controle do Sistema Operacional via PyAutoGUI, subprocess e Win32.

Cobre:
- Abrir/fechar aplicativos
- Mouse e teclado (click, hotkeys, type)
- Screenshots com análise via GPT-4o Vision
- Controle de volume (pycaw/win32)
- Sistema de arquivos
- Bloqueio de tela
- Comandos de shell
"""
import asyncio
import base64
import ctypes
import io
import os
import subprocess
from pathlib import Path

import pyautogui
import pygetwindow as gw
from groq import Groq
from loguru import logger
from PIL import Image
from tenacity import retry, stop_after_attempt, wait_fixed

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.15

_groq = Groq(api_key=os.getenv("GROQ_API_KEY"))

# ─── Mapa de nomes comuns → executável Windows ───────────────────────────────
APPS_MAP: dict[str, str] = {
    # ── Navegadores ──────────────────────────────────────────────────────────
    "chrome":            "chrome",
    "google chrome":     "chrome",
    "firefox":           "firefox",
    "mozilla":           "firefox",
    "mozilla firefox":   "firefox",
    "edge":              "msedge",
    "microsoft edge":    "msedge",
    "opera":             "opera",
    "opera gx":          "opera",
    "brave":             "brave",
    "brave browser":     "brave",
    "vivaldi":           "vivaldi",
    "tor":               "tor browser",
    "tor browser":       "tor browser",
    "internet explorer": "iexplore",
    "ie":                "iexplore",
    "safari":            "safari",
    "uc browser":        "ucbrowser",
    "waterfox":          "waterfox",
    "pale moon":         "palemoon",
    "palemoon":          "palemoon",
    "librewolf":         "librewolf",
    "yandex":            "browser",
    "yandex browser":    "browser",
    # ── Office ───────────────────────────────────────────────────────────────
    "word":              "winword",
    "excel":             "excel",
    "powerpoint":        "powerpnt",
    "outlook":           "outlook",
    # ── Sistema ──────────────────────────────────────────────────────────────
    "notepad":           "notepad",
    "bloco de notas":    "notepad",
    "calculadora":       "calc",
    "calculator":        "calc",
    "explorador":        "explorer",
    "explorer":          "explorer",
    "gerenciador de tarefas": "taskmgr",
    "taskmgr":           "taskmgr",
    "paint":             "mspaint",
    "terminal":          "cmd",
    "cmd":               "cmd",
    "powershell":        "powershell",
    # ── Desenvolvimento ───────────────────────────────────────────────────────
    "vs code":           "code",
    "vscode":            "code",
    "visual studio code":"code",
    # ── Comunicação / Redes Sociais ───────────────────────────────────────────
    "whatsapp":          "WhatsApp",
    "telegram":          "telegram",
    "discord":           "discord",
    "slack":             "slack",
    "skype":             "skype",
    "teams":             "teams",
    "zoom":              "zoom",
    # ── Mídia ─────────────────────────────────────────────────────────────────
    "spotify":           "spotify",
    "vlc":               "vlc",
    "obs":               "obs64",
    "photoshop":         "photoshop",
}

# ─── Mapa browser → executável com suporte a URL ──────────────────────────────
_BROWSER_EXE: dict[str, str] = {
    "chrome":       "chrome",
    "google chrome":"chrome",
    "firefox":      "firefox",
    "mozilla":      "firefox",
    "edge":         "msedge",
    "microsoft edge":"msedge",
    "opera":        "opera",
    "opera gx":     "opera",
    "brave":        "brave",
    "vivaldi":      "vivaldi",
    "tor":          "tor browser",
    "yandex":       "browser",
    "ie":           "iexplore",
    "internet explorer": "iexplore",
}


# ─── Aplicativos ──────────────────────────────────────────────────────────────

def open_app(name: str) -> str:
    exe = APPS_MAP.get(name.lower().strip(), name)
    try:
        subprocess.Popen(exe, shell=True)
        return f"Aplicativo '{name}' aberto."
    except Exception as exc:
        logger.error(f"open_app falhou: {exc}")
        return f"Não foi possível abrir '{name}': {exc}"


def _find_browser_path(name: str) -> str | None:
    """Localiza o executável real de um navegador no Windows (PATH + caminhos comuns + registro)."""
    import glob, winreg

    # Caminhos de instalação mais comuns
    bases = [
        os.path.expandvars(r"%LOCALAPPDATA%\Programs"),
        os.path.expandvars(r"%LOCALAPPDATA%"),
        os.path.expandvars(r"%PROGRAMFILES%"),
        os.path.expandvars(r"%PROGRAMFILES(X86)%"),
        os.path.expandvars(r"%APPDATA%"),
    ]

    # Padrões ABSOLUTOS verificados primeiro (evita pegar versões erradas)
    absolute_paths = {
        "chrome":   [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        ],
        "firefox":  [
            r"C:\Program Files\Mozilla Firefox\firefox.exe",
            r"C:\Program Files (x86)\Mozilla Firefox\firefox.exe",
        ],
        "msedge":   [
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        ],
        "opera":    [
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\Opera\opera.exe"),
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\Opera GX\opera.exe"),
            r"C:\Program Files\Opera\opera.exe",
        ],
        "brave":    [
            os.path.expandvars(r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\Application\brave.exe"),
            r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
        ],
        "vivaldi":  [
            os.path.expandvars(r"%LOCALAPPDATA%\Vivaldi\Application\vivaldi.exe"),
            r"C:\Program Files\Vivaldi\Application\vivaldi.exe",
        ],
        "browser":  [
            os.path.expandvars(r"%LOCALAPPDATA%\Yandex\YandexBrowser\Application\browser.exe"),
        ],
        "iexplore": [r"C:\Program Files\Internet Explorer\iexplore.exe"],
    }

    # Verifica caminhos absolutos primeiro
    for path in absolute_paths.get(name, []):
        if os.path.isfile(path):
            return path

    # Padrões relativos (fallback por glob)
    patterns = {
        "chrome":   ["Google/Chrome/Application/chrome.exe"],
        "firefox":  ["Mozilla Firefox/firefox.exe"],
        "msedge":   ["Microsoft/Edge/Application/msedge.exe"],
        "opera":    ["Opera/opera.exe", "Opera GX/opera.exe"],
        "brave":    ["BraveSoftware/Brave-Browser/Application/brave.exe"],
        "vivaldi":  ["Vivaldi/Application/vivaldi.exe"],
        "browser":  ["Yandex/YandexBrowser/Application/browser.exe"],
        "iexplore": [],
    }

    candidates = patterns.get(name, [f"{name}.exe"])

    for base in bases:
        for pattern in candidates:
            # Normaliza separadores para Windows
            pattern_win = pattern.replace("/", os.sep)
            full = os.path.join(base, pattern_win)
            if os.path.isfile(full):
                return full
            # glob para versões com número no caminho (ex: Chrome\Application\134.0.x\...)
            glob_pat = os.path.join(base, "**", os.path.basename(pattern_win))
            hits = glob.glob(glob_pat, recursive=True)
            if hits:
                return hits[0]

    # Tenta no registro (App Paths)
    try:
        key_path = rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{name}.exe"
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as k:
            return winreg.QueryValue(k, None)
    except Exception:
        pass

    return None   # não encontrado


# Cache de caminhos descobertos (evita buscar toda vez)
_browser_path_cache: dict[str, str] = {}


def open_url(url: str, browser: str = "default") -> str:
    """
    Abre qualquer URL ou site em um navegador específico ou no padrão do sistema.
    Normaliza domínios parciais e converte texto livre em busca no Google.
    """
    from urllib.parse import quote_plus

    # ── Normaliza a URL ───────────────────────────────────────────────────────
    url = url.strip()
    if not url.startswith(("http://", "https://", "file://")):
        if "." in url and " " not in url:
            url = "https://" + url
        else:
            url = f"https://www.google.com/search?q={quote_plus(url)}"

    browser_key = browser.lower().strip()

    # ── Navegador padrão do sistema ───────────────────────────────────────────
    if browser_key in ("default", "padrão", ""):
        try:
            os.startfile(url)
        except Exception:
            subprocess.Popen(f'start "" "{url}"', shell=True)
        return f"URL '{url}' aberta no navegador padrão."

    # ── Resolve o executável do browser ──────────────────────────────────────
    exe_name = _BROWSER_EXE.get(browser_key, browser_key)   # ex: "opera" → "opera"

    # Verifica cache primeiro
    if exe_name not in _browser_path_cache:
        found = _find_browser_path(exe_name)
        if found:
            _browser_path_cache[exe_name] = found
            logger.info(f"Browser encontrado: {exe_name} → {found}")
        else:
            _browser_path_cache[exe_name] = ""

    full_path = _browser_path_cache.get(exe_name, "")

    # ── Abre com o caminho completo ───────────────────────────────────────────
    if full_path:
        try:
            subprocess.Popen([full_path, url])
            return f"'{url}' aberto no {browser}."
        except Exception as exc:
            logger.error(f"Falha ao abrir {full_path}: {exc}")

    # ── Fallback: deixa o Windows resolver pelo nome + start ──────────────────
    try:
        subprocess.Popen(f'start "" "{exe_name}" "{url}"', shell=True)
        return f"'{url}' aberto no {browser} (via shell)."
    except Exception as exc:
        return f"Não foi possível abrir '{url}' no {browser}: {exc}"


def close_app(name: str) -> str:
    # Tenta pelo título da janela
    try:
        wins = gw.getWindowsWithTitle(name)
        if wins:
            for w in wins:
                w.close()
            return f"Janela '{name}' fechada."
    except Exception:
        pass

    # Fallback: taskkill pelo nome do processo
    result = subprocess.run(
        ["taskkill", "/IM", name, "/F"],
        capture_output=True, text=True, shell=True
    )
    if result.returncode == 0:
        return f"Processo '{name}' encerrado."
    return f"Não foi possível fechar '{name}'."


# ─── Teclado e Mouse ──────────────────────────────────────────────────────────

def press_hotkey(keys: str) -> str:
    parts = [k.strip() for k in keys.split("+")]
    try:
        pyautogui.hotkey(*parts)
        return f"Atalho '{keys}' executado."
    except Exception as exc:
        return f"Erro ao executar atalho '{keys}': {exc}"


def type_text(text: str, press_enter: bool = False) -> str:
    try:
        pyautogui.write(text, interval=0.04)
        if press_enter:
            pyautogui.press("enter")
        return "Texto digitado."
    except Exception as exc:
        # Fallback para caracteres especiais (acentos, etc.)
        try:
            import pyperclip
            pyperclip.copy(text)
            pyautogui.hotkey("ctrl", "v")
            if press_enter:
                pyautogui.press("enter")
            return "Texto colado via área de transferência."
        except Exception:
            return f"Erro ao digitar texto: {exc}"


def click_at(x: int, y: int, double: bool = False) -> str:
    try:
        if double:
            pyautogui.doubleClick(x, y)
        else:
            pyautogui.click(x, y)
        return f"Clique em ({x}, {y})."
    except Exception as exc:
        return f"Erro ao clicar: {exc}"


def right_click_at(x: int, y: int) -> str:
    try:
        pyautogui.rightClick(x, y)
        return f"Clique direito em ({x}, {y})."
    except Exception as exc:
        return f"Erro ao clicar: {exc}"


def scroll_at(x: int, y: int, direction: str, clicks: int = 3) -> str:
    amount = clicks if direction == "up" else -clicks
    try:
        pyautogui.scroll(amount, x=x, y=y)
        return f"Scroll {direction} em ({x}, {y})."
    except Exception as exc:
        return f"Erro ao rolar: {exc}"


def get_screen_size() -> str:
    w, h = pyautogui.size()
    return f"Resolução da tela: {w}x{h} pixels."


# ─── Screenshot + GPT-4o Vision ───────────────────────────────────────────────

async def take_screenshot() -> str:
    """Captura a tela e usa GPT-4o Vision para descrever o que está sendo exibido."""
    try:
        screenshot = pyautogui.screenshot()

        # Redimensiona para reduzir tokens (mantém aspecto)
        max_w = 1280
        if screenshot.width > max_w:
            ratio = max_w / screenshot.width
            new_h = int(screenshot.height * ratio)
            screenshot = screenshot.resize((max_w, new_h), Image.LANCZOS)

        buf = io.BytesIO()
        screenshot.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode()

        response = _groq.chat.completions.create(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "Descreva detalhadamente o que está sendo exibido na tela. "
                                "Inclua: qual aplicativo está aberto, elementos visíveis (botões, campos, menus), "
                                "texto relevante, e a posição aproximada de elementos importantes em pixels. "
                                "Seja específico e técnico — você está ajudando um agente de automação."
                            ),
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{b64}"},
                        },
                    ],
                }
            ],
            max_tokens=1000,
        )
        return response.choices[0].message.content
    except Exception as exc:
        logger.error(f"take_screenshot falhou: {exc}")
        return f"Não foi possível capturar a tela: {exc}"


# ─── Volume e Mídia ───────────────────────────────────────────────────────────

def set_volume(level: int) -> str:
    level = max(0, min(100, level))
    try:
        # PowerShell: define volume via COM
        script = f"(New-Object -ComObject WScript.Shell).SendKeys([char]174 * 50); " \
                 f"$vol = {level}; " \
                 f"Add-Type -TypeDefinition 'using System.Runtime.InteropServices; " \
                 f"[Guid(\"5CDF2C82-841E-4546-9722-0CF74078229A\"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)] " \
                 f"interface IAudioEndpointVolume {{ }}'"
        # Abordagem mais simples: usar nircmd ou PowerShell direto
        result = subprocess.run(
            ["powershell", "-Command",
             f"$obj = New-Object -ComObject WScript.Shell; "
             f"for($i=0;$i -lt 50;$i++){{$obj.SendKeys([char]174)}}; "
             f"$steps = [math]::Round({level}/2); "
             f"for($i=0;$i -lt $steps;$i++){{$obj.SendKeys([char]175)}}"],
            capture_output=True, timeout=10
        )
        return f"Volume definido para {level}%."
    except Exception as exc:
        # Fallback: teclas de volume
        pyautogui.press("volumemute")
        pyautogui.press("volumemute")
        return f"Ajuste de volume para {level}% (aproximado via teclas)."


MEDIA_KEYS = {
    "play_pause": "playpause",
    "next": "nexttrack",
    "previous": "prevtrack",
    "stop": "stop",
}

def media_control(action: str) -> str:
    key = MEDIA_KEYS.get(action)
    if not key:
        return f"Ação de mídia desconhecida: {action}"
    pyautogui.press(key)
    return f"Comando de mídia '{action}' enviado."


# ─── Tela e Sistema ───────────────────────────────────────────────────────────

def lock_screen() -> str:
    ctypes.windll.user32.LockWorkStation()
    return "Tela bloqueada."


def run_command(command: str, shell: str = "cmd") -> str:
    try:
        if shell == "powershell":
            proc = subprocess.run(
                ["powershell", "-Command", command],
                capture_output=True, text=True, timeout=30
            )
        else:
            proc = subprocess.run(
                command, shell=True, capture_output=True, text=True, timeout=30
            )
        output = (proc.stdout + proc.stderr).strip()
        return output[:2000] if output else "(sem saída)"
    except subprocess.TimeoutExpired:
        return "Comando excedeu o tempo limite de 30 segundos."
    except Exception as exc:
        return f"Erro ao executar comando: {exc}"


# ─── Sistema de Arquivos ──────────────────────────────────────────────────────

def open_file(path: str) -> str:
    try:
        os.startfile(path)
        return f"Arquivo '{path}' aberto."
    except Exception as exc:
        return f"Erro ao abrir arquivo: {exc}"


def create_folder(path: str) -> str:
    try:
        Path(path).mkdir(parents=True, exist_ok=True)
        return f"Pasta '{path}' criada."
    except Exception as exc:
        return f"Erro ao criar pasta: {exc}"


def list_files(path: str) -> str:
    try:
        entries = list(Path(path).iterdir())
        if not entries:
            return f"Pasta '{path}' está vazia."
        lines = []
        for e in sorted(entries)[:50]:
            kind = "[PASTA]" if e.is_dir() else "[ARQ]"
            lines.append(f"{kind} {e.name}")
        return "\n".join(lines)
    except Exception as exc:
        return f"Erro ao listar '{path}': {exc}"
