FROM python:3.12-slim

WORKDIR /app

# Select dependency set at build time:
#   requirements.txt       — full (includes HF/torch); used locally & in CI
#   requirements-prod.txt   — slim (Gemini embeddings only); used on the VM
ARG REQUIREMENTS=requirements.txt

COPY requirements.txt requirements-prod.txt ./
RUN pip install --no-cache-dir -r ${REQUIREMENTS}

COPY app/ ./app/

# $PORT is injected by some PaaS hosts; default to 8000 (used by the VM compose).
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
