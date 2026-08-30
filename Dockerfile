FROM ghcr.io/astral-sh/uv:0.11.14@sha256:1025398289b62de8269e70c45b91ffa37c373f38118d7da036fb8bb8efc85d97 AS uv

FROM python:3.12-slim@sha256:09f7da3bc104798d0afb40bc08d23ab2da20a76130cec1f2ef170848f5d85217 AS builder

WORKDIR /build
COPY --from=uv /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv
COPY pyproject.toml README.md ./
COPY uv.lock ./
COPY src ./src
RUN uv sync --frozen --no-dev --extra multi-user --no-editable

FROM python:3.12-slim@sha256:09f7da3bc104798d0afb40bc08d23ab2da20a76130cec1f2ef170848f5d85217 AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/opt/venv/bin:$PATH

RUN useradd --create-home --shell /usr/sbin/nologin --uid 10001 appuser
COPY --from=builder /opt/venv /opt/venv

USER appuser
WORKDIR /home/appuser

EXPOSE 8000
ENTRYPOINT ["yandex-workspace-mcp"]
CMD ["--transport", "stdio"]
