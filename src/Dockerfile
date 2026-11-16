FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN DJANGO_SECRET_KEY=build-only python manage.py collectstatic --noinput \
    && chmod +x entrypoint.sh \
    && useradd --create-home --uid 1000 appuser

USER appuser
EXPOSE 8000
ENTRYPOINT ["./entrypoint.sh"]
