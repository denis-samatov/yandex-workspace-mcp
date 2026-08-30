import logging
import sys
from collections.abc import MutableMapping
from typing import Any

import structlog

from .models.errors import redact_sensitive


def _redact_event(
    _logger: Any, _method_name: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    redacted = redact_sensitive(event_dict)
    return redacted if isinstance(redacted, dict) else {}


class _RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        rendered = super().format(record)
        redacted = redact_sensitive(rendered)
        return redacted if isinstance(redacted, str) else "[REDACTED]"


class _OwnedStreamHandler(logging.StreamHandler):
    _yandex_workspace_handler = True


def setup_logging(log_level: str = "INFO") -> None:
    """Configure structured logging using structlog."""

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            _redact_event,
            structlog.processors.JSONRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = _RedactingFormatter("%(message)s")
    handler = _OwnedStreamHandler(sys.stderr)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    for existing in list(root_logger.handlers):
        if getattr(existing, "_yandex_workspace_handler", False):
            root_logger.removeHandler(existing)
    root_logger.addHandler(handler)
    root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    # HTTPX includes full request URLs in INFO records, including signed capability queries.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def get_logger(name: str) -> structlog.BoundLogger:
    return structlog.get_logger(name)
