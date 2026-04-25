"""
Text-to-Speech — edge-tts + Windows MCI
Correções críticas:
  - _play() roda em executor (nunca bloqueia o event loop do asyncio)
  - _generate() tem timeout de 12s (edge-tts não trava mais)
  - Falhas isoladas: o loop principal continua mesmo sem áudio
"""
import asyncio
import ctypes
import os
import tempfile
from loguru import logger
import edge_tts

VOICE     = os.getenv("TTS_VOICE",  "pt-BR-AntonioNeural")
TTS_RATE  = os.getenv("TTS_RATE",   "-8%")
TTS_PITCH = os.getenv("TTS_PITCH",  "-12Hz")

_winmm = ctypes.windll.winmm

def _mci_send(cmd: str) -> int:
    return _winmm.mciSendStringW(cmd, None, 0, None)

def _play_blocking(mp3_path: str) -> None:
    """Reprodução MCI síncrona — deve ser chamada via run_in_executor."""
    path  = os.path.abspath(mp3_path).replace("/", "\\")
    alias = "jarvis_tts"
    _mci_send(f'close {alias}')                          # garante que não há alias antigo
    _mci_send(f'open "{path}" type mpegvideo alias {alias}')
    _mci_send(f'play {alias} wait')
    _mci_send(f'close {alias}')


class TextToSpeech:
    def __init__(self):
        self._loop = None
        logger.info(f"TTS pronto — {VOICE} | rate {TTS_RATE} | pitch {TTS_PITCH}")

    async def speak(self, text: str) -> None:
        text = text.strip()
        if not text:
            return

        # Guarda o loop para uso no executor
        self._loop = asyncio.get_event_loop()

        logger.info(f"TTS → {text[:80]!r}{'...' if len(text) > 80 else ''}")

        for attempt in range(3):
            mp3_path = None
            try:
                # Gera o MP3 com timeout de 12s
                mp3_path = await asyncio.wait_for(self._generate(text), timeout=12)

                # Reproduz em thread separada para não bloquear o event loop
                await self._loop.run_in_executor(None, _play_blocking, mp3_path)
                return

            except asyncio.TimeoutError:
                logger.warning(f"TTS tentativa {attempt+1}/3: timeout na geração")
            except Exception as exc:
                logger.warning(f"TTS tentativa {attempt+1}/3 falhou: {exc}")
            finally:
                if mp3_path:
                    try:
                        os.unlink(mp3_path)
                    except Exception:
                        pass

            if attempt < 2:
                await asyncio.sleep(1.0)

        logger.error("TTS falhou 3x — continuando sem áudio.")

    async def _generate(self, text: str) -> str:
        """Gera MP3 via edge-tts. Retorna caminho do arquivo temporário."""
        communicate = edge_tts.Communicate(text=text, voice=VOICE,
                                           rate=TTS_RATE, pitch=TTS_PITCH)
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            tmp_path = f.name
        await communicate.save(tmp_path)
        return tmp_path
