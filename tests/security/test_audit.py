import json
import logging

from yandex_workspace_mcp.security.audit import (
    AuditEvent,
    AuditLogger,
    audit_context,
)


def test_audit_event_emits_only_normative_fields() -> None:
    records: list[str] = []

    class Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record.getMessage())

    logger = logging.getLogger("test.audit.normative")
    logger.handlers = [Capture()]
    logger.propagate = False
    audit = AuditLogger(logger=logger)
    with audit_context(correlation_id="corr", principal_id="person@example.com"):
        audit.emit(
            AuditEvent(
                timestamp="2026-08-11T00:00:00Z",
                correlation_id="corr",
                principal_id="opaque-principal",
                source="wiki",
                action="wiki.update_page",
                resource_kind="page",
                normalized_locator="Team/Page",
                outcome="success",
                error_category=None,
                destructive=False,
                duration_ms=12,
            )
        )

    event = json.loads(records[0])
    assert set(event) == {
        "timestamp",
        "correlation_id",
        "principal_id",
        "source",
        "action",
        "resource_kind",
        "normalized_locator",
        "outcome",
        "error_category",
        "destructive",
        "duration_ms",
    }


def test_legacy_audit_adapter_drops_content_tokens_and_raw_errors() -> None:
    records: list[str] = []

    class Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record.getMessage())

    logger = logging.getLogger("test.audit.legacy")
    logger.handlers = [Capture()]
    logger.propagate = False
    audit = AuditLogger(logger=logger)
    with audit_context(correlation_id="corr", principal_id="principal"):
        audit.log(
            "disk.delete",
            path="/Work/report.md",
            result="failure",
            error="Bearer super-secret https://host/path?token=secret",
            content="private document",
        )

    serialized = records[0]
    assert "super-secret" not in serialized
    assert "private document" not in serialized
    assert "token=secret" not in serialized
    event = json.loads(serialized)
    assert event["action"] == "disk.delete"
    assert event["normalized_locator"] == "/Work/report.md"
    assert event["destructive"] is True
