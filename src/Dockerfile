FROM node:22-slim AS js-builder
WORKDIR /build
COPY package.json package-lock.json* ./
RUN npm ci --no-audit
COPY static_src/ ./static_src/
COPY build.js ./
RUN node build.js

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
COPY --from=js-builder /build/ledger/static/ledger/jkurwa.bundle.js \
     /app/ledger/static/ledger/jkurwa.bundle.js

RUN DJANGO_SECRET_KEY=build-only python manage.py collectstatic --noinput \
    && chmod +x entrypoint.sh \
    && useradd --create-home --uid 1000 appuser

USER appuser
EXPOSE 8000
ENTRYPOINT ["./entrypoint.sh"]
