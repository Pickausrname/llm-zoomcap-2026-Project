"""
Central configuration for the MOSFET Selection RAG application.

Loads secrets from `.env` (via python-dotenv) and exposes the
filesystem paths shared by every layer of the application (ingestion,
knowledge storage, retrieval, evaluation, monitoring).

Additional configuration (model identifiers, retrieval parameters, LLM
pricing, the active retrieval approach, etc.) is added here
incrementally as those layers are implemented.
"""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

# Loaded as early as possible so every module reading os.environ (LLM
# clients, etc.) sees values from ./.env.
load_dotenv()

# ---------------------------------------------------------------------------
# Base paths
# ---------------------------------------------------------------------------
BASE_DIR: Path = Path(__file__).resolve().parent.parent
DATA_DIR: Path = BASE_DIR / "data"
RAW_DIR: Path = DATA_DIR / "raw"
MODELS_DIR: Path = BASE_DIR / "models"
EMBEDDING_MODEL_DIR: Path = MODELS_DIR / "embedding"
RERANKER_MODEL_DIR: Path = MODELS_DIR / "reranker"

# ---------------------------------------------------------------------------
# SQLite database files
# ---------------------------------------------------------------------------
KNOWLEDGE_DB: Path = DATA_DIR / "knowledge.db"
MONITORING_DB: Path = DATA_DIR / "monitoring.db"

# ---------------------------------------------------------------------------
# Evaluation artifacts
# ---------------------------------------------------------------------------
GROUND_TRUTH_CSV: Path = DATA_DIR / "ground_truth.csv"
RETRIEVAL_EVAL_RESULTS_JSON: Path = DATA_DIR / "retrieval_eval_results.json"
RETRIEVAL_EVAL_RESULTS_CSV: Path = DATA_DIR / "retrieval_eval_results.csv"
LLM_EVAL_RESULTS_JSON: Path = DATA_DIR / "llm_eval_results.json"
LLM_EVAL_RESULTS_CSV: Path = DATA_DIR / "llm_eval_results.csv"

# ---------------------------------------------------------------------------
# Model identifiers (spec.md sections 2, 6.2, 7.1)
# ---------------------------------------------------------------------------
EMBEDDING_MODEL_ID: str = "sentence-transformers/multi-qa-MiniLM-L6-cos-v1"
RERANKER_MODEL_ID: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"

# Output dimensionality of EMBEDDING_MODEL_ID; drives the width of the
# `master_vec` sqlite-vec column in db/knowledge_store.py.
EMBEDDING_DIM: int = 384

OPENAI_MODEL: str = "gpt-5.4-mini"
GEMINI_MODEL: str = "gemini-2.5-flash"

# Single swap point read by query rewriting, generation, judging, and
# evaluation (spec.md section 6.3): one of "openai" or "gemini".
DEFAULT_LLM_PROVIDER: str = "openai"

# Fraction of conversations the Streamlit app (app/qa_panel.py) auto-judges
# via the live production relevance judge (spec.md sections 10.2/12.2).
# 1.0 = judge every conversation (fully spec-compliant default -- the
# dashboard's "Judge Relevance Distribution" chart populates from the first
# query). Lower to reduce judge-LLM cost at scale; not exposed in the UI.
JUDGE_SAMPLE_RATE: float = 1.0

# ---------------------------------------------------------------------------
# Retrieval parameters (spec.md section 9)
# ---------------------------------------------------------------------------
TOP_K: int = 20  # candidates returned by Stage 1 hybrid search
FINAL_N: int = 5  # documents kept after Stage 2 cross-encoder re-rank
RRF_K: int = 60  # Reciprocal Rank Fusion constant

# Retrieval approach identifiers compared by evaluation/evaluate_retrieval.py
# (spec.md section 11.2).
APPROACH_LEXICAL: str = "lexical_bm25"
APPROACH_VECTOR: str = "dense_vector"
APPROACH_HYBRID: str = "hybrid_fusion"
APPROACH_HYBRID_RERANK: str = "hybrid_rerank"

# Hybrid fusion weight: final_score = ALPHA * vector_score + (1 - ALPHA) * keyword_score.
ALPHA: float = 0.5

# Winning configuration, programmatically overwritten by
# evaluation/evaluate_retrieval.py (spec.md section 11.3) once offline
# evaluation determines the best-performing approach/parameters. The
# production retrieval pipeline reads these two values at call time, so
# updating them here is enough to change production behavior.
ACTIVE_RETRIEVAL_APPROACH: str = APPROACH_HYBRID_RERANK
ACTIVE_ALPHA: float = ALPHA

# ---------------------------------------------------------------------------
# LLM pricing (USD per 1K tokens), used for cost estimation in the LLM
# clients and the monitoring store. Placeholder rates — replace with the
# provider's published pricing before relying on these for real reporting.
# ---------------------------------------------------------------------------
PRICING_PER_1K_TOKENS: dict[str, dict[str, float]] = {
    OPENAI_MODEL: {"prompt": 0.00015, "completion": 0.00060},
    GEMINI_MODEL: {"prompt": 0.00007, "completion": 0.00030},
}
