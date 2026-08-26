"""
One-time ONNX export of the embedding and reranker HF models (spec.md section 7.1).

Run via `make export-models` (or `python -m src.models_onnx.export`) before
`make ingest` or serving retrieval. Exports are written to
`config.EMBEDDING_MODEL_DIR` and `config.RERANKER_MODEL_DIR` and are then
loaded read-only by `embedder.py` / `reranker.py` via `onnxruntime` -- no
torch/transformers inference is needed at serving time, keeping embedding
and re-ranking local and fast (spec.md section 1.2 data-privacy principle).
"""

from __future__ import annotations

import logging
from pathlib import Path

from optimum.onnxruntime import (
    ORTModelForFeatureExtraction,
    ORTModelForSequenceClassification,
)
from transformers import AutoTokenizer

from src.config import (
    EMBEDDING_MODEL_DIR,
    EMBEDDING_MODEL_ID,
    RERANKER_MODEL_DIR,
    RERANKER_MODEL_ID,
)

logger = logging.getLogger(__name__)

__all__ = ["export_embedding_model", "export_reranker_model", "export_all"]


def _export(model_id: str, output_dir: Path, model_cls: type) -> None:
    """Export `model_id` to ONNX plus its tokenizer, writing both to `output_dir`."""
    output_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Exporting %s to ONNX at %s ...", model_id, output_dir)
    model = model_cls.from_pretrained(model_id, export=True)
    model.save_pretrained(output_dir)
    tokenizer = AutoTokenizer.from_pretrained(model_id)
    tokenizer.save_pretrained(output_dir)
    logger.info("Export complete: %s", output_dir)


def export_embedding_model(output_dir: Path = EMBEDDING_MODEL_DIR) -> None:
    """Export `config.EMBEDDING_MODEL_ID` (multi-qa-MiniLM-L6-cos-v1) to ONNX."""
    _export(EMBEDDING_MODEL_ID, output_dir, ORTModelForFeatureExtraction)


def export_reranker_model(output_dir: Path = RERANKER_MODEL_DIR) -> None:
    """Export `config.RERANKER_MODEL_ID` (ms-marco-MiniLM-L-6-v2) to ONNX."""
    _export(RERANKER_MODEL_ID, output_dir, ORTModelForSequenceClassification)


def export_all() -> None:
    """Export both the embedding and reranker models (entrypoint for `make export-models`)."""
    export_embedding_model()
    export_reranker_model()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    export_all()
