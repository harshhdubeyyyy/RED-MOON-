#!/usr/bin/env python3
"""Shell v2 test (big32 model): commands with digit arguments."""
import importlib.util
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FORGE = [sys.executable, os.path.join(ROOT, "forge.py")]
MODEL = os.path.expanduser("~/workspace/big32/tools/model.py")
FAILURES = []

EXPECTED = ("KERN\n> a23\n5\n> m34\n12\n> x\n?\n> q\nBYE\n")


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'} {name} {detail}")
    if not cond:
        FAILURES.append(name)


def main():
    print("shell v2 digit args (big32 model)")
    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "kern_shell2")
        r = subprocess.run(FORGE + ["build", "--target", "big32",
                                    "--freestanding", "-o", out,
                                    "examples/os/kernel_shell2.fg"],
                           capture_output=True, text=True, cwd=ROOT)
        check("builds freestanding big32", r.returncode == 0, r.stderr[-200:])
        spec = importlib.util.spec_from_file_location("big32model", MODEL)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        res = mod.run(out + ".hex", input_bytes=b"a23\nm34\nx\nq\n")
        uart = res["uart"].decode("utf-8", "replace")
        check("exact transcript", uart == EXPECTED, repr(uart))
        check("halts", res["halted"] is True)
    print(f"\n{len(FAILURES)} failure(s): {FAILURES}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
