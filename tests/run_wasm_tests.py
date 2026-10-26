"""WASM backend tests: compile Forge -> .wasm, run with node, check results."""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CASES = [
    ("examples/wasm/sum.fg", "55"),
    ("examples/wasm/fib.fg", "55"),
]


def main():
    failures = []
    for rel, expected in CASES:
        src = os.path.join(ROOT, rel)
        out = os.path.join("/tmp", os.path.basename(rel).replace(".fg", ".wasm"))
        proc = subprocess.run([sys.executable, os.path.join(ROOT, "forge.py"),
                               "emit-wasm", src, "-o", out],
                              capture_output=True, text=True, cwd=ROOT)
        if proc.returncode != 0:
            failures.append(f"{rel}: emit-wasm failed: {proc.stderr}")
            continue
        proc = subprocess.run(["node", os.path.join(ROOT, "tools", "run_wasm.mjs"), out],
                              capture_output=True, text=True)
        got = proc.stdout.strip()
        if proc.returncode != 0 or got != expected:
            failures.append(f"{rel}: expected {expected}, got {got!r} err={proc.stderr[:200]}")
    if failures:
        print("FAIL:")
        for f in failures:
            print(" -", f)
        return 1
    print("PASS: all WASM tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
