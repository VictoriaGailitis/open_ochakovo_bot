# Frontend assets are compiled once; no Node runtime is shipped to production.
FROM node:22-alpine AS frontend
WORKDIR /build
COPY package.json package-lock.json ./
RUN npm ci
COPY index.html tsconfig*.json vite.config.ts ./
COPY src ./src
COPY public ./public
RUN npm run build

FROM python:3.13-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 DEV_AUTH=0
RUN useradd --system --uid 10001 --create-home appuser && mkdir -p /app/.data && chown appuser:appuser /app/.data
COPY --chown=appuser:appuser server ./server
COPY --from=frontend --chown=appuser:appuser /build/dist ./dist
USER appuser
VOLUME ["/app/.data"]
EXPOSE 3001
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s CMD python -c "from urllib.request import urlopen; urlopen('http://127.0.0.1:3001/api/health',timeout=3)" || exit 1
CMD ["python", "-m", "server", "--host", "0.0.0.0", "--port", "3001"]
