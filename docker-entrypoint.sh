#!/bin/sh
# Auto-exports the ONNX embedding/reranker models on first container start if
# they aren't already present under the bind-mounted ./models volume (spec.md
# section 7.1: "Export MUST run at build time (Docker) or via `make
# export-models`"). Bind-mounting ./models means a fresh clone's ./models
# directory is empty even though the image itself never bakes models in, so
# this check makes `make up` work out of the box for a first-time reviewer
# without a separate manual export step.
set -e

if [ ! -f "models/embedding/model.onnx" ] || [ ! -f "models/reranker/model.onnx" ]; then
    echo "ONNX models not found under ./models -- exporting now (one-time, may take a few minutes)..."
    python -m src.models_onnx.export
fi

exec "$@"
