# FastAPI layer (app/api.py) over pipeline.py. Build context: the repo root (see /.dockerignore).
# Data, the LLM cache, eval results, playbooks and .env are bind-mounted by docker-compose.yml, so the
# layout under /app matches the repo and config.ROOT resolves to /app.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app/src:/app \
    NDA_EMBED_DEVICE=cpu

WORKDIR /app

# Dependencies from uv.lock, but with the CPU build of torch: the lock pins the CUDA 12.4 wheels for the
# local GPU, which would add several GB of nvidia-* libraries the droplet cannot use.
COPY pyproject.toml uv.lock ./
RUN pip install --no-cache-dir uv==0.11.16 \
 && uv export --frozen --no-dev --no-hashes --no-emit-project --no-header --no-annotate -o /tmp/req-all.txt \
 && grep -vE '^(torch|nvidia-|triton)' /tmp/req-all.txt > /tmp/req.txt \
 && uv pip install --system --no-cache torch==2.6.0 --index-url https://download.pytorch.org/whl/cpu \
 && uv pip install --system --no-cache -r /tmp/req.txt

# Bake the C3 embedding model into the image so the first review doesn't wait for a download.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-small-en-v1.5')"

COPY src ./src
COPY app ./app

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)"
CMD ["uvicorn", "app.api:app", "--host", "0.0.0.0", "--port", "8000"]
