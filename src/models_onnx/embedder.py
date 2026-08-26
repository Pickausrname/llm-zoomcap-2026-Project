"""
ONNX CPU inference for the query/document embedding model (spec.md section 7.2).

Loads the ONNX export written by `export.py` from `config.EMBEDDING_MODEL_DIR`
and exposes `embed()`: tokenize -> run session -> mean-pool over the attention
mask -> L2-normalize, matching `sentence-transformers/multi-qa-MiniLM-L6-cos-v1`'s
own pooling so cosine similarity is directly comparable to the reference model.
Runs entirely on CPU via `onnxruntime`, keeping embedding inference local
(spec.md section 1.2 data-privacy principle).
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path

import numpy as np
import onnxruntime as ort
from transformers import AutoTokenizer, PreTrainedTokenizerBase

from src.config import EMBEDDING_DIM, EMBEDDING_MODEL_DIR

logger = logging.getLogger(__name__)

__all__ = ["embed"]

_session: ort.InferenceSession | None = None
_tokenizer: PreTrainedTokenizerBase | None = None
_init_lock = threading.Lock()


def _model_path(model_dir: Path) -> Path:
    onnx_path = model_dir / "model.onnx"
    if not onnx_path.exists():
        raise FileNotFoundError(
            f"No ONNX export found at {onnx_path}. Run `make export-models` "
            "(or `python -m src.models_onnx.export`) first."
        )
    return onnx_path


def _get_session(
    model_dir: Path = EMBEDDING_MODEL_DIR,
) -> tuple[ort.InferenceSession, PreTrainedTokenizerBase]:
    """Lazily load (and cache) the ONNX session + tokenizer, safely across threads."""
    global _session, _tokenizer
    if _session is None or _tokenizer is None:
        # Double-checked locking: concurrent ThreadPoolExecutor callers (spec.md
        # section 11.4) must not each redundantly load their own model copy.
        with _init_lock:
            if _session is None or _tokenizer is None:
                onnx_path = _model_path(model_dir)
                logger.info("Loading embedding ONNX session from %s", onnx_path)
                # Parallelism is already provided by concurrent ThreadPoolExecutor
                # callers (spec.md section 11.4); let each .run() call use a single
                # thread instead of every call fanning out across all CPU cores.
                sess_options = ort.SessionOptions()
                sess_options.intra_op_num_threads = 1
                sess_options.inter_op_num_threads = 1
                # Build into locals first so a failure here (e.g. a missing
                # tokenizer file) never leaves a half-initialized global pair.
                new_session = ort.InferenceSession(
                    str(onnx_path), sess_options=sess_options, providers=["CPUExecutionProvider"]
                )
                new_tokenizer = AutoTokenizer.from_pretrained(model_dir)
                _session, _tokenizer = new_session, new_tokenizer
    return _session, _tokenizer


def _mean_pool(token_embeddings: np.ndarray, attention_mask: np.ndarray) -> np.ndarray:
    """Mean-pool token embeddings, weighting by the attention mask."""
    mask = attention_mask[..., np.newaxis].astype(np.float32)
    summed = (token_embeddings * mask).sum(axis=1)
    counts = np.clip(mask.sum(axis=1), a_min=1e-9, a_max=None)
    return summed / counts


def _l2_normalize(vectors: np.ndarray) -> np.ndarray:
    """L2-normalize rows so cosine similarity reduces to a dot product."""
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    return vectors / np.clip(norms, a_min=1e-9, a_max=None)


def embed(texts: list[str]) -> np.ndarray:
    """
    Embed `texts` with the ONNX `multi-qa-MiniLM-L6-cos-v1` model.

    Args:
        texts: Batch of input strings to embed.

    Returns:
        `np.ndarray` of shape `(len(texts), config.EMBEDDING_DIM)`, L2-normalized
        so cosine similarity between rows reduces to a dot product.
    """
    if not texts:
        return np.empty((0, EMBEDDING_DIM), dtype=np.float32)

    session, tokenizer = _get_session()
    encoded = tokenizer(texts, padding=True, truncation=True, return_tensors="np")
    onnx_input_names = {i.name for i in session.get_inputs()}
    onnx_inputs = {
        "input_ids": encoded["input_ids"].astype(np.int64),
        "attention_mask": encoded["attention_mask"].astype(np.int64),
    }
    if "token_type_ids" in encoded and "token_type_ids" in onnx_input_names:
        onnx_inputs["token_type_ids"] = encoded["token_type_ids"].astype(np.int64)

    # Resolve the output name dynamically rather than assuming "last_hidden_state",
    # since an alternative ONNX exporter toolchain could name it differently.
    output_name = session.get_outputs()[0].name
    (token_embeddings,) = session.run([output_name], onnx_inputs)
    pooled = _mean_pool(token_embeddings, encoded["attention_mask"])
    return _l2_normalize(pooled).astype(np.float32)
