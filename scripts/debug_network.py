#!/usr/bin/env python3
import socket
import urllib.request
import urllib.error
import re
import sys
from pathlib import Path
import subprocess

def get_nameservers():
    ips = []
    try:
        resolv = Path("/etc/resolv.conf")
        if resolv.exists():
            for line in resolv.read_text().splitlines():
                if "nameserver" in line:
                    parts = line.split()
                    if len(parts) >= 2:
                        ips.append(parts[1])
    except Exception as e:
        print(f"Error reading /etc/resolv.conf: {e}")
    return ips

def get_default_gateway():
    try:
        # Run ip route show to get default gateway
        result = subprocess.run(["ip", "route", "show"], capture_output=True, text=True)
        for line in result.stdout.splitlines():
            if line.startswith("default via"):
                parts = line.split()
                if len(parts) >= 3:
                    return parts[2]
    except Exception as e:
        print(f"Error running ip route: {e}")
    return None

def test_connection(ip, port=11434):
    url = f"http://{ip}:{port}/"
    print(f"Testing connection to {url} ... ", end="", flush=True)
    try:
        # 2 seconds timeout
        req = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(req, timeout=2.0) as response:
            print(f"SUCCESS! Status code: {response.status}")
            return True
    except urllib.error.HTTPError as e:
        # Ollama root endpoint might return 404 but it is reachable
        print(f"SUCCESS (HTTPError but reachable)! Status code: {e.code}")
        return True
    except urllib.error.URLError as e:
        reason = e.reason
        if isinstance(reason, socket.timeout):
            print("FAILED (Timeout - likely Windows Firewall blocking or wrong IP)")
        elif isinstance(reason, ConnectionRefusedError):
            print("FAILED (Connection Refused - Ollama not running on this IP/port)")
        else:
            print(f"FAILED (Error: {reason})")
        return False
    except Exception as e:
        print(f"FAILED (Unexpected: {e})")
        return False

def main():
    print("=" * 60)
    print("           WSL 2 -> WINDOWS OLLAMA NETWORK AUDIT")
    print("=" * 60)
    
    # 1. Gather all candidate IPs
    candidates = ["127.0.0.1", "localhost"]
    
    nameservers = get_nameservers()
    print(f"Nameservers from /etc/resolv.conf: {nameservers}")
    for ns in nameservers:
        if ns not in candidates:
            candidates.append(ns)
            
    gateway = get_default_gateway()
    print(f"Default Gateway from ip route: {gateway}")
    if gateway and gateway not in candidates:
        candidates.append(gateway)
        
    # Try host.docker.internal
    try:
        host_ip = socket.gethostbyname("host.docker.internal")
        print(f"Resolved host.docker.internal to: {host_ip}")
        if host_ip not in candidates:
            candidates.append(host_ip)
    except socket.gaierror:
        print("Could not resolve host.docker.internal")

    # 2. Test each candidate
    print("\n--- Starting Connection Tests (Port 11434) ---")
    successful_ips = []
    for ip in candidates:
        if test_connection(ip):
            successful_ips.append(ip)
            
    # 3. Output summary and recommendation
    print("\n" + "=" * 60)
    print("                       SUMMARY & FIX")
    print("=" * 60)
    if successful_ips:
        recommended = successful_ips[0]
        print(f"🎉 Ollama was successfully reached at these IPs: {successful_ips}")
        print(f"\n👉 Update your '.env' file to use:")
        print(f"   OLLAMA_BASE_URL=http://{recommended}:11434")
    else:
        print("❌ Ollama could not be reached on ANY candidate IP address.")
        print("\nPossible solutions:")
        print("1. Verify Ollama is actually running on Windows (tray icon is visible).")
        print("2. Verify Ollama is listening on 0.0.0.0 (run: 'netstat -ano | findstr 11434' in PowerShell).")
        print("3. Check if a Windows Firewall rule is blocking TCP port 11434.")
        print("4. Third-party antivirus (Avast, McAfee, etc.) may be blocking connections.")
    print("=" * 60)

if __name__ == "__main__":
    main()
