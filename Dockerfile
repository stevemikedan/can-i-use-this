# Cloud Run image: the API over the ADK graph plus the built frontend, one
# service. Built by `gcloud run deploy --source .` (deploy/deploy.sh).

# Stage 1 — the frontend. dist/ is never committed; it is built here.
FROM node:22-slim AS webbuild
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

# Stage 2 — the runtime.
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
COPY --from=webbuild /web/dist ./web/dist

# Cloud Run sets PORT; the rest comes from the service definition (deploy.sh):
#   CACHE_BACKEND=firestore  GOOGLE_CLOUD_PROJECT  GOOGLE_CLOUD_LOCATION
#   GOOGLE_GENAI_USE_VERTEXAI=1  PARALLEL_API_KEY (Secret Manager)
ENV PORT=8080
EXPOSE 8080

# One worker: the graph runs each query in a thread; Cloud Run scales instances.
CMD exec uvicorn api.main:app --host 0.0.0.0 --port ${PORT} --workers 1 --timeout-keep-alive 75
