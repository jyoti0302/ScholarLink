"""
Phase 2A Step 4: Configurable Embedding Provider Interface & Cache Manager.

Retains `BAAI/bge-m3` (1024-d dense + learned sparse lexical weights) as the primary
target model while keeping the provider pluggable across:
1. `BGEM3FlagEmbeddingProvider` (native FlagEmbedding `BGEM3FlagModel(return_dense=True, return_sparse=True)`)
2. `CachedOrOnDemandEmbeddingProvider` (serves pre-computed Colab/Kaggle/GPU embeddings from
   PostgreSQL `embedding_cache` by `content_hash`, computing only cache misses via an inner provider)
3. `DeterministicHashEmbeddingProvider` (lightweight deterministic provider for unit/integration tests
   that never downloads large model weights)
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
import hashlib
import json
import math
import re
from typing import Dict, List, Optional, Sequence, Tuple

from sqlalchemy.orm import Session

from backend.database.models import EmbeddingCache

DEFAULT_TARGET_MODEL = "BAAI/bge-m3"
DEFAULT_TARGET_DIM = 1024


@dataclass
class EmbeddingOutput:
    dense: List[float]
    sparse_indices: List[int]
    sparse_values: List[float]


class EmbeddingProvider(ABC):
    """Abstract interface for dense + sparse hybrid embedding providers."""

    @property
    @abstractmethod
    def model_name(self) -> str:
        ...

    @property
    @abstractmethod
    def vector_dim(self) -> int:
        ...

    @abstractmethod
    def encode(self, texts: Sequence[str]) -> List[EmbeddingOutput]:
        ...


class DeterministicHashEmbeddingProvider(EmbeddingProvider):
    """
    Zero-download, deterministic embedding provider for unit tests and CI.
    Produces normalized `vector_dim` dense vectors and token-hash sparse vectors.
    """

    def __init__(self, model_name: str = DEFAULT_TARGET_MODEL, vector_dim: int = DEFAULT_TARGET_DIM):
        self._model_name = model_name
        self._vector_dim = vector_dim

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def vector_dim(self) -> int:
        return self._vector_dim

    def encode(self, texts: Sequence[str]) -> List[EmbeddingOutput]:
        outputs: List[EmbeddingOutput] = []
        for text in texts:
            tokens = re.findall(r"[a-z0-9]+", (text or "").lower())
            vec = [0.0] * self._vector_dim
            sparse_map: Dict[int, float] = {}

            for tok in tokens:
                digest = hashlib.sha256(tok.encode("utf-8")).digest()
                idx_dense = int.from_bytes(digest[:4], "big") % self._vector_dim
                sign = 1.0 if (digest[4] & 1) == 0 else -1.0
                vec[idx_dense] += sign
                idx_sparse = int.from_bytes(digest[8:12], "big") % 250002  # XLM-R vocab size of BGE-M3
                sparse_map[idx_sparse] = sparse_map.get(idx_sparse, 0.0) + 1.0

            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            dense = [round(v / norm, 6) for v in vec]
            s_indices = sorted(sparse_map.keys())
            s_values = [round(math.log1p(sparse_map[i]), 4) for i in s_indices]
            outputs.append(EmbeddingOutput(dense=dense, sparse_indices=s_indices, sparse_values=s_values))
        return outputs


class BGEM3FlagEmbeddingProvider(EmbeddingProvider):
    """
    Native BAAI/bge-m3 provider using `FlagEmbedding.BGEM3FlagModel`.
    Generates both 1024-d dense embeddings and learned sparse lexical weights (`lexical_weights`)
    in a single forward pass. Lazily loads the model only when `encode()` is called.
    """

    def __init__(
        self,
        model_name: str = DEFAULT_TARGET_MODEL,
        use_fp16: bool = True,
        device: Optional[str] = None,
        batch_size: int = 16,
        max_length: int = 512,
    ):
        self._model_name = model_name
        self._use_fp16 = use_fp16
        self._device = device
        self._batch_size = batch_size
        self._max_length = max_length
        self._model = None

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def vector_dim(self) -> int:
        return DEFAULT_TARGET_DIM

    def _ensure_loaded(self):
        if self._model is None:
            from FlagEmbedding import BGEM3FlagModel  # type: ignore

            self._model = BGEM3FlagModel(
                self._model_name,
                use_fp16=self._use_fp16,
                device=self._device,
            )

    def encode(self, texts: Sequence[str]) -> List[EmbeddingOutput]:
        if not texts:
            return []
        self._ensure_loaded()
        res = self._model.encode(
            list(texts),
            batch_size=self._batch_size,
            max_length=self._max_length,
            return_dense=True,
            return_sparse=True,
            return_colbert_vecs=False,
        )
        dense_vecs = res["dense_vecs"]
        lexical_weights = res["lexical_weights"]
        outputs: List[EmbeddingOutput] = []
        for d_vec, lex_dict in zip(dense_vecs, lexical_weights):
            # lex_dict maps token_id (str or int) -> float weight
            pairs: List[Tuple[int, float]] = sorted(
                ((int(k), float(v)) for k, v in lex_dict.items() if float(v) > 0.0),
                key=lambda x: x[0],
            )
            outputs.append(
                EmbeddingOutput(
                    dense=[float(x) for x in d_vec],
                    sparse_indices=[p[0] for p in pairs],
                    sparse_values=[p[1] for p in pairs],
                )
            )
        return outputs


class EmbeddingCacheStore:
    """Reads and writes dense + sparse vectors in PostgreSQL `embedding_cache` by `(content_hash, model_name)`."""

    @staticmethod
    def get_cached_batch(
        db: Session,
        content_hashes: Sequence[str],
        model_name: str,
    ) -> Dict[str, EmbeddingOutput]:
        if not content_hashes:
            return {}
        rows = (
            db.query(EmbeddingCache)
            .filter(
                EmbeddingCache.embedding_model == model_name,
                EmbeddingCache.content_hash.in_(list(set(content_hashes))),
            )
            .all()
        )
        found: Dict[str, EmbeddingOutput] = {}
        for r in rows:
            found[r.content_hash] = EmbeddingOutput(
                dense=json.loads(r.dense_vector_json),
                sparse_indices=json.loads(r.sparse_indices_json or "[]"),
                sparse_values=json.loads(r.sparse_values_json or "[]"),
            )
        return found

    @staticmethod
    def save_cached_batch(
        db: Session,
        items: Dict[str, EmbeddingOutput],
        model_name: str,
        vector_dim: int,
    ) -> int:
        if not items:
            return 0
        existing_hashes = {
            r[0]
            for r in db.query(EmbeddingCache.content_hash)
            .filter(
                EmbeddingCache.embedding_model == model_name,
                EmbeddingCache.content_hash.in_(list(items.keys())),
            )
            .all()
        }
        added = 0
        for chash, emb in items.items():
            if chash in existing_hashes:
                continue
            db.add(
                EmbeddingCache(
                    content_hash=chash,
                    embedding_model=model_name,
                    dense_vector_json=json.dumps(emb.dense),
                    sparse_indices_json=json.dumps(emb.sparse_indices),
                    sparse_values_json=json.dumps(emb.sparse_values),
                    vector_dim=vector_dim,
                )
            )
            added += 1
        if added:
            db.flush()
        return added
