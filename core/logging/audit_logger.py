"""
core/logging/audit_logger.py
============================
Rotating file-based audit logger for tracking tool requests and authorization.
"""

import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from datetime import datetime, timezone
from core.config import settings


class AuditLogger:
    """Manages secure, structured JSON logging of all agent actions."""

    def __init__(self):
        self.log_path = Path(settings.audit_log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

        self.logger = logging.getLogger("jarvis_audit")
        self.logger.setLevel(logging.INFO)
        self.logger.propagate = False  # Avoid duplicates in standard console log

        # Setup rotating file handler (5MB limit, keep 5 backups)
        handler = RotatingFileHandler(
            self.log_path,
            maxBytes=5 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8"
        )
        formatter = logging.Formatter("%(message)s")
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)

    def log_action(
        self,
        tool_name: str,
        parameters: dict,
        status: str,
        details: str = "",
        result: str = "N/A"
    ):
        """
        Log a tool authorization or execution event.

        Statuses:
        - PENDING: Intercepted by confirmation gate.
        - APPROVED: Approved by user.
        - DENIED: Aborted by user.
        - BYPASSED: Low risk tool ran directly.
        - DRY_RUN: Simulated execution.
        """
        # Scrub sensitive tokens from logging parameters
        scrubbed_params = {}
        for k, v in parameters.items():
            if "token" in k.lower() or "password" in k.lower():
                scrubbed_params[k] = "[REDACTED]"
            else:
                scrubbed_params[k] = v

        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tool": tool_name,
            "parameters": scrubbed_params,
            "authorization_status": status,
            "details": details,
            "result_status": result,
        }
        self.logger.info(json.dumps(record))


# Global audit logger singleton
audit_logger = AuditLogger()
