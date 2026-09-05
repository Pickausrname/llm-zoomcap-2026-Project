# Makefile -- task runner for the MOSFET Selection RAG app (spec.md section 14.2).
#
# Every pipeline stage is runnable via a single `make` command so a peer
# reviewer never needs to memorize Python or Docker invocations directly.
# Targets that run inside the local venv assume it's already created and
# activated (see README.md "Local setup"); the Docker targets do not
# require a local venv at all.

.PHONY: build export-models ingest ground-truth eval-retrieval eval-llm up down

# --- Docker ------------------------------------------------------------

build:
	docker compose build

up:
	docker compose up

down:
	docker compose down

# --- Pipeline stages (run inside the active Python environment) --------

export-models:
	python -m src.models_onnx.export

ingest:
	python -m src.ingestion.pipeline

ground-truth:
	python -m src.evaluation.generate_ground_truth

eval-retrieval:
	python -m src.evaluation.evaluate_retrieval

eval-llm:
	python -m src.evaluation.evaluate_llm
