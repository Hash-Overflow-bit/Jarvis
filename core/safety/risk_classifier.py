"""
core/safety/risk_classifier.py
==============================
Risk classification system for Jarvis tools.
"""

from core.config import settings


class RiskLevel:
    LOW = "low"          # Read-only, no side effects
    MEDIUM = "medium"    # State change, downloads code, reversible writes
    HIGH = "high"        # Destruction, deletes files, overrides changes
    CRITICAL = "critical"  # Dynamic execution, code compilation, pushing to remote


# Map registered tools to their standard risk profiles
TOOL_RISK_MAP = {
    "file_scanner": RiskLevel.LOW,
    "directory_audit": RiskLevel.LOW,
    "file_cleanup": RiskLevel.HIGH,
    "git_clone": RiskLevel.MEDIUM,
    "git_pull": RiskLevel.MEDIUM,
    "git_status": RiskLevel.LOW,
    "git_add": RiskLevel.MEDIUM,
    "git_commit": RiskLevel.MEDIUM,
    "git_push": RiskLevel.CRITICAL,
    "poetry_install": RiskLevel.MEDIUM,
    "poetry_add": RiskLevel.MEDIUM,
    "poetry_show": RiskLevel.LOW,
    
    # File Manipulation (M4.5+)
    "create_directory": RiskLevel.MEDIUM,
    "write_file": RiskLevel.MEDIUM,
    
    # Memory Knowledge Graph (M4.5+)
    "graph_status": RiskLevel.LOW,
    "rebuild_knowledge_graph": RiskLevel.HIGH,
    "forget_document": RiskLevel.HIGH,
}


class RiskClassifier:
    """Classifies risk level of tools and decides if confirmation is required."""

    def get_risk_level(self, tool_name: str) -> str:
        """Returns the risk level of the tool, defaulting to MEDIUM if unknown."""
        return TOOL_RISK_MAP.get(tool_name, RiskLevel.MEDIUM)

    def should_confirm(self, tool_name: str) -> bool:
        """
        Determines if confirmation is required for a tool based on SAFE_MODE.

        SAFE_MODE rules:
        - 'off': never confirm.
        - 'permissive': confirm HIGH and CRITICAL risks.
        - 'strict': confirm MEDIUM, HIGH, and CRITICAL risks.
        """
        mode = settings.safe_mode
        if mode == "off":
            return False

        risk = self.get_risk_level(tool_name)

        if mode == "permissive":
            return risk in [RiskLevel.HIGH, RiskLevel.CRITICAL]

        if mode == "strict":
            return risk in [RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL]

        return True


# Global risk classifier singleton
risk_classifier = RiskClassifier()
