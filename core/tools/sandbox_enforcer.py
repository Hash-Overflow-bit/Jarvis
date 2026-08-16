"""
core/tools/sandbox_enforcer.py
==============================
Validates all path inputs to ensure they do not escape authorized sandbox directories.
Prevents directory traversal (e.g. `../../`) and symlink attacks.
"""

from pathlib import Path
from typing import Union
from core.config import settings


class SandboxEnforcer:
    """
    Validates target paths against the configured sandbox roots.
    """

    def __init__(self, allowed_roots: list[Path] | None = None):
        # Fall back to config settings if no custom roots provided
        roots = allowed_roots if allowed_roots is not None else settings.sandbox_roots
        self.allowed_roots = [p.resolve() for p in roots]

    def validate(self, target_path: Union[str, Path]) -> Path:
        """
        Resolves the target path to an absolute path, ensuring any symbolic links
        or relative segments (like '..') are resolved, and checks that it resides
        strictly within one of the approved sandbox roots.

        Args:
            target_path: The file or directory path to validate.

        Returns:
            The resolved absolute Path object.

        Raises:
            PermissionError: If the path escapes the sandbox boundaries.
            ValueError: If there are no sandbox roots configured.
        """
        if not self.allowed_roots:
            raise ValueError(
                "Sandbox security failure: No allowed sandbox roots are configured. "
                "Please configure SANDBOX_ROOTS in your .env file."
            )

        # Resolve the path to get absolute path and expand symlinks
        resolved = Path(target_path).resolve()

        for root in self.allowed_roots:
            try:
                # relative_to raises ValueError if resolved is not inside root
                resolved.relative_to(root)
                return resolved
            except ValueError:
                continue

        raise PermissionError(
            f"Security Violation: Path '{resolved}' escapes all approved sandbox roots: "
            f"{[str(r) for r in self.allowed_roots]}"
        )


# Global enforcer instance utilizing settings
enforcer = SandboxEnforcer()
