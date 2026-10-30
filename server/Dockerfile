FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

RUN pip install --no-cache-dir uv
COPY server/pyproject.toml ./
RUN uv sync --no-dev --no-install-project
COPY server/ /app/
COPY docs/engineering/database/0001_initial_schema.sql /app/schema/0001_initial_schema.sql

EXPOSE 8000
CMD ["uv", "run", "--no-sync", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
