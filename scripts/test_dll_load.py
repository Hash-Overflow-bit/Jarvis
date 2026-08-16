"""
scripts/test_dll_load.py
========================
Diagnose the exact DLL load failure using ctypes.WinDLL.
"""

import os
import sys
import ctypes
import platform
from pathlib import Path

print("==================================================")
print(" Windows DLL Load Diagnostics")
print("==================================================")

if platform.system() != "Windows":
    print("This script is only for Windows diagnostic testing.")
    sys.exit(1)

try:
    import nvidia.cublas
    pkg_dir = Path(nvidia.cublas.__path__[0])
    nvidia_dir = pkg_dir.parent
    print("Registering DLL paths:")
    for sub in nvidia_dir.iterdir():
        if sub.is_dir():
            bin_dir = sub / "bin"
            if bin_dir.is_dir():
                print(f"  Adding: {bin_dir}")
                os.add_dll_directory(str(bin_dir))
except Exception as e:
    print("Failed to resolve nvidia path:", e)
    sys.exit(1)

print("--------------------------------------------------")

# Test 1: Load cudart64_12.dll
try:
    print("Testing load: cudart64_12.dll ...")
    ctypes.WinDLL("cudart64_12.dll")
    print("✓ SUCCESS: cudart64_12.dll loaded!")
except Exception as e:
    print("✗ FAILED: cudart64_12.dll could not be loaded.")
    print("  Error:", e)

print("--------------------------------------------------")

# Test 2: Load cublasLt64_12.dll
try:
    print("Testing load: cublasLt64_12.dll ...")
    ctypes.WinDLL("cublasLt64_12.dll")
    print("✓ SUCCESS: cublasLt64_12.dll loaded!")
except Exception as e:
    print("✗ FAILED: cublasLt64_12.dll could not be loaded.")
    print("  Error:", e)

print("--------------------------------------------------")

# Test 3: Load cublas64_12.dll
try:
    print("Testing load: cublas64_12.dll ...")
    ctypes.WinDLL("cublas64_12.dll")
    print("✓ SUCCESS: cublas64_12.dll loaded!")
except Exception as e:
    print("✗ FAILED: cublas64_12.dll could not be loaded.")
    print("  Error:", e)

print("==================================================")
