FROM python:3.11-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN python -m pip install --upgrade pip wheel setuptools
RUN pip wheel --wheel-dir /wheels -r requirements.txt

FROM python:3.11-slim AS runner

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/home/appuser/.cache/huggingface \
    FAISS_INDEX_PATH=/data/faiss.index \
    FAISS_ID_MAP_PATH=/data/faiss_id_map.json

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 10001 appuser

COPY --from=builder /wheels /wheels
COPY requirements.txt .

RUN pip install --no-index --find-links=/wheels -r requirements.txt && rm -rf /wheels

RUN python -c "from transformers import CLIPModel, CLIPProcessor; model_id='openai/clip-vit-base-patch32'; CLIPModel.from_pretrained(model_id); CLIPProcessor.from_pretrained(model_id)"

COPY app ./app

RUN mkdir -p /data /app/uploads /home/appuser/.cache/huggingface && \
    chown -R appuser:appuser /app /data /home/appuser

USER appuser

ENV HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
