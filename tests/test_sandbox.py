"""
tests/test_sandbox.py
=====================
Unit tests for the SandboxEnforcer paths security boundaries.
Validates blocking of directory traversal, external paths, and symlink escapes.
"""

import os
import tempfile
import pytest
from pathlib import Path
from core.tools.sandbox_enforcer import SandboxEnforcer


@pytest.fixture
def temp_sandbox_setup():
    """Sets up a temporary directory environment for testing sandboxing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        root_path = Path(temp_dir).resolve()
        
        # Create directories inside the root
        allowed_dir = root_path / "allowed_sandbox"
        allowed_dir.mkdir()
        
        forbidden_dir = root_path / "forbidden_area"
        forbidden_dir.mkdir()
        
        # Create dummy file outside sandbox
        secret_file = forbidden_dir / "secret.txt"
        secret_file.write_text("super secret data")
        
        yield allowed_dir, forbidden_dir, secret_file


def test_sandbox_allows_valid_path(temp_sandbox_setup):
    allowed_dir, _, _ = temp_sandbox_setup
    enforcer = SandboxEnforcer([allowed_dir])

    # Path directly inside
    test_file = allowed_dir / "test.txt"
    test_file.write_text("hello")

    # Should pass validation
    validated = enforcer.validate(test_file)
    assert validated == test_file.resolve()


def test_sandbox_blocks_outside_path(temp_sandbox_setup):
    allowed_dir, _, secret_file = temp_sandbox_setup
    enforcer = SandboxEnforcer([allowed_dir])

    # Direct access to forbidden file
    with pytest.raises(PermissionError):
        enforcer.validate(secret_file)


def test_sandbox_blocks_directory_traversal(temp_sandbox_setup):
    allowed_dir, _, _ = temp_sandbox_setup
    enforcer = SandboxEnforcer([allowed_dir])

    # Traversal attempt
    traversal_path = allowed_dir / "../forbidden_area/secret.txt"
    
    with pytest.raises(PermissionError):
        enforcer.validate(traversal_path)


def test_sandbox_blocks_symlink_escape(temp_sandbox_setup):
    allowed_dir, _, secret_file = temp_sandbox_setup
    enforcer = SandboxEnforcer([allowed_dir])

    # Create a symlink inside allowed_dir pointing to secret_file outside
    symlink_path = allowed_dir / "escape_link.txt"
    
    try:
        symlink_path.symlink_to(secret_file)
    except OSError:
        # Skip if symlink creation is not permitted by OS (e.g. non-admin on Windows)
        pytest.skip("Symlinks not supported or permitted on this OS / environment")

    # Enforcer must resolve the symlink and block it
    with pytest.raises(PermissionError):
        enforcer.validate(symlink_path)

    # Clean up symlink
    symlink_path.unlink()
