"""
Cérebro Obsidian — busca semântica por TF-IDF nas notas do vault.
Indexa todas as notas .md na primeira consulta (lazy loading).
"""
import os
import re
import math
import glob
from pathlib import Path
from loguru import logger

VAULT_PATH = os.getenv(
    "OBSIDIAN_VAULT",
    r"C:\Users\Sávio Mendonça\Documents\Obsidian\Sávio Mendonça"
)
MAX_RESULTS = 5
MAX_CHARS_PER_NOTE = 1500
STOPWORDS = {
    "de", "a", "o", "que", "e", "do", "da", "em", "um", "para", "com",
    "uma", "os", "no", "se", "na", "por", "mais", "as", "dos", "como",
    "mas", "ao", "ele", "das", "à", "seu", "sua", "ou", "quando", "muito",
    "nos", "já", "eu", "também", "só", "pelo", "pela", "até", "isso",
    "ela", "entre", "depois", "sem", "mesmo", "aos", "seus", "quem",
    "nas", "me", "esse", "eles", "você", "essa", "num", "nem", "suas",
    "meu", "às", "minha", "numa", "pelos", "elas", "havia", "seja",
    "qual", "será", "nós", "tenho", "lhe", "deles", "essas", "esses",
    "pelas", "este", "dele", "tu", "te", "vocês", "vos", "lhes", "meus",
    "minhas", "teu", "tua", "teus", "tuas", "nosso", "nossa", "nossos",
    "nossas", "is", "the", "a", "an", "and", "or", "but", "in", "on",
    "at", "to", "for", "of", "with", "by", "from", "as", "be", "are",
}


def _tokenize(text: str) -> list[str]:
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    return [w for w in text.split() if w not in STOPWORDS and len(w) > 2]


def _tf(tokens: list[str]) -> dict[str, float]:
    count: dict[str, int] = {}
    for t in tokens:
        count[t] = count.get(t, 0) + 1
    total = len(tokens) or 1
    return {w: c / total for w, c in count.items()}


class ObsidianBrain:
    _instance: "ObsidianBrain | None" = None

    def __init__(self):
        self._docs: list[dict] = []   # [{path, title, content, tf}]
        self._idf: dict[str, float] = {}
        self._indexed = False

    @classmethod
    def get(cls) -> "ObsidianBrain":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _index(self) -> None:
        if self._indexed:
            return
        logger.info(f"Indexando vault: {VAULT_PATH}")
        paths = glob.glob(os.path.join(VAULT_PATH, "**", "*.md"), recursive=True)

        df: dict[str, int] = {}
        for path in paths:
            try:
                content = Path(path).read_text(encoding="utf-8", errors="ignore")
                tokens = _tokenize(content)
                tf = _tf(tokens)
                title = Path(path).stem
                self._docs.append({"path": path, "title": title, "content": content, "tf": tf})
                for word in set(tokens):
                    df[word] = df.get(word, 0) + 1
            except Exception:
                continue

        n = len(self._docs) or 1
        self._idf = {w: math.log(n / (c + 1)) + 1 for w, c in df.items()}
        self._indexed = True
        logger.info(f"Vault indexado: {len(self._docs)} notas")

    def search(self, query: str, top_k: int = MAX_RESULTS) -> str:
        self._index()
        if not self._docs:
            return "Nenhuma nota encontrada no vault do Obsidian."

        q_tokens = _tokenize(query)
        if not q_tokens:
            return "Consulta vazia."

        scores: list[tuple[float, dict]] = []
        for doc in self._docs:
            score = sum(
                doc["tf"].get(t, 0) * self._idf.get(t, 0)
                for t in q_tokens
            )
            if score > 0:
                scores.append((score, doc))

        scores.sort(key=lambda x: x[0], reverse=True)
        top = scores[:top_k]

        if not top:
            return f"Nenhuma nota relevante encontrada para: '{query}'"

        partes = []
        for score, doc in top:
            trecho = doc["content"][:MAX_CHARS_PER_NOTE].strip()
            partes.append(f"### {doc['title']}\n{trecho}")

        return f"Encontrei {len(top)} nota(s) relevante(s) no vault:\n\n" + "\n\n---\n\n".join(partes)

    def salvar_nota(self, titulo: str, conteudo: str) -> str:
        try:
            nome = re.sub(r'[<>:"/\\|?*]', "-", titulo) + ".md"
            caminho = os.path.join(VAULT_PATH, nome)
            Path(caminho).write_text(conteudo, encoding="utf-8")
            self._indexed = False  # forçar reindexação
            return f"Nota '{titulo}' salva no vault: {caminho}"
        except Exception as e:
            return f"Erro ao salvar nota: {e}"
