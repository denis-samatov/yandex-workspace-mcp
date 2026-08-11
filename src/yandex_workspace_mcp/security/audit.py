import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any


class AuditLogger:
    def __init__(self, name: str = "mcp.audit"):
        self.logger = logging.getLogger(name)
        # Prevent double logging if attached to root
        self.logger.propagate = False
        
        if not self.logger.handlers:
            handler = logging.StreamHandler(sys.stderr)
            handler.setFormatter(logging.Formatter('%(message)s'))
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)

    def log(self, action: str, **kwargs: Any) -> None:
        """
        Log an audit event in JSON format.
        
        Args:
            action: The action being performed (e.g., 'disk.delete', 'wiki.update_page')
            **kwargs: Additional contextual data (e.g., path, slug, user details)
        """
        event = {
            "timestamp": datetime.now(UTC).isoformat(),
            "type": "audit",
            "action": action,
            **kwargs
        }
        self.logger.info(json.dumps(event))

audit_logger = AuditLogger()
