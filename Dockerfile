# Dockerfile -- app image for the MOSFET Selection RAG stack (spec.md section 14).
#
# Single image used for the Streamlit UI as well as every offline pipeline
# stage (ingestion, ground-truth generation, evaluation) -- docker-compose.yml
# runs this image as the long-lived `app` service (streamlit) and can also
# run one-off commands against it (`docker compose run --rm app <command>`)
# for `make ingest` / `make eval-retrieval` / etc. when not using a local venv.

FROM python:3.11-slim

# onnxruntime (CPU) needs libgomp at runtime; curl is only used by the
# HEALTHCHECK below.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY skills/ ./skills/
COPY docker-entrypoint.sh .
RUN chmod +x docker-entrypoint.sh

# ./data and ./models are bind-mounted by docker-compose.yml so that
# generated SQLite files and ONNX exports persist across container restarts
# (spec.md section 14.1). Empty dirs here just make the image runnable
# standalone (e.g. `docker run` without compose) without erroring on a
# missing path.
RUN mkdir -p data/raw models/embedding models/reranker

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s \
    CMD curl --fail http://localhost:8501/_stcore/health || exit 1

ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["streamlit", "run", "src/app/streamlit_app.py", "--server.address=0.0.0.0", "--server.port=8501"]
