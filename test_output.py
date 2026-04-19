# -*- coding: utf-8 -*-
print("=== Test script started ===")
import sys
print(f"Python version: {sys.version}")
print(f"Encoding: {sys.stdout.encoding}")

try:
    sys.stdout.flush()
except Exception as e:
    print(f"Flush error: {e}")

import argparse
pa = argparse.ArgumentParser()
pa.add_argument("--test", action="store_true")
args = pa.parse_args()
print(f"Args: {args}")
print("=== Test script completed ===")
