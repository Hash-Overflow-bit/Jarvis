"""
core/tools/sandbox_enforcer.py
==============================
Validates all path inputs to ensure they do not escape authorized sandbox directories.
Prevents directory traversal (e.g. `../../`) and symlink attacks.

Sandbox Mode:
  SANDBOX_MODE=true  (default) — restricts all operations to SANDBOX_ROOTS paths only.
  SANDBOX_MODE=false           — unrestricted mode: Jarvis can read/write/delete anywhere
                                 on the filesystem that the OS user has permission to access.
"""

import platform
from pathlib import Path
from typing import Union
import re
from core.config import settings


class SandboxEnforcer:
    """
    Validates target paths against the configured sandbox roots.
    When sandbox_mode is disabled, all paths are permitted (unrestricted mode).
    """

    def __init__(self, allowed_roots: list[Path] | None = None):
        # Track whether explicit roots were passed (used to determine enforce mode)
        self._custom_roots_provided = allowed_roots is not None

        # Fall back to config settings if no custom roots provided
        roots = allowed_roots if allowed_roots is not None else settings.sandbox_roots
        self.allowed_roots = [p.resolve() for p in roots]

        # Automatically whitelist default workspace directory for M3 git/poetry tools
        try:
            workspace = settings.default_workspace_dir
            if workspace not in self.allowed_roots:
                self.allowed_roots.append(workspace)
        except Exception:
            pass

    @property
    def _sandbox_enabled(self) -> bool:
        """
        Returns True if sandbox path restrictions are active.

        - If explicit allowed_roots were passed to __init__ (e.g. in unit tests),
          sandbox is ALWAYS enforced regardless of SANDBOX_MODE.
        - If using the global default enforcer (no custom roots), respects SANDBOX_MODE.
          SANDBOX_MODE=false → unrestricted (bypass). SANDBOX_MODE=true → enforced.
        """
        if self._custom_roots_provided:
            # Always enforce when caller explicitly specified roots
            return True
        return settings.sandbox_mode

    def validate(self, target_path: Union[str, Path]) -> Path:
        """
        Resolves the target path using PathResolver and validates it against sandbox roots.
        """
        from core.tools.path_resolver import PathResolver
        
        # 1. Resolve path deterministically
        resolved = PathResolver.resolve(target_path)

        # --- Unrestricted mode: allow any path ---
        if not self._sandbox_enabled:
            return resolved

        # --- Sandbox mode: check against allowed roots ---
        if not self.allowed_roots:
            raise ValueError(
                "Sandbox security failure: No allowed sandbox roots are configured. "
                "Please configure SANDBOX_ROOTS in your .env file."
            )

        for root in self.allowed_roots:
            try:
                resolved.relative_to(root.resolve())
                return resolved
            except ValueError:
                continue

        raise PermissionError(
            f"Security Violation: Path '{resolved}' escapes all approved sandbox roots: "
            f"{[str(r) for r in self.allowed_roots]}"
        )


# Global enforcer instance utilizing settings
enforcer = SandboxEnforcer()
