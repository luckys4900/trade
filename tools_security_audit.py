#!/usr/bin/env python3
"""
Everything Claude Code: Security Audit for Trading System
Scans for common vulnerabilities in trading bot code
"""

import json
import re
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent

# Security checks
SECURITY_CHECKS = {
    "hardcoded_secrets": {
        "patterns": [
            r"api_key\s*=\s*['\"][\w\-]{20,}['\"]",
            r"secret\s*=\s*['\"][\w\-]{20,}['\"]",
            r"password\s*=\s*['\"][\w\-]{8,}['\"]",
            r"token\s*=\s*['\"][\w\-]{20,}['\"]",
        ],
        "risk": "HIGH",
        "description": "Hardcoded API keys/secrets in source code"
    },
    "unvalidated_user_input": {
        "patterns": [
            r"eval\s*\(",
            r"exec\s*\(",
            r"pickle\.loads",
            r"yaml\.load",
        ],
        "risk": "HIGH",
        "description": "Dangerous functions that can execute arbitrary code"
    },
    "sql_injection": {
        "patterns": [
            r"query\s*=\s*['\"]SELECT.*[+%].*['\"]",
            r"execute\s*\(\s*f['\"]",
        ],
        "risk": "HIGH",
        "description": "Potential SQL injection vulnerabilities"
    },
    "insecure_random": {
        "patterns": [
            r"random\.random\s*\(",
            r"random\.choice\s*\(",
        ],
        "risk": "MEDIUM",
        "description": "Weak random number generation for crypto"
    },
    "missing_input_validation": {
        "patterns": [
            r"float\s*\(\s*user_input",
            r"int\s*\(\s*user_input",
            r"json\.loads\s*\(\s*request",
        ],
        "risk": "MEDIUM",
        "description": "Input not validated before processing"
    },
    "insecure_api_calls": {
        "patterns": [
            r"requests\.get\s*\(\s*['\"]http://[^s]",
            r"verify\s*=\s*False",
            r"ssl\._create_unverified_context",
        ],
        "risk": "MEDIUM",
        "description": "Insecure HTTP or disabled SSL verification"
    },
    "exception_swallowing": {
        "patterns": [
            r"except\s*:\s*pass",
            r"except\s*Exception\s*:\s*pass",
        ],
        "risk": "LOW",
        "description": "Bare except clauses hide errors"
    }
}

def scan_python_files():
    """Scan all Python files in project"""
    py_files = list(PROJECT_ROOT.glob("*.py"))
    print(f"[*] Found {len(py_files)} Python files to scan")
    return py_files

def audit_file(filepath):
    """Audit single file for security issues"""
    issues = []
    
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
            lines = content.split('\n')
    except Exception as e:
        return [{"file": filepath.name, "error": str(e)}]

    # Check each security pattern
    for check_name, check_config in SECURITY_CHECKS.items():
        for pattern in check_config.get("patterns", []):
            for line_num, line in enumerate(lines, 1):
                if re.search(pattern, line, re.IGNORECASE):
                    issues.append({
                        "file": filepath.name,
                        "line": line_num,
                        "check": check_name,
                        "risk": check_config["risk"],
                        "description": check_config["description"],
                        "code": line.strip()[:80]
                    })
    
    return issues

def generate_report(all_issues):
    """Generate security audit report"""
    
    # Summary by risk level
    summary = {
        "HIGH": len([i for i in all_issues if i.get("risk") == "HIGH"]),
        "MEDIUM": len([i for i in all_issues if i.get("risk") == "MEDIUM"]),
        "LOW": len([i for i in all_issues if i.get("risk") == "LOW"]),
        "TOTAL": len(all_issues)
    }

    report = f"""# Security Audit Report

Generated: 2026-04-16
Tool: Everything Claude Code Security Scanner

## Summary

- HIGH Risk: {summary["HIGH"]}
- MEDIUM Risk: {summary["MEDIUM"]}
- LOW Risk: {summary["LOW"]}
- TOTAL Issues: {summary["TOTAL"]}

## Recommendations

### For HIGH Risk Issues:
1. Remove all hardcoded secrets
2. Use environment variables or .env files
3. Never commit credentials to git
4. Review code for dangerous functions (eval, exec, etc.)

### For MEDIUM Risk Issues:
1. Validate all user inputs
2. Use HTTPS for API calls
3. Enable SSL/TLS verification
4. Use cryptographically secure random (secrets module)

### For LOW Risk Issues:
1. Replace bare except: with specific exception handling
2. Log caught exceptions for debugging
3. Don't silently fail - raise or log

## Trading Bot Specific Checks

✓ Critical for trading systems:
  - API keys never hardcoded
  - All network calls use HTTPS
  - Position sizes validated (no division by zero, etc.)
  - Trade prices checked for sanity (no negative, infinite, etc.)
  - Order amounts validated before execution
  - Emergency stop logic tested

## Next Steps

1. Fix all HIGH risk issues immediately
2. Plan MEDIUM risk remediation
3. Document LOW risk decisions
4. Enable pre-commit hooks to prevent credential commits:
   - pip install detect-secrets
   - detect-secrets scan > .secrets.baseline
   - Add to git pre-commit hook

---
**Status**: Review Required
**Action**: Fix HIGH and MEDIUM risk issues before production
"""

    if all_issues:
        report += "\n## Detailed Findings\n\n"
        for issue in sorted(all_issues, key=lambda x: x.get("risk", "LOW")):
            report += f"""
### {issue.get('file', 'unknown')}:{issue.get('line', '?')}
**Risk**: {issue.get('risk', 'UNKNOWN')}
**Check**: {issue.get('check', 'unknown')}
**Description**: {issue.get('description', 'N/A')}
**Code**: `{issue.get('code', 'N/A')}`
"""

    return report

if __name__ == "__main__":
    print("=" * 70)
    print("Everything Claude Code: Security Audit")
    print("=" * 70)

    # Scan files
    print("\n[*] Scanning for security issues...")
    py_files = scan_python_files()
    
    all_issues = []
    for filepath in py_files[:10]:  # Limit to first 10 files
        print(f"  Checking {filepath.name}...", end="")
        issues = audit_file(filepath)
        all_issues.extend(issues)
        print(f" [{len(issues)} issues]" if issues else " [OK]")

    # Generate report
    print("\n[*] Generating report...")
    report = generate_report(all_issues)

    # Save report
    report_file = PROJECT_ROOT / "SECURITY_AUDIT_REPORT.md"
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(report)

    # Save JSON for parsing
    report_json = PROJECT_ROOT / "security_audit_issues.json"
    with open(report_json, 'w', encoding='utf-8') as f:
        json.dump(all_issues, f, indent=2)

    print(f"\n[OK] Reports saved:")
    print(f"  - SECURITY_AUDIT_REPORT.md")
    print(f"  - security_audit_issues.json")
    
    print("\n" + "=" * 70)
    if all_issues:
        print(f"SECURITY AUDIT: {len(all_issues)} issues found")
        high = len([i for i in all_issues if i.get("risk") == "HIGH"])
        print(f"  HIGH: {high} (FIX IMMEDIATELY)")
    else:
        print("SECURITY AUDIT: No issues detected")
    print("=" * 70)
