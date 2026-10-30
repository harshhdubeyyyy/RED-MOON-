#!/usr/bin/env python3
"""ecall3 demo kernel test (big32 model).

Proves the three-argument ecall builtin: ecall3(16, 1, 41) must print
141, which only happens if the second argument actually arrives in a1
(the handler returns arg1 + 100). Expects the exact transcript
"2\n141\n-2\nDONE\n" and halted.
"""
import importlib.util
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FORGE = [sys.executable, os.path.join(ROOT, "forge.py")]
MODEL = os.path.expanduser("~/workspace/big32/tools/model.py")
FAILURES = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'} {name} {detail}")
    if not cond:
        FAILURES.append(name)


def main():
    print("ecall3 demo (big32 model)")
    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "kern_ecall3")
        r = subprocess.run(FORGE + ["build", "--target", "big32",
                                    "--freestanding", "-o", out,
                                    "examples/os/kernel_ecall3.fg"],
                           capture_output=True, text=True, cwd=ROOT)
        check("builds freestanding big32", r.returncode == 0, r.stderr[-300:])
        if r.returncode != 0:
            print("FAILED")
            return 1
        spec = importlib.util.spec_from_file_location("big32model", MODEL)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        res = mod.run(out + ".hex")
        uart = res["uart"].decode("utf-8", "replace")
        check("halts", res["halted"] is True)
        check("exact transcript", uart == "2\n141\n-2\nDONE\n", repr(uart))
    if FAILURES:
        print("FAILED:", FAILURES)
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
