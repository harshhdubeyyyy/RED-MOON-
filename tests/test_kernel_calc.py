#!/usr/bin/env python3
"""Calculator app kernel test (big32 model)."""
import importlib.util
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FORGE = [sys.executable, os.path.join(ROOT, "forge.py")]
MODEL = os.path.expanduser("~/workspace/big32/tools/model.py")
FAILURES = []

EXPECTED = "KERN\n> 12+34\n46\n> 50-8\n42\n> 6*7\n42\n> 20/4\n5\nDONE"


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'} {name} {detail}")
    if not cond:
        FAILURES.append(name)


def main():
    print("calculator app (big32 model)")
    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "kern_calc")
        r = subprocess.run(FORGE + ["build", "--target", "big32",
                                    "--freestanding", "-o", out,
                                    "examples/os/kernel_calc.fg"],
                           capture_output=True, text=True, cwd=ROOT)
        check("builds freestanding big32", r.returncode == 0, r.stderr[-200:])
        spec = importlib.util.spec_from_file_location("big32model", MODEL)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        res = mod.run(out + ".hex", input_bytes=b"12+34\n50-8\n6*7\n20/4\n")
        uart = res["uart"].decode("utf-8", "replace")
        check("exact transcript", uart == EXPECTED, repr(uart))
        check("halts", res["halted"] is True)
    print(f"\n{len(FAILURES)} failure(s): {FAILURES}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
