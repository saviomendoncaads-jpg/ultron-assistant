# -*- coding: utf-8 -*-
"""
Automação do Bloco de Notas via RPA (subprocess + pyautogui + pygetwindow).
"""
import subprocess
import time
import pyautogui
import pygetwindow as gw
from loguru import logger

pyautogui.PAUSE = 0.04
pyautogui.FAILSAFE = False

_NOTEPAD_TITLES = ["Sem título - Bloco de Notas", "Untitled - Notepad",
                   "Bloco de Notas", "Notepad", "*Sem título - Bloco de Notas"]


def _find_notepad_window():
    for title_fragment in ["Bloco de Notas", "Notepad"]:
        windows = [w for w in gw.getAllWindows() if title_fragment in w.title]
        if windows:
            return windows[0]
    return None


def open_notepad_and_type(text: str) -> str:
    """Abre o Bloco de Notas, aguarda foco e digita o texto."""
    logger.info(f"Abrindo Bloco de Notas para digitar: {text[:60]}...")

    # 1. Abre o notepad
    subprocess.Popen(["notepad.exe"])

    # 2. Aguarda janela aparecer (até 5 segundos)
    win = None
    for _ in range(25):
        time.sleep(0.2)
        win = _find_notepad_window()
        if win:
            break

    if not win:
        return "Erro: Bloco de Notas não abriu a tempo."

    # 3. Traz para primeiro plano e aguarda foco estabilizar
    try:
        win.activate()
    except Exception:
        pass
    time.sleep(0.5)

    # 4. Garante foco clicando na área de texto (centro da janela)
    try:
        cx = win.left + win.width // 2
        cy = win.top + win.height // 2
        pyautogui.click(cx, cy)
        time.sleep(0.3)
    except Exception as e:
        logger.warning(f"Falha ao clicar no centro da janela: {e}")

    # 5. Digita o texto — typewrite para ASCII, write() para unicode
    _type_text_safe(text)

    logger.info("Texto digitado no Bloco de Notas com sucesso.")
    return "Documento redigido conforme solicitado, senhor."


def _type_text_safe(text: str):
    """Digita texto suportando caracteres especiais e acentos em PT-BR."""
    # pyautogui.typewrite só aceita ASCII confiável; para acentos usa write via clipboard
    try:
        import pyperclip
        pyperclip.copy(text)
        pyautogui.hotkey("ctrl", "v")
    except Exception:
        # Fallback: digita caractere por caractere com intervalo
        for ch in text:
            try:
                pyautogui.typewrite(ch, interval=0.03)
            except Exception:
                pyautogui.press("space")
