import subprocess
import sys

# Try different installation methods
methods = [
    ["pip", "install", "--prefer-binary", "hyperliquid-python-sdk>=0.3.0"],
    ["pip", "install", "--only-binary", ":all:", "hyperliquid-python-sdk"],
    ["pip", "install", "hyperliquid>=2.0"],
]

for cmd in methods:
    print(f"Trying: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        print("Success!")
        sys.exit(0)
    print(f"Failed: {result.stderr[-200:]}\n")

print("All methods failed. Please install manually.")
