FROM python:3.14-slim

LABEL org.opencontainers.image.title="Kalshi Quotes MCP" \
      org.opencontainers.image.source="https://github.com/gordoaf/kalshi-quotes-mcp" \
      org.opencontainers.image.licenses="MIT"

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
ENV PATH="/app/.venv/bin:$PATH"
WORKDIR /app
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src ./src
RUN python -m pip install uv==0.13.9 \
    && uv sync --locked --no-dev --no-editable \
    && useradd --create-home --uid 10001 app
USER app
EXPOSE 8000
ENTRYPOINT ["kalshi-quotes-mcp"]
CMD ["--transport", "streamable-http", "--host", "0.0.0.0", "--port", "8000"]
