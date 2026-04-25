"""
BrainEngine — Cérebro de Conhecimento do JARVIS
================================================
Indexa e busca arquivos .md do vault do Obsidian usando BM25 (Okapi).

Características:
  - 100% local, sem GPU, sem servidor, sem API paga
  - Cache inteligente: só re-indexa se o vault mudou (hash dos arquivos)
  - Chunking com overlap para não perder contexto nas bordas
  - Thread-safe: index() deve ser chamado em executor, search() é síncrono

Variáveis .env:
  OBSIDIAN_VAULT_PATH  → caminho absoluto da pasta do vault
  BRAIN_TOP_K          → quantos chunks retornar por busca (padrão: 5)
  BRAIN_MIN_SCORE      → score mínimo BM25 para considerar relevante (padrão: 0.3)
"""

import os
import re
import hashlib
import pickle
import threading
from pathlib import Path
from loguru import logger

try:
    from rank_bm25 import BM25Okapi
    _BM25_OK = True
except ImportError:
    _BM25_OK = False
    logger.error("rank_bm25 não instalado. Execute: pip install rank-bm25")

# ── Configuração via .env ─────────────────────────────────────────────────────
VAULT_PATH      = os.getenv("OBSIDIAN_VAULT_PATH", "").strip()
BRAIN_TOP_K     = int(os.getenv("BRAIN_TOP_K",     "5"))
BRAIN_MIN_SCORE = float(os.getenv("BRAIN_MIN_SCORE", "0.3"))

CHUNK_WORDS   = 300   # palavras por chunk
CHUNK_OVERLAP = 60    # overlap entre chunks consecutivos

_CACHE_FILE = Path(__file__).parent.parent / ".brain_cache.pkl"


# ─────────────────────────────────────────────────────────────────────────────
#  BrainEngine
# ─────────────────────────────────────────────────────────────────────────────
class BrainEngine:
    """Indexa o vault do Obsidian e fornece busca BM25 ultra-rápida."""

    def __init__(self):
        self._ready   = False
        self._lock    = threading.Lock()
        self.chunks:  list[dict] = []   # {"text": str, "title": str}
        self._bm25    = None
        self.vault    = Path(VAULT_PATH) if VAULT_PATH else None

    # ── API pública ───────────────────────────────────────────────────────────

    def index(self) -> None:
        """
        Indexa o vault. DEVE ser chamado em thread separada (é bloqueante).
        Usa cache: só reconstrói o índice se os arquivos mudaram.
        """
        if not _BM25_OK:
            return
        if not self.vault:
            logger.warning("OBSIDIAN_VAULT_PATH não definido no .env — Brain desativado.")
            return
        if not self.vault.exists():
            logger.warning(f"Vault não encontrado: '{self.vault}' — Brain desativado.")
            return

        vault_hash = self._vault_hash()

        if self._try_load_cache(vault_hash):
            return  # cache válido, nada a fazer

        self._build_index()
        self._save_cache(vault_hash)

    def search(self, query: str, top_k: int = BRAIN_TOP_K) -> list[dict]:
        """
        Busca BM25 — retorna lista de dicts {"title", "text", "score"}.
        Retorna lista vazia se brain não estiver pronto ou sem resultados relevantes.
        """
        if not self._ready or self._bm25 is None:
            return []

        tokens = _tokenize(query)
        if not tokens:
            return []

        scores  = self._bm25.get_scores(tokens)
        top_idx = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]

        return [
            {
                "title": self.chunks[i]["title"],
                "text":  self.chunks[i]["text"],
                "score": float(scores[i]),
            }
            for i in top_idx
            if scores[i] >= BRAIN_MIN_SCORE
        ]

    @property
    def is_ready(self) -> bool:
        return self._ready

    @property
    def stats(self) -> str:
        """Resumo do índice para logging."""
        if not self._ready:
            return "Brain não disponível"
        return f"{len(self.chunks)} chunks indexados do vault"

    # ── Internos ──────────────────────────────────────────────────────────────

    def _vault_hash(self) -> str:
        """Hash MD5 baseado nos caminhos e timestamps de modificação dos .md."""
        files = sorted(self.vault.rglob("*.md"))
        sig   = "".join(f"{f}:{f.stat().st_mtime}" for f in files)
        return hashlib.md5(sig.encode()).hexdigest()

    def _try_load_cache(self, vault_hash: str) -> bool:
        """Carrega cache se o hash bater. Retorna True em caso de sucesso."""
        if not _CACHE_FILE.exists():
            return False
        try:
            with open(_CACHE_FILE, "rb") as f:
                cache = pickle.load(f)
            if cache.get("hash") != vault_hash:
                return False
            self.chunks = cache["chunks"]
            # Reconstrói BM25 a partir dos chunks (mais seguro que serializar o objeto)
            tokenized   = [_tokenize(c["text"]) for c in self.chunks]
            self._bm25  = BM25Okapi(tokenized)
            self._ready = True
            logger.info(f"Brain carregado do cache — {len(self.chunks)} chunks")
            return True
        except Exception as exc:
            logger.debug(f"Cache inválido, reconstruindo índice: {exc}")
            return False

    def _build_index(self) -> None:
        """Lê todos os .md, faz chunking e constrói o índice BM25."""
        files = list(self.vault.rglob("*.md"))
        logger.info(f"Indexando {len(files)} arquivos do vault...")

        self.chunks = []
        for md_file in files:
            try:
                raw     = md_file.read_text(encoding="utf-8", errors="ignore")
                cleaned = _clean_markdown(raw)
                for chunk in _chunk_text(cleaned, md_file.stem):
                    self.chunks.append(chunk)
            except Exception:
                pass

        if not self.chunks:
            logger.warning("Vault indexado mas nenhum chunk gerado — verifique o caminho.")
            return

        tokenized  = [_tokenize(c["text"]) for c in self.chunks]
        self._bm25 = BM25Okapi(tokenized)
        self._ready = True
        logger.info(f"Brain pronto: {len(self.chunks)} chunks | {len(files)} arquivos")

    def _save_cache(self, vault_hash: str) -> None:
        try:
            with open(_CACHE_FILE, "wb") as f:
                pickle.dump({"hash": vault_hash, "chunks": self.chunks}, f)
            logger.debug("Cache do Brain salvo.")
        except Exception as exc:
            logger.warning(f"Falha ao salvar cache do Brain: {exc}")


# ─────────────────────────────────────────────────────────────────────────────
#  Utilitários de texto
# ─────────────────────────────────────────────────────────────────────────────

def _tokenize(text: str) -> list[str]:
    """Tokenização simples: lowercase + remove pontuação."""
    return re.sub(r"[^\w\s]", " ", text.lower()).split()


def _clean_markdown(text: str) -> str:
    """Remove elementos de sintaxe Markdown que poluem o índice."""
    text = re.sub(r"^---.*?---\s*",          "",   text, flags=re.DOTALL)  # frontmatter YAML
    text = re.sub(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]", r"\1", text)         # [[links]]
    text = re.sub(r"```.*?```",              " ",  text, flags=re.DOTALL)  # blocos de código
    text = re.sub(r"`[^`]+`",               " ",  text)                   # código inline
    text = re.sub(r"!\[.*?\]\(.*?\)",        " ",  text)                   # imagens
    text = re.sub(r"\[.*?\]\(.*?\)",         " ",  text)                   # [links](url)
    text = re.sub(r"^#{1,6}\s+",            " ",  text, flags=re.MULTILINE)# headings
    text = re.sub(r"[*_~]{1,3}(.*?)[*_~]{1,3}", r"\1", text)              # bold/italic
    text = re.sub(r"^\s*[-*+]\s+",          " ",  text, flags=re.MULTILINE)# listas
    text = re.sub(r"^\s*\d+\.\s+",          " ",  text, flags=re.MULTILINE)# listas numeradas
    text = re.sub(r"\n{3,}",               "\n\n", text)
    return text.strip()


def _chunk_text(text: str, title: str) -> list[dict]:
    """Divide texto em chunks com overlap para preservar contexto nas bordas."""
    words  = text.split()
    chunks = []
    start  = 0
    while start < len(words):
        end       = min(start + CHUNK_WORDS, len(words))
        chunk_txt = " ".join(words[start:end])
        if len(chunk_txt.strip()) > 50:   # ignora chunks muito pequenos
            chunks.append({"text": chunk_txt, "title": title})
        start += CHUNK_WORDS - CHUNK_OVERLAP
    return chunks
