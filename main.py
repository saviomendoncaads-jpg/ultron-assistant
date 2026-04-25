"""
JARVIS — Orquestrador Principal
================================
Arquitetura de threads:
  Thread 1 (main)   → Qt event loop  — desenha a HUD a 60fps, nunca bloqueia
  Thread 2 (daemon) → asyncio loop   — STT, LLM/Brain, TTS, automações

Comunicação: ui_queue (thread-safe Queue)
  backend coloca → ("state", "listening"|"processing"|"speaking"|"idle")
                   ("text",  str)
                   ("amplitude", float 0-1)
"""
import asyncio
import os
import sys
import threading
from pathlib import Path

# Garante que o diretório de trabalho seja sempre o da pasta do projeto
os.chdir(Path(__file__).parent)

from dotenv import load_dotenv

# ── Valida .env ───────────────────────────────────────────────────────────────
env_path = Path(__file__).parent / ".env"
if not env_path.exists():
    print("[ERRO] Arquivo .env nao encontrado.")
    sys.exit(1)
load_dotenv(env_path)

# ── Qt deve ser importado ANTES dos módulos que usam QApplication ─────────────
from PyQt6.QtWidgets import QApplication
from hud import HUDWindow
from modules.ui import ui_queue

# ── Restante dos imports ──────────────────────────────────────────────────────
from loguru import logger
from modules.stt import SpeechToText
from modules.llm import UltronAgent
from modules.tts import TextToSpeech
from modules.brain_engine import BrainEngine
from modules.automation.executor import ActionExecutor

# ── Logging ───────────────────────────────────────────────────────────────────
logger.remove()
logger.add(sys.stderr,
           format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | {message}",
           level="INFO", colorize=True)
logger.add("ultron.log", rotation="10 MB", retention="7 days", level="DEBUG")

WAKE_WORD = os.getenv("WAKE_WORD", "").lower().strip()

# Evento para encerrar o loop async quando a janela fechar
_shutdown = threading.Event()


# ─────────────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _put(cmd: str, data):
    """Envia mensagem para a UI de forma thread-safe."""
    ui_queue.put((cmd, data))


# ─────────────────────────────────────────────────────────────────────────────
#  Loop assíncrono — roda em thread separada
# ─────────────────────────────────────────────────────────────────────────────

async def run_assistant():
    loop = asyncio.get_event_loop()

    # ── Inicializa Brain (indexação do Obsidian) ──────────────────────────────
    brain = BrainEngine()
    vault_path = os.getenv("OBSIDIAN_VAULT_PATH", "").strip()

    if vault_path:
        _put("state", "processing")
        _put("text", "indexando cerebro...")
        logger.info("Iniciando indexação do vault do Obsidian...")
        # Roda em executor para não bloquear o event loop (pode demorar para vaults grandes)
        await loop.run_in_executor(None, brain.index)
        logger.info(brain.stats)
    else:
        logger.warning("OBSIDIAN_VAULT_PATH não definido — Brain desativado.")

    # ── Inicializa módulos ────────────────────────────────────────────────────
    stt      = SpeechToText()
    tts      = TextToSpeech()
    executor = ActionExecutor()
    agent    = UltronAgent(executor, brain)

    # ── Saudação inicial ──────────────────────────────────────────────────────
    _put("state", "speaking")
    _put("text", "sistemas online")
    try:
        await tts.speak("Sistemas online, Senhor.")
    except Exception:
        pass  # falha no TTS da saudação nunca impede o loop

    # ── Loop principal ────────────────────────────────────────────────────────
    while not _shutdown.is_set():
        try:
            # 1. Escuta
            _put("state", "listening")
            _put("text", "ouvindo...")

            wav = stt.listen(on_amplitude=lambda a: _put("amplitude", a))
            if wav is None:
                _put("state", "idle")
                continue

            # 2. Transcreve
            _put("state", "processing")
            _put("text", "processando...")
            _put("amplitude", 0.0)

            transcript = stt.transcribe(wav)
            if not transcript or len(transcript.strip()) < 3:
                _put("state", "idle")
                _put("text", "aguardando...")
                continue

            # Filtra wake word (se configurada)
            if WAKE_WORD and WAKE_WORD not in transcript.lower():
                _put("state", "idle")
                continue

            print(f"\n[Senhor] {transcript}")
            _put("text", transcript[:46])

            # 3. Agente — pensa, busca Brain e executa
            _put("state", "processing")
            response = await agent.run(transcript)

            # 4. Responde
            print(f"[JARVIS] {response}\n")
            _put("state", "speaking")
            _put("text", response[:46])
            await tts.speak(response)

            _put("state", "idle")
            _put("text", "aguardando...")

        except Exception as exc:
            logger.exception(f"Erro no loop principal: {exc}")
            try:
                _put("state", "idle")
                await tts.speak("Ocorreu uma falha interna, Senhor. Retomando escuta.")
            except Exception:
                pass

    await executor.cleanup()


def _thread_target():
    asyncio.run(run_assistant())


# ─────────────────────────────────────────────────────────────────────────────
#  Entry point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)

    window = HUDWindow()
    window.show()

    app.aboutToQuit.connect(lambda: _shutdown.set())

    t = threading.Thread(target=_thread_target, daemon=True)
    t.start()

    sys.exit(app.exec())
