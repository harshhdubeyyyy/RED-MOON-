"""WASM backend tests: compile Forge -> .wasm, run with node, check results."""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CASES = [
    ("examples/wasm/sum.fg", "55"),
    ("examples/wasm/fib.fg", "55"),
    ("examples/wasm/float_demo.fg", "12566"),
    ("examples/wasm/break_nested.fg", "6"),
    ("examples/wasm/str_index.fg", "2"),
]

# WIT-first: the program is checked against its declared world at
# build time; main's return value confirms the module still runs.
WIT_CASES = [
    ("examples/wasm/wit_add.fg", "examples/wasm/wit_add.wit", "42"),
    ("examples/wasm/wit_list.fg", "examples/wasm/wit_list.wit", "42"),
]

# WIT mismatches must fail the build with a specific message.
WIT_BAD = [
    ("tests/wit_bad_missing.wit", "world exports 'sub' but the program has no such function"),
    ("tests/wit_bad_param.wit", "parameter 2: WIT type f64 but the function takes s64"),
    ("tests/wit_bad_ret.wit", "returns f64 but the function returns s64"),
    ("tests/wit_bad_undeclared.wit", "function 'greet' is not declared in the world's exports"),
    ("tests/wit_bad_import.wit", "WIT imports are not supported"),
    ("tests/wit_bad_arity.wit", "declares 1 parameter(s) but the function takes 2"),
    ("tests/wit_bad_iface.wit", "only func exports/imports are supported"),
    ("tests/wit_bad_noworld.wit", "no world declaration found"),
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
    for rel, wit, expected in WIT_CASES:
        src = os.path.join(ROOT, rel)
        out = os.path.join("/tmp", os.path.basename(rel).replace(".fg", ".wasm"))
        proc = subprocess.run([sys.executable, os.path.join(ROOT, "forge.py"),
                               "emit-wasm", src, "--wit", os.path.join(ROOT, wit),
                               "-o", out],
                              capture_output=True, text=True, cwd=ROOT)
        if proc.returncode != 0:
            failures.append(f"{rel} ({wit}): emit-wasm --wit failed: {proc.stderr}")
            continue
        proc = subprocess.run(["node", os.path.join(ROOT, "tools", "run_wasm.mjs"), out],
                              capture_output=True, text=True)
        got = proc.stdout.strip()
        if proc.returncode != 0 or got != expected:
            failures.append(f"{rel} ({wit}): expected {expected}, got {got!r} err={proc.stderr[:200]}")
    for wit, needle in WIT_BAD:
        proc = subprocess.run([sys.executable, os.path.join(ROOT, "forge.py"),
                               "emit-wasm", os.path.join(ROOT, "examples/wasm/wit_add.fg"),
                               "--wit", os.path.join(ROOT, wit),
                               "-o", "/tmp/wit_bad.wasm"],
                              capture_output=True, text=True, cwd=ROOT)
        if proc.returncode == 0 or needle not in proc.stderr:
            failures.append(f"{wit}: expected failure with {needle!r}, "
                            f"got rc={proc.returncode} err={proc.stderr[:200]!r}")
    if failures:
        print("FAIL:")
        for f in failures:
            print(" -", f)
        return 1
    print("PASS: all WASM tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
