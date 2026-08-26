"""
ONNX CPU inference for the cross-encoder re-ranker (spec.md section 7.3, 9.3).

Loads the ONNX export written by `export.py` from `config.RERANKER_MODEL_DIR`
and exposes `score()`: scores each `(query, document)` pair with
`cross-encoder/ms-marco-MiniLM-L-6-v2`, returning the raw relevance logit for
each document. Higher scores are more relevant; callers sort descending
(spec.md section 9.3). Runs entirely on CPU via `onnxruntime`.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path

import numpy as np
import onnxruntime as ort
from transformers import AutoTokenizer, PreTrainedTokenizerBase

from src.config import RERANKER_MODEL_DIR

logger = logging.getLogger(__name__)

__all__ = ["score"]

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
    model_dir: Path = RERANKER_MODEL_DIR,
) -> tuple[ort.InferenceSession, PreTrainedTokenizerBase]:
    """Lazily load (and cache) the ONNX session + tokenizer, safely across threads."""
    global _session, _tokenizer
    if _session is None or _tokenizer is None:
        # Double-checked locking: concurrent ThreadPoolExecutor callers (spec.md
        # section 11.4) must not each redundantly load their own model copy.
        with _init_lock:
            if _session is None or _tokenizer is None:
                onnx_path = _model_path(model_dir)
                logger.info("Loading reranker ONNX session from %s", onnx_path)
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


def score(query: str, docs: list[str]) -> list[float]:
    """
    Score each `(query, doc)` pair with the ONNX cross-encoder.

    Args:
        query: The (rewritten) user query.
        docs: Candidate document texts from Stage 1 hybrid search.

    Returns:
        List of relevance scores, one per `docs` entry, in the same order
        as `docs`. Higher is more relevant.
    """
    if not docs:
        return []

    session, tokenizer = _get_session()
    encoded = tokenizer(
        [query] * len(docs),
        docs,
        padding=True,
        truncation=True,
        return_tensors="np",
    )
    onnx_input_names = {i.name for i in session.get_inputs()}
    onnx_inputs = {
        "input_ids": encoded["input_ids"].astype(np.int64),
        "attention_mask": encoded["attention_mask"].astype(np.int64),
    }
    if "token_type_ids" in encoded and "token_type_ids" in onnx_input_names:
        onnx_inputs["token_type_ids"] = encoded["token_type_ids"].astype(np.int64)

    # Resolve the output name dynamically rather than assuming "logits",
    # since an alternative ONNX exporter toolchain could name it differently.
    output_name = session.get_outputs()[0].name
    (logits,) = session.run([output_name], onnx_inputs)
    return logits.reshape(-1).astype(np.float32).tolist()
