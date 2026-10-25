FROM node:22-alpine AS frontend
WORKDIR /build
COPY package.json package-lock.json ./
RUN npm ci
COPY index.html game-preview.html tsconfig*.json vite.config.ts ./
COPY src ./src
COPY public ./public
RUN npm run build

FROM python:3.13-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 DEV_AUTH=0 DJANGO_DEBUG=0 DJANGO_SETTINGS_MODULE=backoffice.settings
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt && useradd --system --uid 10001 --create-home appuser && mkdir -p /app/.data && chown appuser:appuser /app/.data
COPY --chown=appuser:appuser manage.py ./manage.py
COPY --chown=appuser:appuser backoffice ./backoffice
COPY --chown=appuser:appuser server ./server
COPY --chown=appuser:appuser src/games/sprite-manifest.json ./src/games/sprite-manifest.json
COPY --from=frontend --chown=appuser:appuser /build/public/assets/games-v5 ./public/assets/games-v5
COPY --chown=appuser:appuser scripts/container-start.sh ./scripts/container-start.sh
COPY --from=frontend --chown=appuser:appuser /build/dist ./dist
USER appuser
VOLUME ["/app/.data"]
EXPOSE 3001
HEALTHCHECK --interval=30s --timeout=5s --start-period=45s CMD python -c "from urllib.request import urlopen; urlopen('http://127.0.0.1:3001/api/health',timeout=3)" || exit 1
CMD ["sh", "scripts/container-start.sh"]
