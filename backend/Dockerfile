# syntax=docker/dockerfile:1.7
# ---------------------------------------------------------------- builder
FROM python:3.11-slim AS builder

ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# CPU-only torch first, so sentence-transformers doesn't drag in CUDA (~3 GB)
RUN pip install torch==2.7.0 --index-url https://download.pytorch.org/whl/cpu
COPY requirements.txt .
RUN pip install -r requirements.txt

# Bake the embedding + reranker models into the image: first query is fast and
# the container works with no internet access (air-gapped on-prem installs).
ARG EMBEDDING_MODEL=sentence-transformers/all-mpnet-base-v2
ARG RERANKER_MODEL=cross-encoder/ms-marco-MiniLM-L-6-v2
ENV HF_HOME=/opt/hf
RUN python -c "from sentence_transformers import SentenceTransformer, CrossEncoder; \
SentenceTransformer('${EMBEDDING_MODEL}', device='cpu'); CrossEncoder('${RERANKER_MODEL}', device='cpu')"

# ---------------------------------------------------------------- runtime
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    HF_HOME=/opt/hf \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system strata && useradd --system --gid strata --home /app strata \
    && mkdir -p /data/uploads && chown -R strata:strata /data

COPY --from=builder /opt/venv /opt/venv
COPY --from=builder --chown=strata:strata /opt/hf /opt/hf

WORKDIR /app
COPY --chown=strata:strata . .

USER strata
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

# migrations run once, from the `migrate` service in docker-compose
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers ${API_WORKERS:-2} --proxy-headers --forwarded-allow-ips='*'"]
