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
    "delete_directory": RiskLevel.HIGH,
    
    # Memory Knowledge Graph (M4.5+)
    "graph_status": RiskLevel.LOW,
    "rebuild_knowledge_graph": RiskLevel.HIGH,
    "forget_document": RiskLevel.HIGH,
    
    # Dynamic Sub-Agents (M5+)
    "agent_builder": RiskLevel.CRITICAL,

    # Browser Automation (M6)
    "skyvern_tool": RiskLevel.MEDIUM,
}


class RiskClassifier:
    """Classifies risk level of tools and decides if confirmation is required."""

    def get_risk_level(self, tool_name: str) -> str:
        """Returns the risk level of the tool, defaulting to MEDIUM if unknown."""
        return TOOL_RISK_MAP.get(tool_name, RiskLevel.MEDIUM)

    def should_confirm(self, tool_name: str, args: dict = None) -> bool:
        """
        Determines if confirmation is required for a tool or action.
        If SAFE_MODE is 'off', no tools require confirmation.
        Otherwise:
        - Any HIGH risk profile tool or deletion tool requires user confirmation.
        - Any tool invocation (e.g. delegate_task) whose arguments contain destructive parameters/keywords requires confirmation.
        - Browser actions with critical intents (submit, purchase, password) require confirmation.
        """
        import json
        if settings.safe_mode == "off":
            return False

        # Explicit destructive tool names or RiskLevel.HIGH
        destructive_tools = {
            "file_cleanup", "forget_document", "delete_directory",
            "delete_file", "remove_file", "remove_directory"
        }
        if tool_name in destructive_tools:
            return True
        if self.get_risk_level(tool_name) == RiskLevel.HIGH:
            return True

        # Browser action risk escalation: critical actions require confirmation
        if tool_name == "skyvern_tool" and args and isinstance(args, dict):
            goal = (args.get("navigation_goal") or "").lower()
            critical_browser_actions = (
                "submit", "purchase", "buy", "pay", "checkout",
                "send message", "send email", "delete", "cancel",
                "password", "change password", "security", "transfer"
            )
            if any(w in goal for w in critical_browser_actions):
                return True

        # Check arguments for destructive parameters/keywords (e.g. delegated tasks)
        if args and isinstance(args, dict):
            args_str = json.dumps(args).lower()
            if any(w in args_str for w in ("delete", "remove", "trash", "purge", "erase", "destroy")):
                return True

        return False


# Global risk classifier singleton
risk_classifier = RiskClassifier()
