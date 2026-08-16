"""
scripts/test_whisper.py
=======================
Diagnostic script to check Windows CUDA DLL loading paths.
"""

import os
import sys
import platform
from pathlib import Path

print("==================================================")
print(" Jarvis STT CUDA Diagnostics")
print("==================================================")
print("OS:", platform.system())
print("Python Path:", sys.executable)
print("Working Directory:", os.getcwd())

# Check site-packages paths
for p in sys.path:
    if "site-packages" in p.lower():
        print("Search Path:", p)

print("--------------------------------------------------")

# Check nvidia package structure
try:
    import nvidia.cublas
    print("✓ nvidia.cublas IMPORT: SUCCESS")
    pkg_dir = None
    if hasattr(nvidia.cublas, "__path__") and nvidia.cublas.__path__:
        pkg_dir = Path(nvidia.cublas.__path__[0])
    elif hasattr(nvidia.cublas, "__file__") and nvidia.cublas.__file__:
        pkg_dir = Path(nvidia.cublas.__file__).parent
        
    if pkg_dir:
        nvidia_dir = pkg_dir.parent
        print("  nvidia root folder:   ", nvidia_dir)
        if nvidia_dir.is_dir():
            for sub in nvidia_dir.iterdir():
                if sub.is_dir():
                    bin_dir = sub / "bin"
                    print(f"  - Subpackage '{sub.name}': bin exists: {bin_dir.is_dir()}")
                    if bin_dir.is_dir():
                        print(f"    DLLs: {[f.name for f in bin_dir.glob('*')]}")
except ImportError as e:
    print("✗ nvidia.cublas IMPORT: FAILED")
    print("  Error:", e)

print("==================================================")
