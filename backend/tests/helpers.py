"""Test helpers: a tiny PDF writer and a deterministic fake embedder."""

import hashlib
import math
import re

from app.services.embeddings import EmbeddingProvider


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def make_pdf(pages: list[str]) -> bytes:
    """Build a minimal, valid multi-page PDF with one line of Helvetica text per input line.

    Hand-rolled so tests need no PDF-generation dependency and no fixture files.
    """
    objects: list[bytes] = []
    n = len(pages)
    font_id = 3 + 2 * n
    kids = " ".join(f"{3 + 2 * i} 0 R" for i in range(n))
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {n} >>".encode())
    for i, text in enumerate(pages):
        lines = text.split("\n")
        ops = ["BT", "/F1 11 Tf", "14 TL", "50 780 Td"]
        for line in lines:
            ops.append(f"({_escape(line)}) Tj T*")
        ops.append("ET")
        stream = "\n".join(ops).encode("latin-1")
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 842] "
            f"/Resources << /Font << /F1 {font_id} 0 R >> >> /Contents {4 + 2 * i} 0 R >>".encode()
        )
        objects.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for num, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{num} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


class FakeEmbedder(EmbeddingProvider):
    """Hashed bag-of-words vectors: texts sharing words get high cosine similarity.

    Deterministic and instant, so retrieval behaviour is testable without the
    real model. Query prefixing is skipped (it would only add shared noise).
    """

    dim = 384
    _word = re.compile(r"[a-z0-9]+")

    def _vec(self, text: str) -> list[float]:
        v = [0.0] * self.dim
        for w in self._word.findall(text.lower()):
            if len(w) < 3:
                continue
            h = int(hashlib.md5(w.encode(), usedforsecurity=False).hexdigest(), 16)
            v[h % self.dim] += 1.0
        norm = math.sqrt(sum(x * x for x in v)) or 1.0
        # Avoid an all-zero vector (cosine distance undefined).
        return [x / norm for x in v] if any(v) else [1.0 / math.sqrt(self.dim)] * self.dim

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]

    async def embed_query(self, text: str) -> list[float]:
        return self._vec(text)
