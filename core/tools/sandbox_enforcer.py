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
        Resolves the target path and validates it.

        - If SANDBOX_MODE=false: resolves and returns the path unconditionally.
          Jarvis can operate on any path the OS user can access.
        - If SANDBOX_MODE=true: enforces that the path must reside inside one of
          the approved SANDBOX_ROOTS directories.

        Args:
            target_path: The file or directory path to validate.

        Returns:
            The resolved absolute Path object.

        Raises:
            PermissionError: If sandbox is ON and the path escapes allowed roots.
            ValueError: If sandbox is ON but no roots are configured.
        """
        target_str = str(target_path)
        is_windows = settings.is_windows or (platform.system() == "Windows")

        # Convert WSL drive paths (e.g. /mnt/c/Users/...) to Windows format on native Windows
        if is_windows:
            wsl_match = re.match(r"^/mnt/([a-zA-Z])/(.*)", target_str.replace("\\", "/"))
            if wsl_match:
                drive = wsl_match.group(1).upper()
                rest = wsl_match.group(2)
                target_str = f"{drive}:/{rest}"

        target_str_slash = target_str.replace("\\", "/")

        # Try resolving path directly
        try:
            resolved = Path(target_str).resolve()
        except Exception:
            resolved = Path(target_str)

        # Check if resolved is ALREADY inside one of allowed_roots
        is_already_allowed = False
        if self.allowed_roots:
            for root in self.allowed_roots:
                try:
                    resolved.relative_to(root.resolve())
                    is_already_allowed = True
                    break
                except ValueError:
                    continue

        if not is_already_allowed:
            # Catch actual fake placeholder path hallucinations
            # DO NOT catch real user home directories or valid absolute paths
            fake_path_pattern = r"(?:^/?sandbox/|^/?path/to/|<workspace_path>/|<workspace>/|<username>/?|your_username/?|/Users/(?:username|your_username)/|/home/(?:username|user)/)"

            if re.search(fake_path_pattern, target_str_slash, re.IGNORECASE):
                if "desktop" in target_str_slash.lower() or target_str_slash.lower().startswith("/sandbox/") or target_str_slash.lower().startswith("sandbox/"):
                    desktop = str(settings.desktop_dir.resolve()).replace("\\", "/") + "/"
                    target_str_slash = re.sub(fake_path_pattern + r"(?:desktop|sandbox)/?", desktop, target_str_slash, flags=re.IGNORECASE)
                else:
                    workspace = str(settings.default_workspace_dir.resolve()).replace("\\", "/") + "/"
                    target_str_slash = re.sub(fake_path_pattern, workspace, target_str_slash, flags=re.IGNORECASE)
                target_str_slash = target_str_slash.replace("//", "/")
                target_str = target_str_slash
                resolved = Path(target_str).resolve()

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
