"""Policy ingestion + retrieval.

Pipeline: load markdown -> normalise -> chunk by section/paragraph (with metadata) ->
sparse TF-IDF "embeddings" -> in-memory vector index -> cosine-similarity search with an
explicit sufficiency decision (so the agent can say "the policy does not establish this").

The embedding backend is a deliberately simple, dependency-free TF-IDF vectoriser. The public
interface (`PolicyRetriever.search`) is stable, so a dense-embedding / Chroma backend can be
swapped in later without touching the agent or tools.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, asdict
from pathlib import Path

STOPWORDS = set("""a an the and or but if then else of to in on at by for from with without about into over after before
is are was were be been being am do does did done doing have has had having can could should would will shall may might
i me my mine we our you your he she it its they them their this that these those there here what which who whom whose
when where why how not no yes any some all each every other than as so such very just also please tell give need want
get got let us long take takes much many""".split())

MIN_SCORE = 0.12       # minimum cosine similarity for a chunk to count as evidence
MIN_COVERAGE = 0.6     # minimum share of the query content terms found in the chunk
MAX_CHUNK_CHARS = 700
RELATIVE_CUTOFF = 0.4  # keep only hits scoring >= 40% of the best hit


def normalise(text: str) -> str:
    text = text.replace("\u2019", "'").replace("\u2014", "-")
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def _stem(tok: str) -> str:
    for suf in ("ations", "ation", "ings", "ing", "ies", "ed", "es", "s"):
        if tok.endswith(suf) and len(tok) - len(suf) >= 3:
            return tok[: -len(suf)] + ("y" if suf == "ies" else "")
    return tok


def tokenize(text: str) -> list[str]:
    return [_stem(t) for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in STOPWORDS and len(t) > 1]


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    document: str
    section_no: int
    section_title: str
    text: str


@dataclass(frozen=True)
class Hit:
    chunk_id: str
    document: str
    section_no: int
    section_title: str
    text: str
    score: float
    coverage: float

    def metadata(self) -> dict:
        d = asdict(self)
        d.pop("text")
        return d


@dataclass
class RetrievalResult:
    sufficient: bool
    hits: list[Hit]
    reason: str = ""


def chunk_markdown(text: str, document: str) -> list[Chunk]:
    """Split on `## N. Title` sections, then on paragraphs (capped at MAX_CHUNK_CHARS)."""
    chunks: list[Chunk] = []
    for m in re.finditer(r"^##\s+(\d+)\.\s+(.+?)\n(.*?)(?=^##\s|\Z)", text, re.S | re.M):
        sec_no, title, body = int(m.group(1)), m.group(2).strip(), normalise(m.group(3))
        paras = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
        buf, idx = "", 0
        for p in paras + [None]:
            if p is not None and len(buf) + len(p) + 1 <= MAX_CHUNK_CHARS:
                buf = (buf + "\n" + p).strip()
                continue
            if buf:
                idx += 1
                chunks.append(Chunk(f"policy-s{sec_no}-c{idx}", document, sec_no, title, buf))
            buf = p or ""
    return chunks


class PolicyRetriever:
    def __init__(self, policy_path: Path):
        self.path = Path(policy_path)
        self.chunks: list[Chunk] = chunk_markdown(self.path.read_text(encoding="utf-8"), self.path.name)
        if not self.chunks:
            raise ValueError("policy document produced no chunks")
        self._build_index()

    def _build_index(self) -> None:
        docs = [tokenize(c.section_title + " " + c.text) for c in self.chunks]
        n = len(docs)
        df = Counter(t for d in docs for t in set(d))
        self.idf = {t: math.log((1 + n) / (1 + f)) + 1.0 for t, f in df.items()}
        self.vectors = [self._vector(d) for d in docs]
        self.terms = [set(d) for d in docs]

    def _vector(self, tokens: list[str]) -> dict[str, float]:
        tf = Counter(tokens)
        vec = {t: (1 + math.log(c)) * self.idf.get(t, 0.0) for t, c in tf.items() if t in self.idf}
        norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
        return {t: v / norm for t, v in vec.items()}

    def search(self, query: str, top_k: int = 3) -> RetrievalResult:
        q_tokens = tokenize(query)
        if not q_tokens:
            return RetrievalResult(False, [], "empty_query")
        qv = self._vector(q_tokens)
        if not qv:
            return RetrievalResult(False, [], "no_overlap")
        q_terms = set(q_tokens)
        scored = []
        for i, vec in enumerate(self.vectors):
            score = sum(w * vec.get(t, 0.0) for t, w in qv.items())
            coverage = len(q_terms & self.terms[i]) / len(q_terms)
            scored.append((score, coverage, i))
        scored.sort(reverse=True)
        hits = []
        for score, cov, i in scored[:top_k]:
            if score <= 0:
                continue
            c = self.chunks[i]
            hits.append(Hit(c.chunk_id, c.document, c.section_no, c.section_title, c.text, round(score, 4), round(cov, 3)))
        if not hits:
            return RetrievalResult(False, [], "no_overlap")
        best = hits[0]
        hits = [h for h in hits if h.score >= RELATIVE_CUTOFF * best.score]   # drop weak extra chunks
        ok = best.score >= MIN_SCORE and best.coverage >= MIN_COVERAGE
        return RetrievalResult(ok, hits if ok else hits, "" if ok else "low_confidence")
