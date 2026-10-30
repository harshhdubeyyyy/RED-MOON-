#!/usr/bin/env python3
"""Lifetime-ordered allocator kernel test, second QAIRT borrow (big32 model).

Segregated short/long free lists: short churn can never fragment
long-lived space, and per-region lists make the region split safe
by construction (a merge can never cross regions). Expects
transcript LIFEKKKKKDONE, halted, short bump advanced three
24-byte blocks, long bump advanced one 24-byte block.
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


def word(dmem, a):
    return (dmem[a] | (dmem[a + 1] << 8) |
            (dmem[a + 2] << 16) | (dmem[a + 3] << 24))


def main():
    print("lifetime-ordered allocator v2 (big32 model)")
    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "kern_lifetime2")
        r = subprocess.run(FORGE + ["build", "--target", "big32",
                                    "--freestanding", "-o", out,
                                    "examples/os/kernel_lifetime2.fg"],
                           capture_output=True, text=True, cwd=ROOT)
        check("builds freestanding big32", r.returncode == 0, r.stderr[-200:])
        spec = importlib.util.spec_from_file_location("big32model", MODEL)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        res = mod.run(out + ".hex")
        uart = res["uart"].decode("utf-8", "replace")
        check("exact transcript LIFEKKKKKDONE", uart == "LIFEKKKKKDONE", repr(uart))
        check("halts", res["halted"] is True)
        d = res["dmem"]
        check("short bump advanced 3 blocks (40960+72)", word(d, 32832) == 41032, word(d, 32832))
        check("long bump advanced 1 block (45056+24)", word(d, 32840) == 45080, word(d, 32840))
    print(f"\n{len(FAILURES)} failure(s): {FAILURES}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
