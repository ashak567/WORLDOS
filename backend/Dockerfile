FROM python:3.12-slim
WORKDIR /app
COPY backend/pyproject.toml ./
COPY backend/app ./app
COPY backend/tests ./tests
COPY db/init ./db/init
RUN pip install --no-cache-dir .
EXPOSE 8000
CMD ["sh", "-c", "if [ \"$WORLDOS_RUN_MIGRATIONS_ON_START\" = \"true\" ]; then python -m app.migrate; fi; exec uvicorn app.main:app --host 0.0.0.0 --port \"${PORT:-8000}\""]

