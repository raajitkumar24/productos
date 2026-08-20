FROM python:3.12-slim AS builder

WORKDIR /build
COPY pyproject.toml README.md ./
COPY src ./src
RUN python -m venv /opt/productos && \
    /opt/productos/bin/pip install --no-cache-dir .

FROM python:3.12-slim

ENV PATH=/opt/productos/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app
COPY --from=builder /opt/productos /opt/productos
COPY alembic.ini ./alembic.ini
COPY db ./db
RUN addgroup --system productos && adduser --system --ingroup productos productos
USER productos
EXPOSE 8000
CMD ["uvicorn", "productos.api:app", "--host", "0.0.0.0", "--port", "8000"]
