FROM python:3.12-slim

WORKDIR /app

# Run as non-root
RUN useradd -m -s /bin/bash appuser
RUN chown -R appuser:appuser /app

# Install dependencies using pip (since uv might not be installed in the slim image)
COPY . /app/
RUN pip install --no-cache-dir .

USER appuser

ENTRYPOINT ["yandex-workspace-mcp"]
CMD ["--transport", "stdio"]
