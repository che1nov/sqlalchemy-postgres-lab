FROM python:3.11-slim AS base
WORKDIR /srv/tracker
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 MPLCONFIGDIR=/tmp/matplotlib
COPY requirements.txt requirements.lock ./
RUN pip install --no-cache-dir -r requirements.txt -c requirements.lock \
    && useradd --create-home tracker
COPY --chown=tracker:tracker . .

FROM base AS tests
RUN pip install --no-cache-dir -r requirements-dev.txt -c requirements.lock
USER tracker
CMD ["python", "-m", "pytest", "-q"]

FROM base AS runtime
USER tracker
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8000"]
