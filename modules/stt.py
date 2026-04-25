"""
Speech-to-Text — GRATUITO, sem chave de API.
Captura áudio com sounddevice (VAD por energia) e transcreve com Google STT.
"""
import io
import os
import wave
import numpy as np
import sounddevice as sd
import speech_recognition as sr
from loguru import logger

SAMPLE_RATE = int(os.getenv("AUDIO_SAMPLE_RATE", 16000))
SILENCE_THRESHOLD = int(os.getenv("AUDIO_SILENCE_THRESHOLD", 500))
SILENCE_DURATION = float(os.getenv("AUDIO_SILENCE_DURATION", 1.8))
STT_LANGUAGE = os.getenv("STT_LANGUAGE", "pt-BR")
CHUNK_DURATION = 0.05   # 50ms

_recognizer = sr.Recognizer()
_recognizer.energy_threshold = 300
_recognizer.dynamic_energy_threshold = True


class SpeechToText:
    def listen(self, on_amplitude=None) -> bytes | None:
        """Grava do microfone até silêncio prolongado. Retorna WAV bytes ou None.

        on_amplitude: callback opcional chamado a cada chunk com valor 0.0–1.0,
                      permite a UI reagir em tempo real à voz do usuário.
        """
        chunk_size = int(SAMPLE_RATE * CHUNK_DURATION)
        recorded: list[np.ndarray] = []
        silent_chunks = 0
        speaking = False
        silence_limit = int(SILENCE_DURATION / CHUNK_DURATION)

        logger.info("Aguardando fala...")

        try:
            with sd.InputStream(samplerate=SAMPLE_RATE, channels=1,
                                dtype="int16", blocksize=chunk_size) as stream:
                while True:
                    chunk, _ = stream.read(chunk_size)
                    amplitude_raw = float(np.abs(chunk).mean())

                    # Emite amplitude normalizada (0–1) para a UI
                    if on_amplitude is not None:
                        on_amplitude(min(1.0, amplitude_raw / 3000.0))

                    if amplitude_raw > SILENCE_THRESHOLD:
                        if not speaking:
                            logger.info("Fala detectada — gravando...")
                            speaking = True
                        silent_chunks = 0
                        recorded.append(chunk.copy())
                    elif speaking:
                        recorded.append(chunk.copy())
                        silent_chunks += 1
                        if silent_chunks >= silence_limit:
                            break
        except Exception as exc:
            logger.error(f"Erro ao capturar áudio: {exc}")
            return None

        if not recorded:
            return None

        return self._to_wav_bytes(np.concatenate(recorded, axis=0))

    def transcribe(self, wav_bytes: bytes) -> str:
        """Transcreve WAV via Google STT (gratuito, sem chave)."""
        audio_data = sr.AudioData(wav_bytes, SAMPLE_RATE, 2)
        try:
            text = _recognizer.recognize_google(audio_data, language=STT_LANGUAGE)
            logger.info(f"Transcrição: {text!r}")
            return text.strip()
        except sr.UnknownValueError:
            logger.debug("Áudio não reconhecido (silêncio ou ruído).")
            return ""
        except sr.RequestError as exc:
            logger.error(f"Erro no Google STT: {exc}")
            return ""

    @staticmethod
    def _to_wav_bytes(audio: np.ndarray) -> bytes:
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(audio.tobytes())
        return buf.getvalue()
