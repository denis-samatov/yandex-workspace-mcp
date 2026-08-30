import contextlib
import contextvars
import hashlib
import json
import logging
import sys
import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from typing import Any

from mcp.server.context import CallNext, HandlerResult, ServerRequestContext

from ..models.base import PublicModel

_correlation_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "correlation_id", default=None
)
_principal_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "principal_id", default=None
)


class AuditEvent(PublicModel):
    timestamp: str
    correlation_id: str
    principal_id: str
    source: str
    action: str
    resource_kind: str
    normalized_locator: str | None
    outcome: str
    error_category: str | None
    destructive: bool
    duration_ms: int


def current_correlation_id() -> str:
    value = _correlation_id.get()
    return value or uuid.uuid4().hex


def _opaque_principal(value: str | None) -> str:
    if not value:
        return "anonymous"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]


@contextlib.contextmanager
def audit_context(*, correlation_id: str, principal_id: str) -> Iterator[None]:
    correlation_token = _correlation_id.set(correlation_id)
    principal_token = _principal_id.set(principal_id)
    try:
        yield
    finally:
        _principal_id.reset(principal_token)
        _correlation_id.reset(correlation_token)


class AuditLogger:
    def __init__(self, name: str = "mcp.audit", logger: logging.Logger | None = None):
        self.logger = logger or logging.getLogger(name)
        self.logger.propagate = False
        self.logger.setLevel(logging.INFO)
        if not self.logger.handlers:
            handler = logging.StreamHandler(sys.stderr)
            handler.setFormatter(logging.Formatter("%(message)s"))
            self.logger.addHandler(handler)

    def emit(self, event: AuditEvent) -> None:
        self.logger.info(json.dumps(event.model_dump(mode="json"), sort_keys=True))

    def log(self, action: str, **kwargs: Any) -> None:
        """Compatibility adapter that intentionally ignores unapproved fields."""

        source, _, resource_kind = action.partition(".")
        locator = next(
            (
                kwargs[key]
                for key in ("path", "slug", "to_path", "from_path")
                if isinstance(kwargs.get(key), str)
            ),
            None,
        )
        outcome = str(kwargs.get("result", "unknown"))
        event = AuditEvent(
            timestamp=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            correlation_id=current_correlation_id(),
            principal_id=_opaque_principal(_principal_id.get()),
            source=source or "workspace",
            action=action,
            resource_kind=resource_kind or "resource",
            normalized_locator=locator,
            outcome=outcome,
            error_category="upstream_error" if "error" in kwargs else None,
            destructive="delete" in action or bool(kwargs.get("permanently")),
            duration_ms=max(0, int(kwargs.get("duration_ms", 0))),
        )
        self.emit(event)


audit_logger = AuditLogger()


class AuditContextMiddleware:
    def __init__(self, principal_provider: Callable[[], str]) -> None:
        self._principal_provider = principal_provider

    async def __call__(
        self, ctx: ServerRequestContext[Any, Any], call_next: CallNext
    ) -> HandlerResult:
        if ctx.method != "tools/call":
            return await call_next(ctx)
        with audit_context(
            correlation_id=uuid.uuid4().hex,
            principal_id=self._principal_provider(),
        ):
            return await call_next(ctx)
