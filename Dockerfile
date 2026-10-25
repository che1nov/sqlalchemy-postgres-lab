FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --create-home --uid 10001 appuser
COPY --chown=appuser:appuser . .
USER appuser

# Проект — CLI-приложение: применяет миграции, показывает CRUD и завершается.
CMD ["sh", "-c", "alembic upgrade head && python -m orm_lab.demo"]
