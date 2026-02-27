#!/usr/bin/env python3
"""
ASCII Guard for DM Puppeteer
=============================
Run this before committing to catch non-ASCII characters in Python source.

Usage:
    python ascii_guard.py              # check all .py files
    python ascii_guard.py file1.py     # check specific files

Exit code 0 = clean, 1 = violations found.

WHY: The project has recurring UTF-8 encoding corruption. Emoji and
special characters (em-dashes, multiplication signs) get double-encoded
through copy/paste, LLM output, or editor re-saves, producing garbled
multi-byte sequences. The fix is simple: use only ASCII in source files.

RULES:
  - No emoji in string literals (use ASCII labels instead)
  - No em-dashes (use --)
  - No special Unicode punctuation (use ASCII equivalents)
  - Comments are ASCII-only too
"""

import sys
import os
import glob


def check_file(filepath):
    """Check a single file for non-ASCII characters. Returns list of violations."""
    violations = []
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for lineno, line in enumerate(f, 1):
                bad_chars = []
                for i, c in enumerate(line):
                    if ord(c) > 127:
                        bad_chars.append((i, c, f"U+{ord(c):04X}"))
                if bad_chars:
                    violations.append({
                        'file': filepath,
                        'line': lineno,
                        'text': line.rstrip(),
                        'chars': bad_chars,
                    })
    except UnicodeDecodeError as e:
        violations.append({
            'file': filepath,
            'line': 0,
            'text': f'FILE ENCODING ERROR: {e}',
            'chars': [],
        })
    return violations


def main():
    if len(sys.argv) > 1:
        files = sys.argv[1:]
    else:
        # Find all .py files in current directory
        files = sorted(glob.glob('*.py'))
        if not files:
            print("No .py files found in current directory.")
            return 0

    total_violations = 0
    for filepath in files:
        if not os.path.isfile(filepath):
            print(f"  SKIP: {filepath} (not found)")
            continue

        violations = check_file(filepath)
        if violations:
            total_violations += len(violations)
            print(f"\n  FAIL: {filepath} ({len(violations)} violations)")
            for v in violations:
                chars_desc = ', '.join(
                    f"col {pos}: '{ch}' ({code})"
                    for pos, ch, code in v['chars']
                )
                print(f"    L{v['line']}: {chars_desc}")
                # Show the line with markers
                text = v['text']
                if len(text) > 100:
                    text = text[:100] + "..."
                print(f"           {text}")
        else:
            print(f"  OK:   {filepath}")

    print()
    if total_violations > 0:
        print(f"FAILED: {total_violations} non-ASCII violations found.")
        print("Fix: replace emoji with ASCII labels, em-dashes with --, etc.")
        return 1
    else:
        print("PASSED: all files are ASCII-clean.")
        return 0


if __name__ == '__main__':
    sys.exit(main())
