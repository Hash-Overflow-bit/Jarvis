"""
core/tools/path_resolver.py
===========================
Deterministic filesystem path resolver.
Resolves natural language location intents (e.g., "desktop", "documents", "downloads")
into canonical absolute Path objects, accounting for cross-platform differences
and OneDrive redirections on Windows.
"""

import os
from pathlib import Path
from core.config import settings

class PathResolver:
    """Central utility for resolving abstract paths into absolute filesystem paths."""

    @classmethod
    def resolve(cls, target_path: str | Path) -> Path:
        """
        Resolves an abstract target string to an absolute path.
        Understands location aliases like "desktop", "home", "documents", "downloads", "workspace".
        """
        target_str = str(target_path).strip().replace("\\", "/")
        
        # Strip trailing slash if any
        if target_str.endswith("/") and len(target_str) > 1:
            target_str = target_str[:-1]
            
        lower_target = target_str.lower()
        
        # 1. Resolve exact aliases
        if lower_target in ("desktop", "~/desktop"):
            return settings.desktop_dir
        if lower_target in ("home", "~"):
            return Path.home().resolve()
        if lower_target in ("workspace", "<workspace_path>", "<workspace>"):
            return settings.default_workspace_dir
            
        home = Path.home()
        # 2. Support known standard subfolders explicitly
        if lower_target in ("documents", "~/documents"):
            return cls._find_standard_folder("Documents")
        if lower_target in ("downloads", "~/downloads"):
            return cls._find_standard_folder("Downloads")
            
        # 3. Resolve prefix aliases
        # Handle cases like "desktop/report.txt"
        if lower_target.startswith("desktop/") or lower_target.startswith("~/desktop/"):
            remainder = target_str.split("/", 1)[1] if not lower_target.startswith("~/") else target_str[10:]
            return settings.desktop_dir / remainder
            
        if lower_target.startswith("documents/") or lower_target.startswith("~/documents/"):
            remainder = target_str.split("/", 1)[1] if not lower_target.startswith("~/") else target_str[12:]
            return cls._find_standard_folder("Documents") / remainder
            
        if lower_target.startswith("downloads/") or lower_target.startswith("~/downloads/"):
            remainder = target_str.split("/", 1)[1] if not lower_target.startswith("~/") else target_str[12:]
            return cls._find_standard_folder("Downloads") / remainder
            
        if lower_target.startswith("workspace/"):
            remainder = target_str.split("/", 1)[1]
            return settings.default_workspace_dir / remainder
            
        if target_str.startswith("~/"):
            return home / target_str[2:]
            
        # 4. Filter out LLM fake usernames (prevent escaping if sandbox is off)
        if target_str.startswith("/Users/username/") or target_str.startswith("/home/username/") or target_str.startswith("/Users/your_username/"):
            # Redirect to true home
            parts = target_str.split("/")
            remainder = "/".join(parts[3:])
            return (home / remainder).resolve()
            
        # 5. Default: resolve relative or absolute path
        try:
            return Path(target_str).resolve()
        except Exception:
            return Path(target_str)
            
    @classmethod
    def _find_standard_folder(cls, folder_name: str) -> Path:
        """Finds standard folders like Documents or Downloads, checking OneDrive."""
        home = Path.home()
        
        # Check direct home first
        direct = home / folder_name
        if direct.exists() and direct.is_dir():
            return direct.resolve()
            
        # Check OneDrive
        onedrive1 = home / "OneDrive" / folder_name
        if onedrive1.exists() and onedrive1.is_dir():
            return onedrive1.resolve()
            
        onedrive2 = home / "onedrive" / folder_name
        if onedrive2.exists() and onedrive2.is_dir():
            return onedrive2.resolve()
            
        # Check WSL Windows User Profile (if applicable)
        if settings.is_wsl or settings.os_name.lower() == "linux":
            try:
                import getpass
                mnt_c_users = Path("/mnt/c/Users")
                current_user = getpass.getuser()
                if mnt_c_users.exists():
                    active_win_user = mnt_c_users / current_user
                    win_folder = active_win_user / folder_name
                    if win_folder.exists() and win_folder.is_dir():
                        return win_folder.resolve()
                        
                    win_onedrive = active_win_user / "OneDrive" / folder_name
                    if win_onedrive.exists() and win_onedrive.is_dir():
                        return win_onedrive.resolve()
            except Exception:
                pass
                
        # Default fallback (might not exist yet, but is standard)
        return (home / folder_name).resolve()
