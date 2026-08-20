FROM python:3.12-slim AS builder

WORKDIR /build
COPY pyproject.toml README.md LICENSE ./
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
RUN addgroup --system productos && \
    adduser --system --ingroup productos productos && \
    chown productos:productos /app
USER productos
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"
CMD ["uvicorn", "productos.api:app", "--host", "0.0.0.0", "--port", "8000"]
