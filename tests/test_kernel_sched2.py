#!/usr/bin/env python3
"""Priority scheduler policy test (big32 model)."""
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
    print("priority scheduler policy (big32 model)")
    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "kern_sched2")
        r = subprocess.run(FORGE + ["build", "--target", "big32",
                                    "--freestanding", "-o", out,
                                    "examples/os/kernel_sched2.fg"],
                           capture_output=True, text=True, cwd=ROOT)
        check("builds freestanding big32", r.returncode == 0, r.stderr[-200:])
        spec = importlib.util.spec_from_file_location("big32model", MODEL)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        res = mod.run(out + ".hex")
        uart = res["uart"].decode("utf-8", "replace")
        check("exact transcript", uart == "KERN\nP1\nP2\nP0\nDONE", repr(uart))
        check("halts", res["halted"] is True)
        d = res["dmem"]
        check("final states [done, done, done, free]",
              [word(d, 36864 + 8 * i) for i in range(4)] == [2, 2, 2, 0],
              [word(d, 36864 + 8 * i) for i in range(4)])
    print(f"\n{len(FAILURES)} failure(s): {FAILURES}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
