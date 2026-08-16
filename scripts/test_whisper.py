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

# Check nvidia-cublas package
try:
    import nvidia.cublas
    print("✓ nvidia.cublas IMPORT: SUCCESS")
    pkg_dir = None
    if hasattr(nvidia.cublas, "__path__") and nvidia.cublas.__path__:
        pkg_dir = Path(nvidia.cublas.__path__[0])
    elif hasattr(nvidia.cublas, "__file__") and nvidia.cublas.__file__:
        pkg_dir = Path(nvidia.cublas.__file__).parent
        
    print("  File location:        ", pkg_dir)
    if pkg_dir:
        bin_dir = pkg_dir / "bin"
        print("  Bin folder exists:    ", bin_dir.is_dir())
        if bin_dir.is_dir():
            print("  Files in bin:         ", [f.name for f in bin_dir.glob("*")])
except ImportError as e:
    print("✗ nvidia.cublas IMPORT: FAILED")
    print("  Error:", e)

print("--------------------------------------------------")

# Check nvidia-cudnn package
try:
    import nvidia.cudnn
    print("✓ nvidia.cudnn IMPORT:  SUCCESS")
    pkg_dir = None
    if hasattr(nvidia.cudnn, "__path__") and nvidia.cudnn.__path__:
        pkg_dir = Path(nvidia.cudnn.__path__[0])
    elif hasattr(nvidia.cudnn, "__file__") and nvidia.cudnn.__file__:
        pkg_dir = Path(nvidia.cudnn.__file__).parent
        
    print("  File location:        ", pkg_dir)
    if pkg_dir:
        bin_dir = pkg_dir / "bin"
        print("  Bin folder exists:    ", bin_dir.is_dir())
        if bin_dir.is_dir():
            print("  Files in bin:         ", [f.name for f in bin_dir.glob("*")])
except ImportError as e:
    print("✗ nvidia.cudnn IMPORT:  FAILED")
    print("  Error:", e)

print("==================================================")
