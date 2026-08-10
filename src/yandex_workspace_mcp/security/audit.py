from datetime import datetime, timezone
from typing import Any
from yandex_workspace_mcp.logging import get_logger

logger = get_logger("audit")

def log_audit_event(system: str, operation: str, target: str, result: str, **extra: Any) -> None:
    """Log an audit event for a write/destructive operation."""
    # Ensure we never log tokens or content by sanitizing extra fields
    safe_extra = {k: v for k, v in extra.items() if k not in ("token", "content", "authorization")}
    
    logger.info(
        "Audit event",
        audit_event=True,
        system=system,
        operation=operation,
        target=target,
        result=result,
        **safe_extra
    )
