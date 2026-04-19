# -*- coding: utf-8 -*-
"""Check network and API connectivity"""

print("=" * 70)
print("Network and API Connectivity Check")
print("=" * 70)
print("")

import requests
import json

# Test 1: Internet connectivity
print("Test 1: Internet connectivity...")
try:
    response = requests.get("https://www.google.com", timeout=5)
    print("  OK: Internet is accessible")
except Exception as e:
    print(f"  FAILED: Internet error: {e}")

# Test 2: Hyperliquid mainnet DNS
print("\nTest 2: Hyperliquid mainnet DNS...")
try:
    response = requests.get("https://api.hyperliquid.xyz", timeout=10)
    print(f"  OK: Hyperliquid mainnet is accessible (Status: {response.status_code})")
except Exception as e:
    print(f"  FAILED: {e}")

# Test 3: Hyperliquid testnet DNS
print("\nTest 3: Hyperliquid testnet DNS...")
try:
    response = requests.get("https://api.hyperliquid.testnet", timeout=10)
    print(f"  OK: Hyperliquid testnet is accessible (Status: {response.status_code})")
except Exception as e:
    print(f"  FAILED: {e}")

# Test 4: Check firewall/proxy
print("\nTest 4: Check for proxy settings...")
import urllib.request
try:
    proxy = urllib.request.getproxies()
    if proxy:
        print(f"  WARNING: Proxy detected: {proxy}")
    else:
        print("  OK: No proxy detected")
except Exception as e:
    print(f"  ERROR: {e}")

print("")
print("=" * 70)
print("Recommendations:")
print("=" * 70)
print("1. If API is blocked, try using VPN or check firewall")
print("2. Make sure you have stable internet connection")
print("3. Try running again in a few minutes")
print("=" * 70)
