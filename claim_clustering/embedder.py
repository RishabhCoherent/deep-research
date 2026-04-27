"""OpenAI text-embedding-3-small wrapper for descriptor vectors.

One batched call per ~512 descriptors (well under OpenAI's 2048 limit per call).
Returns a numpy array of shape (n_claims, 1536). Cost is negligible
($0.02 per 1M tokens; a typical 90-claim run uses ~3k tokens = $0.00006).
"""
from __future__ import annotations

from typing import Optional

import numpy as np

from .extractor import _get_client
from .models import RawClaim


_EMBED_MODEL = "text-embedding-3-small"   # 1536 dims, $0.02 / 1M tokens
_PRICE_PER_M = 0.02
_BATCH_SIZE = 512


def embed_claims(
    claims: list[RawClaim],
    *,
    model: str = _EMBED_MODEL,
    on_progress=None,
) -> tuple[list[RawClaim], float]:
    """Populate `claim.descriptor_embedding` for every claim with a descriptor.

    Skips claims whose descriptor is empty. Returns (claims, total_cost_usd).
    """
    log = on_progress or (lambda _msg: None)
    if not claims:
        return claims, 0.0

    client = _get_client()
    indices = [i for i, c in enumerate(claims) if c.descriptor]
    if not indices:
        log("[embedder] no descriptors to embed")
        return claims, 0.0

    total_tokens = 0
    for batch_start in range(0, len(indices), _BATCH_SIZE):
        idx_batch = indices[batch_start:batch_start + _BATCH_SIZE]
        texts = [claims[i].descriptor for i in idx_batch]
        try:
            response = client.embeddings.create(model=model, input=texts)
        except Exception as exc:
            log(f"[embedder] batch starting at {batch_start} crashed: {exc}")
            continue
        for k, datum in enumerate(response.data):
            claims[idx_batch[k]].descriptor_embedding = list(datum.embedding)
        total_tokens += int(getattr(response.usage, "total_tokens", 0) or 0)

    cost = (total_tokens / 1_000_000) * _PRICE_PER_M
    log(f"[embedder] embedded {len(indices)} descriptors, {total_tokens:,} toks, ${cost:.5f}")
    return claims, cost


def cosine_matrix(embeddings: list[list[float]]) -> np.ndarray:
    """Return an n×n cosine similarity matrix from a list of embeddings.

    Empty embeddings (claims that failed to embed) get a row/col of zeros.
    """
    n = len(embeddings)
    if n == 0:
        return np.zeros((0, 0))
    mat = np.zeros((n, 1536))
    for i, e in enumerate(embeddings):
        if e:
            mat[i] = np.asarray(e, dtype=float)
    # L2-normalise rows; zero-rows stay zero
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    mat_n = mat / norms
    return mat_n @ mat_n.T
