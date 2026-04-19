# -*- coding: utf-8 -*-
# Syntax error fix script
import sys

with open('force_run_hl.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Print lines 891-903
print("Lines 891-903:")
for i in range(890, 903):
    print(f"{i+1}: {repr(lines[i])}")
